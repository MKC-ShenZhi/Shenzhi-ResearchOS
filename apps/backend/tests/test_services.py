import asyncio
import io
import json
import unittest
from unittest.mock import patch
import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.core.config import ModelConfig
from app.core.errors import BusinessError
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.schemas.chat import ChatAttachment
from app.services.document_parser import parse_document, attachment_context
from app.services.model_provider import ModelProvider, completion_payload, resolve_model
from app.services.sessions import MemorySessionRepository
from app.services.web_search import web_search

CONFIG = ModelConfig('test-key', 'https://model.test/v1', 'deepseek-chat', ('deepseek-chat', 'deepseek-reasoner'), 'deepseek')


class DocumentTests(unittest.TestCase):
    def test_text_normalization_limits_and_ownership(self):
        repo = MemorySessionRepository()
        files = [repo.save_upload('a', f'{i}.md', parse_document(('x' * 31000).encode(), f'{i}.md')) for i in range(3)]
        self.assertTrue(files[0]['truncated'])
        self.assertEqual(files[0]['original_length'], 31000)
        self.assertEqual(files[0]['final_length'], 30000)
        attachments = [ChatAttachment(kind='file', file_id=f['file_id']) for f in files]
        context, warnings = attachment_context(attachments, 'a', repo)
        self.assertLessEqual(len(context), 60000)
        self.assertTrue(any('60,000' in warning for warning in warnings))
        with self.assertRaises(BusinessError):
            attachment_context(attachments, 'b', repo)
        self.assertEqual(parse_document(b'\xef\xbb\xbfhello\r\n\n\nworld', 'a.txt')['text'], 'hello\n\nworld')

    def test_pdf_and_invalid_files(self):
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 10 100 Td (Hello research) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        out = io.BytesIO(); writer.write(out)
        self.assertIn('Hello research', parse_document(out.getvalue(), 'paper.pdf')['text'])
        for data, name in [(b'bad', 'a.docx'), (b'', 'a.txt'), (b'bad', 'a.pdf'), (b'x' * (20 * 1024 * 1024 + 1), 'a.txt')]:
            with self.subTest(name=name, size=len(data)), self.assertRaises(BusinessError):
                parse_document(data, name)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_delta_reasoning_crlf_and_payload(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, text='data: {"choices":[{"delta":{"reasoning_content":"分析"}}]}\r\n\r\ndata: {"choices":[{"delta":{"content":"答案"}}]}\n\ndata: [DONE]\n\n')
        provider = ModelProvider(CONFIG, httpx.MockTransport(handler))
        result = [event async for event in provider.stream([{'role': 'user', 'content': 'q'}], 'deepseek-reasoner', 'deep')]
        self.assertEqual(result, [{'reasoning': '分析'}, {'text': '答案'}])
        self.assertNotIn('temperature', requests[0])
        self.assertEqual(requests[0]['max_tokens'], 8192)
        self.assertEqual(completion_payload('deepseek-chat', [], 'idea')['temperature'], 1.0)
        with self.assertRaises(BusinessError):
            resolve_model('arbitrary-model', CONFIG)

    async def test_errors_missing_key_and_premature_eof(self):
        for response in [httpx.Response(401, text='secret upstream response'), httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')]:
            provider = ModelProvider(CONFIG, httpx.MockTransport(lambda req: response))
            with self.assertRaises(BusinessError) as caught:
                _ = [event async for event in provider.stream([], 'deepseek-chat', 'fast')]
            self.assertNotIn('secret', caught.exception.message)
        missing = ModelProvider(ModelConfig('', CONFIG.base_url, CONFIG.model, CONFIG.models, CONFIG.provider))
        with self.assertRaises(BusinessError):
            _ = [event async for event in missing.stream([], 'deepseek-chat', 'fast')]

    async def test_followups_and_optional_failure(self):
        provider = ModelProvider(CONFIG, httpx.MockTransport(lambda req: httpx.Response(200, json={'choices': [{'message': {'content': '```json\n["细节？", "对比？", "应用？"]\n```'}}]})))
        self.assertEqual(len(await provider.followups('q', 'a' * 21)), 3)
        provider.transport = httpx.MockTransport(lambda req: httpx.Response(503))
        self.assertEqual(await provider.followups('q', 'a' * 21), [])

    async def test_provider_cancellation_closes_response(self):
        started, closed = asyncio.Event(), asyncio.Event()
        class BlockingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                started.set()
                await asyncio.Event().wait()
                yield b''
            async def aclose(self):
                closed.set()
        provider = ModelProvider(CONFIG, httpx.MockTransport(lambda req: httpx.Response(200, stream=BlockingStream())))
        async def consume():
            return [event async for event in provider.stream([], 'deepseek-chat', 'fast')]
        task = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(closed.is_set())

    async def test_search_fallback_and_news(self):
        requests = []
        def handler(request):
            requests.append(request)
            if request.url.host == 'api.tavily.com':
                raise httpx.ReadTimeout('timeout', request=request)
            return httpx.Response(200, json={'results': [
                {'title': 'News', 'url': 'https://example.org/paper', 'content': 'result', 'engine': 'test'},
                {'title': 'unsafe', 'url': 'javascript:alert(1)'},
            ]})
        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test', 'SEARXNG_BASE_URL': 'https://search.test'}):
            items, warnings = await web_search('最新研究', transport=httpx.MockTransport(handler))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['engine'], 'test')
        self.assertTrue(warnings)
        self.assertEqual(json.loads(requests[0].content)['topic'], 'news')
        self.assertEqual(requests[1].url.params['format'], 'json')
        with patch.dict('os.environ', {}, clear=True):
            items, warnings = await web_search(
                'q',
                transport=httpx.MockTransport(lambda request: httpx.Response(500)),
            )
        self.assertEqual(items, [])
        self.assertTrue(warnings)


