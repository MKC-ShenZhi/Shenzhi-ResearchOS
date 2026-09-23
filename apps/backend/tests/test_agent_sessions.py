"""Persistent Agent session API and repository behavior."""
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
from app.services.agent_sessions.repository import MemoryAgentSessionRepository
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
        self.repo = MemoryAgentSessionRepository()
        self.api_repo = patch('app.api.agent.agent_session_repository', self.repo)
        self.service_repo = patch(
            'app.services.agent_sessions.service.agent_session_repository', self.repo,
        )
        self.api_repo.start()
        self.service_repo.start()

    def tearDown(self):
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


if __name__ == '__main__':
    unittest.main()
