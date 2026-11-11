"""Backend product Session projection tests using the Agent Gateway boundary."""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from collections import deque
from unittest.mock import patch

import httpx

from app.core.errors import BusinessError
from app.main import app
from app.services.agent_sessions import live as live_runs
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
from app.services.agent_sessions.service import TimelineCapture, get_session_detail
from app.services.agent_uploads import agent_upload_store


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split('\n\n'):
        name = data = None
        for line in block.splitlines():
            if line.startswith('event: '):
                name = line[7:]
            elif line.startswith('data: '):
                data = json.loads(line[6:])
        if name:
            events.append((name, data))
    return events


class FakeAgentGateway:
    """A deterministic remote Agent boundary; no Runtime is imported by Backend tests."""

    def __init__(self):
        self.plans = deque()
        self.runs = {}
        self.submissions = []
        self.steers = []
        self.cancelled = []
        self.submit_error = None
        self._next_id = 0

    def enqueue(self, *, final_text='已完成', status='completed', events=None,
                output=None, error_message=None, gate=None, event_error=None):
        self.plans.append({
            'final_text': final_text, 'status': status,
            'events': list(events or []), 'output': output,
            'error_message': error_message, 'gate': gate,
            'event_error': event_error,
        })

    async def submit(self, payload):
        if self.submit_error is not None:
            error, self.submit_error = self.submit_error, None
            raise error
        self._next_id += 1
        task_id, run_id = f'task-{self._next_id}', f'run-{self._next_id}'
        plan = self.plans.popleft() if self.plans else {
            'final_text': '已完成', 'status': 'completed', 'events': [], 'output': None,
            'error_message': None, 'gate': None, 'event_error': None,
        }
        plan['payload'] = payload
        plan['task_id'] = task_id
        plan['run_id'] = run_id
        plan['event_error_raised'] = False
        plan['hide_report_once'] = False
        plan['events'] = [
            {'task_id': task_id, 'run_id': run_id, 'seq': index + 1,
             'turn': int(event.get('data', {}).get('turn', 0)),
             'name': event['name'], 'data': event.get('data', {}),
             'occurred_at': '2026-11-11T00:00:00+00:00'}
            for index, event in enumerate(plan['events'])
        ]
        self.runs[run_id] = plan
        self.submissions.append(payload)
        return {'task_id': task_id, 'current_run_id': run_id}

    async def events(self, run_id, owner, after_seq):
        plan = self.runs[run_id]
        if plan['event_error'] and plan['event_error_raised']:
            raise plan['event_error']
        if plan['event_error']:
            plan['event_error_raised'] = True
        return [item for item in plan['events'] if item['seq'] > after_seq]

    async def run(self, run_id, owner):
        plan = self.runs[run_id]
        if plan['gate'] is not None and not plan['gate'].is_set():
            return {'report': None}
        if plan['event_error'] and not plan['hide_report_once']:
            plan['hide_report_once'] = True
            return {'report': None}
        result = {
            'stop_reason': ('cancelled' if plan['status'] == 'cancelled'
                            else 'error' if plan['status'] == 'failed' else 'stop'),
            'final_text': plan['final_text'],
            'final_reasoning': '', 'output': plan['output'], 'question': None,
            'turns': 1, 'duration_ms': 1, 'prompt_tokens': 1,
            'completion_tokens': 1, 'truncated': False,
            'messages': [
                {'kind': 'user', 'text': plan['payload']['prompt']},
                {'kind': 'assistant', 'content': plan['final_text'], 'reasoning': '',
                 'tool_calls': [], 'stop_reason': 'stop', 'usage_tokens': 2},
            ],
        }
        return {'report': {
            'run_id': run_id, 'task_id': plan['task_id'], 'status': plan['status'],
            'result': result, 'error_code': '20004' if plan['error_message'] else None,
            'error_message': plan['error_message'],
        }}

    async def task(self, task_id, owner):
        plan = next(item for item in self.runs.values() if item['task_id'] == task_id)
        return {'current_run_id': plan['run_id'], 'cancel_requested': plan['status'] == 'cancelled'}

    async def steer(self, run_id, owner, message):
        if run_id not in self.runs:
            raise BusinessError(20004, '运行不存在', 404)
        self.steers.append((run_id, owner, message))
        return {'stored': True}

    async def cancel(self, task_id, owner):
        plan = next(item for item in self.runs.values() if item['task_id'] == task_id)
        self.cancelled.append((task_id, owner))
        plan['status'] = 'cancelled'
        if plan['gate'] is not None:
            plan['gate'].set()
        return {'task_id': task_id, 'cancel_requested': True}

    async def config(self):
        return {'models': [], 'default_model': None, 'skills': []}


