"""Architecture checks using scripted providers and real Runtime/Worker adapters."""
import asyncio
import json
import unittest
from unittest.mock import patch

from agent_contracts.messages import AIMessage, MESSAGE_EVENT_MODELS
from agent_app import (
    AgentRuntime, Finish, ReasoningDelta, StopReason, TextDelta, ToolCall,
    ToolCallEvent, ToolOutput, ToolResultMessage, message_from_dict, message_to_dict, tool,
)
from agent_app.capabilities.web_search import web_search_tool
from agent_app.execution.memory import Checkpoint, InMemoryCheckpointStore
from agent_app.execution.message_stream import MessageStream
from agent_app.execution.references import source_reference
from agent_app.worker.host import report_payload
from tests.unit.test_agent import FakeProvider, HANG


def replay(events):
    """A consumer reconstructs state from events; message_end must only calibrate."""
    message = None
    opened = None
    seen = set()
    for event in events:
        if event.seq in seen:
            continue
        seen.add(event.seq)
        name, data = event.name, event.data
        if name not in MESSAGE_EVENT_MODELS:
            continue
        MESSAGE_EVENT_MODELS[name].model_validate(data)
        if name == 'message_start':
            message = json.loads(json.dumps(data['message']))
        elif name == 'block_start':
            assert opened is None
            opened = data['block']['id']
            message['blocks'].append(dict(data['block']))
        elif name == 'block_delta':
            assert data['block_id'] == opened
            message['blocks'][-1]['content'] += data['delta']
        elif name == 'block_end':
            assert data['block_id'] == opened
            opened = None
        elif name == 'reference_upsert':
            refs = {ref['id']: ref for ref in message['references']}
            refs[data['reference']['id']] = data['reference']
            message['references'] = list(refs.values())
        elif name == 'message_end':
            assert opened is None
            assert message['blocks'] == data['message']['blocks']
            assert message['references'] == data['message']['references']
            message = data['message']
    return AIMessage.model_validate(message)


class MessageAssemblyTests(unittest.TestCase):
    def test_citation_can_split_at_every_character_and_round_trip(self):
        ref = source_reference(type='paper', title='Paper', entity_id='p1')
        content = f'# 回答\n\n结果 [[cite:{ref.id}]]，再次引用 [[cite:{ref.id}]]。\n```py\nx = 1\n```'
        for boundary in range(len(content) + 1):
            events = []
            stream = MessageStream(lambda name, data: events.append((name, data)), model='fake')
            stream.start()
            stream.register([ref, ref])
            stream.append(content[:boundary])
            stream.append(content[boundary:])
            message = stream.finish('done', duration_ms=1)
            self.assertEqual(message.blocks[0].content, content)
            self.assertEqual(len(message.references), 1)
            self.assertEqual(sum(name == 'reference_upsert' for name, _ in events), 1)
            self.assertEqual(''.join(data['delta'] for name, data in events if name == 'block_delta'), content)

    def test_unresolved_and_incomplete_citations_degrade_before_streaming(self):
        events = []
        stream = MessageStream(lambda name, data: events.append((name, data)), model='fake')
        for character in '证据 [[cite:made_up]] / [[cite:]] / [[cite:unfinished':
            stream.append(character)
        message = stream.finish('failed', duration_ms=1)
        self.assertEqual(message.blocks[0].content, '证据 [引用不可用] / [引用不可用] / [引用不完整]')
        self.assertTrue(message.metadata['invalid_citations'])
        self.assertNotIn('[[cite:', ''.join(data['delta'] for name, data in events if name == 'block_delta'))

    def test_reference_detail_upserts_without_replacing_identity(self):
        stream = MessageStream(lambda *_: None, model='fake')
        first = source_reference(type='paper', title='Paper', entity_id='p1')
        detailed = source_reference(type='paper', title='Paper', entity_id='p1', doi='10.1/example',
                                    authors=['Ada'], year=2026, url='https://example.test/paper')
        same_doi = source_reference(type='paper', title='Paper', doi='https://doi.org/10.1/EXAMPLE')
        stream.register([first, detailed, same_doi])
        message = stream.finish('done', duration_ms=1)
        self.assertEqual(len(message.references), 1)
        self.assertEqual(message.references[0].id, first.id)
        self.assertEqual(message.references[0].authors, ['Ada'])


class RuntimeMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_sources_multiple_blocks_replay_and_worker_report(self):
        ref = source_reference(type='paper', title='Paper', entity_id='p1', authors=['Ada'], year=2026)

        @tool(name='search', description='test')
        async def search():
            return ToolOutput(content='{"results": ["Paper"]}', references=(ref, ref))

        provider = FakeProvider([
            [ReasoningDelta('思考'), TextDelta('先检索。'), ToolCallEvent(ToolCall('c1', 'search', {})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta(f'## 结果\n结论 [[cite:{ref.id}]]'), Finish(StopReason.STOP)],
        ])
        events = []
        result = await AgentRuntime(provider=provider, tools=[search], model='fake').run('q', on_event=events.append)
        self.assertEqual(result.message.status, 'done')
        self.assertEqual([block.content for block in result.message.blocks],
                         ['先检索。', f'## 结果\n结论 [[cite:{ref.id}]]'])
        self.assertEqual(len(result.message.references), 1)
        self.assertEqual([event.seq for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(replay(events), result.message)
        self.assertEqual(replay(events + events), result.message)
        tool_content = next(item['content'] for item in provider.requests[1].messages if item['role'] == 'tool')
        self.assertEqual(json.loads(tool_content)['references'][0]['id'], ref.id)
        self.assertTrue(any(event.name == 'delta' and 'reasoning' in event.data for event in events))
        payload = report_payload({'task_id': 't1', 'run_id': 'r1'}, result)
        self.assertEqual(AIMessage.model_validate(payload['result']['message']), result.message)
        self.assertEqual(payload['result']['final_text'], result.final_text)
        durable_tool = next(item for item in result.messages if isinstance(item, ToolResultMessage))
        self.assertEqual(message_from_dict(message_to_dict(durable_tool)), durable_tool)

    async def test_error_and_stop_keep_short_unflushed_content(self):
        for ending, expected in ((ValueError('broken stream'), 'failed'),
                                 (Finish(StopReason.STOP), 'done')):
            with self.subTest(expected=expected):
                events = []
                result = await AgentRuntime(provider=FakeProvider([[TextDelta('部分'), ending]])).run(
                    'q', on_event=events.append)
                self.assertEqual(result.message.status, expected)
                self.assertEqual(result.message.blocks[0].content, '部分')
                self.assertEqual(replay(events), result.message)

        stop = asyncio.Event()
        events = []

        def observe(event):
            events.append(event)
            if event.name == 'block_delta':
                stop.set()

        result = await AgentRuntime(provider=FakeProvider([[TextDelta('保留'), TextDelta('跳过')]])).run(
            'q', stop=stop, on_event=observe)
        self.assertEqual(result.message.status, 'stopped')
        self.assertEqual(replay(events).blocks[0].content, '保留')

    async def test_external_cancellation_emits_terminal_message_then_propagates(self):
        events = []
        ready = asyncio.Event()

        def observe(event):
            events.append(event)
            if event.name == 'block_delta':
                ready.set()

        task = asyncio.create_task(AgentRuntime(provider=FakeProvider([[TextDelta('保留'), HANG]])).run(
            'q', on_event=observe))
        await asyncio.wait_for(ready.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(replay(events).status, 'stopped')
        self.assertEqual(replay(events).blocks[0].content, '保留')

    async def test_timeout_closes_partial_block_before_grace_turn(self):
        events = []
        result = await AgentRuntime(provider=FakeProvider([
            [TextDelta('超时前'), HANG], [TextDelta('收尾'), Finish(StopReason.STOP)],
        ]), deadline_s=0.02).run('q', on_event=events.append)
        self.assertEqual(result.message.status, 'timeout')
        self.assertEqual([block.content for block in result.message.blocks], ['超时前', '收尾'])
        self.assertEqual(replay(events), result.message)

    async def test_question_and_empty_response_keep_existing_behavior(self):
        @tool(name='question', description='test')
        async def question():
            return ToolOutput(terminal={'kind': 'question', 'question': '请选择'})

        events = []
        result = await AgentRuntime(provider=FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'question', {})), Finish(StopReason.TOOL_CALLS)],
        ]), tools=[question]).run('q', on_event=events.append)
        self.assertEqual(result.message.status, 'awaiting_input')
        self.assertEqual(result.question['question'], '请选择')
        self.assertEqual(replay(events).blocks, [])
        empty = await AgentRuntime(provider=FakeProvider([[Finish(StopReason.STOP)]])).run('q')
        self.assertEqual(empty.message.blocks, [])

    async def test_checkpoint_retains_presentation_sources_and_sequence(self):
        ref = source_reference(type='webpage', title='Source', url='https://example.test/')

        @tool(name='lookup', description='test')
        async def lookup():
            return ToolOutput(content='source', references=(ref,))

        class RecordingStore(InMemoryCheckpointStore):
            def __init__(self):
                super().__init__()
                self.saved = []

            async def save(self, checkpoint):
                self.saved.append(checkpoint)
                await super().save(checkpoint)

        store = RecordingStore()
        runtime = AgentRuntime(provider=FakeProvider([
            [TextDelta('检索'), ToolCallEvent(ToolCall('c1', 'lookup', {})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('完成'), Finish(StopReason.STOP)],
        ]), tools=[lookup], checkpoint_store=store)
        await runtime.run('q')
        # The first checkpoint is a legal continuation boundary (ends with a tool result).
        checkpoint = store.saved[0]
        # Round trip also exercises backward-compatible optional checkpoint fields.
        checkpoint = Checkpoint.from_json(checkpoint.to_json())
        events = []
        resumed = await AgentRuntime(provider=FakeProvider([
            [TextDelta(f'续答 [[cite:{ref.id}]]'), Finish(StopReason.STOP)],
        ])).resume(checkpoint, on_event=events.append)
        self.assertEqual(resumed.message.id, checkpoint.presentation['id'])
        self.assertEqual(resumed.message.references[0].id, ref.id)
        self.assertEqual(events[0].seq, checkpoint.event_seq + 1)
        self.assertEqual(replay(events), resumed.message)

    async def test_web_search_registers_only_provider_sources(self):
        search = web_search_tool()
        call = ToolCall('c1', 'web_search', {'query': 'q'})
        with patch('agent_app.capabilities.web_search.web_search', return_value=(
            [{'title': 'Real result', 'url': 'https://example.test/real', 'snippet': 'evidence'}], [],
        )):
            output = await search.execute(call, search.spec.params_model(query='q'))
        self.assertEqual(output.references[0].title, 'Real result')
        self.assertEqual(output.references[0].url, 'https://example.test/real')

    async def test_invalid_tool_source_is_an_error_result_not_a_fabricated_reference(self):
        @tool(name='broken_source', description='test')
        async def broken_source():
            return ToolOutput(content='evidence', references=({'title': 'missing required fields'},))

        runtime = AgentRuntime(provider=FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'broken_source', {})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('证据不足。'), Finish(StopReason.STOP)],
        ]), tools=[broken_source])
        result = await runtime.run('q')
        self.assertEqual(result.message.references, [])
        error = next(item for item in result.messages if isinstance(item, ToolResultMessage))
        self.assertTrue(error.is_error)
        self.assertEqual(result.message.status, 'done')
