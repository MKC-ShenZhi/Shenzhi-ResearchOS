"""Persistent Agent session API and repository behavior."""
import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx

from app.core.errors import BusinessError
from app.main import app
from app.services.agent import AgentRuntime
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.types import StopReason, ToolCall
from app.services.agent_sessions import live as live_runs
from app.services.agent_sessions.service import TimelineCapture
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
from app.services.agent_uploads import agent_upload_store
from tests.test_agent import FakeProvider, make_echo


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split('\n\n'):
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith('event: '):
                name = line[7:]
            elif line.startswith('data: '):
                data = json.loads(line[6:])
        if name:
            events.append((name, data))
    return events


class AgentSessionApiTests(unittest.IsolatedAsyncioTestCase):
    OWNER_A = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000011'}
    OWNER_B = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000012'}

    def setUp(self):
        self.env = patch.dict(os.environ, {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        })
        self.env.start()
        self.registry = patch.object(live_runs, '_live', {})
        self.registry.start()
        self.repo = MemoryAgentSessionRepository()
        self.api_repo = patch('app.api.agent.agent_session_repository', self.repo)
        self.service_repo = patch(
            'app.services.agent_sessions.service.agent_session_repository', self.repo,
        )
        self.api_repo.start()
        self.service_repo.start()

    def tearDown(self):
        self.registry.stop()
        self.service_repo.stop()
        self.api_repo.stop()
        self.env.stop()

    async def request(self, method: str, path: str, *, owner=None, json_body=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url='http://test',
        ) as client:
            return await client.request(
                method, path, headers=owner or self.OWNER_A, json=json_body,
            )

    async def create(self, prompt='第一条问题', owner=None):
        response = await self.request('POST', '/api/v1/agent/sessions', owner=owner,
                                      json_body={'prompt': prompt, 'mode': 'fast'})
        self.assertEqual(response.status_code, 200)
        return response.json()['data']['id']

    async def test_create_get_rename_delete_and_owner_isolation(self):
        session_id = await self.create('这是自动标题')
        detail = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
        self.assertEqual(detail.json()['data']['title'], '这是自动标题')
        self.assertEqual(detail.json()['data']['turns'], [])

        forbidden = await self.request(
            'GET', f'/api/v1/agent/sessions/{session_id}', owner=self.OWNER_B,
        )
        self.assertEqual(forbidden.status_code, 404)
        forbidden_rename = await self.request(
            'PATCH', f'/api/v1/agent/sessions/{session_id}', owner=self.OWNER_B,
            json_body={'title': '不应成功'},
        )
        self.assertEqual(forbidden_rename.status_code, 404)
        forbidden_delete = await self.request(
            'DELETE', f'/api/v1/agent/sessions/{session_id}', owner=self.OWNER_B,
        )
        self.assertEqual(forbidden_delete.status_code, 404)
        forbidden_run = await self.request(
            'POST', f'/api/v1/agent/sessions/{session_id}/run', owner=self.OWNER_B,
            json_body={'prompt': '越权运行', 'mode': 'fast'},
        )
        self.assertEqual(forbidden_run.status_code, 404)

        renamed = await self.request(
            'PATCH', f'/api/v1/agent/sessions/{session_id}', json_body={'title': '重命名'},
        )
        self.assertEqual(renamed.json()['data']['title'], '重命名')
        deleted = await self.request('DELETE', f'/api/v1/agent/sessions/{session_id}')
        self.assertEqual(deleted.status_code, 200)
        missing = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
        self.assertEqual(missing.status_code, 404)

    async def test_cursor_pagination_returns_ten_then_next_page(self):
        for index in range(21):
            await self.create(f'问题 {index}')
        first = await self.request('GET', '/api/v1/agent/sessions?limit=10')
        data = first.json()['data']
        self.assertEqual(len(data['sessions']), 10)
        self.assertTrue(data['has_more'])
        self.assertTrue(data['next_cursor'])
        second = await self.request(
            'GET', f"/api/v1/agent/sessions?limit=10&cursor={data['next_cursor']}",
        )
        second_data = second.json()['data']
        self.assertEqual(len(second_data['sessions']), 10)
        self.assertTrue(second_data['has_more'])
        self.assertFalse({item['id'] for item in data['sessions']}
                         & {item['id'] for item in second_data['sessions']})
        third = await self.request(
            'GET', f"/api/v1/agent/sessions?limit=10&cursor={second_data['next_cursor']}",
        )
        third_data = third.json()['data']
        self.assertEqual(len(third_data['sessions']), 1)
        self.assertFalse(third_data['has_more'])
        self.assertIsNone(third_data['next_cursor'])

    async def test_legacy_import_is_idempotent_and_owner_scoped(self):
        payload = {
            'import_key': 'local-v1:old-session',
            'title': '本地历史',
            'created_at': 1_700_000_000,
            'updated_at': 1_700_000_100,
            'turns': [
                {'role': 'user', 'content': '旧问题'},
                {'role': 'assistant', 'content': '旧答案',
                 'process': [{'kind': 'text', 'text': '旧答案'}]},
            ],
        }
        first = await self.request('POST', '/api/v1/agent/sessions/import', json_body=payload)
        retry = await self.request('POST', '/api/v1/agent/sessions/import', json_body=payload)
        other_owner = await self.request(
            'POST', '/api/v1/agent/sessions/import', owner=self.OWNER_B, json_body=payload,
        )
        self.assertEqual(first.json()['data']['id'], retry.json()['data']['id'])
        self.assertNotEqual(first.json()['data']['id'], other_owner.json()['data']['id'])
        detail = await self.request(
            'GET', f"/api/v1/agent/sessions/{first.json()['data']['id']}",
        )
        self.assertEqual(detail.json()['data']['turns'][0]['assistant_content'], '旧答案')

    async def test_run_persists_turn_and_restores_backend_history(self):
        session_id = await self.create('打个招呼')
        runtime = AgentRuntime(provider=FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})),
              Finish(StopReason.TOOL_CALLS)],
             [TextDelta('完成回答'), Finish(StopReason.STOP)]],
        ), tools=[make_echo()])
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.request(
                'POST', f'/api/v1/agent/sessions/{session_id}/run',
                json_body={'prompt': '打个招呼', 'mode': 'fast', 'skills': [], 'attachments': []},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parse_sse(response.text)[-1][0], 'result')

        detail = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
        turns = detail.json()['data']['turns']
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]['assistant_content'], '完成回答')
        self.assertEqual(turns[0]['status'], 'done')
        self.assertTrue(any(item['kind'] == 'text' for item in turns[0]['process']))
        tool_item = next(item['tool'] for item in turns[0]['process'] if item['kind'] == 'tool')
        self.assertEqual(tool_item['name'], 'echo')
        self.assertTrue(tool_item['done'])
        self.assertFalse(tool_item['isError'])
        self.assertEqual([item['kind'] for item in self.repo.sessions[session_id].runtime_history],
                         ['user', 'assistant', 'tool', 'assistant'])

    async def test_file_attachment_is_bound_to_one_turn_without_persisting_file_id(self):
        owner = 'anon:00000000-0000-4000-8000-000000000011'
        uploaded = await agent_upload_store.save(owner, 'notes.md', {
            'text': '附件解析正文', 'original_length': 6, 'final_length': 6,
            'truncated': False, 'warning': None,
        })
        created = await self.request('POST', '/api/v1/agent/sessions', json_body={
            'prompt': '请分析附件', 'attachments': [{'kind': 'file', 'file_id': uploaded['file_id'], 'title': 'notes.md'}],
        })
        session_id = created.json()['data']['id']
        self.assertNotIn('attachments', created.json()['data']['settings'])
        runtime = AgentRuntime(provider=FakeProvider([[TextDelta('已分析'), Finish(StopReason.STOP)]]))
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run', json_body={
                'prompt': '请分析附件', 'attachments': [{'kind': 'file', 'file_id': uploaded['file_id'], 'title': 'notes.md'}],
            })
        self.assertEqual(response.status_code, 200)
        detail = (await self.request('GET', f'/api/v1/agent/sessions/{session_id}')).json()['data']
        self.assertEqual(detail['turns'][0]['settings']['attachments'], [{'kind': 'file', 'title': 'notes.md'}])
        self.assertNotIn(uploaded['file_id'], json.dumps(detail, ensure_ascii=False))
        self.assertIn('附件解析正文', self.repo.sessions[session_id].runtime_history[0]['text'])
        with self.assertRaises(BusinessError):
            await agent_upload_store.get(owner, uploaded['file_id'])

    async def test_failed_and_stopped_turns_remain_persisted(self):
        failed_id = await self.create('失败测试')
        runtime = AgentRuntime(provider=FakeProvider(
            [[TextDelta('部分内容'), Finish(StopReason.ERROR, error_message='provider failed')]],
        ))
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.request(
                'POST', f'/api/v1/agent/sessions/{failed_id}/run',
                json_body={'prompt': '失败测试', 'mode': 'fast'},
            )
        self.assertEqual(parse_sse(response.text)[-1][1]['status'], 'failed')
        self.assertEqual((await self.repo.get(failed_id, 'anon:00000000-0000-4000-8000-000000000011')).turns[0].status,
                         'failed')

        stopped_id = await self.create('停止测试')
        turn = await self.repo.start_turn(
            stopped_id, 'anon:00000000-0000-4000-8000-000000000011', '停止测试', {}, [],
        )
        await self.repo.finish_turn(
            stopped_id, 'anon:00000000-0000-4000-8000-000000000011', turn.id,
            {'status': 'stopped', 'stopped': True, 'stop_reason': 'cancelled',
             'assistant_content': '部分回答', 'process': [{'kind': 'text', 'text': '部分回答'}]},
        )
        restored = await self.repo.get(
            stopped_id, 'anon:00000000-0000-4000-8000-000000000011',
        )
        self.assertTrue(restored.turns[0].stopped)
        self.assertEqual(restored.turns[0].assistant_content, '部分回答')

    async def test_same_session_rejects_a_second_active_run(self):
        session_id = await self.create('并发测试')
        owner = 'anon:00000000-0000-4000-8000-000000000011'
        await self.repo.start_turn(session_id, owner, '第一轮', {}, [])
        with self.assertRaises(BusinessError) as raised:
            await self.repo.start_turn(session_id, owner, '并发轮', {}, [])
        self.assertEqual(raised.exception.status, 409)

    async def test_disconnect_does_not_cancel_background_tool_run(self):
        session_id = await self.create('断开后继续')
        release = asyncio.Event()

        class GatedProvider(FakeProvider):
            async def stream(self, request):
                await release.wait()
                async for event in super().stream(request):
                    yield event

        runtime = AgentRuntime(provider=GatedProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('后台完成'), Finish(StopReason.STOP)],
        ]), tools=[make_echo()])
        disconnected = asyncio.Event()
        first_event = asyncio.Event()
        body = json.dumps({'prompt': '断开后继续', 'mode': 'fast'}).encode()
        body_received = False

        async def receive():
            nonlocal body_received
            if not body_received:
                body_received = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            if b'event: run_start' in message.get('body', b''):
                first_event.set()

        scope = {
            'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
            'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
            'path': f'/api/v1/agent/sessions/{session_id}/run', 'query_string': b'',
            'headers': [(b'host', b'test'), (b'content-type', b'application/json'),
                        *[(key.encode(), value.encode()) for key, value in self.OWNER_A.items()]],
            'client': ('127.0.0.1', 12345), 'server': ('test', 80), 'root_path': '',
        }
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            request = asyncio.create_task(app(scope, receive, send))
            try:
                await asyncio.wait_for(first_event.wait(), 3)
                live = live_runs.get_live(session_id, f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}")
                self.assertIsNotNone(live)
                self.assertIn(live.task, live_runs._tasks)
                disconnected.set()
                await asyncio.wait_for(request, 3)
                self.assertFalse(live.task.done())
                self.assertFalse(live.done)
                # A second detail read must not reconcile a still-running live task.
                detail = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
                self.assertEqual(detail.json()['data']['turns'][-1]['status'], 'running')
                conflict = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                              json_body={'prompt': '重复运行'})
                self.assertEqual(conflict.status_code, 409)
                release.set()
                await asyncio.wait_for(asyncio.shield(live.task), 3)
            finally:
                disconnected.set()
                release.set()
                await asyncio.wait_for(request, 3)
        turn = self.repo.sessions[session_id].turns[-1]
        self.assertEqual(turn.status, 'done')
        self.assertNotEqual(turn.stop_reason, 'connection_closed')
        self.assertEqual(turn.assistant_content, '后台完成')
        self.assertTrue(any(item['kind'] == 'tool' for item in turn.process))
        self.assertTrue(live.done)
        self.assertNotIn(live.task, live_runs._tasks)

    async def test_completed_run_replay_ids_after_and_owner_isolation(self):
        session_id = await self.create('回放')
        runtime = AgentRuntime(provider=FakeProvider([[TextDelta('完整回答'), Finish(StopReason.STOP)]]))
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                          json_body={'prompt': '回放'})
        endpoint = f'/api/v1/agent/sessions/{session_id}/run/stream'
        replay = await self.request('GET', endpoint)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.text, response.text)
        names = [name for name, _ in parse_sse(replay.text)]
        self.assertEqual(names[0], 'run_start')
        self.assertEqual(names[-1], 'result')
        ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith('id: ')]
        self.assertEqual(ids, list(range(len(names))))
        after = await self.request('GET', endpoint + '?after=2')
        self.assertEqual(parse_sse(after.text), parse_sse(replay.text)[2:])
        self.assertEqual([int(line[4:]) for line in after.text.splitlines() if line.startswith('id: ')], ids[2:])
        exhausted = await self.request('GET', endpoint + f'?after={len(ids) + 3}')
        self.assertEqual(exhausted.text, '')
        invalid = await self.request('GET', endpoint + '?after=-1')
        self.assertEqual(invalid.status_code, 422)
        forbidden = await self.request('GET', endpoint, owner=self.OWNER_B)
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(replay.headers['cache-control'], 'no-cache, no-transform')
        self.assertEqual(replay.headers['x-accel-buffering'], 'no')

    async def test_stream_without_live_run_returns_404(self):
        session_id = await self.create('无运行')
        for sid in (session_id, 'ses_missing'):
            response = await self.request('GET', f'/api/v1/agent/sessions/{sid}/run/stream')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()['message'], '当前没有运行中的任务')

    async def test_orphan_reconciliation_closes_history_and_preserves_previous_turn(self):
        owner = f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}"
        session_id = await self.create('历史')
        previous = await self.repo.start_turn(session_id, owner, '上一问', {}, [])
        history = [{'kind': 'user', 'text': '上一问'},
                   {'kind': 'assistant', 'content': '上一答', 'reasoning': '', 'tool_calls': [],
                    'stop_reason': 'stop', 'usage_tokens': 0}]
        await self.repo.finish_turn(session_id, owner, previous.id,
                                    {'status': 'done', 'transcript': history})
        orphan = await self.repo.start_turn(session_id, owner, '中断前的用户原文', {}, [])
        orphan.assistant_content = '部分结果'
        orphan.transcript = [{'kind': 'assistant', 'tool_calls': [{'id': 'unclosed'}]}]
        detail = (await self.request('GET', f'/api/v1/agent/sessions/{session_id}')).json()['data']
        turn = detail['turns'][-1]
        self.assertEqual(turn['status'], 'stopped')
        self.assertEqual(turn['stop_reason'], 'interrupted')
        self.assertTrue(turn['stopped'])
        self.assertEqual(turn['error'], '运行已中断（服务重启或异常退出），请重新发送')
        transcript = self.repo.sessions[session_id].runtime_history
        self.assertEqual(transcript[:2], history)
        self.assertEqual(transcript[-2], {'kind': 'user', 'text': orphan.user_content})
        self.assertEqual(transcript[-1]['tool_calls'], [])
        self.assertEqual(transcript[-1]['content'], '部分结果')
        again = (await self.request('GET', f'/api/v1/agent/sessions/{session_id}')).json()['data']
        self.assertEqual(again, detail)

    async def test_unexpected_bridge_failure_persists_failed_and_sends_result(self):
        session_id = await self.create('异常兜底')

        async def broken_events(*args, **kwargs):
            yield 'run_start', {'run_id': 'broken'}
            yield 'delta', {'text': '部分答案'}
            raise RuntimeError('测试桥接失败')

        with patch('app.services.agent_sessions.service.agent_runtime.run_events', broken_events):
            response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                          json_body={'prompt': '异常兜底'})
        result = parse_sse(response.text)[-1][1]
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['stop_reason'], 'error')
        self.assertIn('测试桥接失败', result['error']['message'])
        turn = self.repo.sessions[session_id].turns[-1]
        self.assertEqual(turn.status, 'failed')
        self.assertEqual(turn.stop_reason, 'error')
        self.assertEqual(turn.assistant_content, '部分答案')
        self.assertEqual(turn.transcript[-2]['text'], '异常兜底')
        self.assertEqual(turn.transcript[-1]['tool_calls'], [])

    async def test_replayed_run_can_still_be_steered_and_stopped(self):
        from app.services.agent_sessions.service import start_session_run

        session_id = await self.create('显式停止')
        owner = f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}"
        release = asyncio.Event()

        class GatedProvider(FakeProvider):
            async def stream(self, request):
                self.started.set()
                await release.wait()
                async for event in super().stream(request):
                    yield event

        provider = GatedProvider([[TextDelta('停止前的片段'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider)
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            live = await start_session_run(owner=owner, session_id=session_id, prompt='显式停止',
                                           model=None, mode='fast', attachments=[], workspace_id=None, skills=[])
            await asyncio.wait_for(provider.started.wait(), 3)
            subscriber = live_runs.subscribe(live)
            _, name, event = await anext(subscriber)
            self.assertEqual(name, 'run_start')
            run_id = event['run_id']
            await subscriber.aclose()
            steer = await self.request('POST', f'/api/v1/agent/run/{run_id}/steer', json_body={'text': '插话'})
            self.assertEqual(steer.status_code, 200)
            stop = await self.request('POST', f'/api/v1/agent/run/{run_id}/stop')
            self.assertEqual(stop.status_code, 200)
            release.set()
            await asyncio.wait_for(asyncio.shield(live.task), 3)
        self.assertEqual(self.repo.sessions[session_id].turns[-1].status, 'stopped')
        self.assertEqual(live.events[-1][1]['stop_reason'], 'cancelled')


class TimelineCaptureTests(unittest.TestCase):
    def test_system_and_compaction_are_not_persisted_but_user_notes_are(self):
        capture = TimelineCapture([])
        capture.event('message', {'kind': 'system', 'text': '预算提示'})
        capture.event('compaction', {'before_chars': 100, 'after_chars': 10})
        self.assertEqual(capture.steers, [])
        capture.event('message', {'kind': 'steer', 'text': '用户插话'})
        capture.event('message', {'kind': 'follow_up', 'text': '用户追问'})
        self.assertEqual(capture.steers, [
            {'kind': 'steer', 'text': '用户插话'}, {'kind': 'follow_up', 'text': '用户追问'},
        ])


class LiveRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscribers_wake_independently_and_disconnect_does_not_cancel_task(self):
        live = live_runs.LiveRun('ses_live', 'owner', 'turn_live')
        task = asyncio.create_task(asyncio.Event().wait())
        live.task = task
        first = live_runs.subscribe(live)
        second = live_runs.subscribe(live)
        waiting_first = asyncio.create_task(anext(first))
        waiting_second = asyncio.create_task(anext(second))
        try:
            await asyncio.sleep(0)
            live_runs.append(live, 'delta', {'text': 'a'})
            expected = (0, 'delta', {'text': 'a'})
            self.assertEqual(await asyncio.wait_for(waiting_first, 1), expected)
            self.assertEqual(await asyncio.wait_for(waiting_second, 1), expected)
            await first.aclose()
            self.assertFalse(task.done())
            live_runs.append(live, 'result', {'status': 'done'})
            live_runs.finish(live)
            self.assertEqual([event async for event in second], [(1, 'result', {'status': 'done'})])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await first.aclose()
            await second.aclose()

    async def test_heartbeat_and_retention_do_not_expire_a_replacement_run(self):
        live = live_runs.LiveRun('ses_retained', 'owner', 'turn_old')
        with patch.object(live_runs, '_live', {}):
            live_runs.register(live)
            self.assertIsNone(live_runs.get_live(live.session_id, 'other-owner'))
            loop = asyncio.get_running_loop()
            with patch.object(loop, 'call_later') as schedule:
                live_runs.finish(live)
            delay, expire = schedule.call_args.args
            self.assertEqual(delay, 600)
            replacement = live_runs.LiveRun(live.session_id, 'owner', 'turn_new')
            live_runs.register(replacement)
            expire()
            self.assertIs(live_runs.get_live(live.session_id, 'owner'), replacement)
            with patch.object(loop, 'call_later') as schedule:
                live_runs.finish(replacement)
            schedule.call_args.args[1]()
            self.assertIsNone(live_runs.get_live(live.session_id, 'owner'))
        waiting = live_runs.LiveRun('ses_heartbeat', 'owner', 'turn_wait')
        stream = live_runs.subscribe(waiting)

        async def timeout(awaitable, timeout):
            awaitable.close()
            self.assertEqual(timeout, 15)
            raise TimeoutError

        with patch.object(live_runs.asyncio, 'wait_for', timeout):
            self.assertIsNone(await anext(stream))
        live_runs.finish(waiting)
        self.assertEqual([event async for event in stream], [])


if __name__ == '__main__':
    unittest.main()
