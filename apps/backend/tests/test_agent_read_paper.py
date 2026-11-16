import asyncio
import io
import json
import socket
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.agent.fetch_url import fetch_url_tool
from app.services.agent.read_paper import _paginate, read_paper_tool
from app.services.agent.types import ToolCall


class StubKnowledgeService:
    def __init__(self):
        self.paper_ids: list[str] = []

    async def get_paper(self, paper_id: str):
        self.paper_ids.append(paper_id)
        return SimpleNamespace(pdf_url='https://1.1.1.1/fulltext')


class ReadPaperIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_opaque_paper_id_is_forwarded_to_knowledge_without_rewriting(self):
        knowledge = StubKnowledgeService()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200,
            headers={'content-type': 'text/html; charset=utf-8'},
            content=b'<main>Fallback page text</main>',
            request=request,
        ))
        tool = read_paper_tool(knowledge=knowledge, transport=transport)
        paper_id = 'paper:opaque/value?part=1%2Fsection'
        args = tool.spec.params_model.model_validate({'paper_id': paper_id})

        output = await tool.execute(ToolCall('call-1', 'read_paper', {'paper_id': paper_id}), args)

        self.assertEqual(knowledge.paper_ids, [paper_id])
        self.assertFalse(json.loads(output)['pdf'])


class FetchConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def assert_nonblocking(self, factory):
        def handler(request):
            time.sleep(0.3)
            return httpx.Response(200, headers={'content-type': 'text/html'},
                                  content=b'<main>Research evidence</main>', request=request)

        tool = factory(transport=httpx.MockTransport(handler))
        call = ToolCall('read-1', tool.spec.name, {'url': 'https://papers.example/article'})
        finished = asyncio.Event()
        ticks = 0

        async def invoke():
            try:
                return await tool.execute(call, tool.spec.params_model.model_validate(call.arguments))
            finally:
                finished.set()

        async def ticker():
            nonlocal ticks
            while not finished.is_set():
                await asyncio.sleep(0.05)
                if not finished.is_set():
                    ticks += 1

        addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                      '', ('1.1.1.1', 443))]
        with patch('app.services.agent.netguard.socket.getaddrinfo', return_value=addresses):
            output, _ = await asyncio.gather(invoke(), ticker())
        self.assertIn('Research evidence', json.loads(output)['text'])
        self.assertGreaterEqual(ticks, 3)

    async def test_fetch_url_does_not_block_event_loop(self):
        await self.assert_nonblocking(fetch_url_tool)

    async def test_read_paper_html_fallback_does_not_block_event_loop(self):
        await self.assert_nonblocking(read_paper_tool)

    async def test_html_output_default_and_explicit_limits(self):
        for factory in (read_paper_tool, fetch_url_tool):
            for requested, expected in ((None, 7000), (100_000, 7000), (1200, 1200)):
                with self.subTest(tool=factory.__name__, requested=requested):
                    tool = factory(transport=httpx.MockTransport(lambda request: httpx.Response(
                        200, headers={'content-type': 'text/html'},
                        content=('<main>' + '正文' * 5000 + '</main>').encode(), request=request)))
                    arguments = {'url': 'https://1.1.1.1/article'}
                    if requested is not None:
                        arguments['max_chars'] = requested
                    call = ToolCall('html-1', tool.spec.name, arguments)
                    output = await tool.execute(call, tool.spec.params_model.model_validate(arguments))
                    body = json.loads(output)
                    self.assertLess(len(output), 8000)
                    self.assertEqual(len(body['text']), expected)
                    self.assertEqual(body['text_chars'], expected)
                    self.assertTrue(body['truncated'])


def make_multipage_pdf():
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    font_ref = writer._add_object(font)
    for index in range(1, 5):
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref}),
        })
        stream = DecodedStreamObject()
        text = f'Page {index} evidence. ' + 'research result ' * 200
        stream.set_data(f'BT /F1 12 Tf 10 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class ReadPaperOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_pdf_output_fits_context_and_can_resume(self):
        data = make_multipage_pdf()
        tool = read_paper_tool(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, headers={'content-type': 'application/pdf'}, content=data, request=request)))

        async def read(**kwargs):
            arguments = {'url': 'https://1.1.1.1/paper.pdf', **kwargs}
            call = ToolCall('pdf-1', 'read_paper', arguments)
            return await tool.execute(call, tool.spec.params_model.model_validate(arguments))

        output = await read()
        body = json.loads(output)
        self.assertLess(len(output), 8000)
        self.assertTrue(body['pdf'])
        self.assertEqual(body['pages_total'], 4)
        self.assertLessEqual(body['text_chars'], 7000)
        self.assertEqual(body['pages_read'], '1-3')
        self.assertTrue(body['truncated'])
        self.assertEqual(body['next_page_from'], 3)
        self.assertEqual(body['truncated']['at_page'], 3)
        for field in ('pages_total', 'pages_read', 'truncated', 'next_page_from'):
            self.assertLess(output.index(f'"{field}"'), output.index('"text"'))

        resumed = json.loads(await read(page_from=body['next_page_from'], page_to=4))
        self.assertEqual(resumed['pages_read'], '3-4')
        self.assertIn('Page 4 evidence', resumed['text'])
        self.assertNotIn('truncated', resumed)
        self.assertNotIn('next_page_from', resumed)

    def test_page_boundary_cut_reports_next_unread_page(self):
        first_page = '--- p.1 ---\n' + 'a' * 300
        text, meta = _paginate(['a' * 300, 'b' * 300], None, None, len(first_page) + 100)
        self.assertEqual(text, first_page)
        self.assertEqual(meta['pages_read'], '1-1')
        self.assertEqual(meta['next_page_from'], 2)
        self.assertEqual(meta['truncated']['at_page'], 2)

    def test_page_separators_count_towards_text_limit(self):
        text, meta = _paginate(['a' * 300] * 30, None, None, 7000)
        self.assertLessEqual(len(text), 7000)
        self.assertEqual(meta['text_chars'], len(text))
        self.assertTrue(meta['truncated'])


if __name__ == '__main__':
    unittest.main()
