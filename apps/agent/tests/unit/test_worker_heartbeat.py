import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from agent_app.api import routes
from agent_app.infrastructure.database import get_session
from agent_app.main import app
from agent_app.worker.host import AgentControlClient


class WorkerHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_and_api_agree_on_renewal_and_cancellation(self):
        session = object()

        async def fake_session():
            yield session

        renew = AsyncMock(side_effect=[(True, False), (True, True), (False, False)])
        with (
            patch.dict(os.environ, {'AGENT_SERVICE_TOKEN': 'test-token'}),
            patch.dict(app.dependency_overrides, {get_session: fake_session}),
            patch.object(routes.repository, 'heartbeat', renew),
        ):
            control = AgentControlClient(transport=httpx.ASGITransport(app=app))
            try:
                renewed = await control.heartbeat('run-1', 'worker-1', 1)
                cancelling = await control.heartbeat('run-1', 'worker-1', 1)
                stale = await control.heartbeat('run-1', 'worker-1', 1)
            finally:
                await control.close()

        self.assertTrue(renewed.active)
        self.assertFalse(renewed.cancel_requested)
        self.assertTrue(cancelling.active)
        self.assertTrue(cancelling.cancel_requested)
        self.assertFalse(stale.active)
        self.assertEqual(renew.await_count, 3)
        renew.assert_awaited_with(session, 'run-1', 'worker-1', 1)
