import json
import unittest
from unittest.mock import patch

import httpx

from agent_app.main import app
from agent_app.worker.host import AgentControlClient


class V1ProtocolRetirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_does_not_register_v1_internal_routes(self):
        paths = set(app.openapi()['paths'])
        self.assertFalse({path for path in paths if path.startswith('/internal/v1')})

    async def test_worker_uses_v2_even_when_legacy_protocol_env_is_present(self):
        requests = []

        async def respond(request):
            requests.append(request)
            return httpx.Response(200, json={'schema_version': 1, 'run': None})

        with patch.dict('os.environ', {
            'AGENT_WORKER_PROTOCOL': '1',
            'AGENT_WORKER_TOKEN': 'worker-token',
            'AGENT_SERVICE_TOKEN': 'service-token',
        }, clear=True):
            control = AgentControlClient(transport=httpx.MockTransport(respond))
            try:
                result = await control.claim('worker-1')
            finally:
                await control.close()

        self.assertIsNone(result['run'])
        self.assertEqual(requests[0].url.path, '/internal/v2/worker/claim')
        self.assertEqual(requests[0].headers['authorization'], 'Bearer worker-token')
        body = json.loads(requests[0].content)
        self.assertEqual(body['schema_version'], 1)
        self.assertFalse(body['demo_mode'])


if __name__ == '__main__':
    unittest.main()
