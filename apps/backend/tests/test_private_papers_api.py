"""Private upload uses the bounded reader and an authenticated owner."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.api.private_papers import service
from app.core.identity import require_user
from app.main import app


class PrivatePaperApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.dependency_overrides[require_user] = lambda: SimpleNamespace(subject_id='user-1')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.pop(require_user, None)

    async def test_upload_passes_owner_folder_and_file_to_service(self):
        expected = {'id': 1, 'filename': 'paper.pdf', 'title': 'paper', 'size_bytes': 8,
                    'created_at': '2026-10-15T00:00:00+00:00'}
        with patch.object(service, 'save', new_callable=AsyncMock, return_value=expected) as save:
            response = await self.client.post('/api/v1/private-papers?folder_id=3',
                                              files={'file': ('paper.pdf', b'%PDF-123', 'application/pdf')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], expected)
        save.assert_awaited_once_with('user-1', 3, 'paper.pdf', b'%PDF-123')

    async def test_oversize_upload_returns_structured_413_before_save(self):
        with patch.object(service, 'save', new_callable=AsyncMock) as save:
            response = await self.client.post('/api/v1/private-papers?folder_id=3',
                                              files={'file': ('paper.pdf', b'x' * (20 * 1024 * 1024 + 1), 'application/pdf')})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()['code'], 20006)
        save.assert_not_awaited()

    async def test_file_download_is_owner_scoped(self):
        with patch.object(service, 'file', new_callable=AsyncMock, return_value=b'%PDF-test') as read:
            response = await self.client.get('/api/v1/private-papers/7/file')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'%PDF-test')
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        read.assert_awaited_once_with('user-1', 7)
