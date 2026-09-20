"""Deep Research Skill 资产与当前 Agent 产品组合的离线验收。"""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml

from app.main import app
from app.services.agent import StopReason, ToolCall
from app.services.agent import service as agent_service
from app.services.agent import workspace as agent_workspace
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.runtime import AgentRuntime
from app.services.agent.skills import default_store
from tests.test_agent import FakeProvider
from tests.test_agent_api import parse_sse


SKILL_DIR = Path(__file__).resolve().parents[1] / 'skills' / 'deep-research'
REQUIRED_TOOLS = {
    'paper_search', 'paper_detail', 'citation_graph', 'read_paper',
    'web_search', 'fetch_url', 'ask_user',
}
WORKSPACE_TOOLS = {'read_file', 'write_file', 'edit_file', 'run_command'}
OWNER_ID = '00000000-0000-4000-8000-000000000031'
OWNER = {'x-shenzhi-anonymous-id': OWNER_ID}


class DeepResearchAssetTests(unittest.TestCase):
    def test_store_frontmatter_and_references(self):
        store = default_store()
        skill = store.get('deep-research')
        self.assertIsNotNone(skill)
        self.assertTrue(skill.executable)
        raw = skill.path.read_text(encoding='utf-8')
        front = yaml.safe_load(raw.split('---', 2)[1])
        self.assertEqual(front['name'], 'deep-research')
        self.assertTrue(front['description'].strip())

        referenced = set(re.findall(r'references/[\w.-]+\.md', skill.body))
        self.assertEqual(referenced, {
            'references/citation-policy.md', 'references/endpoint-notes.md',
            'references/report-templates.md', 'references/venue-rankings.md',
            'references/source-quality.md', 'references/report-style.md',
        })
        for filename in referenced:
            with self.subTest(filename=filename):
                self.assertTrue((SKILL_DIR / filename).is_file())
                self.assertTrue(store.read_file('deep-research', filename))
        self.assertEqual(len(list((SKILL_DIR / 'references').glob('*.md'))), 6)

    def test_no_unneeded_code_or_legacy_dependencies(self):
        self.assertFalse((SKILL_DIR / 'tools.py').exists())
        self.assertFalse((SKILL_DIR / 'scripts').exists())
        content = '\n'.join(path.read_text(encoding='utf-8')
                            for path in SKILL_DIR.rglob('*.md'))
        for stale in ('/search/explore', 'services/retrieval.py',
                      'RETRIEVAL_API_URL', 'SZDR_BASE_URL', '/api/retrieval/',
                      'deep-reading skill', 'academic-search skill', 'paper-triage skill'):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, content)
        self.assertIn('## 参考来源', content)


class DeepResearchRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
            'DASHSCOPE_API_KEY': '', 'SKILLS_VENDOR': '',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_forced_and_plain_runtime(self):
        forced = agent_service.build_run_runtime(owner=f'anon:{OWNER_ID}',
                                                  forced_skills=['deep-research'])
        self.assertTrue(REQUIRED_TOOLS <= set(forced.registry.tools))
        self.assertIn('工作单元：证据槽', forced.system)
        self.assertIn('## 参考来源', forced.system)

        plain = agent_service.build_run_runtime(owner=f'anon:{OWNER_ID}')
        self.assertTrue(REQUIRED_TOOLS <= set(plain.registry.tools))
        self.assertIn('<available_skills>', plain.system)
        self.assertNotIn('工作单元：证据槽', plain.system)

    def test_workspace_tools_are_available(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)):
            runtime = agent_service.build_run_runtime(
                owner=f'anon:{OWNER_ID}', forced_skills=['deep-research'],
                session_id='dr_skill_tools')
            self.assertTrue(REQUIRED_TOOLS | WORKSPACE_TOOLS <= set(runtime.registry.tools))


class DeepResearchApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
            'DASHSCOPE_API_KEY': '', 'BACKEND_BFF_SECRET': '',
            'BACKEND_ALLOW_INSECURE_LOCAL_BFF': 'true', 'SKILLS_VENDOR': '',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    async def request(self, method, url, **kwargs):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://test') as client:
            return await client.request(method, url, headers=OWNER, **kwargs)

    async def test_config_lists_skill(self):
        response = await self.request('GET', '/api/v1/agent/config')
        self.assertEqual(response.status_code, 200)
        skills = response.json()['data']['skills']
        entry = next(item for item in skills if item['name'] == 'deep-research')
        self.assertTrue(entry['description'])

    async def test_forced_run_writes_report_and_returns_it(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'write_file', {
                'path': 'report.md', 'content': '# 报告\n\n离线验收。\n',
            })), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('报告已写入 report.md'), Finish(StopReason.STOP)],
        ])
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)), \
                patch.object(agent_service, 'default_runtime',
                             side_effect=lambda **kwargs: AgentRuntime(provider=provider, **kwargs)):
            response = await self.request('POST', '/api/v1/agent/run', json={
                'prompt': '生成一份测试报告', 'skills': ['deep-research'],
                'session_id': 'dr_skill_report',
            })
            self.assertEqual(response.status_code, 200)
            events = parse_sse(response.text)
            self.assertIn('tool_call', [name for name, _ in events])
            self.assertIn('tool_end', [name for name, _ in events])
            result = events[-1][1]
            self.assertEqual(result['status'], 'done')
            self.assertEqual(result['output']['report_path'], 'report.md')
            self.assertEqual(result['output']['report'], '# 报告\n\n离线验收。\n')
            self.assertIn('工作单元：证据槽', str(provider.requests[0].messages))
            report = agent_service.read_session_file(
                f'anon:{OWNER_ID}', 'dr_skill_report', 'report.md')[0]
            self.assertEqual(report.decode(), result['output']['report'])

    async def test_forced_run_can_ask_user(self):
        provider = FakeProvider([[
            ToolCallEvent(ToolCall('c1', 'ask_user', {
                'question': '研究哪个时间段？',
                'options': [{'value': '最近五年'}, {'value': '全部历史'}],
            })), Finish(StopReason.TOOL_CALLS),
        ]])
        with patch.object(agent_service, 'default_runtime',
                          side_effect=lambda **kwargs: AgentRuntime(provider=provider, **kwargs)):
            response = await self.request('POST', '/api/v1/agent/run', json={
                'prompt': '研究这个领域', 'skills': ['deep-research'],
            })
        self.assertEqual(response.status_code, 200)
        result = parse_sse(response.text)[-1][1]
        self.assertEqual(result['status'], 'awaiting_input')
        self.assertEqual(result['output']['kind'], 'question')
        self.assertEqual(result['output']['question'], '研究哪个时间段？')


if __name__ == '__main__':
    unittest.main()
