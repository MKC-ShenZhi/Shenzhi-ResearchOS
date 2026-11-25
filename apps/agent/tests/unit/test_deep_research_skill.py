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
from agent_app.execution.types import AgentEvent, RunResult
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
            'DEEPSEEK_API_KEY': 'test',
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
                response = await client.get('/internal/v2/config')
        self.assertEqual(response.status_code, 200)
        skill = next(item for item in response.json()['skills'] if item['name'] == 'deep-research')
        self.assertTrue(skill['description'])

    async def execute_with_provider(self, provider, *, runtime_type=AgentRuntime, **session_options):
        control = AsyncMock(spec=host.AgentControlClient)
        control.get.return_value = {'controls': []}
        claim = {'lease_token': 1, 'event_seq': 0, 'run': {
            'run_id': 'run-1', 'task_id': 'task-1', 'owner_id': f'anon:{OWNER_ID}',
            'prompt': '研究这个领域', 'skills': ['deep-research'], **session_options,
        }}

        def build_with_fake_provider(**kwargs):
            return build_runtime(
                runtime_factory=lambda **options: runtime_type(provider=provider, **options),
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

    async def test_reused_call_id_keeps_each_turns_own_outcome(self):
        for edit_succeeds in (False, True):
            with self.subTest(edit_succeeds=edit_succeeds), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)):
                workspace = agent_workspace.ensure_session_workspace(f'anon:{OWNER_ID}', 'report-session')
                (workspace / 'draft.markdown').write_bytes(b'old\r\n')
                provider = FakeProvider([
                    [ToolCallEvent(ToolCall('call_0', 'write_file', {
                        'path': 'report.md', 'content': '# Current run',
                    })), Finish(StopReason.TOOL_CALLS)],
                    [ToolCallEvent(ToolCall('call_0', 'edit_file', {
                        'path': 'draft.markdown',
                        'edits': [{'old_text': 'old' if edit_succeeds else 'missing',
                                   'new_text': 'edited'}],
                    })), Finish(StopReason.TOOL_CALLS)],
                    [TextDelta('Done'), Finish(StopReason.STOP)],
                ])
                control = await self.execute_with_provider(provider, session_id='report-session')
                posts = [item.args[1] for item in control.post.await_args_list]
                outcomes = [(event['turn'], event['data']['tool_call_id'], event['data']['is_error'])
                            for event in posts if event.get('name') == 'tool_end']
                self.assertEqual(outcomes, [(1, 'call_0', False), (2, 'call_0', not edit_succeeds)])
                output = ReportIngestWire.model_validate(posts[-1]).result['output']
                self.assertEqual((output['report_path'], output['report']),
                                 ('draft.markdown', 'edited\r\n') if edit_succeeds
                                 else ('report.md', '# Current run'))

    async def test_reports_stay_with_the_writing_run_on_followup(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)):
            first = await self.execute_with_provider(FakeProvider([
                [ToolCallEvent(ToolCall('call_0', 'write_file', {
                    'path': 'report.md', 'content': '# First run',
                })), Finish(StopReason.TOOL_CALLS)],
                [TextDelta('Report ready'), Finish(StopReason.STOP)],
            ]), session_id='report-session')
            first_result = ReportIngestWire.model_validate(first.post.await_args.args[1]).result
            self.assertEqual(first_result['output']['report'], '# First run')
            self.assertEqual(first_result['output']['report_path'], 'report.md')

            second = await self.execute_with_provider(
                FakeProvider([[TextDelta('Follow-up answer'), Finish(StopReason.STOP)]]),
                run_id='run-2', task_id='task-2', session_id='report-session', skills=[],
                prompt='What does that mean?', history=first_result['messages'],
            )
            followup = ReportIngestWire.model_validate(second.post.await_args.args[1])
        self.assertEqual(followup.status.value, 'completed')
        self.assertEqual(followup.result['final_text'], 'Follow-up answer')
        self.assertIsNone(followup.result['output'])

    async def test_report_survives_removal_of_tool_messages_from_final_transcript(self):
        class CompactedRuntime(AgentRuntime):
            async def run(self, *args, **kwargs):
                result = await super().run(*args, **kwargs)
                # Simulate compaction removing the tool messages before the result is returned.
                result.messages.clear()
                return result

        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'write_file', {
                'path': 'report.md', 'content': '# From tool events',
            })), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('Done'), Finish(StopReason.STOP)],
        ])
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(agent_workspace, 'WORKSPACE_ROOT', Path(tmp)):
            control = await self.execute_with_provider(provider, runtime_type=CompactedRuntime,
                                                       session_id='report-session')
        report = ReportIngestWire.model_validate(control.post.await_args.args[1])
        self.assertEqual(report.result['messages'], [])
        self.assertEqual(report.result['output'], {
            'kind': 'report', 'report': '# From tool events', 'report_path': 'report.md',
        })

    async def test_tracking_exception_does_not_interrupt_event_delivery(self):
        provider = FakeProvider([[TextDelta('Still delivered'), Finish(StopReason.STOP)]])
        with patch.object(host.ReportFileOperations, 'observe', side_effect=ValueError('test')), \
                self.assertLogs('agent.worker', level='WARNING'):
            control = await self.execute_with_provider(provider)
        posts = [item.args[1] for item in control.post.await_args_list]
        self.assertIn('delta', [item.get('name') for item in posts])
        self.assertEqual(posts[-1]['status'], 'completed')
        self.assertEqual(posts[-1]['result']['final_text'], 'Still delivered')


