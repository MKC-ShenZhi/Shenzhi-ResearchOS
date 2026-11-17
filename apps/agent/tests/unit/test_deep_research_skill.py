"""Deep Research Skill 资产与当前 Agent 产品组合的离线验收。"""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import yaml
from agent_contracts import ReportIngestWire

from agent_app import StopReason, ToolCall
from agent_app import service as agent_service
from agent_app import workspace as agent_workspace
from agent_app.application.composition import build_runtime
from agent_app.execution.runtime import AgentRuntime
from agent_app.execution.types import AssistantMessage, RunResult, ToolResultMessage
from agent_app.extensions.skills import default_store
from agent_app.integrations.llm.agent_stream import Finish, TextDelta, ToolCallEvent
from agent_app.main import app
from agent_app.worker import host
from tests.unit.test_agent import FakeProvider


SKILL_DIR = Path(__file__).resolve().parents[2] / 'skills' / 'deep-research'
REQUIRED_TOOLS = {
    'paper_search', 'paper_detail', 'citation_graph', 'read_paper',
    'web_search', 'fetch_url', 'ask_user',
}
WORKSPACE_TOOLS = {'read_file', 'write_file', 'edit_file', 'run_command'}
OWNER_ID = '00000000-0000-4000-8000-000000000031'


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


class DeepResearchServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_lists_skill(self):
        with patch.dict('os.environ', {'AGENT_SERVICE_TOKEN': 'test-token'}, clear=True):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url='http://test',
                headers={'Authorization': 'Bearer test-token'},
            ) as client:
                response = await client.get('/internal/v1/config')
        self.assertEqual(response.status_code, 200)
        skill = next(item for item in response.json()['skills'] if item['name'] == 'deep-research')
        self.assertTrue(skill['description'])

    async def execute_with_provider(self, provider, **session_options):
        control = AsyncMock(spec=host.AgentControlClient)
        control.get.return_value = {'controls': []}
        claim = {'lease_token': 1, 'run': {
            'run_id': 'run-1', 'task_id': 'task-1', 'owner_id': f'anon:{OWNER_ID}',
            'prompt': '研究这个领域', 'skills': ['deep-research'], **session_options,
        }}

        def build_with_fake_provider(**kwargs):
            return build_runtime(
                runtime_factory=lambda **options: AgentRuntime(provider=provider, **options),
                **kwargs,
            )

        with patch.dict('os.environ', {'SKILLS_VENDOR': ''}, clear=True), \
                patch.object(host, 'build_runtime', side_effect=build_with_fake_provider):
            await host.execute_claim(control, claim, 'worker-1')
        return control

    async def test_forced_run_writes_report_and_returns_it(self):
        markdown = '# 报告\n\n离线验收。\n'
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'write_file', {
                'path': 'report.md', 'content': markdown,
            })), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('报告已写入 report.md'), Finish(StopReason.STOP)],
        ])
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)):
            control = await self.execute_with_provider(provider, session_id='dr_skill_report')
            content, _ = agent_workspace.read_session_file(
                f'anon:{OWNER_ID}', 'dr_skill_report', 'report.md',
            )

        posted = control.post.await_args_list
        events = [item.args[1]['name'] for item in posted if item.args[0].endswith('/events')]
        self.assertIn('tool_call', events)
        self.assertIn('tool_end', events)
        path, payload = posted[-1].args
        self.assertEqual(path, '/internal/v1/runs/run-1/report')
        report = ReportIngestWire.model_validate(payload)
        self.assertEqual(report.status.value, 'completed')
        output = report.result['output']
        self.assertEqual(output['kind'], 'report')
        self.assertEqual(output['report_path'], 'report.md')
        self.assertEqual(output['report'].replace('\r\n', '\n'), markdown)
        self.assertEqual(output['report'], content.decode('utf-8'))
        self.assertIn('工作单元：证据槽', str(provider.requests[0].messages))

    async def test_forced_run_can_ask_user(self):
        provider = FakeProvider([[
            ToolCallEvent(ToolCall('c1', 'ask_user', {
                'question': '研究哪个时间段？',
                'options': [{'value': '最近五年'}, {'value': '全部历史'}],
            })), Finish(StopReason.TOOL_CALLS),
        ]])
        control = await self.execute_with_provider(provider)
        path, report = control.post.await_args.args
        self.assertEqual(path, '/internal/v1/runs/run-1/report')
        self.assertEqual(report['status'], 'awaiting_input')
        self.assertEqual(report['result']['output']['kind'], 'question')
        self.assertEqual(report['result']['output']['question'], '研究哪个时间段？')


