"""Agent HTTP 入口测试：SSE 事件流、history 校验、参数校验、BFF 鉴权。"""
import base64
import json
import unittest
from unittest.mock import patch

import httpx

from app.main import app
from app.core.errors import BusinessError
from app.services.agent_sessions.entities import AgentSession
from app.services.agent_sessions.repository import MemoryAgentSessionRepository


class FakeAgentGateway:
    def __init__(self):
        self.events_data = []
        self.result = {'status': 'completed', 'result': {
            'stop_reason': 'stop', 'final_text': '你好', 'output': None,
            'turns': 1, 'duration_ms': 5, 'prompt_tokens': 1,
            'completion_tokens': 1, 'truncated': False,
        }}
        self.submissions = []
        self.files = {}

    async def submit(self, payload):
        self.submissions.append(payload)
        return {'task_id': 'task-1', 'current_run_id': 'run-1'}

    async def events(self, run_id, owner, after_seq):
        return [item for item in self.events_data if item['seq'] > after_seq]

    async def run(self, run_id, owner):
        return {'report': self.result}

    async def task(self, task_id, owner):
        return {'current_run_id': 'run-1'}

    async def config(self):
        return {'models': [], 'default_model': None, 'skills': []}

    async def steer(self, run_id, owner, text):
        raise BusinessError(20004, '运行不存在', 404)

    async def read_session_file(self, owner, session_id, path):
        if '..' in path.replace('\\', '/').split('/'):
            raise BusinessError(20004, '路径超出工作区边界', 400)
        item = self.files.get((session_id, path))
        if item is None:
            raise BusinessError(20004, '文件不存在', 404)
        return item


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
            'BACKEND_BFF_SECRET': '', 'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true',
            # 本地 .env 配了数据库时也固定走内存存储，避免连到开发库
            'CHAT_DATABASE_URL': ''})
        self.env.start()
        self.repo = MemoryAgentSessionRepository()
        self.gateway = FakeAgentGateway()
        self.api_repo = patch('app.api.agent.agent_session_repository', self.repo)
        self.gateway_patch = patch('app.api.agent.agent_gateway', self.gateway)
        self.api_repo.start()
        self.gateway_patch.start()

    def tearDown(self):
        self.gateway_patch.stop()
        self.api_repo.stop()
        self.env.stop()

    OWNER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}

    async def post(self, payload):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            return await client.post('/api/v1/agent/run', json=payload, headers=self.OWNER)

    async def test_run_streams_events_and_result(self):
        self.gateway.events_data = [{'seq': 1, 'name': 'delta', 'data': {'text': '你好'}}]
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
        self.gateway.events_data = [
            {'seq': 1, 'name': 'tool_call', 'data': {'name': 'echo'}},
            {'seq': 2, 'name': 'tool_end', 'data': {'name': 'echo'}},
        ]
        self.gateway.result['result']['final_text'] = '完成'
        response = await self.post({'prompt': '调用 echo'})
        events = parse_sse(response.text)
        self.assertIn('tool_call', [name for name, _ in events])
        self.assertIn('tool_end', [name for name, _ in events])
        self.assertEqual(events[-1][1]['final_text'], '完成')

    async def test_history_roundtrip_accepted(self):
        history = [{'kind': 'user', 'text': '上一问'},
                   {'kind': 'assistant', 'content': '上一答', 'reasoning': '',
                    'tool_calls': [], 'stop_reason': 'stop'}]
        response = await self.post({'prompt': '继续', 'history': history})
        events = parse_sse(response.text)
        self.assertEqual(events[-1][1]['status'], 'done')
        self.assertEqual(self.gateway.submissions[0]['history'], history)

    async def test_invalid_history_rejected(self):
        response = await self.post({'prompt': 'x', 'history': [{'kind': 'bogus'}]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 20001)

    async def test_session_file_endpoint(self):
        owner = f"anon:{self.OWNER_ID}"
        self.repo.sessions['ses_file1'] = AgentSession(
            id='ses_file1', owner=owner, title='文件测试会话',
        )
        self.gateway.files[('ses_file1', 'rag_review.md')] = ('# 报告\n正文'.encode(), 'text/markdown')
        self.gateway.files[('ses_file1', 'data.bin')] = (b'\x00\x01\xff', 'application/octet-stream')
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
            binary = await client.get('/api/v1/agent/session/ses_file1/file',
                                      params={'path': 'data.bin'}, headers=self.OWNER)
            self.assertEqual(binary.headers['content-type'].split(';')[0],
                             'application/octet-stream')
            escape = await client.get('/api/v1/agent/session/ses_file1/file',
                                      params={'path': '../x.md'}, headers=self.OWNER)
            self.assertEqual(escape.status_code, 400)
            missing = await client.get('/api/v1/agent/session/ses_file1/file',
                                       params={'path': 'nope.md'}, headers=self.OWNER)
            self.assertEqual(missing.status_code, 404)
            other = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
            forbidden = await client.get('/api/v1/agent/session/ses_file1/file',
                                         params={'path': 'rag_review.md'}, headers=other)
            self.assertEqual(forbidden.status_code, 404)
            deleted = await client.delete('/api/v1/agent/sessions/ses_file1', headers=self.OWNER)
            self.assertEqual(deleted.status_code, 200)
            after_delete = await client.get('/api/v1/agent/session/ses_file1/file',
                                            params={'path': 'rag_review.md'}, headers=self.OWNER)
            self.assertEqual(after_delete.status_code, 404)

    OWNER_ID = '00000000-0000-4000-8000-000000000001'

    # 真实 1x1 RGBA PNG 字节（IHDR/IDAT/IEND + CRC 齐全，非占位文本）：报告图产物直出用
    PNG_1X1 = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=')

    def asset_workspace(self, session_id: str):
        """Seed Agent Gateway artifact responses for product API forwarding checks."""
        owner = f'anon:{self.OWNER_ID}'
        self.repo.sessions[session_id] = AgentSession(
            id=session_id, owner=owner, title='资源测试会话',
        )
        self.gateway.files[(session_id, 'figures/chart-1.png')] = (self.PNG_1X1, 'image/png')

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
            self.assertEqual(response.headers['cache-control'], 'private, no-store')
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
            normalized = await client.get('/api/v1/agent/assets/ses_asset2/..%2F..%2Fetc%2Fpasswd',
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
        self.asset_workspace('ses_asset4')
        self.gateway.files[('ses_asset4', 'figures/plot.svg')] = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            'image/svg+xml')
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
