"""Agent uploads remain parsed-text-only and work across backend instances."""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
from sqlalchemy import select, update

from app.core.database import dispose_engine, session_scope
from app.core.errors import BusinessError
from app.main import app
from app.models.agent_upload import AgentUploadRow
from app.services.agent_uploads import AgentUploadStore


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class AgentUploadPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        })
        self.env.start()
        self.owner = f'anon:{uuid.uuid4()}'
        self.other = f'anon:{uuid.uuid4()}'
        self.headers = {'x-shenzhi-anonymous-id': self.owner.removeprefix('anon:')}
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        store = AgentUploadStore()
        await store.purge_owner(self.owner)
        await store.purge_owner(self.other)
        await self.client.aclose()
        self.env.stop()
        await dispose_engine()

    async def test_upload_is_shared_owner_scoped_and_consumed(self):
        response = await self.client.post('/api/v1/agent/uploads', headers=self.headers,
                                          files={'file': ('notes.md', b'private paper notes')})
        self.assertEqual(response.status_code, 200)
        public = response.json()['data']
        self.assertNotIn('text', public)
        file_id = public['file_id']
        second_instance = AgentUploadStore()
        self.assertEqual((await second_instance.get(self.owner, file_id))['text'], 'private paper notes')
        with self.assertRaises(BusinessError):
            await second_instance.get(self.other, file_id)
        async with session_scope() as db:
            row = await db.scalar(select(AgentUploadRow).where(AgentUploadRow.id == uuid.UUID(file_id)))
            self.assertEqual(row.text, 'private paper notes')
            self.assertFalse(hasattr(row, 'content'))
        await second_instance.consume(self.owner, [file_id])
        with self.assertRaises(BusinessError):
            await AgentUploadStore().get(self.owner, file_id)

    async def test_expired_text_is_rejected_and_purged(self):
        store = AgentUploadStore()
        saved = await store.save(self.owner, 'notes.md', {
            'text': 'temporary', 'original_length': 9, 'final_length': 9,
            'truncated': False, 'warning': None,
        })
        async with session_scope() as db:
            await db.execute(update(AgentUploadRow).where(
                AgentUploadRow.id == uuid.UUID(saved['file_id'])
            ).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        with self.assertRaises(BusinessError):
            await AgentUploadStore().get(self.owner, saved['file_id'])
        self.assertGreaterEqual(await store.purge_expired(), 1)

    async def test_pending_text_follows_anonymous_account_claim(self):
        store = AgentUploadStore()
        saved = await store.save(self.owner, 'notes.md', {
            'text': 'temporary', 'original_length': 9, 'final_length': 9,
            'truncated': False, 'warning': None,
        })
        await store.claim_owner(self.owner, self.other)
        with self.assertRaises(BusinessError):
            await AgentUploadStore().get(self.owner, saved['file_id'])
        self.assertEqual((await AgentUploadStore().get(self.other, saved['file_id']))['text'],
                         'temporary')


class AgentUploadMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_is_owner_scoped_and_consumable(self):
        with patch.dict(os.environ, {'CHAT_DATABASE_URL': ''}):
            store = AgentUploadStore()
            saved = await store.save('anon:test', 'notes.md', {
                'text': 'hello', 'original_length': 5, 'final_length': 5,
                'truncated': False, 'warning': None,
            })
            self.assertEqual((await store.get('anon:test', saved['file_id']))['text'], 'hello')
            with self.assertRaises(BusinessError):
                await store.get('anon:other', saved['file_id'])
            await store.consume('anon:test', [saved['file_id']])
            with self.assertRaises(BusinessError):
                await store.get('anon:test', saved['file_id'])