class WorkerReportOutputTests(unittest.TestCase):
    def setUp(self):
        self.request = {
            'run_id': 'run-1', 'task_id': 'task-1',
            'owner_id': f'anon:{OWNER_ID}', 'session_id': 'report-session',
        }
        self.workspace_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(agent_workspace, 'WORKSPACE_ROOT', self.workspace_root))
        self.root = agent_workspace.ensure_session_workspace(
            self.request['owner_id'], self.request['session_id'],
        )

    def test_last_successful_markdown_edit_preserves_crlf_and_metadata(self):
        markdown = '# 报告\r\n\r\n编辑后的正文。\r\n'
        (self.root / 'edited.markdown').write_bytes(markdown.encode('utf-8'))
        (self.root / 'old.md').write_text('larger prior report' * 20, encoding='utf-8')
        (self.root / 'draft.md').write_text('draft', encoding='utf-8')
        history = [AssistantMessage(tool_calls=(ToolCall('c1', 'write_file', {'path': 'old.md'}),)),
                   ToolResultMessage('c1', 'write_file', 'written')]
        result = RunResult(stop_reason=StopReason.STOP, messages=[
            *history,
            AssistantMessage(tool_calls=(
                ToolCall('c2', 'edit_file', {'path': 'edited.markdown', 'edits': []}),
                ToolCall('c3', 'edit_file', {'path': 'draft.md', 'edits': []}),
                ToolCall('c4', 'write_file', {'path': 'notes.txt'}),
            )),
            ToolResultMessage('c2', 'edit_file', 'edited'),
            ToolResultMessage('c3', 'edit_file', 'failed', is_error=True),
            ToolResultMessage('c4', 'write_file', 'written'),
        ], output={'sources': ['paper-1']})
        host.attach_report_output(self.request, result, history)

        payload = host.report_payload(self.request, result)
        self.assertEqual(payload['result']['output'], {
            'kind': 'report', 'report': markdown, 'report_path': 'edited.markdown',
            'sources': ['paper-1'],
        })

    def test_fallback_uses_largest_markdown_in_current_owner_workspace(self):
        other = agent_workspace.ensure_session_workspace('anon:unrelated', self.request['session_id'])
        (other / 'private.md').write_text('other owner' * 20, encoding='utf-8')
        (self.root / 'small.md').write_text('small', encoding='utf-8')
        (self.root / 'report.MARKDOWN').write_text('largest in this session', encoding='utf-8')
        history = [AssistantMessage(tool_calls=(ToolCall('c1', 'write_file', {'path': 'small.md'}),)),
                   ToolResultMessage('c1', 'write_file', 'written')]
        result = RunResult(stop_reason=StopReason.STOP, messages=[
            *history,
            AssistantMessage(tool_calls=(ToolCall('c2', 'write_file', {
                'path': str(other / 'private.md'),
            }),)),
            ToolResultMessage('c2', 'write_file', 'written'),
        ])

        host.attach_report_output(self.request, result, history)

        self.assertEqual(result.output['report_path'], 'report.MARKDOWN')
        self.assertEqual(result.output['report'], 'largest in this session')

    def test_existing_terminal_output_remains_unchanged(self):
        for output in ({'kind': 'report', 'report': 'existing'}, {'kind': 'question'},
                       {'kind': 'other'}, 'non-dict artifact'):
            with self.subTest(output=output), patch.object(host, 'read_session_file') as read:
                result = RunResult(stop_reason=StopReason.STOP, output=output)
                host.attach_report_output(self.request, result)
                self.assertIs(result.output, output)
                read.assert_not_called()

    def test_missing_report_keeps_successful_result(self):
        result = RunResult(stop_reason=StopReason.STOP, messages=[
            AssistantMessage(tool_calls=(ToolCall('c1', 'write_file', {'path': 'missing.md'}),)),
            ToolResultMessage('c1', 'write_file', 'written'),
        ])
        with self.assertLogs('agent.worker', level='WARNING'):
            host.attach_report_output(self.request, result)
        self.assertIsNone(result.output)
        self.assertEqual(host.report_payload(self.request, result)['status'], 'completed')

    def test_non_session_run_does_not_discover_workspace(self):
        result = RunResult(stop_reason=StopReason.STOP)
        with patch.object(host, 'ensure_session_workspace') as ensure_workspace:
            host.attach_report_output({**self.request, 'session_id': None}, result)
        self.assertIsNone(result.output)
        ensure_workspace.assert_not_called()


if __name__ == '__main__':
    unittest.main()