class P2ObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_knowledge_client_records_completed_and_failed_external_requests(self):
        records = []

        def record(_logger, _level, event, fields):
            records.append((event, fields))

        with patch('app.integrations.knowledge.client.log_event', side_effect=record):
            client = KnowledgeBaseClient(
                base_url='https://knowledge.test',
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'results': []})),
            )
            await client.search({'query': 'q'})

            failing = KnowledgeBaseClient(
                base_url='https://knowledge.test',
                transport=httpx.MockTransport(lambda request: httpx.Response(503)),
            )
            with self.assertRaises(Exception):
                await failing.search({'query': 'q'})

        self.assertEqual(records[0][0], 'knowledge.request.completed')
        self.assertEqual(records[0][1]['provider'], 'knowledge_base')
        self.assertEqual(records[0][1]['operation'], 'POST /api/retrieval/search')
        self.assertNotIn('query', records[0][1])
        self.assertEqual(records[1][0], 'knowledge.request.failed')
        self.assertEqual(records[1][1]['status_code'], 503)

    async def test_model_provider_records_stream_terminal_events_without_changing_errors(self):
        records = []

        def record(_logger, _level, event, fields):
            records.append((event, fields))

        with patch('app.services.model_provider.log_event', side_effect=record):
            provider = ModelProvider(
                CONFIG,
                httpx.MockTransport(lambda request: httpx.Response(200, text='data: [DONE]\n\n')),
            )
            self.assertEqual([event async for event in provider.stream([], 'deepseek-chat', 'fast')], [])

            failing = ModelProvider(
                CONFIG,
                httpx.MockTransport(lambda request: httpx.Response(503)),
            )
            with self.assertRaises(BusinessError):
                _ = [event async for event in failing.stream([], 'deepseek-chat', 'fast')]

        self.assertEqual(records[0][0], 'llm.request.completed')
        self.assertEqual(records[0][1]['operation'], 'chat.completions.stream')
        self.assertEqual(records[1][0], 'llm.request.failed')
        self.assertEqual(records[1][1]['status_code'], 503)

    async def test_web_search_records_provider_failure_and_fallback_completion(self):
        records = []

        def record(_logger, _level, event, fields):
            records.append((event, fields))

        def handler(request):
            if request.url.host == 'api.tavily.com':
                raise httpx.ReadTimeout('timeout', request=request)
            return httpx.Response(200, json={'results': [{'title': 'Result', 'url': 'https://example.test'}]})

        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test', 'SEARXNG_BASE_URL': 'https://search.test'}), \
             patch('app.services.web_search.log_event', side_effect=record):
            items, _warnings = await web_search('q', transport=httpx.MockTransport(handler))

        self.assertEqual(len(items), 1)
        self.assertEqual([event for event, _fields in records], [
            'web_search.provider_failed',
            'web_search.completed',
        ])
        self.assertEqual(records[0][1]['provider'], 'tavily')
        self.assertEqual(records[1][1]['provider'], 'searxng')


if __name__ == '__main__':
    unittest.main()
