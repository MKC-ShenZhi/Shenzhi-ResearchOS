"""Agent HTTP 入口测试：SSE 事件流、history 校验、参数校验、BFF 鉴权。"""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.main import app
from app.services.agent import AgentRuntime
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.types import StopReason, ToolCall
from tests.test_agent import FakeProvider, make_echo


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split('\n\n'):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith('event: '):
                name = line[7:]
            elif line.startswith('data: '):
                data = json.loads(line[6:])
        if name is not None:
            events.append((name, data))
    return events


class AgentApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat', 'DASHSCOPE_API_KEY': '',
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true'})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    OWNER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}

    async def post(self, payload):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            return await client.post('/api/v1/agent/run', json=payload, headers=self.OWNER)

    async def test_run_streams_events_and_result(self):
        runtime = AgentRuntime(provider=FakeProvider(
            [[TextDelta('你'), TextDelta('好'), Finish(StopReason.STOP)]]))
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.post({'prompt': '打个招呼'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/event-stream', response.headers['content-type'])
        events = parse_sse(response.text)
        names = [name for name, _ in events]
        self.assertEqual(names[-1], 'result')
        self.assertEqual(names[0], 'run_start')
        result = events[-1][1]
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['final_text'], '你好')

    async def test_tool_round_trip_over_http(self):
        runtime = AgentRuntime(provider=FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('完成'), Finish(StopReason.STOP)],
        ]), tools=[make_echo()])
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.post({'prompt': '调用 echo'})
        events = parse_sse(response.text)
        self.assertIn('tool_call', [name for name, _ in events])
        self.assertIn('tool_end', [name for name, _ in events])
        self.assertEqual(events[-1][1]['final_text'], '完成')

    async def test_history_roundtrip_accepted(self):
        history = [{'kind': 'user', 'text': '上一问'},
                   {'kind': 'assistant', 'content': '上一答', 'reasoning': '',
                    'tool_calls': [], 'stop_reason': 'stop'}]
        runtime = AgentRuntime(provider=FakeProvider([[TextDelta('好'), Finish(StopReason.STOP)]]))
        with patch('app.services.agent.service.default_runtime', return_value=runtime):
            response = await self.post({'prompt': '继续', 'history': history})
        events = parse_sse(response.text)
        self.assertEqual(events[-1][1]['status'], 'done')

    async def test_invalid_history_rejected(self):
        response = await self.post({'prompt': 'x', 'history': [{'kind': 'bogus'}]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 20001)

    async def test_session_file_endpoint(self):
        from app.services.agent import service
        from app.services.agent import workspace
        # request_owner 返回 'anon:<uuid>'，产物目录按此 owner 哈希——写入须用同一格式
        owner = f"anon:{self.OWNER_ID}"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                root = service.ensure_session_workspace(owner, 'ses_file1')
                (root / 'rag_review.md').write_text('# 报告\n正文', encoding='utf-8')
                (root / 'data.bin').write_bytes(b'\x00\x01\xff')

                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url='http://test') as client:
                    inline = await client.get('/api/v1/agent/session/ses_file1/file',
                                              params={'path': 'rag_review.md'}, headers=self.OWNER)
                    self.assertEqual(inline.status_code, 200)
                    self.assertEqual(inline.headers['content-type'].split(';')[0], 'text/markdown')
                    self.assertIn('inline', inline.headers['content-disposition'])
                    self.assertIn('报告', inline.text)

                    download = await client.get('/api/v1/agent/session/ses_file1/file',
                                                params={'path': 'rag_review.md', 'download': 'true'},
                                                headers=self.OWNER)
                    self.assertIn('attachment', download.headers['content-disposition'])

                    # 二进制内容按 octet-stream 交付
                    binary = await client.get('/api/v1/agent/session/ses_file1/file',
                                              params={'path': 'data.bin'}, headers=self.OWNER)
                    self.assertEqual(binary.headers['content-type'].split(';')[0],
                                     'application/octet-stream')

                    # 路径禁闭与不存在
                    escape = await client.get('/api/v1/agent/session/ses_file1/file',
                                              params={'path': '../x.md'}, headers=self.OWNER)
                    self.assertEqual(escape.status_code, 400)
                    missing = await client.get('/api/v1/agent/session/ses_file1/file',
                                               params={'path': 'nope.md'}, headers=self.OWNER)
                    self.assertEqual(missing.status_code, 404)

                    # 越权 owner：owner 不同 → 目录不同 → 404
                    other = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
                    forbidden = await client.get('/api/v1/agent/session/ses_file1/file',
                                                 params={'path': 'rag_review.md'}, headers=other)
                    self.assertEqual(forbidden.status_code, 404)

    OWNER_ID = '00000000-0000-4000-8000-000000000001'

    # 真实 1x1 RGBA PNG 字节（IHDR/IDAT/IEND + CRC 齐全，非占位文本）：报告图产物直出用
    PNG_1X1 = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=')

    def asset_workspace(self, session_id: str):
        """建真实临时工作区并种入嵌套图片产物，返回该会话的工作区根（清理挂到 addCleanup）。"""
        from app.services.agent import service
        from app.services.agent import workspace
        tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(tmp.cleanup)
        root = service.ensure_session_workspace(f'anon:{self.OWNER_ID}', session_id)
        (root / 'figures').mkdir(exist_ok=True)
        (root / 'figures' / 'chart-1.png').write_bytes(self.PNG_1X1)
        return root

    async def test_session_asset_serves_png_with_cache_header(self):
        self.assertTrue(self.PNG_1X1.startswith(b'\x89PNG\r\n\x1a\n'))  # 常量损坏时立刻失败
        self.asset_workspace('ses_asset1')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            # 嵌套相对路径必须命中（:path 转换器）
            response = await client.get('/api/v1/agent/assets/ses_asset1/figures/chart-1.png',
                                        headers=self.OWNER)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'].split(';')[0], 'image/png')
            self.assertEqual(response.headers['cache-control'], 'private, max-age=300')
            self.assertIn('inline', response.headers['content-disposition'])
            self.assertEqual(response.content, self.PNG_1X1)

    async def test_session_asset_rejects_escape_and_missing(self):
        self.asset_workspace('ses_asset2')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            # 逃逸：带 %2F/%2e 的形式把真实的 ".." 送进路径参数，必须由 Workspace.resolve 挡住
            for escape_path in ['..%2F..%2Fetc%2Fpasswd', '%2e%2e/%2e%2e/etc/passwd']:
                with self.subTest(path=escape_path):
                    escape = await client.get(f'/api/v1/agent/assets/ses_asset2/{escape_path}',
                                              headers=self.OWNER)
                    self.assertEqual(escape.status_code, 400)
                    self.assertEqual(escape.json()['code'], 20004)   # 路径超出工作区边界
            # 裸 ".." 会被 HTTP 客户端先归一掉（请求没到路由）——底线是任何形式都不得 200
            normalized = await client.get('/api/v1/agent/assets/ses_asset2/../../etc/passwd',
                                          headers=self.OWNER)
            self.assertNotEqual(normalized.status_code, 200)
            missing = await client.get('/api/v1/agent/assets/ses_asset2/figures/nope.png',
                                       headers=self.OWNER)
            self.assertEqual(missing.status_code, 404)

    async def test_session_asset_owner_isolation(self):
        self.asset_workspace('ses_asset3')
        other = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            # owner 不同 → 哈希目录不同 → 同一 session_id 也 404
            forbidden = await client.get('/api/v1/agent/assets/ses_asset3/figures/chart-1.png',
                                         headers=other)
            self.assertEqual(forbidden.status_code, 404)

    async def test_session_asset_svg_is_inline_but_csp_hardened(self):
        root = self.asset_workspace('ses_asset4')
        (root / 'figures' / 'plot.svg').write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            encoding='utf-8')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            response = await client.get('/api/v1/agent/assets/ses_asset4/figures/plot.svg',
                                        headers=self.OWNER)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'].split(';')[0], 'image/svg+xml')
            self.assertIn('inline', response.headers['content-disposition'])
            # inline SVG 是活动内容：必须带关掉脚本/外链的 CSP
            self.assertEqual(response.headers['content-security-policy'],
                             "default-src 'none'; style-src 'unsafe-inline'")

    async def test_session_export_html_and_jsonl(self):
        messages = [
            {'kind': 'user', 'text': '什么是 RAG'},
            {'kind': 'assistant', 'content': 'RAG 是检索增强生成', 'reasoning': '',
             'tool_calls': [{'id': 'c1', 'name': 'paper_search', 'arguments': '{}'}],
             'stop_reason': 'stop'},
        ]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            html_res = await client.post('/api/v1/agent/session/export',
                                         json={'title': 'RAG 会话', 'messages': messages,
                                               'format': 'html'}, headers=self.OWNER)
            self.assertEqual(html_res.status_code, 200)
            self.assertIn('text/html', html_res.headers['content-type'])
            self.assertIn('attachment', html_res.headers['content-disposition'])
            self.assertIn('RAG 是检索增强生成', html_res.text)
            self.assertIn('paper_search', html_res.text)       # 工具调用进报告

            jsonl_res = await client.post('/api/v1/agent/session/export',
                                          json={'title': 't', 'messages': messages,
                                                'format': 'jsonl'}, headers=self.OWNER)
            self.assertIn('application/jsonl', jsonl_res.headers['content-type'])
            lines = jsonl_res.text.strip().split('\n')
            self.assertEqual(len(lines), 2)                    # 一行一消息
            self.assertEqual(json.loads(lines[0])['kind'], 'user')

    async def test_blank_prompt_rejected(self):
        response = await self.post({'prompt': ''})
        self.assertEqual(response.status_code, 422)

    async def test_steer_endpoint_and_config(self):
        # config 返回技能清单（模板机制已删，prompts/* 不再存在）
        config_response = await self.client_get('/api/v1/agent/config')
        self.assertEqual(config_response.status_code, 200)
        self.assertIsInstance(config_response.json()['data']['skills'], list)

        # 不存在的 run → 404
        response = await self.client_post_json(
            '/api/v1/agent/run/deadbeef/steer', {'text': '插话'})
        self.assertEqual(response.status_code, 404)

    async def client_get(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(url, headers=self.OWNER)

    async def client_post_json(self, url: str, payload: dict) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.post(url, json=payload, headers=self.OWNER)


if __name__ == '__main__':
    unittest.main()
