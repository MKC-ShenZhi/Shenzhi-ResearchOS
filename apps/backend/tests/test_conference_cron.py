import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from app.api.maintenance import router
from app.services.discovery_pool.scheduler import conference_sync_enabled

class ConferenceCronTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'CRON_SECRET': 'test-secret', 'CONFERENCE_CRON_ENABLED': 'true', 'CHAT_DATABASE_URL': 'postgresql://test/unused'})
        self.env.start()
        app = FastAPI()
        app.include_router(router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.job = AsyncMock(return_value={'status': 'updated'})
        self.mock = patch('app.api.maintenance.ConferenceSync.run', self.job)
        self.mock.start()

    async def asyncTearDown(self):
        await self.client.aclose()
        self.mock.stop()
        self.env.stop()

    async def call(self, token='test-secret'):
        return await self.client.get('/api/v1/internal/conference-sync', headers={'Authorization': f'Bearer {token}'})

    async def test_unauthorized_and_unconfigured_never_run(self):
        for token in ('', 'wrong'):
            self.assertEqual((await self.call(token)).status_code, 401)
        for settings in ({'CRON_SECRET': ''}, {'CONFERENCE_CRON_ENABLED': 'false'}, {'CHAT_DATABASE_URL': ''}):
            with patch.dict(os.environ, settings):
                self.assertEqual((await self.call()).status_code, 503)
        self.job.assert_not_awaited()

    async def test_awaits_shared_job_including_safe_skips(self):
        for status in ('updated', 'unchanged', 'locked', 'not-due', 'retry-delayed'):
            self.job.return_value = {'status': status}
            response = await self.call()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['data']['status'], status)
            self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.job.await_count, 5)
        self.job.assert_awaited_with()

    async def test_failure_and_timeout_return_non_success(self):
        for error, status in ((RuntimeError('private connection detail'), 503), (TimeoutError(), 504)):
            self.job.side_effect = error
            with self.assertLogs('app.api.maintenance', level='ERROR'):
                response = await self.call()
            self.assertEqual(response.status_code, status)
            self.assertNotIn('private connection detail', response.text)

    async def test_real_deadline_cancels_job(self):
        async def stalled():
            await asyncio.sleep(10)
        self.job.side_effect = stalled
        timeout = asyncio.timeout
        with patch('app.api.maintenance.asyncio.timeout', side_effect=lambda _: timeout(0.01)):
            with self.assertLogs('app.api.maintenance', level='ERROR'):
                self.assertEqual((await self.call()).status_code, 504)

    def test_vercel_uses_http_instead_of_conference_loop(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'CONFERENCE_SYNC_ENABLED': 'true'}):
            self.assertFalse(conference_sync_enabled())
        with patch.dict(os.environ, {'VERCEL': '', 'CONFERENCE_SYNC_ENABLED': 'true'}):
            self.assertTrue(conference_sync_enabled())

    def test_cron_config(self):
        config = json.loads((Path(__file__).parents[1] / 'vercel.json').read_text())
        self.assertIn({'path': '/api/v1/internal/conference-sync', 'schedule': '0 1 * * *'}, config['crons'])
        self.assertGreater(config['functions']['api/index.py']['maxDuration'], 240)
