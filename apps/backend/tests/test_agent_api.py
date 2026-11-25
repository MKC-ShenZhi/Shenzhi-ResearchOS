"""Agent HTTP 入口测试：SSE 事件流、history 校验、参数校验、BFF 鉴权。"""
import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
        self.client_request_digests = []

    async def submit(self, payload, *, client_request_digest=None):
        self.submissions.append(payload)
        self.client_request_digests.append(client_request_digest)
        return {'task_id': 'task-1', 'current_run_id': 'run-1'}

    async def events(self, run_id, owner, after_seq):
        return [item for item in self.events_data if item['seq'] > after_seq]

    async def run(self, run_id, owner):
        return {'report': self.result}

    async def task(self, task_id, owner):
        return {'current_run_id': 'run-1'}

    async def usage(self, task_id, owner):
        return {'turns': 1, 'duration_ms': 5, 'truncated': False}

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
        self._post_number = 0
        self.gateway = FakeAgentGateway()
        self.api_repo = patch('app.api.agent.agent_session_repository', self.repo)
        # New product tasks always use the unified V2 boundary. Tests substitute
        # the same deterministic fake so existing SSE assertions stay valid.
        self.v2_patch = patch('app.services.agent_gateway.v2.AgentGatewayV2',
                              return_value=self.gateway)
        self.api_repo.start()
        self.v2_patch.start()

    def tearDown(self):
        self.v2_patch.stop()
        self.api_repo.stop()
        self.env.stop()

    OWNER = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000001'}

    async def post(self, payload, headers=None, *, include_idempotency=True):
        self._post_number += 1
        request_headers = {**self.OWNER, **(headers or {})}
        if include_idempotency and 'Idempotency-Key' not in request_headers:
            request_headers['Idempotency-Key'] = f'api-test-{self._post_number}'
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            return await client.post('/api/v2/agent/run', json=payload,
                                     headers=request_headers)

    async def test_v1_product_routes_are_not_registered(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            old = await client.get('/api/v1/agent/config', headers=self.OWNER)
            current = await client.get('/api/v2/agent/config', headers=self.OWNER)
        self.assertEqual(old.status_code, 404)
        self.assertEqual(current.status_code, 200)

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

    async def test_authorized_product_entry_uses_v2_without_fallback(self):
        from app.services.agent_entitlements.service import EntitlementError
        v2 = FakeAgentGateway()
        with patch.dict('os.environ', {'AGENT_V2_ADMISSION': 'authorized'}), \
             patch('app.services.agent_gateway.v2.AgentGatewayV2', return_value=v2):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test',
                headers={'x-shenzhi-user-id': 'registered', 'Idempotency-Key': 'stable-key'}) as browser:
                response = await browser.post('/api/v2/agent/run', json={'prompt': 'hello', 'model': 'test/m1'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(parse_sse(response.text)[-1][1]['final_text'], '你好')
                self.assertEqual(v2.submissions[0]['idempotency_key'], 'stable-key')
                self.assertEqual(v2.submissions[0]['owner_id'], 'user:registered')
                self.assertEqual(len(self.gateway.submissions), 0)
                v2.submit = AsyncMock(side_effect=EntitlementError('QUOTA_EXHAUSTED', 403))
                denied = await browser.post('/api/v2/agent/run', json={'prompt': 'hello', 'model': 'test/m1'})
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(denied.json()['message'], 'QUOTA_EXHAUSTED')
                self.assertEqual(len(self.gateway.submissions), 0)

    async def test_anonymous_new_task_uses_v2_gateway(self):
        v2 = FakeAgentGateway()
        v2.events_data = [{'seq': 1, 'name': 'delta', 'data': {'text': '你好'}}]
        with patch('app.services.agent_gateway.v2.AgentGatewayV2', return_value=v2):
            response = await self.post({'prompt': '匿名任务'},
                                       headers={'Idempotency-Key': 'anon-v2-key'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(parse_sse(response.text)[-1][1]['final_text'], '你好')
        self.assertEqual(v2.submissions[0]['owner_id'],
                         'anon:00000000-0000-4000-8000-000000000001')
        self.assertEqual(v2.submissions[0]['idempotency_key'], 'anon-v2-key')
        self.assertTrue(v2.client_request_digests[0].startswith('sha256:'))
        # The V1 boundary must not receive new submissions.
        self.assertEqual(self.gateway.submissions, [])

    async def test_anonymous_new_task_requires_idempotency_key(self):
        v2 = FakeAgentGateway()
        with patch('app.services.agent_gateway.v2.AgentGatewayV2', return_value=v2):
            response = await self.post({'prompt': '缺少幂等键'}, include_idempotency=False)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(v2.submissions, [])

    async def test_stateless_retry_recovers_before_resolving_expired_attachment(self):
        from app.api.agent import _client_request_digest
        from app.schemas.agent import AgentRunBody

        body = {'prompt': '带附件任务', 'attachments': [{'kind': 'file', 'file_id': 'expired-slot'}]}
        digest_value = _client_request_digest(AgentRunBody.model_validate(body))
        stored = SimpleNamespace(client_request_digest=digest_value)
        db = unittest.mock.MagicMock()
        db.scalar = AsyncMock(return_value=stored)
        scope = unittest.mock.MagicMock()
        scope.return_value.__aenter__ = AsyncMock(return_value=db)
        scope.return_value.__aexit__ = AsyncMock(return_value=False)
        self.gateway.recover_submission = AsyncMock(return_value={
            'task_id': 'task-1', 'current_run_id': 'run-1',
        })
        attachment_resolver = AsyncMock(side_effect=AssertionError('expired upload must not be resolved'))
        with patch('app.core.database.database_url', return_value='postgresql://test'), \
             patch('app.core.database.session_scope', scope), \
             patch('app.api.agent.resolve_agent_attachments', attachment_resolver):
            response = await self.post(body, headers={'Idempotency-Key': 'retry-with-expired-file'})
            conflict = await self.post(
                {**body, 'prompt': '不同请求'},
                headers={'Idempotency-Key': 'retry-with-expired-file'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(parse_sse(response.text)[-1][1]['final_text'], '你好')
        self.gateway.recover_submission.assert_awaited_once_with(
            'anon:00000000-0000-4000-8000-000000000001', 'retry-with-expired-file')
        self.assertEqual(conflict.status_code, 409)
        attachment_resolver.assert_not_awaited()
        self.assertEqual(self.gateway.submissions, [])

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
            inline = await client.get('/api/v2/agent/session/ses_file1/file',
                                      params={'path': 'rag_review.md'}, headers=self.OWNER)
            self.assertEqual(inline.status_code, 200)
            self.assertEqual(inline.headers['content-type'].split(';')[0], 'text/markdown')
            self.assertIn('inline', inline.headers['content-disposition'])
            self.assertIn('报告', inline.text)
            download = await client.get('/api/v2/agent/session/ses_file1/file',
                                        params={'path': 'rag_review.md', 'download': 'true'},
                                        headers=self.OWNER)
            self.assertIn('attachment', download.headers['content-disposition'])
            binary = await client.get('/api/v2/agent/session/ses_file1/file',
                                      params={'path': 'data.bin'}, headers=self.OWNER)
            self.assertEqual(binary.headers['content-type'].split(';')[0],
                             'application/octet-stream')
            escape = await client.get('/api/v2/agent/session/ses_file1/file',
                                      params={'path': '../x.md'}, headers=self.OWNER)
            self.assertEqual(escape.status_code, 400)
            missing = await client.get('/api/v2/agent/session/ses_file1/file',
                                       params={'path': 'nope.md'}, headers=self.OWNER)
            self.assertEqual(missing.status_code, 404)
            other = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
            forbidden = await client.get('/api/v2/agent/session/ses_file1/file',
                                         params={'path': 'rag_review.md'}, headers=other)
            self.assertEqual(forbidden.status_code, 404)
            deleted = await client.delete('/api/v2/agent/sessions/ses_file1', headers=self.OWNER)
            self.assertEqual(deleted.status_code, 200)
            after_delete = await client.get('/api/v2/agent/session/ses_file1/file',
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
            response = await client.get('/api/v2/agent/assets/ses_asset1/figures/chart-1.png',
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
                    escape = await client.get(f'/api/v2/agent/assets/ses_asset2/{escape_path}',
                                              headers=self.OWNER)
                    self.assertEqual(escape.status_code, 400)
                    self.assertEqual(escape.json()['code'], 20004)   # 路径超出工作区边界
            # 裸 ".." 会被 HTTP 客户端先归一掉（请求没到路由）——底线是任何形式都不得 200
            normalized = await client.get('/api/v2/agent/assets/ses_asset2/..%2F..%2Fetc%2Fpasswd',
                                          headers=self.OWNER)
            self.assertNotEqual(normalized.status_code, 200)
            missing = await client.get('/api/v2/agent/assets/ses_asset2/figures/nope.png',
                                       headers=self.OWNER)
            self.assertEqual(missing.status_code, 404)

    async def test_session_asset_owner_isolation(self):
        self.asset_workspace('ses_asset3')
        other = {'x-shenzhi-anonymous-id': '00000000-0000-4000-8000-000000000002'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            # owner 不同 → 哈希目录不同 → 同一 session_id 也 404
            forbidden = await client.get('/api/v2/agent/assets/ses_asset3/figures/chart-1.png',
                                         headers=other)
            self.assertEqual(forbidden.status_code, 404)

    async def test_session_asset_svg_is_inline_but_csp_hardened(self):
        self.asset_workspace('ses_asset4')
        self.gateway.files[('ses_asset4', 'figures/plot.svg')] = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            'image/svg+xml')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            response = await client.get('/api/v2/agent/assets/ses_asset4/figures/plot.svg',
                                        headers=self.OWNER)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'].split(';')[0], 'image/svg+xml')
            self.assertIn('inline', response.headers['content-disposition'])
            # inline SVG 是活动内容：必须带关掉脚本/外链的 CSP
            self.assertEqual(response.headers['content-security-policy'],
                             "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:")

    async def test_active_artifacts_are_sandboxed_on_both_file_routes(self):
        self.asset_workspace('ses_active')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            for filename, mime in [('page.html', 'text/html'), ('plot.svg', 'image/svg+xml')]:
                content = b'<script>fetch("/api/v2/agent/sessions")</script>'
                self.gateway.files[('ses_active', filename)] = (content, mime)
                for url, params in [
                    (f'/api/v2/agent/assets/ses_active/{filename}', {}),
                    ('/api/v2/agent/session/ses_active/file', {'path': filename}),
                    ('/api/v2/agent/session/ses_active/file', {'path': filename, 'download': 'true'}),
                ]:
                    response = await client.get(url, params=params, headers=self.OWNER)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, content)
                    policy = response.headers['content-security-policy'].split('; ')
                    self.assertIn('sandbox', policy)
                    self.assertIn("default-src 'none'", policy)

    async def test_session_export_html_and_jsonl(self):
        messages = [
            {'kind': 'user', 'text': '什么是 RAG'},
            {'kind': 'assistant', 'content': 'RAG 是检索增强生成', 'reasoning': '',
             'tool_calls': [{'id': 'c1', 'name': 'paper_search', 'arguments': '{}'}],
             'stop_reason': 'stop'},
        ]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            html_res = await client.post('/api/v2/agent/session/export',
                                         json={'title': 'RAG 会话', 'messages': messages,
                                               'format': 'html'}, headers=self.OWNER)
            self.assertEqual(html_res.status_code, 200)
            self.assertIn('text/html', html_res.headers['content-type'])
            self.assertIn('attachment', html_res.headers['content-disposition'])
            self.assertIn('RAG 是检索增强生成', html_res.text)
            self.assertIn('paper_search', html_res.text)       # 工具调用进报告

            jsonl_res = await client.post('/api/v2/agent/session/export',
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
        config_response = await self.client_get('/api/v2/agent/config')
        self.assertEqual(config_response.status_code, 200)
        self.assertIsInstance(config_response.json()['data']['skills'], list)

        # 不存在的 run → 404
        response = await self.client_post_json(
            '/api/v2/agent/run/deadbeef/steer', {'text': '插话'})
        self.assertEqual(response.status_code, 404)

    async def test_run_control_resolves_v2_binding_without_owner_switch(self):
        gateway = AsyncMock()
        gateway.token = 'gateway-token'
        gateway.run.return_value = {'task_id': 'task-1'}
        gateway.steer.return_value = {'stored': True}
        with patch('app.api.agent.submission_gateway', return_value=gateway):
            response = await self.client_post_json(
                '/api/v2/agent/run/run-1/steer', {'text': '聚焦结论'})
        self.assertEqual(response.status_code, 200)
        # Anonymous historical owners must not force a V1 control path.
        gateway.steer.assert_awaited_once_with(
            'run-1', 'anon:00000000-0000-4000-8000-000000000001', '聚焦结论')

    async def test_run_control_does_not_fallback_to_v1_when_v2_is_unavailable(self):
        gateway = AsyncMock()
        gateway.run.side_effect = BusinessError(20004, 'Agent 服务凭据未配置', 503)
        with patch('app.api.agent.submission_gateway', return_value=gateway):
            response = await self.client_post_json(
                '/api/v2/agent/run/run-1/stop', {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.gateway.result['status'], 'completed')

    async def test_v2_session_artifact_uses_shared_service_gateway(self):
        session_id = 'ses_v2_file'
        owner = f"anon:{self.OWNER['x-shenzhi-anonymous-id']}"
        self.gateway.read_session_file = AsyncMock()
        session = AgentSession(id=session_id, owner=owner, title='V2 文件')
        from app.services.agent_sessions.entities import AgentTurn
        session.turns.append(AgentTurn(
            id='turn-v2-file', session_id=session_id, user_content='图表',
            settings={'_agent_protocol': 2},
            status='done',
        ))
        self.repo.sessions[session_id] = session
        v2 = AsyncMock()
        v2.read_session_file.return_value = (b'v2 artifact', 'text/plain')
        with patch('app.api.agent.submission_gateway', return_value=v2):
            response = await self.client_get(
                f'/api/v2/agent/session/{session_id}/file?path=report.txt')
            asset = await self.client_get(
                f'/api/v2/agent/assets/{session_id}/report.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'v2 artifact')
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.content, b'v2 artifact')
        self.assertEqual(v2.read_session_file.await_count, 2)
        v2.read_session_file.assert_awaited_with(owner, session_id, 'report.txt')
        self.gateway.read_session_file.assert_not_awaited()

    async def client_get(self, url: str) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(url, headers=self.OWNER)

    async def client_post_json(self, url: str, payload: dict) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.post(url, json=payload, headers=self.OWNER)


if __name__ == '__main__':
    unittest.main()
