"""Whole-payload fidelity across Gateway, product SSE, repositories and history."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from app.api import agent as api
from app.api import agent_v2
from app.core.errors import BusinessError
from app.main import app
from app.services.agent_gateway.client import AgentGateway
from app.services.agent_gateway.v2 import AgentGatewayV2
from app.services.agent_sessions import live as live_runs, service
from app.services.agent_sessions.messages import copy_message
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
from tests.test_agent_sessions import FakeAgentGateway, parse_sse
from tests.test_agent_sse_retries import RetryGateway
from tests.test_agent_sse_tail import decode


def make_message(*, identifier='msg_fixture', status='done'):
    # Explicit nulls and omitted optional fields must remain distinguishable.
    return {
        'id': identifier, 'role': 'assistant', 'status': status,
        'created_at': 1795651200.125, 'schema_version': 1,
        'metadata': {'model': 'fixture/model', 'duration_ms': 9,
                     'nested': {'values': [None, False, 0, '中文 🧪']}},
        'blocks': [
            {'id': 'b2', 'type': 'markdown',
             'content': '# 结论\n\n重复引用 [[cite:r2]] [[cite:r2]]\n\n| a | b |\n|---|---|\n|1|2|\n'},
            {'id': 'b1', 'type': 'markdown',
             'content': '```python\nx = "<tag>"\n```\n\n$x^2$ [[cite:r1]]\r\n尾部空格  \n'},
        ],
        'references': [
            {'id': 'r2', 'type': 'paper', 'title': '测试论文', 'url': None, 'entity_id': 'paper:1',
             'authors': ['乙', '甲'], 'year': 2026, 'venue': 'Fixture', 'doi': '10.0/fixture'},
            {'id': 'r1', 'type': 'webpage', 'title': '测试网页', 'url': 'https://example.test/?q=a%20b#part'},
        ],
    }


def message_events(message):
    start = {**deepcopy(message), 'status': 'running', 'blocks': [], 'references': []}
    events = [{'name': 'message_start', 'data': {'message': start}}]
    for reference in message['references']:
        events.append({'name': 'reference_upsert', 'data': {
            'message_id': message['id'], 'reference': deepcopy(reference),
        }})
    for block in message['blocks']:
        events.append({'name': 'block_start', 'data': {
            'message_id': message['id'], 'block': {**block, 'content': ''},
        }})
        for chunk in (block['content'][:17], block['content'][17:31], block['content'][31:]):
            events.append({'name': 'block_delta', 'data': {
                'message_id': message['id'], 'block_id': block['id'], 'delta': chunk,
            }})
        events.append({'name': 'block_end', 'data': {'message_id': message['id'], 'block_id': block['id']}})
    events.append({'name': 'message_end', 'data': {'message': deepcopy(message)}})
    return events


class MessageGateway(FakeAgentGateway):
    def __init__(self, message, *, include_report_message=True, gate=None):
        super().__init__()
        self.message = message
        self.include_report_message = include_report_message
        statuses = {'done': 'completed', 'failed': 'failed', 'stopped': 'cancelled',
                    'timeout': 'timed_out', 'awaiting_input': 'awaiting_input'}
        self.enqueue(final_text='旧文本字段', status=statuses[message['status']],
                     events=message_events(message), gate=gate)

    async def run(self, run_id, owner):
        response = await super().run(run_id, owner)
        if response.get('report') and self.include_report_message:
            response['report']['result']['message'] = deepcopy(self.message)
        return response


class MessageRetryGateway(RetryGateway):
    def __init__(self, *, legacy_final=False):
        super().__init__(2)
        self.messages = {'r1': make_message(identifier='msg_failed', status='failed'),
                         'r2': None if legacy_final else make_message(identifier='msg_final')}

    async def run(self, run_id, owner):
        response = await super().run(run_id, owner)
        if self.messages[run_id] is not None:
            response['report']['result']['message'] = deepcopy(self.messages[run_id])
        return response

    async def events(self, run_id, owner, after_seq):
        events = message_events(self.messages[run_id]) if self.messages[run_id] else []
        return [{'seq': index + 1, **event} for index, event in enumerate(events) if index + 1 > after_seq]


class StructuredMessageTransportTests(unittest.IsolatedAsyncioTestCase):
    OWNER = 'anon:00000000-0000-4000-8000-000000000044'

    def setUp(self):
        self.enterContext(patch.dict('os.environ', {
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true', 'CHAT_DATABASE_URL': '',
        }))
        self.repo = MemoryAgentSessionRepository()
        self.enterContext(patch.object(service, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(api, 'agent_session_repository', self.repo))
        self.enterContext(patch.object(live_runs, '_live', {}))

    def gateway(self, message, **options):
        gateway = MessageGateway(message, **options)
        self.enterContext(patch.object(service, 'agent_gateway', gateway))
        self.enterContext(patch.object(api, 'agent_gateway', gateway))
        return gateway

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.request(method, path, headers={'x-shenzhi-anonymous-id': self.OWNER[5:]}, **kwargs)

    async def start(self, gateway):
        session = await self.repo.create(self.OWNER, 'message', {})
        live = await service.start_session_run(
            owner=self.OWNER, session_id=session.id, prompt='message', model=None, mode='fast',
            attachments=[], workspace_id=None, skills=[], gateway=gateway,
        )
        return session.id, live

    async def drain(self, response):
        async def collect():
            return [event async for chunk in response.body_iterator if (event := decode(chunk)) is not None]
        return await asyncio.wait_for(collect(), timeout=5)

    async def test_sse_final_result_storage_history_and_every_reconnect_cursor_are_identical(self):
        original = make_message()
        gateway = self.gateway(original)
        session_id, live = await self.start(gateway)
        events = await self.drain(api.session_run_stream(live))
        self.assertEqual([{'name': name, 'data': data} for _, name, data in events[1:-1]], message_events(original))
        self.assertEqual(events[-1][2]['message'], original)
        self.assertEqual(events[-1][2]['final_text'], '旧文本字段')
        detail = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
        self.assertEqual(detail.json()['data']['turns'][0]['message'], original)
        # Rebuild from durable Agent events at every product offset, including result.
        for after in range(len(events) + 1):
            live_runs._live.clear()
            response = await api.attach_agent_session_run(session_id, after=after, owner=self.OWNER)
            self.assertEqual(await self.drain(response), events[after:])
        self.assertEqual(original, make_message())

    async def test_http_run_endpoint_preserves_message(self):
        original = make_message()
        self.gateway(original)
        session = await self.repo.create(self.OWNER, 'HTTP run', {})
        response = await self.request('POST', f'/api/v1/agent/sessions/{session.id}/run', json={'prompt': 'q'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parse_sse(response.text)[-1][1]['message'], original)

    async def test_stateless_stream_and_terminal_statuses_preserve_the_snapshot(self):
        for status in ('done', 'failed', 'stopped', 'timeout', 'awaiting_input'):
            with self.subTest(status=status):
                original = make_message(status=status)
                gateway = self.gateway(original)
                task = await gateway.submit({'prompt': 'q'})
                events = [decode(chunk) async for chunk in api._agent_task_stream(self.OWNER, task, [], gateway=gateway)]
                self.assertEqual(events[-1][2]['message'], original)
                # A different task tests the same path into completed Turn storage.
                gateway = self.gateway(original)
                session_id, live = await self.start(gateway)
                await live.task
                turn = (await self.repo.get(session_id, self.OWNER)).turns[-1]
                self.assertEqual(turn.public()['message'], original)

    async def test_active_projection_recovery_preserves_message(self):
        original = make_message()
        gate = asyncio.Event()
        gateway = self.gateway(original, gate=gate)
        session_id, live = await self.start(gateway)
        await asyncio.sleep(0)
        live.task.cancel()
        await asyncio.gather(live.task, return_exceptions=True)
        live_runs._live.clear()
        gate.set()
        recovered = await service.resume_session_run(session_id, self.OWNER)
        events = await self.drain(api.session_run_stream(recovered))
        self.assertEqual(events[-1][2]['message'], original)
        self.assertEqual((await self.repo.get(session_id, self.OWNER)).turns[-1].message, original)

    async def test_report_without_snapshot_uses_message_end_without_rebuilding(self):
        original = make_message()
        _, live = await self.start(self.gateway(original, include_report_message=False))
        events = await self.drain(api.session_run_stream(live))
        self.assertEqual(events[-1][2]['message'], original)

    async def test_conflicting_or_invalid_message_is_not_silently_persisted(self):
        for invalid in ('conflict', 'reference', 'status', 'missing_snapshot'):
            with self.subTest(invalid=invalid):
                original = make_message()
                gateway = self.gateway(original)
                if invalid == 'conflict':
                    gateway.plans[0]['events'][-1]['data']['message']['metadata']['duration_ms'] = 999
                elif invalid == 'reference':
                    gateway.message = {**original, 'references': []}
                elif invalid == 'status':
                    gateway.message = {**original, 'status': 'failed'}
                else:
                    gateway.include_report_message = False
                    gateway.plans[0]['events'].pop()
                session_id, live = await self.start(gateway)
                events = await self.drain(api.session_run_stream(live))
                self.assertFalse(any(name == 'result' for _, name, _ in events))
                turn = (await self.repo.get(session_id, self.OWNER)).turns[-1]
                self.assertEqual(turn.status, 'running')
                self.assertIsNone(turn.message)
                self.assertIsNone(live_runs.get_live(session_id, self.OWNER))

    async def test_retry_keeps_attempt_messages_and_does_not_reuse_old_snapshot(self):
        for legacy_final in (False, True):
            gateway = MessageRetryGateway(legacy_final=legacy_final)
            self.enterContext(patch.object(service, 'agent_gateway', gateway))
            session_id, live = await self.start(gateway)
            events = await self.drain(api.session_run_stream(live))
            self.assertEqual(events[-1][2]['message'], gateway.messages['r2'])
            self.assertEqual((await self.repo.get(session_id, self.OWNER)).turns[-1].message, gateway.messages['r2'])
            live_runs._live.clear()
            recovered = await service.resume_session_run(session_id, self.OWNER)
            self.assertEqual(await self.drain(api.session_run_stream(recovered)), events)

    async def test_memory_and_sse_snapshots_are_isolated_from_consumer_mutation(self):
        message = make_message()
        session = await self.repo.create(self.OWNER, 'snapshot', {})
        turn, _ = await self.repo.start_turn(session.id, self.OWNER, 'q', {}, [])
        stored = await self.repo.finish_turn(session.id, self.OWNER, turn.id, {'status': 'done', 'message': message})
        message['references'][0]['authors'].reverse()
        self.assertEqual(stored.public()['message'], make_message())
        returned = stored.public()['message']
        returned['metadata']['nested']['values'].append('mutated')
        self.assertEqual(stored.public()['message'], make_message())
        live = live_runs.LiveRun(session.id, self.OWNER, turn.id)
        payload = {'message': make_message()}
        live_runs.append(live, 'message_end', payload)
        live_runs.finish(live)
        payload['message']['blocks'].clear()
        first = [item async for item in live_runs.subscribe(live)]
        first[0][2]['message']['blocks'].clear()
        second = [item async for item in live_runs.subscribe(live)]
        self.assertEqual(second[0][2]['message'], make_message())

    async def test_legacy_history_and_import_remain_readable_without_inventing_sources(self):
        session = await self.repo.import_legacy(self.OWNER, {'import_key': 'legacy', 'turns': [
            {'role': 'user', 'content': 'q'},
            {'role': 'assistant', 'content': '旧文本 [[cite:literal]]  \n', 'sources': [{'title': 'old'}]},
        ]})
        response = await self.request('GET', f'/api/v1/agent/sessions/{session.id}')
        turn = response.json()['data']['turns'][0]
        self.assertIsNone(turn['message'])
        self.assertEqual(turn['assistant_content'], '旧文本 [[cite:literal]]  \n')
        self.assertEqual(turn['sources'], [{'title': 'old'}])
        live = await service._reuse_turn(session.turns[0], self.OWNER)
        self.assertIsNone((await self.drain(api.session_run_stream(live)))[-1][2]['message'])

    async def test_message_owner_isolation_still_applies(self):
        session_id, live = await self.start(self.gateway(make_message()))
        await live.task
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get(f'/api/v1/agent/sessions/{session_id}', headers={
                'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000099',
            })
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('msg_fixture', response.text)

    async def test_v2_stream_envelope_preserves_nested_message(self):
        message = make_message()
        session_id, live = await self.start(self.gateway(message))
        await live.task
        self.repo.sessions[session_id].turns[-1].settings['_agent_protocol'] = 2
        with patch.object(agent_v2, 'resume_session_run', return_value=live), \
                patch('app.services.agent_sessions.repository.agent_session_repository', self.repo):
            response = await agent_v2.resume(session_id, owner=self.OWNER, after=0)
            events = await self.drain(response)
        self.assertEqual(events[-1][2]['schema_version'], 1)
        self.assertEqual(events[-1][2]['message'], message)


class MessageGatewayValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_v1_and_v2_gateway_round_trip_and_invalid_payload_rejection(self):
        message = make_message()
        for cls in (AgentGateway, AgentGatewayV2):
            for invalid in (False, True):
                with self.subTest(gateway=cls.__name__, invalid=invalid):
                    payload = deepcopy(message)
                    if invalid:
                        payload['references'] = []
                    report = {'run_id': 'r1', 'task_id': 't1', 'status': 'completed',
                              'result': {'message': payload}, 'usage': {}}
                    event = {'task_id': 't1', 'run_id': 'r1', 'seq': 1, 'turn': 1,
                             'name': 'message_end', 'data': {'message': payload},
                             'occurred_at': '2026-11-26T00:00:00+00:00'}

                    def handler(request):
                        if request.url.path.endswith('/events'):
                            return httpx.Response(200, json={'events': [event]})
                        return httpx.Response(200, json={
                            'run_id': 'r1', 'task_id': 't1', 'attempt': 1, 'status': 'completed',
                            'created_at': '2026-11-26T00:00:00+00:00', 'task_status': 'completed',
                            'report': report,
                        })

                    gateway = cls(base_url='http://agent.test', token='test-only', transport=httpx.MockTransport(handler))
                    if invalid:
                        with self.assertRaises(ValidationError):
                            await gateway.run('r1', 'owner')
                        with self.assertRaises(ValidationError):
                            await gateway.events('r1', 'owner', 0)
                    else:
                        self.assertEqual((await gateway.run('r1', 'owner'))['report']['result']['message'], message)
                        self.assertEqual((await gateway.events('r1', 'owner', 0))[0]['data'], event['data'])

    def test_validation_does_not_insert_omitted_defaults(self):
        message = make_message()
        message.pop('role')
        message.pop('schema_version')
        self.assertEqual(copy_message(message), message)
        with self.assertRaises(BusinessError):
            copy_message(message, status='failed')
