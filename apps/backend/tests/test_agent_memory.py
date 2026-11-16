"""Agent 内部记忆与可观测性：turn 边界 Checkpoint、resume 续跑、RunResult 观测字段。"""
import tempfile
import unittest
from pathlib import Path

from app.services.agent import AgentRuntime, SkillRoot, SkillStore, StopReason
from app.services.agent.memory import Checkpoint, InMemoryCheckpointStore
from app.services.agent.provider import Finish, TextDelta, ToolCallEvent
from app.services.agent.types import ToolCall, ToolResultMessage
from tests.test_agent import FakeProvider, make_echo


class CheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_checkpoint_saved_at_turn_boundaries(self):
        store = InMemoryCheckpointStore()
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'a'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('完成'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], checkpoint_store=store)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        # run 结束前最后一次保存发生在末轮 turn 边界：transcript 已含工具往返
        checkpoints = list(store._checkpoints.values())
        self.assertGreaterEqual(len(checkpoints), 1)
        final = max(checkpoints, key=lambda c: c.turn)
        self.assertEqual(final.turn, 2)  # 每个完成的 turn 都有快照（含末轮）
        kinds = [m['kind'] for m in final.messages]
        self.assertIn('tool', kinds)  # 快照合法：tool 结果与父调用同在

    async def test_resume_continues_to_completion(self):
        store = InMemoryCheckpointStore()
        call = [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)]
        first = AgentRuntime(provider=FakeProvider([call]), tools=[make_echo()],
                             checkpoint_store=store, max_turns=1)
        events = []
        interrupted = await first.run('q', on_event=events.append)
        self.assertEqual(interrupted.status, 'failed')  # max_turns=1：末轮调用被合成失败
        run_id = next(e.data['run_id'] for e in events if e.name == 'run_start')
        checkpoint = await store.load(run_id)
        self.assertIsNotNone(checkpoint)
        second = AgentRuntime(provider=FakeProvider(
            [[TextDelta('续跑完成'), Finish(StopReason.STOP)]]),
            tools=[make_echo()], checkpoint_store=store)
        resumed = await second.resume(checkpoint)
        self.assertEqual(resumed.status, 'done')
        self.assertEqual(resumed.final_text, '续跑完成')
        # 恢复保留了断点前的完整轨迹（用户消息 + 工具往返），且继续追加
        self.assertGreaterEqual(len(resumed.messages), len(interrupted.messages))
        self.assertEqual(resumed.messages[0].text, 'q')

    async def test_checkpoint_json_roundtrip(self):
        checkpoint = Checkpoint(run_id='r1', turn=2, messages=[
            {'kind': 'user', 'text': 'q'},
            {'kind': 'tool', 'call_id': 'c1', 'name': 'echo', 'content': 'ok',
             'is_error': False, 'pinned': True},
        ], prompt_tokens=7, completion_tokens=9,
            summary='上次摘要', read_files=['a.md'], modified_files=['b.md'],
            loaded_skills=['alpha'], pinned_chars=123, executed_tools=4)
        restored = Checkpoint.from_json(checkpoint.to_json())
        self.assertEqual(restored.run_id, 'r1')
        self.assertEqual(restored.turn, 2)
        messages = restored.decoded_messages()
        self.assertEqual(messages[1].pinned, True)
        self.assertEqual((restored.prompt_tokens, restored.completion_tokens), (7, 9))
        # compaction 与 run 级状态完整往返（resume 不重置预算/技能/摘要）
        self.assertEqual(restored.summary, '上次摘要')
        self.assertEqual(restored.read_files, ['a.md'])
        self.assertEqual(restored.modified_files, ['b.md'])
        self.assertEqual(restored.loaded_skills, ['alpha'])
        self.assertEqual(restored.pinned_chars, 123)
        self.assertEqual(restored.executed_tools, 4)

    async def test_resume_restores_tool_budget(self):
        checkpoint = Checkpoint(run_id='r1', turn=1, messages=[
            {'kind': 'user', 'text': 'q'},
            {'kind': 'assistant', 'content': '', 'reasoning': '',
             'tool_calls': [{'call_id': 'c0', 'name': 'echo', 'arguments': '{"value":"a"}'}],
             'stop_reason': 'tool_calls'},
            {'kind': 'tool', 'call_id': 'c0', 'name': 'echo', 'content': 'ok',
             'is_error': False, 'pinned': False},
        ], executed_tools=1)
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'b'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('收尾'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_tool_calls=1)
        result = await runtime.resume(checkpoint)
        self.assertEqual(result.status, 'done')
        results = [m for m in result.messages if isinstance(m, ToolResultMessage)]
        self.assertTrue(results[-1].is_error)   # 已用 1/1 → 续跑后预算延续，不重置
        self.assertIn('预算', results[-1].content)

    async def test_resume_restores_loaded_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'alpha'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text(
                '---\nname: alpha\ndescription: 测试技能\n---\n\n正文', encoding='utf-8')
            store = SkillStore.load([SkillRoot(Path(tmp), executable=True)])
        checkpoint = Checkpoint(run_id='r1', turn=1, messages=[
            {'kind': 'user', 'text': 'q'},
            {'kind': 'assistant', 'content': '', 'reasoning': '',
             'tool_calls': [{'call_id': 'c0', 'name': 'read_skill',
                             'arguments': '{"name": "alpha"}'}], 'stop_reason': 'tool_calls'},
            {'kind': 'tool', 'call_id': 'c0', 'name': 'read_skill', 'content': 'ok',
             'is_error': False, 'pinned': True},
        ], loaded_skills=['alpha'])
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'read_skill', {'name': 'alpha'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('好的'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, skills=store)
        result = await runtime.resume(checkpoint)
        self.assertEqual(result.status, 'done')
        results = [m for m in result.messages if isinstance(m, ToolResultMessage)]
        # 已装载集合随 checkpoint 延续：resume 后 pin 状态与正文照常生效（不再有拦截规则）
        self.assertFalse(results[-1].is_error)
        self.assertIn('正文', results[-1].content)


class MetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_checkpoint_without_store(self):
        provider = FakeProvider([[TextDelta('hi'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider)
        result = await runtime.run('q')
        self.assertEqual(result.turns, 1)


if __name__ == '__main__':
    unittest.main()
