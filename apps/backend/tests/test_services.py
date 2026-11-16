import io
import json
import unittest
from unittest.mock import patch
import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.core.errors import BusinessError
from app.integrations.knowledge.client import KnowledgeBaseClient
from app.schemas.agent import AgentAttachment
from app.services.uploads.parser import parse_document
from app.services.agent.attachments import attachment_context
from app.integrations.web_search.provider import web_search


class DocumentTests(unittest.TestCase):
    def test_text_normalization_and_combined_attachment_limit(self):
        files = {f'f{i}': {**parse_document(('x' * 31000).encode(), f'{i}.md'), 'filename': f'{i}.md'}
                 for i in range(3)}
        self.assertTrue(files['f0']['truncated'])
        self.assertEqual(files['f0']['original_length'], 31000)
        self.assertEqual(files['f0']['final_length'], 30000)
        attachments = [AgentAttachment(kind='file', file_id=file_id) for file_id in files]
        context, warnings = attachment_context(attachments, files)
        self.assertLessEqual(len(context), 60000)
        self.assertTrue(any('60,000' in warning for warning in warnings))
        with self.assertRaises(BusinessError):
            attachment_context([AgentAttachment(kind='file', file_id='expired')], files)
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


class WebSearchTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_web_search_records_provider_failure_and_fallback_completion(self):
        records = []

        def record(_logger, _level, event, fields):
            records.append((event, fields))

        def handler(request):
            if request.url.host == 'api.tavily.com':
                raise httpx.ReadTimeout('timeout', request=request)
            return httpx.Response(200, json={'results': [{'title': 'Result', 'url': 'https://example.test'}]})

        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test', 'SEARXNG_BASE_URL': 'https://search.test'}), \
             patch('app.integrations.web_search.provider.log_event', side_effect=record):
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
