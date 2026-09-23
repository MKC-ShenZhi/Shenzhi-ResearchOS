"""Collection and history routes keep the authenticated user boundary."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.collections import CollectionFolder, FolderListResponse
from app.schemas.history import ReadingHistoryItem, ReadingHistoryResponse
from app.schemas.knowledge import PaperDetail, Provenance


class LibraryApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BACKEND_BFF_SECRET': 'test-secret'})
        self.env.start()
        self.client = TestClient(app)
        self.user_headers = {'x-shenzhi-bff-secret': 'test-secret', 'x-shenzhi-user-id': 'user-a'}
        self.anonymous_headers = {
            'x-shenzhi-bff-secret': 'test-secret',
            'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }

    def tearDown(self):
        self.env.stop()

    def test_collections_and_history_reject_anonymous_access(self):
        for method, path in (
            ('get', '/api/v1/collections/folders'),
            ('get', '/api/v1/history'),
            ('post', '/api/v1/papers/paper-a/view'),
        ):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, headers=self.anonymous_headers).status_code, 401)

    def test_authenticated_routes_use_trusted_user(self):
        folders = FolderListResponse(folders=[CollectionFolder(id=1, name='想读', is_default=True, paper_count=0)])
        history = ReadingHistoryResponse(items=[], total=0, page=1, page_size=20)
        with (
            patch('app.api.collections.service.folders', new=AsyncMock(return_value=folders)) as get_folders,
            patch('app.api.history.service.list', new=AsyncMock(return_value=history)) as get_history,
            patch('app.api.history.service.record', new=AsyncMock()) as record,
        ):
            self.assertEqual(self.client.get('/api/v1/collections/folders', headers=self.user_headers).json()['data']['folders'][0]['name'], '想读')
            self.assertEqual(self.client.get('/api/v1/history', headers=self.user_headers).json()['data']['total'], 0)
            self.assertEqual(self.client.post('/api/v1/papers/paper-a/view', headers=self.user_headers).status_code, 200)
        get_folders.assert_awaited_once_with('user-a')
        get_history.assert_awaited_once_with('user-a', 1, 20, '')
        record.assert_awaited_once_with('user-a', 'paper-a')

    def test_personal_overview_maps_real_reading_history_items(self):
        history_item = ReadingHistoryItem.model_validate({
            **PaperDetail(
                id='paper:real:1',
                title='A real paper',
                provenance=Provenance(external_id='paper:real:1'),
            ).model_dump(),
            'paper_id': 'paper:real:1',
            'last_viewed_at': '2026-09-23T07:42:06Z',
        })
        folders = FolderListResponse(folders=[])
        history = ReadingHistoryResponse(items=[history_item], total=1, page=1, page_size=5)
        with (
            patch('app.api.knowledge.collection_service.folders', new=AsyncMock(return_value=folders)),
            patch('app.api.knowledge.reading_history_service.list', new=AsyncMock(return_value=history)),
        ):
            response = self.client.get('/api/v1/knowledge/personal-overview', headers=self.user_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['recentPapers'][0]['id'], 'paper:real:1')
        self.assertEqual(response.json()['data']['recentPapers'][0]['paper_id'], 'paper:real:1')


if __name__ == '__main__':
    unittest.main()
