"""2a persistence acceptance cases (requires live CHAT_DATABASE_URL + migrated DB)."""
from __future__ import annotations

import json
import os
import unittest
import uuid
from unittest.mock import patch

import httpx
from sqlalchemy import select, text

from app.core.database import session_scope
from app.main import app
from app.models.chat import ChatMessageRow, ChatSessionRow
from app.schemas.knowledge import KnowledgeSearchResponse
from app.services import chat
from app.services.sessions import repository

OWNER = {'x-shenzhi-anonymous-id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}
OTHER = {'x-shenzhi-anonymous-id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'}
OWNER_KEY = 'anon:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OTHER_KEY = 'anon:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'


class FakeProvider:
    calls: list = []

    async def stream(self, messages, model, mode):
        self.calls.append(messages)
        yield {'text': '验收正文 $x$'}

    async def followups(self, question, answer):
        return ['追问1？']


class FakeKnowledge:
    async def search(self, request):
        return KnowledgeSearchResponse(results=[])


def events(text: str):
    result = []
    for block in text.split('\n\n'):
        kind = data = None
        for line in block.splitlines():
            if line.startswith('event: '):
                kind = line[7:]
            if line.startswith('data: '):
                data = json.loads(line[6:])
        if kind:
            result.append((kind, data))
    return result


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class Acceptance2a(unittest.IsolatedAsyncioTestCase):
    """Maps to docs/chat/ACCEPTANCE-2a.md case IDs."""

    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        self.assertTrue(
            repository.is_durable,
            'expected PostgresSessionRepository; start a fresh process with CHAT_DATABASE_URL',
        )
        self.env = patch.dict('os.environ', {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
            'DASHSCOPE_API_KEY': '', 'BACKEND_BFF_SECRET': '',
            'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
        })
        self.env.start()
        await repository.purge_owner(OWNER_KEY)
        await repository.purge_owner(OTHER_KEY)
        FakeProvider.calls = []
        self.provider = patch.object(chat, 'ModelProvider', FakeProvider)
        self.provider.start()
        self.retrieval = patch.object(chat, 'knowledge_service', FakeKnowledge())
        self.retrieval.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://test', headers=OWNER,
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.provider.stop()
        self.retrieval.stop()
        self.env.stop()

    async def test_C01_ephemeral_false(self):
        response = await self.client.get('/api/v1/chat/sessions')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()['data']
        self.assertFalse(body['ephemeral'])
        self.assertEqual(body['sessions'], [])

    async def test_C02_C03_first_chat_and_stream(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '首问验收'})).json()['data']
        sid, mid = created['session_id'], created['message_id']
        stream = events((await self.client.get(f'/api/v1/chat/messages/{mid}/stream')).text)
        self.assertEqual(stream[-1][1]['status'], 'done')
        detail = (await self.client.get(f'/api/v1/chat/sessions/{sid}')).json()['data']
        self.assertIn('验收正文', detail['messages'][0]['content'])
        self.assertEqual(detail['messages'][0]['status'], 'done')
        async with session_scope() as db:
            sessions = (await db.scalars(select(ChatSessionRow).where(ChatSessionRow.owner == OWNER_KEY))).all()
            messages = (await db.scalars(select(ChatMessageRow))).all()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].owner, OWNER_KEY)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].status, 'done')

    async def test_C04_followup_uses_history(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '首问'})).json()['data']
        await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")
        follow = (await self.client.post(
            f"/api/v1/chat/sessions/{created['session_id']}/messages",
            json={'question': '续问'},
        )).json()['data']
        await self.client.get(f"/api/v1/chat/messages/{follow['message_id']}/stream")
        self.assertTrue(any(
            m.get('role') == 'assistant' and '验收正文' in m.get('content', '')
            for m in FakeProvider.calls[-1]
        ))

    async def test_C05_reload_from_pg_without_memory(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '持久标题问题'})).json()['data']
        await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")
        repository.messages.clear()
        listing = (await self.client.get('/api/v1/chat/sessions')).json()['data']['sessions']
        self.assertEqual(len(listing), 1)
        self.assertTrue(listing[0]['title'].startswith('持久'))
        detail = (await self.client.get(f"/api/v1/chat/sessions/{created['session_id']}")).json()['data']
        self.assertIn('验收正文', detail['messages'][0]['content'])

    async def test_C06_favorite_rename_survives_cache_clear(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '改名源'})).json()['data']
        await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")
        await self.client.patch(
            f"/api/v1/chat/sessions/{created['session_id']}",
            json={'favorite': True, 'title': '验收重命名'},
        )
        repository.messages.clear()
        listing = (await self.client.get('/api/v1/chat/sessions')).json()['data']['sessions']
        self.assertEqual((listing[0]['favorite'], listing[0]['title']), (True, '验收重命名'))

    async def test_C07_delete(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '待删'})).json()['data']
        await self.client.delete(f"/api/v1/chat/sessions/{created['session_id']}")
        self.assertEqual(
            (await self.client.get(f"/api/v1/chat/sessions/{created['session_id']}")).status_code,
            404,
        )
        async with session_scope() as db:
            row = await db.scalar(
                select(ChatSessionRow).where(ChatSessionRow.id == uuid.UUID(created['session_id']))
            )
        self.assertIsNone(row)

    async def test_C08_owner_isolation(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': '隔离'})).json()['data']
        sid, mid = created['session_id'], created['message_id']
        for method, path, body in [
            ('GET', f'/sessions/{sid}', None),
            ('PATCH', f'/sessions/{sid}', {'favorite': True}),
            ('DELETE', f'/sessions/{sid}', None),
            ('POST', f'/sessions/{sid}/messages', {'question': 'q'}),
            ('GET', f'/messages/{mid}/stream', None),
            ('POST', f'/messages/{mid}/stop', None),
            ('POST', f'/messages/{mid}/resume', None),
        ]:
            response = await self.client.request(method, '/api/v1/chat' + path, headers=OTHER, json=body)
            self.assertEqual(response.status_code, 404, path)
        other_list = (await self.client.get('/api/v1/chat/sessions', headers=OTHER)).json()['data']['sessions']
        self.assertEqual(other_list, [])

    async def test_C08b_resume_after_cache_miss(self):
        created = (await self.client.post('/api/v1/chat/sessions', json={'question': 'resume缺缓存'})).json()['data']
        mid = created['message_id']
        await self.client.post(f'/api/v1/chat/messages/{mid}/stop')
        repository.messages.clear()
        resumed = await self.client.post(f'/api/v1/chat/messages/{mid}/resume')
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()['data']['message_id'], mid)

    async def test_C09_recover_marks_streaming_failed(self):
        from sqlalchemy import update
        session = await repository.create(OWNER_KEY, 'recover', {
            'type': 'ask', 'mode': 'fast', 'model': 'deepseek-chat', 'web_search': False,
        })
        message = await repository.add_message(session, 'recover', session.settings)
        # Simulate pre-crash content already mirrored (2a.1 checkpoint or partial write).
        async with session_scope() as db:
            await db.execute(
                update(ChatMessageRow)
                .where(ChatMessageRow.id == uuid.UUID(message.id))
                .values(content='半截')
            )
        await repository.recover()
        repository.messages.clear()
        restored = await repository.get(session.id, OWNER_KEY)
        self.assertEqual(restored.messages[0].status, 'failed')
        self.assertEqual(restored.messages[0].content, '半截')

    async def test_C10_finalize_idempotent(self):
        session = await repository.create(OWNER_KEY, 'idem', {
            'type': 'ask', 'mode': 'fast', 'model': 'deepseek-chat', 'web_search': False,
        })
        message = await repository.add_message(session, 'idem', session.settings)
        message.content, message.status = '最终', 'done'
        await repository.persist_message(message)
        message.content = '应被忽略'
        await repository.persist_message(message)
        async with session_scope() as db:
            row = await db.scalar(select(ChatMessageRow).where(ChatMessageRow.id == uuid.UUID(message.id)))
        self.assertEqual(row.content, '最终')


@unittest.skipUnless(os.getenv('CHAT_DATABASE_URL'), 'CHAT_DATABASE_URL not set')
class EnvironmentChecks(unittest.TestCase):
    def test_E01_E02_schema(self):
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine

        url = os.environ['CHAT_DATABASE_URL']
        if url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)

        async def check():
            engine = create_async_engine(url)
            async with engine.connect() as conn:
                tables = (await conn.execute(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
                ))).scalars().all()
                version = (await conn.execute(text('SELECT version_num FROM alembic_version'))).scalar_one()
            await engine.dispose()
            return tables, version

        tables, version = asyncio.run(check())
        self.assertIn('chat_sessions', tables)
        self.assertIn('chat_messages', tables)
        self.assertEqual(version, '002_anon_expiry_idx')


if __name__ == '__main__':
    unittest.main()