class ReportFileOperationsTests(unittest.TestCase):
    def test_duplicate_call_in_same_turn_invalidates_even_an_earlier_success(self):
        tracker = host.ReportFileOperations()
        tracker.observe(AgentEvent(1, 1, 'tool_call', {
            'tool_call_id': 'call_0', 'name': 'write_file', 'arguments': '{"path":"report.md"}',
        }))
        tracker.observe(AgentEvent(2, 1, 'tool_end', {
            'tool_call_id': 'call_0', 'name': 'write_file', 'is_error': False,
        }))
        self.assertEqual(tracker.latest_path(), 'report.md')
        tracker.observe(AgentEvent(3, 1, 'tool_call', {
            'tool_call_id': 'call_0', 'name': 'read_file', 'arguments': '{"path":"notes.md"}',
        }))
        tracker.observe(AgentEvent(4, 1, 'tool_end', {
            'tool_call_id': 'call_0', 'name': 'write_file', 'is_error': False,
        }))
        self.assertIsNone(tracker.latest_path())

    def test_result_name_must_match_call(self):
        tracker = host.ReportFileOperations()
        tracker.observe(AgentEvent(1, 1, 'tool_call', {
            'tool_call_id': 'c1', 'name': 'edit_file', 'arguments': '{"path":"report.md"}',
        }))
        tracker.observe(AgentEvent(2, 1, 'tool_end', {
            'tool_call_id': 'c1', 'name': 'read_file', 'is_error': False,
        }))
        self.assertIsNone(tracker.latest_path())


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

    def test_report_output_preserves_crlf_and_metadata(self):
        markdown = '# 报告\r\n\r\n编辑后的正文。\r\n'
        (self.root / 'edited.markdown').write_bytes(markdown.encode('utf-8'))
        result = RunResult(stop_reason=StopReason.STOP, output={'sources': ['paper-1']})
        host.attach_report_output(self.request, result, 'edited.markdown')

        payload = host.report_payload(self.request, result)
        self.assertEqual(payload['result']['output'], {
            'kind': 'report', 'report': markdown, 'report_path': 'edited.markdown',
            'sources': ['paper-1'],
        })

    def test_cross_owner_path_does_not_read_another_workspace(self):
        other = agent_workspace.ensure_session_workspace('anon:unrelated', self.request['session_id'])
        (other / 'private.md').write_text('other owner', encoding='utf-8')
        result = RunResult(stop_reason=StopReason.STOP)
        with self.assertLogs('agent.worker', level='WARNING'), \
                patch.object(host, 'read_session_file') as read:
            host.attach_report_output(self.request, result, str(other / 'private.md'))
        read.assert_not_called()
        self.assertIsNone(result.output)

    def test_existing_terminal_output_remains_unchanged(self):
        for output in ({'kind': 'report', 'report': 'existing'}, {'kind': 'question'},
                       {'kind': 'other'}, 'non-dict artifact'):
            with self.subTest(output=output), patch.object(host, 'read_session_file') as read:
                result = RunResult(stop_reason=StopReason.STOP, output=output)
                host.attach_report_output(self.request, result, 'report.md')
                self.assertIs(result.output, output)
                read.assert_not_called()

    def test_missing_report_keeps_successful_result(self):
        (self.root / 'historical.md').write_text('old report', encoding='utf-8')
        result = RunResult(stop_reason=StopReason.STOP)
        with self.assertLogs('agent.worker', level='WARNING'):
            host.attach_report_output(self.request, result, 'missing.md')
        self.assertIsNone(result.output)
        self.assertEqual(host.report_payload(self.request, result)['status'], 'completed')

    def test_non_session_run_does_not_discover_workspace(self):
        result = RunResult(stop_reason=StopReason.STOP)
        with patch.object(host, 'ensure_session_workspace') as ensure_workspace:
            host.attach_report_output({**self.request, 'session_id': None}, result, 'report.md')
        self.assertIsNone(result.output)
        ensure_workspace.assert_not_called()


if __name__ == '__main__':
    unittest.main()
