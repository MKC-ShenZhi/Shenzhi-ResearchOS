import json
import unittest
from unittest.mock import patch

import httpx

from agent_app.worker.host import AgentControlClient


class WorkerHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_heartbeat_uses_v2_identity_and_response_contract(self):
        requests = []

        async def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                'schema_version': 1, 'active': True, 'cancel_requested': True,
            })

        with patch.dict('os.environ', {'AGENT_WORKER_TOKEN': 'worker-token'}, clear=True):
            control = AgentControlClient(transport=httpx.MockTransport(respond))
            control.execution_id = 'execution-1'
            try:
                state = await control.heartbeat('run-1', 'worker-1', 3)
            finally:
                await control.close()

        self.assertTrue(state.active)
        self.assertTrue(state.cancel_requested)
        request = requests[0]
        self.assertEqual(request.url.path, '/internal/v2/runs/run-1/heartbeat')
        self.assertEqual(request.headers['authorization'], 'Bearer worker-token')
        body = json.loads(request.content)
        self.assertEqual(body['execution_id'], 'execution-1')
        self.assertEqual(body['worker_id'], 'worker-1')
        self.assertEqual(body['lease_token'], 3)


if __name__ == '__main__':
    unittest.main()
