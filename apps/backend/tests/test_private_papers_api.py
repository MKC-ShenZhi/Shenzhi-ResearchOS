"""Private upload uses the bounded reader and an authenticated owner."""
import unittest
import asyncio
import os
import uuid
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from pypdf import PdfWriter

from app.api.private_papers import service
from app.core.database import dispose_engine, session_scope
from app.core.errors import BusinessError
from app.core.identity import require_user
from app.main import app
from app.models.collections import CollectionFolderRow
from app.models.private_paper import PrivatePaperRow
from app.services.library.private_papers import (
    COMPRESSED_PREFIX, PRIVATE_PAPER_QUOTA_BYTES, _prepare_pdf, _restore_pdf,
)


def sample_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


class PrivatePaperStorageTests(unittest.TestCase):
    def test_compressible_pdf_round_trips_and_legacy_pdf_remains_readable(self):
        content = sample_pdf() + b'\n%' + b'A' * 100_000
        stored = _prepare_pdf(content)
        self.assertTrue(stored.startswith(COMPRESSED_PREFIX))
        self.assertEqual(_restore_pdf(stored, len(content)), content)
        self.assertEqual(_restore_pdf(sample_pdf(), len(sample_pdf())), sample_pdf())

    def test_compressed_pdf_rejects_wrong_size(self):
        content = sample_pdf() + b'\n%' + b'A' * 100_000
        stored = _prepare_pdf(content)
        with self.assertRaises(ValueError):
            _restore_pdf(stored, len(content) - 1)


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class PrivatePaperQuotaPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await dispose_engine()

    async def test_quota_counts_all_folders_and_serializes_parallel_uploads(self):
        user_id = f'private-paper-test-{uuid.uuid4()}'
        other_id = f'private-paper-test-{uuid.uuid4()}'
        content = sample_pdf()
        async with session_scope() as db:
            folders = [CollectionFolderRow(user_id=user_id, name=name) for name in ('one', 'two')]
            folders.append(CollectionFolderRow(user_id=other_id, name='other'))
            db.add_all(folders)
            await db.flush()
            folder_ids = [folder.id for folder in folders]
            db.add(PrivatePaperRow(user_id=user_id, folder_id=folder_ids[0],
                                   filename='old.pdf', title='old', content=content,
                                   size_bytes=PRIVATE_PAPER_QUOTA_BYTES - len(content)))
        try:
            results = await asyncio.gather(
                service.save(user_id, folder_ids[1], 'new-1.pdf', content),
                service.save(user_id, folder_ids[1], 'new-2.pdf', content),
                return_exceptions=True,
            )
            self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
            failures = [result for result in results if isinstance(result, BusinessError)]
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0].code, 20010)
            self.assertEqual(failures[0].status, 413)
            self.assertEqual(await service.file(user_id, next(result['id'] for result in results
                                                             if isinstance(result, dict))), content)
            compressible = content + b'\n%' + b'A' * 100_000
            other = await service.save(other_id, folder_ids[2], 'other.pdf', compressible)
            self.assertEqual(await service.file(other_id, other['id']), compressible)
            async with session_scope() as db:
                stored = await db.get(PrivatePaperRow, other['id'])
                self.assertTrue(stored.content.startswith(COMPRESSED_PREFIX))
                self.assertEqual(stored.size_bytes, len(compressible))
        finally:
            async with session_scope() as db:
                for folder_id in folder_ids:
                    folder = await db.get(CollectionFolderRow, folder_id)
                    if folder is not None:
                        await db.delete(folder)
