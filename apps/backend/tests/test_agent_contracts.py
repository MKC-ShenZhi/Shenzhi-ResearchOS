"""Backend Gateway contract tests for the unified V2 HTTP boundary."""
from __future__ import annotations

import unittest

import httpx
from pydantic import ValidationError

from app.services.agent_gateway.gateway import AgentGateway


class AgentGatewayContractTests(unittest.IsolatedAsyncioTestCase):
    def gateway(self, handler):
        return AgentGateway(
            base_url='http://agent.test', token='gateway-secret',
            transport=httpx.MockTransport(handler),
        )

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
                'completed_at': '2026-11-11T00:00:01+00:00', 'task_status': 'completed',
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

    async def test_task_runs_preserves_order_and_forwards_owner_and_gateway_auth(self):
        def handler(request):
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.path, '/internal/v2/tasks/t1/runs')
            self.assertEqual(request.url.params['owner_id'], 'anon:1')
            self.assertEqual(request.headers['authorization'], 'Bearer gateway-secret')
            return httpx.Response(200, json={'run_ids': ['r3', 'r1', 'r2']})

        self.assertEqual(await self.gateway(handler).task_runs('t1', 'anon:1'), ['r3', 'r1', 'r2'])

    async def test_task_runs_rejects_missing_or_empty_history(self):
        for payload in ({}, {'run_ids': []}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await self.gateway(lambda _: httpx.Response(200, json=payload)).task_runs('t1', 'u1')


if __name__ == '__main__':
    unittest.main()
