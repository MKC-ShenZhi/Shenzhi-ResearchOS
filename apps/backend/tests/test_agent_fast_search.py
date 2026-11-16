"""首页智能搜索的模式隔离与预算回归。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.agent import service, workspace
from app.services.agent.policies import run_deadline_s, tool_call_budget


class FastSearchRuntimeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {
            'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
            'DASHSCOPE_API_KEY': '', 'SKILLS_VENDOR': '',
        })
        env.start()
        self.addCleanup(env.stop)

    def test_fast_tools_and_prompt(self):
        runtime = service.build_run_runtime(owner='u1', mode='fast')
        names = set(runtime.registry.tools)
        self.assertTrue({'paper_search', 'paper_detail', 'read_paper',
                         'fetch_url', 'web_search'} <= names)
        self.assertFalse({'citation_graph', 'ask_user', 'read_skill',
                          'draw_chart', 'image_search'} & names)
        self.assertNotIn('available_skills', runtime.system)
        self.assertIn('智能搜索」快速模式', runtime.system)
        self.assertIn('本轮工具调用预算：12 次', runtime.system)
        self.assertEqual(runtime.deadline_s, 180)
        self.assertEqual(runtime.max_tool_calls, 12)
        default = service.build_run_runtime(owner='u1')
        self.assertEqual(set(default.registry.tools), names)

    def test_other_modes_keep_full_tools_and_budget(self):
        for mode in ('deep', 'idea', 'doubt'):
            with self.subTest(mode=mode):
                runtime = service.build_run_runtime(owner='u1', mode=mode)
                self.assertTrue({'ask_user', 'citation_graph', 'read_skill'}
                                <= set(runtime.registry.tools))
                self.assertIn('available_skills', runtime.system)
                self.assertNotIn('智能搜索」快速模式', runtime.system)
                self.assertEqual(runtime.deadline_s, 900)
                self.assertEqual(runtime.max_tool_calls, 120)
                self.assertIn('本轮工具调用预算：120 次', runtime.system)

    def test_fast_with_explicit_skill_keeps_full_tools(self):
        runtime = service.build_run_runtime(owner='u1', mode='fast',
                                            forced_skills=['deep-research'])
        self.assertTrue({'ask_user', 'citation_graph', 'read_skill'}
                        <= set(runtime.registry.tools))
        self.assertIn('用户显式选择了技能「deep-research」', runtime.system)
        self.assertNotIn('智能搜索」快速模式', runtime.system)

    def test_workspace_tools_stay_available_but_heavy_tools_are_mode_specific(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
            for mode, skills, heavy in (('fast', (), False), ('deep', (), True),
                                        ('fast', ['deep-research'], True)):
                with self.subTest(mode=mode, skills=skills):
                    runtime = service.build_run_runtime(
                        owner='u1', mode=mode, forced_skills=skills, session_id='fast_tools')
                    names = set(runtime.registry.tools)
                    self.assertTrue({'read_file', 'write_file', 'edit_file', 'run_command'} <= names)
                    for name in ('draw_chart', 'image_search'):
                        self.assertEqual(name in names, heavy)
                    self.assertIsNotNone(runtime.after_tool_call)

    def test_mode_budgets(self):
        self.assertEqual(run_deadline_s('fast'), 180)
        self.assertEqual(tool_call_budget('fast'), 12)
        for mode in ('deep', 'idea', 'doubt'):
            with self.subTest(mode=mode):
                self.assertEqual(run_deadline_s(mode), 900)
                self.assertEqual(tool_call_budget(mode), 120)
