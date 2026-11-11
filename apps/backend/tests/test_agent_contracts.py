"""Backend Gateway contract tests for the shared Agent HTTP wire models."""
from __future__ import annotations

import json
import unittest

import httpx
from pydantic import ValidationError

from app.services.agent_gateway.client import AgentGateway


class AgentGatewayContractTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, handler):
        return AgentGateway(
            base_url='http://agent.test', token='service-secret',
            transport=httpx.MockTransport(handler),
        )

    async def test_submit_uses_shared_wire_schema_and_validates_task_response(self):
        seen = {}

        def handler(request):
            seen['auth'] = request.headers.get('authorization')
            seen['payload'] = json.loads(request.content)
            return httpx.Response(200, json={
                'task_id': 't1', 'owner_id': 'anon:1', 'session_id': 'ses1',
                'turn_id': 'turn1', 'status': 'queued', 'current_run_id': 'r1',
                'cancel_requested': False, 'created_at': '2026-11-11T00:00:00+00:00',
            })

        result = await self.gateway(handler).submit({
            'owner_id': 'anon:1', 'prompt': 'research', 'session_id': 'ses1',
            'turn_id': 'turn1', 'budget': {'max_tool_calls': 0},
        })
        self.assertEqual(seen['auth'], 'Bearer service-secret')
        self.assertEqual(seen['payload']['budget']['max_tool_calls'], 0)
        self.assertEqual((result['task_id'], result['current_run_id']), ('t1', 'r1'))

    async def test_submit_rejects_unpaired_session_and_turn_before_network(self):
        gateway = self.gateway(lambda _request: self.fail('request must not be sent'))
        with self.assertRaises(ValidationError):
            await gateway.submit({'owner_id': 'u1', 'prompt': 'research', 'session_id': 'ses1'})

    async def test_run_and_event_responses_are_validated_as_shared_wire_types(self):
        def handler(request):
            if request.url.path.endswith('/events'):
                return httpx.Response(200, json={'events': [{
                    'task_id': 't1', 'run_id': 'r1', 'seq': 2, 'turn': 1,
                    'name': 'delta', 'data': {'text': 'answer'},
                    'occurred_at': '2026-11-11T00:00:00+00:00',
                }]})
            return httpx.Response(200, json={
                'run_id': 'r1', 'task_id': 't1', 'attempt': 1, 'status': 'completed',
                'created_at': '2026-11-11T00:00:00+00:00', 'started_at': None,
                'completed_at': '2026-11-11T00:00:01+00:00',
                'task_status': 'completed',
                'report': {
                    'run_id': 'r1', 'task_id': 't1', 'status': 'completed',
                    'result': {'final_text': 'answer'},
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 3},
                    'error_code': None, 'error_message': None,
                },
            })

        gateway = self.gateway(handler)
        run = await gateway.run('r1', 'anon:1')
        events = await gateway.events('r1', 'anon:1', 1)
        self.assertEqual(run['report']['result']['final_text'], 'answer')
        self.assertEqual(events[0]['seq'], 2)

    async def test_invalid_agent_wire_response_is_rejected(self):
        gateway = self.gateway(lambda _request: httpx.Response(200, json={
            'task_id': 't1', 'owner_id': 'u1', 'session_id': None, 'turn_id': None,
            'status': 'queued', 'current_run_id': 'r1', 'created_at': 'invalid',
            'unknown_field': True,
        }))
        with self.assertRaises(ValidationError):
            await gateway.submit({'owner_id': 'u1', 'prompt': 'research'})


if __name__ == '__main__':
    unittest.main()