class AgentSessionProjectionTests(unittest.IsolatedAsyncioTestCase):
    OWNER_A = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000011'}
    OWNER_B = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000012'}

    def setUp(self):
        self.env = patch.dict(os.environ, {
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
            'CHAT_DATABASE_URL': '',
        })
        self.env.start()
        self.repo = MemoryAgentSessionRepository()
        self.gateway = FakeAgentGateway()
        self.live_registry = patch.object(live_runs, '_live', {})
        self.live_registry.start()
        self.api_repo = patch('app.api.agent.agent_session_repository', self.repo)
        self.service_repo = patch('app.services.agent_sessions.service.agent_session_repository', self.repo)
        self.api_gateway = patch('app.api.agent.agent_gateway', self.gateway)
        self.service_gateway = patch('app.services.agent_sessions.service.agent_gateway', self.gateway)
        for patcher in (self.api_repo, self.service_repo, self.api_gateway, self.service_gateway):
            patcher.start()

    def tearDown(self):
        for patcher in (self.service_gateway, self.api_gateway, self.service_repo, self.api_repo):
            patcher.stop()
        self.live_registry.stop()
        self.env.stop()

    async def request(self, method: str, path: str, *, owner=None, json_body=None, headers=None):
        request_headers = {**(owner or self.OWNER_A), **(headers or {})}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            return await client.request(method, path, headers=request_headers, json=json_body)

    async def create(self, prompt='第一条问题', owner=None):
        response = await self.request('POST', '/api/v1/agent/sessions', owner=owner,
                                      json_body={'prompt': prompt, 'mode': 'fast'})
        self.assertEqual(response.status_code, 200)
        return response.json()['data']['id']

    async def test_crud_and_owner_isolation(self):
        session_id = await self.create('这是自动标题')
        detail = await self.request('GET', f'/api/v1/agent/sessions/{session_id}')
        self.assertEqual(detail.json()['data']['title'], '这是自动标题')
        forbidden = await self.request('GET', f'/api/v1/agent/sessions/{session_id}', owner=self.OWNER_B)
        self.assertEqual(forbidden.status_code, 404)
        renamed = await self.request('PATCH', f'/api/v1/agent/sessions/{session_id}',
                                    json_body={'title': '重命名'})
        self.assertEqual(renamed.json()['data']['title'], '重命名')
        self.assertEqual((await self.request('DELETE', f'/api/v1/agent/sessions/{session_id}')).status_code, 200)
        self.assertEqual((await self.request('GET', f'/api/v1/agent/sessions/{session_id}')).status_code, 404)

    async def test_cursor_pagination_and_legacy_import_are_product_owned(self):
        for index in range(12):
            await self.create(f'问题 {index}')
        first = (await self.request('GET', '/api/v1/agent/sessions?limit=10')).json()['data']
        self.assertEqual(len(first['sessions']), 10)
        second = (await self.request('GET',
            f"/api/v1/agent/sessions?limit=10&cursor={first['next_cursor']}")).json()['data']
        self.assertEqual(len(second['sessions']), 2)
        payload = {'import_key': 'legacy-1', 'title': '本地会话', 'turns': [
            {'role': 'user', 'content': '旧问题'},
            {'role': 'assistant', 'content': '旧答案', 'process': [{'kind': 'text', 'text': '旧答案'}]},
        ]}
        imported = await self.request('POST', '/api/v1/agent/sessions/import', json_body=payload)
        repeated = await self.request('POST', '/api/v1/agent/sessions/import', json_body=payload)
        self.assertEqual(imported.json()['data']['id'], repeated.json()['data']['id'])

    async def test_session_run_projects_agent_events_report_and_task_link(self):
        session_id = await self.create('打个招呼')
        self.gateway.enqueue(final_text='完成回答', events=[
            {'name': 'delta', 'data': {'turn': 1, 'text': '完成'}},
            {'name': 'tool_call', 'data': {'turn': 1, 'tool_call_id': 'c1',
                                           'name': 'echo', 'arguments': '{"value":"x"}'}},
            {'name': 'tool_end', 'data': {'turn': 1, 'tool_call_id': 'c1',
                                          'summary': 'x', 'duration_ms': 1}},
        ])
        response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                      json_body={'prompt': '打个招呼', 'mode': 'fast'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(parse_sse(response.text)[-1][1]['final_text'], '完成回答')
        session = await self.repo.get(session_id, f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}")
        turn = session.turns[0]
        self.assertEqual(turn.status, 'done')
        self.assertTrue(turn.settings['agent_task_id'].startswith('task-'))
        self.assertTrue(any(item['kind'] == 'tool' and item['tool']['done'] for item in turn.process))
        self.assertEqual([item['kind'] for item in session.runtime_history], ['user', 'assistant'])

    async def test_idempotency_replays_durable_events_without_local_live_cache(self):
        session_id = await self.create('幂等任务')
        body = {'prompt': '幂等任务', 'mode': 'fast'}
        headers = {'Idempotency-Key': 'agent-operation-1'}
        self.gateway.enqueue(final_text='第一次回答', events=[
            {'name': 'delta', 'data': {'turn': 0, 'text': '第一次回答'}},
        ])
        first = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                   json_body=body, headers=headers)
        live_runs._live.pop(session_id, None)
        replay = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                    json_body=body, headers=headers)
        self.assertEqual(parse_sse(replay.text)[-1][1]['final_text'], '第一次回答')
        self.assertEqual(len(self.gateway.submissions), 1)
        conflict = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                      json_body={'prompt': '别的请求'}, headers=headers)
        self.assertEqual(conflict.status_code, 409)
        endpoint = f'/api/v1/agent/sessions/{session_id}/run/stream'
        replayed = await self.request('GET', endpoint)
        self.assertEqual(parse_sse(replayed.text)[-1][1]['final_text'], '第一次回答')
        self.assertEqual(parse_sse(first.text)[-1][1]['final_text'], '第一次回答')

    async def test_attachment_is_owner_checked_consumed_and_sent_through_gateway(self):
        owner = f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}"
        upload = await agent_upload_store.save(owner, 'notes.md', {
            'text': '附件解析正文', 'original_length': 6, 'final_length': 6,
            'truncated': False, 'warning': None,
        })
        session_id = await self.create('请分析附件')
        response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
            json_body={'prompt': '请分析附件', 'attachments': [
                {'kind': 'file', 'file_id': upload['file_id'], 'title': 'notes.md'},
            ]})
        self.assertEqual(response.status_code, 200)
        submitted = self.gateway.submissions[0]
        self.assertIn('附件解析正文', submitted['prompt'])
        turn = self.repo.sessions[session_id].turns[0]
        self.assertEqual(turn.settings['attachments'], [{'kind': 'file', 'title': 'notes.md'}])
        self.assertNotIn(upload['file_id'], json.dumps(turn.public(), ensure_ascii=False))
        with self.assertRaises(BusinessError):
            await agent_upload_store.get(owner, upload['file_id'])

    async def test_gateway_submit_failure_is_projected_as_failed_turn(self):
        session_id = await self.create('提交失败')
        self.gateway.submit_error = BusinessError(20004, 'Agent 服务不可用', 503)
        response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                      json_body={'prompt': '提交失败'})
        self.assertEqual(response.status_code, 503)
        turn = self.repo.sessions[session_id].turns[0]
        self.assertEqual(turn.status, 'failed')
        self.assertIn('Agent 服务提交失败', turn.error)

    async def test_failed_event_replay_keeps_partial_product_timeline(self):
        session_id = await self.create('投影失败')
        self.gateway.enqueue(final_text='部分答案', events=[
            {'name': 'delta', 'data': {'turn': 0, 'text': '部分答案'}},
        ], event_error=RuntimeError('Agent events unavailable'))
        response = await self.request('POST', f'/api/v1/agent/sessions/{session_id}/run',
                                      json_body={'prompt': '投影失败'})
        self.assertEqual(response.status_code, 200)
        # The projection catches Agent Gateway failures and closes the product Turn.
        turn = self.repo.sessions[session_id].turns[0]
        self.assertEqual(turn.status, 'failed')
        self.assertEqual(turn.assistant_content, '部分答案')

    async def test_orphan_reconciliation_preserves_previous_transcript(self):
        owner = f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}"
        session_id = await self.create('历史')
        previous, _ = await self.repo.start_turn(session_id, owner, '上一问', {}, [])
        history = [{'kind': 'user', 'text': '上一问'},
                   {'kind': 'assistant', 'content': '上一答', 'reasoning': '',
                    'tool_calls': [], 'stop_reason': 'stop', 'usage_tokens': 0}]
        await self.repo.finish_turn(session_id, owner, previous.id,
                                    {'status': 'done', 'transcript': history})
        orphan, _ = await self.repo.start_turn(session_id, owner, '中断前原文', {}, [])
        orphan.assistant_content = '部分结果'
        orphan.transcript = [{'kind': 'assistant', 'tool_calls': [{'id': 'unfinished'}]}]
        detail = (await self.request('GET', f'/api/v1/agent/sessions/{session_id}')).json()['data']
        self.assertEqual(detail['turns'][-1]['stop_reason'], 'interrupted')
        transcript = self.repo.sessions[session_id].runtime_history
        self.assertEqual(transcript[:2], history)
        self.assertEqual(transcript[-2], {'kind': 'user', 'text': '中断前原文'})
        self.assertEqual(transcript[-1]['tool_calls'], [])

    async def test_durable_active_turn_is_not_reconciled_as_orphan(self):
        owner = f"anon:{self.OWNER_A['x-shenzhi-anonymous-id']}"
        session_id = await self.create('其他进程运行中')
        turn, _ = await self.repo.start_turn(session_id, owner, '其他进程运行中', {}, [])
        self.repo.is_durable = True
        detail = await get_session_detail(session_id, owner)
        self.assertEqual(detail.turns[0].id, turn.id)
        self.assertEqual(detail.turns[0].status, 'running')

    async def test_remote_cancel_and_steer_use_gateway_controls(self):
        session_id = await self.create('可控制任务')
        gate = asyncio.Event()
        self.gateway.enqueue(final_text='已停止', status='completed', gate=gate,
                             events=[{'name': 'delta', 'data': {'turn': 0, 'text': '片段'}}])
        request = asyncio.create_task(self.request(
            'POST', f'/api/v1/agent/sessions/{session_id}/run',
            json_body={'prompt': '可控制任务'},
        ))
        while not self.gateway.submissions:
            await asyncio.sleep(0)
        run_id = next(iter(self.gateway.runs))
        steer = await self.request('POST', f'/api/v1/agent/run/{run_id}/steer',
                                   json_body={'text': '聚焦结论'})
        self.assertEqual(steer.status_code, 200)
        stopped = await self.request('POST', f'/api/v1/agent/run/{run_id}/stop')
        self.assertEqual(stopped.status_code, 200)
        response = await asyncio.wait_for(request, 3)
        self.assertEqual(parse_sse(response.text)[-1][1]['status'], 'stopped')
        self.assertEqual(self.gateway.steers[0][2], '聚焦结论')
        self.assertTrue(self.gateway.cancelled)


class TimelineCaptureTests(unittest.TestCase):
    def test_system_and_compaction_are_not_persisted_but_user_notes_are(self):
        capture = TimelineCapture([])
        capture.event('message', {'kind': 'system', 'text': '预算提示'})
        capture.event('compaction', {'before_chars': 100, 'after_chars': 10})
        self.assertEqual(capture.steers, [])
        capture.event('message', {'kind': 'steer', 'text': '用户插话'})
        capture.event('message', {'kind': 'follow_up', 'text': '用户追问'})
        self.assertEqual(capture.steers, [
            {'text': '用户插话', 'kind': 'steer'}, {'text': '用户追问', 'kind': 'follow_up'},
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


if __name__ == '__main__':
    unittest.main()
