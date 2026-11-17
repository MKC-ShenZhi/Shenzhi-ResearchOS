import json
import unittest
from unittest.mock import patch

import httpx

from agent_app.integrations.web_search.provider import web_search


class WebSearchProviderTests(unittest.IsolatedAsyncioTestCase):
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
                'q', transport=httpx.MockTransport(lambda request: httpx.Response(500)),
            )
        self.assertEqual(items, [])
        self.assertTrue(warnings)

    async def test_provider_failure_and_fallback_completion_are_logged(self):
        records = []

        def record(_logger, _level, event, fields):
            records.append((event, fields))

        def handler(request):
            if request.url.host == 'api.tavily.com':
                raise httpx.ReadTimeout('timeout', request=request)
            return httpx.Response(200, json={'results': [{'title': 'Result', 'url': 'https://example.test'}]})

        with patch.dict('os.environ', {'TAVILY_API_KEY': 'test', 'SEARXNG_BASE_URL': 'https://search.test'}), \
             patch('agent_app.integrations.web_search.provider.log_event', side_effect=record):
            items, _warnings = await web_search('q', transport=httpx.MockTransport(handler))

        self.assertEqual(len(items), 1)
        self.assertEqual([event for event, _fields in records], [
            'web_search.provider_failed', 'web_search.completed',
        ])
        self.assertEqual(records[0][1]['provider'], 'tavily')
        self.assertEqual(records[1][1]['provider'], 'searxng')
