"""Deep Research Skill 资产与当前 Agent 产品组合的离线验收。"""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from agent_app import StopReason, ToolCall
from agent_app import service as agent_service
from agent_app import workspace as agent_workspace
from agent_app.integrations.llm.agent_stream import Finish, TextDelta, ToolCallEvent
from agent_app.execution.runtime import AgentRuntime
from agent_app.extensions.skills import default_store
from tests.unit.test_agent import FakeProvider


SKILL_DIR = Path(__file__).resolve().parents[2] / 'skills' / 'deep-research'
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

        plain = agent_service.build_run_runtime(owner=f'anon:{OWNER_ID}', mode='deep')
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



if __name__ == '__main__':
    unittest.main()
