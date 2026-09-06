import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import httpx
from app.main import app
from app.schemas.knowledge import KnowledgeSearchResponse, PaperSearchResult, Provenance
from app.services import chat
from app.services.sessions import repository

OWNER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}
OTHER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
OWNER_KEY = 'anon:00000000-0000-4000-8000-000000000001'


def events(text):
    result = []
    for block in text.split('\n\n'):
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith('event: '): kind = line[7:]
            if line.startswith('data: '): data = json.loads(line[6:])
        if kind: result.append((kind, data))
    return result


class FakeProvider:
    calls = []
    async def stream(self, messages, model, mode):
        self.calls.append(messages)
        yield {'reasoning': '分析过程'}
        yield {'text': '这是一个带公式 $x^2$ 的回答，用于验证流式输出 [1]。'}
    async def followups(self, question, answer):
        return ['继续解释？', '如何验证？']


class FakeKnowledge:
    async def search(self, request):
        return KnowledgeSearchResponse(results=[PaperSearchResult(
            id='p1', title='Paper', abstract='Evidence', authors=['Author'],
            year=2024, venue='Venue', provenance=Provenance(external_id='p1'),
        )])


class ChatApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat', 'DASHSCOPE_API_KEY': '', 'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true'})
        self.env.start()
        await repository.clear()
        FakeProvider.calls = []
        self.provider = patch.object(chat, 'ModelProvider', FakeProvider); self.provider.start()
        self.knowledge = patch.object(chat, 'knowledge_service', FakeKnowledge()); self.knowledge.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=OWNER)

    async def asyncTearDown(self):
        await repository.close(); await self.client.aclose()
        self.provider.stop(); self.knowledge.stop(); self.env.stop()

    async def create(self, **kwargs):
        response = await self.client.post('/api/v1/chat/sessions', json={
            'question': '首问',
            'capabilities': {'knowledge': {'enabled': True}},
            **kwargs,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    async def test_multiturn_history_favorite_and_delete(self):
        created = await self.create(); sid, mid = created['session_id'], created['message_id']
        response = await self.client.get(f'/api/v1/chat/messages/{mid}/stream')
        stream = events(response.text)
        self.assertEqual(set(kind for kind, data in stream), {'meta', 'delta', 'refs', 'followups', 'done'})
        self.assertEqual(stream[-1][1]['status'], 'done')
        detail = (await self.client.get(f'/api/v1/chat/sessions/{sid}')).json()['data']
        self.assertIn('公式', detail['messages'][0]['content'])
        self.assertEqual(detail['messages'][0]['reasoning'], '分析过程')
        self.assertEqual(detail['messages'][0]['references'][0]['title'], 'Paper')
        follow = (await self.client.post(f'/api/v1/chat/sessions/{sid}/messages', json={'question': '续问'})).json()['data']
        await self.client.get(f"/api/v1/chat/messages/{follow['message_id']}/stream")
        self.assertTrue(any(m['role'] == 'assistant' and '公式' in m['content'] for m in FakeProvider.calls[-1]))
        await self.client.patch(f'/api/v1/chat/sessions/{sid}', json={'favorite': True, 'title': '重命名'})
        listing = (await self.client.get('/api/v1/chat/sessions')).json()['data']['sessions']
        self.assertEqual((listing[0]['favorite'], listing[0]['title']), (True, '重命名'))
        await self.client.delete(f'/api/v1/chat/sessions/{sid}')
        self.assertEqual((await self.client.get(f'/api/v1/chat/messages/{mid}/stream')).status_code, 404)

    async def test_system_prompt_includes_fixed_current_utc_date(self):
        fixed_now = datetime(2026, 9, 6, 10, tzinfo=timezone.utc)
        with patch.object(chat, 'utc_now', return_value=fixed_now):
            created = await self.create(capabilities={'knowledge': {'enabled': False}})
            await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")

        system_prompt = FakeProvider.calls[-1][0]
        self.assertEqual(system_prompt['role'], 'system')
        self.assertIn('当前日期：2026-09-06', system_prompt['content'])
        self.assertIn('当前时间基准：UTC', system_prompt['content'])

    async def test_owner_checks_all_operations(self):
        data = await self.create(); sid, mid = data['session_id'], data['message_id']
        for method, path, body in [('GET', f'/sessions/{sid}', None), ('PATCH', f'/sessions/{sid}', {'favorite': True}),
            ('DELETE', f'/sessions/{sid}', None), ('POST', f'/sessions/{sid}/messages', {'question': 'q'}),
            ('GET', f'/messages/{mid}/stream', None), ('POST', f'/messages/{mid}/stop', None), ('POST', f'/messages/{mid}/resume', None)]:
            response = await self.client.request(method, '/api/v1/chat' + path, headers=OTHER, json=body)
            self.assertEqual(response.status_code, 404, path)
        self.assertEqual((await self.client.get('/api/v1/chat/sessions', headers=OTHER)).json()['data']['sessions'], [])
        with patch.dict('os.environ', {'BACKEND_BFF_SECRET': 'required'}):
            self.assertEqual((await self.client.get('/api/v1/chat/sessions')).status_code, 401)

    async def test_bff_secret_is_fail_closed_with_explicit_loopback_escape_hatch(self):
        with patch.dict('os.environ', {'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': ''}):
            self.assertEqual((await self.client.get('/api/v1/chat/config')).status_code, 503)
            self.assertEqual((await self.client.post('/api/v1/search/explore', json={'query': 'test'})).status_code, 503)
        self.assertEqual((await self.client.get('/api/v1/chat/config')).status_code, 200)
        self.assertEqual((await self.client.get('/api/v1/search/config')).status_code, 404)
        remote = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('203.0.113.10', 123)),
                                   base_url='http://test', headers=OWNER)
        try:
            self.assertEqual((await remote.get('/api/v1/chat/config')).status_code, 503)
        finally:
            await remote.aclose()

    async def test_anonymous_claim_uses_only_trusted_headers(self):
        migration_headers = {
            'x-shenzhi-user-id': 'user-1',
            'x-shenzhi-source-anonymous-id': '00000000-0000-4000-8000-000000000001',
        }
        response = await self.client.post('/api/v1/chat/anonymous-claim', headers=migration_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['data'], {
            'moved_count': 0,
            'skipped_streaming_count': 0,
            'durable': repository.is_durable,
        })
        self.assertEqual((await self.client.post(
            '/api/v1/chat/anonymous-claim',
            headers={'x-shenzhi-user-id': 'user-1'},
            json={'source_owner': OWNER_KEY},
        )).status_code, 401)

    async def test_upload_roundtrip_and_no_disk_spooling(self):
        with patch('tempfile.SpooledTemporaryFile', side_effect=AssertionError('must stay in memory')):
            response = await self.client.post('/api/v1/uploads', files={'file': ('notes.md', b'A' * 1100000, 'text/markdown')})
        self.assertEqual(response.status_code, 200, response.text)
        upload = response.json()['data']; file_id = upload['file_id']
        self.assertTrue(upload['truncated']); self.assertNotIn('text', upload)
        self.assertEqual((await self.client.get(f'/api/v1/uploads/{file_id}', headers=OTHER)).status_code, 404)
        created = await self.create(attachments=[{'kind': 'file', 'file_id': file_id}])
        await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")
        self.assertIn('AAAA', FakeProvider.calls[-1][-1]['content'])
        for name, data, status in [('x.docx', b'a', 415), ('x.txt', b'', 422), ('x.txt', b'A' * (20 * 1024 * 1024 + 1), 413)]:
            response = await self.client.post('/api/v1/uploads', files={'file': (name, data)})
            self.assertEqual(response.status_code, status)

    async def test_validation_replay_and_duplicate_stream_is_not_regeneration(self):
        self.assertEqual((await self.client.post('/api/v1/chat/sessions', json={'question': '  '})).status_code, 422)
        self.assertEqual((await self.client.post('/api/v1/chat/sessions', json={'question': 'q', 'model': 'unknown'})).status_code, 400)
        created = await self.create(); path = f"/api/v1/chat/messages/{created['message_id']}/stream"
        first = await self.client.get(path)
        replay = await self.client.get(path, headers={'Last-Event-ID': '1'})
        self.assertNotEqual(first.text, replay.text)
        self.assertEqual(len(FakeProvider.calls), 1)
        self.assertEqual((await self.client.get(path, headers={'Last-Event-ID': '999999'})).status_code, 400)

    async def test_stop_resume_appends_and_cancels_upstream(self):
        yielded, cancelled = asyncio.Event(), asyncio.Event()
        class SlowProvider(FakeProvider):
            async def stream(self, messages, model, mode):
                try:
                    yield {'text': '未完成'}
                    yielded.set()
                    await asyncio.Event().wait()
                finally: cancelled.set()
        created = await self.create(); mid = created['message_id']; message = await repository.message(mid, OWNER_KEY)
        with patch.object(chat, 'ModelProvider', SlowProvider):
            message.task = asyncio.create_task(chat.generate(message))
            await asyncio.wait_for(yielded.wait(), 2)
            await self.client.post(f'/api/v1/chat/messages/{mid}/stop')
        self.assertTrue(cancelled.is_set()); self.assertEqual(message.status, 'stopped')
        resumed = (await self.client.post(f'/api/v1/chat/messages/{mid}/resume')).json()['data']
        response = await self.client.get(f'/api/v1/chat/messages/{mid}/stream', headers={'Last-Event-ID': resumed['last_event_id']})
        self.assertNotIn('"text": "未完成"', response.text)
        self.assertTrue(message.content.startswith('未完成'))
        self.assertEqual(len((await repository.get(created['session_id'], OWNER_KEY)).messages), 1)
        self.assertIn({'role': 'assistant', 'content': '未完成'}, FakeProvider.calls[-1])

    async def test_truncated_history_emits_visible_warning(self):
        created = await self.create()
        await self.client.get(f"/api/v1/chat/messages/{created['message_id']}/stream")
        follow = (await self.client.post(f"/api/v1/chat/sessions/{created['session_id']}/messages", json={'question': 'next'})).json()['data']
        with patch.object(chat, 'MAX_HISTORY_CHARS', 1):
            response = await self.client.get(f"/api/v1/chat/messages/{follow['message_id']}/stream")
        metas = [data for kind, data in events(response.text) if kind == 'meta' and data.get('context_truncated')]
        self.assertTrue(metas)
        self.assertTrue(any('历史上下文' in warning for warning in metas[0]['warnings']))

    async def test_stop_before_stream_and_memory_capacity(self):
        created = await self.create(); mid = created['message_id']
        await self.client.post(f'/api/v1/chat/messages/{mid}/stop')
        self.assertEqual((await repository.message(mid, OWNER_KEY)).status, 'stopped')
        self.assertEqual(FakeProvider.calls, [])
        self.assertEqual((await self.client.post(f'/api/v1/chat/messages/{mid}/resume')).status_code, 200)
        with patch.object(repository, 'max_sessions', 1):
            response = await self.client.post('/api/v1/chat/sessions', json={'question': 'capacity'})
        self.assertEqual(response.status_code, 200 if repository.is_durable else 429)

    async def test_disconnect_and_product_error(self):
        created = await self.create(); message = await repository.message(created['message_id'], OWNER_KEY)
        class WaitingProvider(FakeProvider):
            async def stream(self, *args):
                yield {'text': 'partial'}
                await asyncio.Event().wait()
        with patch.object(chat, 'ModelProvider', WaitingProvider):
            generator = chat.stream_events(message)
            await anext(generator); await generator.aclose(); await asyncio.sleep(0)
            await chat.stop_message(message)
        self.assertEqual(message.status, 'stopped')
        class BrokenProvider(FakeProvider):
            async def stream(self, *args):
                from app.core.errors import BusinessError
                raise BusinessError(20004, 'model unavailable')
                yield
        other = await self.create()
        with patch.object(chat, 'ModelProvider', BrokenProvider):
            response = await self.client.get(f"/api/v1/chat/messages/{other['message_id']}/stream")
        stream = events(response.text)
        self.assertIn(('error', {'code': 20004, 'message': 'model unavailable'}), stream)
        self.assertEqual(stream[-1][1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
