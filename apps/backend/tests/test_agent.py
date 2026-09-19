"""Agent 基座全矩阵测试：FakeProvider/FakeTool + httpx.MockTransport，零 Key 依赖。

覆盖：单轮流式、工具往返 wire 格式、tool_calls 碎片归并、各失败路径 is_error
回喂、三层超时、stop 优雅停止、外部取消重抛、批次闭合、预算、LENGTH 截断、
轮组截断与孤儿安全、pinned 预算、terminal 直出、消息编解码、钩子、事件序列、
compaction（pi 语义）、provider 零增量重试的 deadline 条件、service 组合。
"""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import BaseModel

from app.core.config import ModelConfig
from app.core.errors import BusinessError
from app.services.agent import (
    AgentRuntime, AssistantMessage, StopReason, ToolCall, ToolOutput, ToolResult, ToolResultMessage,
    UserMessage, message_from_dict, message_to_dict, tool,
)
from app.services.agent.compaction import (
    estimate_context_chars, extract_file_ops, serialize_conversation, wrap_summary,
)
from app.services.agent.context import assemble
from app.services.agent.provider import (
    Finish, ModelRequest, OpenAICompatProvider, TextDelta, ToolCallEvent, Usage,
)
from app.services.agent.types import RunChannel

CONFIG = ModelConfig('test-key', 'https://model.test/v1', 'deepseek-chat', ('deepseek-chat',), 'deepseek')
HANG = object()  # 挂起占位：永不完成


class FakeProvider:
    """可编排的脚本化 Provider；float 项表示 sleep，HANG 表示挂起，异常项原样抛出。"""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.requests: list[ModelRequest] = []
        self.started = asyncio.Event()

    async def stream(self, request):
        self.requests.append(request)
        self.started.set()
        for item in self.scripts.pop(0):
            if item is HANG:
                await asyncio.Event().wait()
            elif isinstance(item, float):
                await asyncio.sleep(item)
            elif isinstance(item, BaseException):
                raise item
            yield item


class EchoParams(BaseModel):
    value: str


def make_echo(name='echo', *, fail=None, delay=0.0, timeout_s=60.0, terminal=False,
              delivery=False):
    @tool(name=name, description='回显', params=EchoParams, timeout_s=timeout_s, delivery=delivery)
    async def echo(args: EchoParams):
        if delay:
            await asyncio.sleep(delay)
        if fail is not None:
            raise fail
        if terminal:
            return ToolOutput(content='制品已交付', terminal={'report': f'report:{args.value}'})
        return f'echo:{args.value}'

    return echo


def tool_messages(result):
    return [m for m in result.messages if isinstance(m, ToolResultMessage)]


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_arguments_do_not_break_next_request(self):
        """线上事故回归：write_file 参数被输出上限截断 → 残缺 JSON 回传 → 上游 400 杀死整轮。

        参数在 AI 层已解析成对象（截断的字段由修复阶梯还原，见 ProviderTests 的
        test_truncated_tool_call_does_not_poison_next_request），因此这里验证运行时侧：
        截断调用被判失败回喂、批次闭合、下一轮请求体里的参数仍是合法 JSON，运行正常收尾。
        """
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.LENGTH)],
            [TextDelta('重发完成'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.turns, 2)
        second = [m for m in provider.requests[1].messages if m['role'] == 'assistant'][-1]
        self.assertEqual(json.loads(second['tool_calls'][0]['function']['arguments']),
                         {'value': 'x'})
        feedback = next(m for m in result.messages
                        if isinstance(m, ToolResultMessage) and m.is_error)
        self.assertIn('输出上限被截断', feedback.content)
        self.assertIn('分段续写', feedback.content)               # 回喂里给了正确的恢复方式

    async def test_single_turn_stream_and_result(self):
        provider = FakeProvider([[TextDelta('你'), TextDelta('好'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, system='测试')
        events = []
        result = await runtime.run('hi', on_event=events.append)
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.final_text, '你好')
        self.assertEqual(result.turns, 1)
        self.assertEqual([e.name for e in events],
                         ['run_start', 'turn_start', 'delta', 'turn_end', 'run_end'])
        self.assertEqual(events[0].data['model'], 'deepseek-chat')
        self.assertEqual(events[-1].data['status'], 'done')

    async def test_tool_round_trip_wire_format(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
             [TextDelta('ans'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.final_text, 'ans')
        self.assertEqual(result.turns, 2)
        self.assertEqual(len(provider.requests), 2)
        messages = provider.requests[1].messages
        assistant = [m for m in messages if m['role'] == 'assistant' and m.get('tool_calls')]
        self.assertEqual(assistant[0]['tool_calls'][0]['function']['name'], 'echo')
        tool_entry = [m for m in messages if m['role'] == 'tool']
        self.assertEqual(tool_entry[0]['tool_call_id'], 'c1')
        self.assertIn('echo:x', tool_entry[0]['content'])

    async def test_tool_error_is_error_feed(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
             [TextDelta('ok'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo(fail=ValueError('boom'))])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertTrue(results[0].is_error)
        self.assertIn('boom', results[0].content)

    async def test_unknown_tool_and_bad_args(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'nope', {})),
             ToolCallEvent(ToolCall('c2', 'echo', {})),          # 缺必填字段
             ToolCallEvent(ToolCall('c3', 'echo', {'value': 123})),  # 类型不符
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('ok'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertTrue(all(r.is_error for r in results))
        self.assertIn('not found', results[0].content)  # pi 原句
        self.assertIn('校验失败', results[1].content)
        self.assertIn('校验失败', results[2].content)

    async def test_tool_timeout_continues(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
             [TextDelta('done'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo(delay=10, timeout_s=0.05)])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertTrue(results[0].is_error)
        self.assertIn('超时', results[0].content)

    async def test_deadline_timeout(self):
        provider = FakeProvider([[HANG]])
        runtime = AgentRuntime(provider=provider, deadline_s=0.05)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'timeout')
        self.assertEqual(result.stop_reason, StopReason.TIMEOUT)

    async def test_tool_budget_forces_answer_only_turn(self):
        """预算耗尽不能只"拒绝"：必须把模型逼进一次无工具的收尾轮，而不是空转到 deadline。

        回归证据（线上）：24 次预算用完后模型连续三批调用全被拒（每个 0ms、is_error），
        最终停止原因是 timeout——已收集的证据永远没变成答案。
        """
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': '1'})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'echo', {'value': '2'})),
             ToolCallEvent(ToolCall('c3', 'echo', {'value': '3'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('基于已有证据的答案'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_tool_calls=2)
        result = await runtime.run('q')
        messages = [m for m in result.messages if isinstance(m, UserMessage)]
        self.assertIn('工具预算已耗尽', messages[-1].text)   # 收尾指令注入了
        self.assertEqual(provider.requests[2].tools, [])    # 收尾轮不再带工具
        self.assertEqual(result.status, 'done')             # 交付而不是 timeout
        self.assertEqual(result.turns, 3)
        self.assertIn('基于已有证据的答案', result.final_text)
        rejected = [m for m in tool_messages(result) if m.is_error]
        # 预算 2：c1 与 c2 各占一个名额，c3 在被拒的那一批里被拒（同批后续调用不再放行）
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].name, 'echo')
        self.assertIn('预算已耗尽', rejected[0].content)

    async def test_budget_rejected_call_before_natural_stop_is_reported(self):
        """模型在收尾轮仍调工具：照实回喂拒绝理由并闭合批次，随后正常交付。"""
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': '1'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('准备继续'), Finish(StopReason.STOP)],
            [ToolCallEvent(ToolCall('c9', 'echo', {'value': '9'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('收尾答案'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_tool_calls=1)
        result = await runtime.run('q')
        rejected = [m for m in tool_messages(result) if m.is_error]
        self.assertEqual([m.name for m in rejected], ['echo'])  # c9 在收尾轮被拒
        self.assertIn('预算已耗尽', rejected[0].content)
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.turns, 4)
        self.assertIn('收尾答案', result.final_text)
        self.assertEqual(provider.requests[2].tools, [])    # 收尾轮无工具

    async def test_tool_budget_visible_in_system_prompt(self):
        """预算数必须写进系统提示：不给读数，模型只能盲判（实测一批并行就烧掉大半）。"""
        plain = AgentRuntime(provider=FakeProvider([]), tools=[make_echo()])
        budgeted = AgentRuntime(provider=FakeProvider([]), tools=[make_echo()], tool_budget=7)
        self.assertNotIn('工具调用预算', plain.system)
        self.assertIn('本轮工具调用预算：7 次', budgeted.system)
        self.assertIn('本轮工具调用预算：7 次', budgeted.system)

    async def test_stop_event_graceful_mid_stream(self):
        provider = FakeProvider([[TextDelta('部'), 0.2, TextDelta('分'), Finish(StopReason.STOP)]])
        stop = asyncio.Event()
        events = []
        runtime = AgentRuntime(provider=provider)
        task = asyncio.create_task(runtime.run('q', on_event=events.append, stop=stop))
        await provider.started.wait()
        await asyncio.sleep(0.05)
        stop.set()
        result = await task
        self.assertEqual(result.status, 'stopped')
        self.assertEqual(result.final_text, '部')  # 停止检查在处理下一个事件之前
        self.assertEqual(events[-1].name, 'run_end')
        self.assertEqual(events[-1].data['status'], 'stopped')

    async def test_stop_event_before_tool_closes_batch(self):
        """停止请求发生在批次中：transcript 必须闭合（每个 call 都有结果）。

        parallel（pi 默认，预检后并发执行）：两个调用都已启动，各自跑完；
        sequential：停止后剩余调用判为未执行。两种模式批次闭合语义一致。
        """
        for mode, second_is_error in (('parallel', False), ('sequential', True)):
            with self.subTest(mode=mode):
                provider = FakeProvider([
                    [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'a'})),
                     ToolCallEvent(ToolCall('c2', 'echo', {'value': 'b'})),
                     Finish(StopReason.TOOL_CALLS)]])
                stop = asyncio.Event()

                def on_event(event):
                    if event.name == 'tool_end' and not event.data['is_error']:
                        stop.set()  # 第一个工具完成后要求停止

                runtime = AgentRuntime(provider=provider, tools=[make_echo(delay=0.05)],
                                       tool_execution=mode)
                result = await runtime.run('q', on_event=on_event, stop=stop)
                self.assertEqual(result.status, 'stopped')
                results = tool_messages(result)
                self.assertEqual(len(results), 2)          # 批次闭合：每个 call 都有结果
                self.assertFalse(results[0].is_error)
                self.assertEqual(results[1].is_error, second_is_error)
                wire, _ = assemble('s', result.messages, max_chars=30_000)  # transcript 可续输
                self.assertTrue(any(m['role'] == 'tool' for m in wire))

    async def test_external_cancel_reraise(self):
        provider = FakeProvider([[HANG]])
        runtime = AgentRuntime(provider=provider)
        task = asyncio.create_task(runtime.run('q'))
        await provider.started.wait()
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_external_cancel_closes_batch(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'a'})),
             ToolCallEvent(ToolCall('c2', 'echo', {'value': 'b'})),
             Finish(StopReason.TOOL_CALLS)]])
        events = []
        runtime = AgentRuntime(provider=provider, tools=[make_echo(delay=1.0)])
        task = asyncio.create_task(runtime.run('q', on_event=events.append))
        await provider.started.wait()
        await asyncio.sleep(0.1)  # 确保第一个工具正在执行中
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        closed = [e for e in events if e.name == 'tool_end' and e.data['is_error']]
        self.assertEqual(len(closed), 2)  # 进行中的 c1 与未开始的 c2 都有合成失败结果
        self.assertTrue(all('取消' in e.data['summary'] for e in closed))

    async def test_max_turns_batch_closure(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
        ])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_turns=2)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.stop_reason, StopReason.MAX_TURNS)
        self.assertIn('轮数', result.error.message)
        results = tool_messages(result)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].is_error)   # 末轮前的工具正常执行
        self.assertTrue(results[1].is_error)    # 末轮调用合成失败结果（不执行）
        assemble('s', result.messages, max_chars=30_000)  # 不抛 = transcript 合法

    async def test_tool_budget_soft_stop(self):
        """预算耗尽（同批后续调用被拒）→ 收尾轮不带工具 → 正常交付，不空转到 deadline。"""
        call = [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)]
        provider = FakeProvider([
            call,
            [ToolCallEvent(ToolCall('c2', 'echo', {'value': 'y'})),
             ToolCallEvent(ToolCall('c3', 'echo', {'value': 'z'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('done'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_tool_calls=2)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.turns, 3)
        self.assertEqual(provider.requests[2].tools, [])  # 收尾轮不带工具
        results = [m for m in tool_messages(result) if m.is_error]
        self.assertEqual(len(results), 1)                 # c3 被拒（预算是 2）
        self.assertIn('预算', results[0].content)
        texts = [m.text for m in result.messages if isinstance(m, UserMessage)]
        self.assertIn('工具预算已耗尽', texts[-1])

    async def test_wrap_up_keeps_delivery_tools(self):
        """收尾模式不是"裸奔"：交付类工具保留在 wire 里、照常执行，非交付调用逐个拒绝——
        撞墙后模型仍能把已收集的证据写成交付物（回归证据：收尾轮连 write_file 都没有，
        报告永远写不出来）。"""
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': '1'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('想收工'), Finish(StopReason.STOP)],   # 自然停止 → 收尾模式启动
            [ToolCallEvent(ToolCall('c2', 'echo', {'value': 'x'})),           # 收尾轮仍试非交付调用
             ToolCallEvent(ToolCall('c3', 'scribe', {'value': '报告'})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('已交付'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider,
                               tools=[make_echo(), make_echo(name='scribe', delivery=True)],
                               max_tool_calls=1)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual([t['function']['name'] for t in provider.requests[2].tools], ['scribe'])
        results = {m.call_id: m for m in tool_messages(result)}
        self.assertTrue(results['c2'].is_error)           # 非交付调用被拒
        self.assertIn('收尾', results['c2'].content)
        self.assertFalse(results['c3'].is_error)          # 交付调用照常执行
        self.assertEqual(results['c3'].content, 'echo:报告')
        self.assertEqual(result.turns, 4)

    async def test_deadline_delivery_window(self):
        """deadline 撞在工具批次中间：受影响调用合成失败结果后，run 用宽限预算做交付轮
        （只带交付工具），把已有证据写成交付物——而不是整批 0ms 失败后什么都不剩
        （回归证据：13 次检索成功后一批 0ms 失败，run 以 timeout 终态、零交付）。"""
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'slow', {'value': '证据'})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'scribe', {'value': '报告'})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('交付说明'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider,
                               tools=[make_echo(name='slow', delay=5.0, timeout_s=30.0),
                                      make_echo(name='scribe', delivery=True)],
                               deadline_s=0.2)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'timeout')
        results = {m.call_id: m for m in tool_messages(result)}
        self.assertTrue(results['c1'].is_error)           # 被超时打断的批次照常闭合
        self.assertFalse(results['c2'].is_error)          # 交付窗口里交付工具执行了
        self.assertIn('交付说明', result.final_text)
        texts = [m.text for m in result.messages if isinstance(m, UserMessage)]
        self.assertIn('时间上限', texts[-1])              # 交付指令注入了

    async def test_delivery_nudge_before_budget_exhausted(self):
        """提前交付引导（对齐 SZDR BUDGET_VISIBILITY_AT=0.83，语义加强）：预算用到 83% 就
        要求模型**立即开始写交付物**、剩余次数只补关键缺口——而不是等用尽被拒后才补救。"""
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall(f'c{i}', 'echo', {'value': str(i)})),
              Finish(StopReason.TOOL_CALLS)] for i in range(1, 10)]
            + [[TextDelta('收尾交付'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], max_tool_calls=8)
        result = await runtime.run('q')
        notes = [m.text for m in result.messages
                 if isinstance(m, UserMessage) and m.text.startswith('预算提示')]
        self.assertEqual(len(notes), 1)                   # 只注入一次
        self.assertIn('已用 7/8 次', notes[0])            # 8 × 0.83 = 6.64 → 首个达标读数是 7
        self.assertIn('现在就开始交付', notes[0])         # 是行动指令，不是单纯读数
        self.assertEqual(result.status, 'done')
        self.assertEqual(provider.requests[9].tools, [])  # 随后的撞墙收尾轮照常无检索工具

    async def test_delivery_nudge_on_time_budget(self):
        """时间预算同样提前引导：剩余时间不足 17% 就要求开始交付（不等 deadline 撞墙）。"""
        provider = FakeProvider([
            [1.8, TextDelta('还在收集'), Finish(StopReason.STOP)],  # 烧掉大部分时间预算
            [TextDelta('交付说明'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, deadline_s=2.0)
        result = await runtime.run('q')
        notes = [m.text for m in result.messages
                 if isinstance(m, UserMessage) and m.text.startswith('时间提示')]
        self.assertEqual(len(notes), 1)
        self.assertIn('现在就开始交付', notes[0])
        self.assertEqual(result.status, 'done')

    async def test_length_truncated_calls_fail(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'trunc'})), Finish(StopReason.LENGTH)],
             [TextDelta('redone'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertTrue(results[0].is_error)
        self.assertIn('截断', results[0].content)

    async def test_terminal_output(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'r'})), Finish(StopReason.TOOL_CALLS)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo(terminal=True)])
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.stop_reason, StopReason.STOP)
        self.assertEqual(result.output, {'report': 'report:r'})  # 制品不经模型转述
        self.assertEqual(result.final_text, '')

    async def test_hooks_order_block_and_rewrite(self):
        order = []

        async def before(call, args):
            order.append(f'before:{call.name}')
            if args.value == 'block':
                return ToolResult(call.call_id, call.name, 'blocked by policy', is_error=True)
            return None

        async def after(call, args, result):
            order.append(f'after:{call.name}')
            return ToolResult(result.call_id, result.name, result.content + '+after')

        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'go'})),
             ToolCallEvent(ToolCall('c2', 'echo', {'value': 'block'})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('ok'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()],
                               before_tool_call=before, after_tool_call=after)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertEqual(results[0].content, 'echo:go+after')
        self.assertTrue(results[1].is_error)
        self.assertEqual(results[1].content, 'blocked by policy')
        # parallel（pi 默认）：预检阶段全部 before 先跑完，再并发执行 + after
        self.assertEqual(order, ['before:echo', 'before:echo', 'after:echo'])

    async def test_hooks_order_sequential_mode(self):
        """显式顺序模式：逐调用 prepare → execute → after 交错（阻断后不执行不 after）。"""
        order = []

        async def before(call, args):
            order.append(f'before:{call.name}')
            if args.value == 'block':
                return ToolResult(call.call_id, call.name, 'blocked by policy', is_error=True)
            return None

        async def after(call, args, result):
            order.append(f'after:{call.name}')
            return None

        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'go'})),
             ToolCallEvent(ToolCall('c2', 'echo', {'value': 'block'})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('ok'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()],
                               before_tool_call=before, after_tool_call=after,
                               tool_execution='sequential')
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(order, ['before:echo', 'after:echo', 'before:echo'])

    async def test_hook_exception_is_error(self):
        async def before(call, args):
            raise RuntimeError('hook boom')

        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
             [TextDelta('ok'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], before_tool_call=before)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        results = tool_messages(result)
        self.assertTrue(results[0].is_error)
        self.assertIn('before_tool_call', results[0].content)

    async def test_empty_response_ends_normally(self):
        """pi agent-loop:226：空 content + 空 tool_calls 也照常收尾，run 判成功。

        异常停止由 provider 映射成 error/aborted 停止原因，不在循环里当错误处理。
        """
        provider = FakeProvider([[Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.final_text, '')
        self.assertIsNone(result.error)

    async def test_usage_accumulation(self):
        provider = FakeProvider(
            [[ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS, Usage(10, 20))],
             [TextDelta('ok'), Finish(StopReason.STOP, Usage(5, 7))]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q')
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (15, 27))

    async def test_message_codec_roundtrip(self):
        messages = [
            UserMessage('hi'),
            AssistantMessage('a', 'r', (ToolCall('c', 'echo', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c', 'echo', 'ok', True, True),
        ]
        self.assertEqual([message_from_dict(message_to_dict(m)) for m in messages], messages)
        with self.assertRaises(ValueError):
            message_from_dict({'kind': 'bogus'})


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def sse(frames, done=True):
        body = ''.join(f'data: {json.dumps(frame, ensure_ascii=False)}\n\n' for frame in frames)
        return body + 'data: [DONE]\n\n' if done else body

    async def collect(self, provider, request):
        events = []
        async for event in provider.stream(request):
            events.append(event)
        return events

    @staticmethod
    def frame(delta=None, finish=None):
        choice = {'delta': delta if delta is not None else {}}
        if finish is not None:
            choice['finish_reason'] = finish
        return {'choices': [choice]}

    async def test_tool_calls_fragment_merge(self):
        frames = [
            self.frame(delta={'tool_calls': [{'index': 0, 'id': 'c1', 'type': 'function',
                                              'function': {'name': 'echo', 'arguments': '{"value"'}}]}),
            self.frame(delta={'tool_calls': [{'index': 0, 'id': 'c1',
                                              'function': {'name': 'echo', 'arguments': ': "x"}'}}]}),
            self.frame(finish='tool_calls'),
        ]
        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=self.sse(frames),
                                           headers={'content-type': 'text/event-stream'})),
            retry_delay=0)
        events = await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        calls = [e for e in events if isinstance(e, ToolCallEvent)]
        finish = [e for e in events if isinstance(e, Finish)][0]
        self.assertEqual(calls[0].call.arguments, {'value': 'x'})
        self.assertEqual(calls[0].call.name, 'echo')
        self.assertEqual(finish.stop_reason, StopReason.TOOL_CALLS)

    async def test_retry_before_first_delta(self):
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ConnectError('boom', request=request)
            return httpx.Response(200, text=self.sse([
                {'choices': [{'delta': {'content': 'A'}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            ]), headers={'content-type': 'text/event-stream'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        events = await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertEqual(events[0].text if events else None, 'A')
        self.assertEqual(len(calls), 2)

    async def test_no_retry_after_delta(self):
        calls = []

        async def body():
            yield b'data: {"choices":[{"delta":{"content":"A"}}]}\n\n'
            raise httpx.ReadError('cut')

        def handler(request):
            calls.append(request)
            return httpx.Response(200, content=body(), headers={'content-type': 'text/event-stream'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        with self.assertRaises(BusinessError) as ctx:
            await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertIn('连接中断', ctx.exception.message)
        self.assertEqual(len(calls), 1)

    async def test_status_error_mapping_and_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={'error': 'rate'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        with self.assertRaises(BusinessError) as ctx:
            await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertIn('限流', ctx.exception.message)
        self.assertEqual(len(calls), 3)  # max_retries=2 → 首次 + 2 次重试（瞬时 4xx/5xx 不放弃长跑）

    async def test_401_immediate_fail_no_retry(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(401, json={'error': 'unauthorized'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        with self.assertRaises(BusinessError) as ctx:
            await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertIn('凭据无效', ctx.exception.message)
        self.assertEqual(len(calls), 1)  # 401 是配置类错误，不重试

    async def test_upstream_400_detail_surfaces(self):
        """400 的上游原文必须带出来：原因（参数/长度/消息序列）只有上游说得清。"""
        def handler(request):
            return httpx.Response(400, json={'error': {'message': 'Range of input length should be [1, 129024]'}})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        with self.assertRaises(BusinessError) as ctx:
            await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertIn('模型不支持当前请求参数', ctx.exception.message)
        self.assertIn('Range of input length', ctx.exception.message)

    async def test_transient_400_retried(self):
        """瞬时 400 重试后可恢复（实测同一 payload 可反复成功，400 多为上游瞬时状态）。"""
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(400, json={'error': 'transient'})
            return httpx.Response(200, content=self.sse([
                {'choices': [{'delta': {'content': 'A'}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            ]), headers={'content-type': 'text/event-stream'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        events = await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        self.assertEqual([e.text for e in events if isinstance(e, TextDelta)], ['A'])
        self.assertEqual(len(calls), 2)

    async def test_thinking_dropped_on_400_before_outer_retry(self):
        """enable_thinking 被拒 → 先去思考重试（同一次调用内），不占用外层重试次数。"""
        seen = []

        def handler(request):
            payload = json.loads(request.content)
            seen.append(bool(payload.get('enable_thinking')))
            if payload.get('enable_thinking'):
                return httpx.Response(400, json={'error': 'enable_thinking not supported'})
            return httpx.Response(200, content=self.sse([
                {'choices': [{'delta': {'content': 'A'}}]},
                {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            ]), headers={'content-type': 'text/event-stream'})

        provider = OpenAICompatProvider(
            ModelConfig('test-key', 'https://model.test/v1', 'qwen-plus', ('qwen-plus',), 'platform'),
            transport=httpx.MockTransport(handler), retry_delay=0, max_retries=0)
        events = await self.collect(provider, ModelRequest('qwen-plus', [{'role': 'user', 'content': 'q'}]))
        self.assertEqual(seen, [True, False])  # 一次带思考（被拒）+ 一次去思考（成功）
        self.assertEqual([e.text for e in events if isinstance(e, TextDelta)], ['A'])

    async def test_truncated_tool_call_does_not_poison_next_request(self):
        """回归：截断的 tool_call 参数曾原样回传 → 上游 400 整轮拒收且重试无用。

        现在参数在 AI 层规范化（pi：解析成对象再序列化），已写完的字段保留，
        下一次请求的 function.arguments 必然是合法 JSON。
        """
        broken = '{"value": "x'      # 截断：缺右括号与引号
        frames = [
            self.frame(delta={'tool_calls': [{'index': 0, 'id': 'c1', 'type': 'function',
                                              'function': {'name': 'echo', 'arguments': broken}}]}),
            self.frame(finish='length'),   # 输出上限截断
        ]

        def handler(request):
            return httpx.Response(200, content=self.sse(frames),
                                  headers={'content-type': 'text/event-stream'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        events = await self.collect(provider, ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}]))
        call = next(e.call for e in events if isinstance(e, ToolCallEvent))
        self.assertEqual(call.arguments, {'value': 'x'})  # 参数已解析，且保留已写完字段

    async def test_retry_skipped_when_deadline_close(self):
        calls = []

        def handler(request):
            calls.append(request)
            raise httpx.ConnectError('boom', request=request)

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler), retry_delay=0)
        # 剩余 1s < 2s 下限：不满足"剩余 deadline > 2s"条件，直接失败不重试
        request = ModelRequest('deepseek-chat', [{'role': 'user', 'content': 'q'}],
                               deadline_at=time.monotonic() + 1.0)
        with self.assertRaises(BusinessError):
            await self.collect(provider, request)
        self.assertEqual(len(calls), 1)

    async def test_missing_key(self):
        provider = OpenAICompatProvider(ModelConfig('', 'https://model.test/v1', 'm', ('m',), 'x'))
        with self.assertRaises(BusinessError):
            await self.collect(provider, ModelRequest('m', []))


class JsonRepairTests(unittest.TestCase):
    """工具参数 JSON 修复阶梯（pi packages/ai/src/utils/json-parse.ts 的移植）。"""

    def setUp(self):
        from app.services.agent import json_repair
        self.module = json_repair

    def test_valid_json_passes_through(self):
        obj = self.module.parse_streaming_json('{"path": "a.md", "content": "正文"}')
        self.assertEqual(obj, {'path': 'a.md', 'content': '正文'})

    def test_truncated_keeps_completed_fields(self):
        """被输出上限截断的参数：已写完的字段必须还原，而不是整份丢成 {}。"""
        truncated = '{"path": "research_state.json", "content": "{\\"q\\": \\"Agent 记忆\\", \\"kw\\": [\\"agent'
        obj = self.module.parse_streaming_json(truncated)
        self.assertEqual(obj['path'], 'research_state.json')
        self.assertIn('Agent 记忆', obj['content'])

    def test_truncated_containers_closed(self):
        self.assertEqual(self.module.parse_streaming_json('{"a": [1, 2, 3'), {'a': [1, 2, 3]})
        self.assertEqual(self.module.parse_streaming_json('{"a": {"b": [{"c": "x'),
                         {'a': {'b': [{'c': 'x'}]}})
        self.assertEqual(self.module.parse_streaming_json('{"a": [1, 2,'), {'a': [1, 2]})

    def test_repair_control_characters_and_escapes(self):
        self.assertEqual(self.module.parse_streaming_json('{"a": "line\nbreak"}'),
                         {'a': 'line\nbreak'})

    def test_always_object_never_raises(self):
        for raw in ('', '   ', 'not json at all', '{"a": "b', None):
            with self.subTest(raw=raw):
                self.assertIsInstance(self.module.parse_streaming_json(raw), dict)

    def test_wire_arguments_serializes_objects(self):
        from app.services.agent.context import wire_arguments
        self.assertEqual(wire_arguments({'a': 1}), '{"a": 1}')
        self.assertEqual(wire_arguments({}), '{}')
        self.assertEqual(json.loads(wire_arguments({'文本': '中文'})), {'文本': '中文'})


class ContextTests(unittest.TestCase):
    def test_trim_by_group_and_orphan_safety(self):
        big = 'x' * 15000
        messages = [
            UserMessage('q1 ' + big), AssistantMessage('a1 ' + big),
            UserMessage('q2'), AssistantMessage('', '', (ToolCall('c1', 'echo', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c1', 'echo', 'ok'),
            UserMessage('q3'),
        ]
        wire, truncated = assemble('sys', messages, max_chars=24_000)
        self.assertTrue(truncated)
        contents = [m.get('content', '') for m in wire]
        self.assertFalse(any('q1' in c for c in contents))   # 最旧轮组整组丢弃
        self.assertTrue(any('q2' in c for c in contents))    # 带工具调用的轮组保留
        tool_entries = [m for m in wire if m['role'] == 'tool']
        self.assertEqual(len(tool_entries), 1)               # tool 结果与其父调用同生共死
        self.assertEqual(tool_entries[0]['tool_call_id'], 'c1')

    def test_tool_result_cap_and_pinned_exempt(self):
        huge = 'x' * 20_000
        messages = [
            UserMessage('q'),
            AssistantMessage('', '', (ToolCall('c1', 'echo', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c1', 'echo', huge),
            AssistantMessage('', '', (ToolCall('c2', 'echo', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c2', 'echo', huge, pinned=True),
            UserMessage('next'),
        ]
        wire, truncated = assemble('', messages, max_chars=100_000, max_tool_result_chars=100)
        self.assertTrue(truncated)
        contents = {m['tool_call_id']: m['content'] for m in wire if m['role'] == 'tool'}
        self.assertLessEqual(len(contents['c1']), 100 + 20)
        self.assertIn('[工具结果已截断]', contents['c1'])
        self.assertEqual(len(contents['c2']), 20_000)  # pinned 不截断

    def test_context_overflow(self):
        messages = [UserMessage('q'), ToolResultMessage('c1', 'echo', 'x' * 90_000, pinned=True), UserMessage('next')]
        with self.assertRaises(BusinessError) as ctx:
            assemble('', messages, max_chars=50_000)
        self.assertIn('上下文超出预算', ctx.exception.message)

    def test_floor_counts_pinned_once(self):
        """回归：当前轮组内的 pinned 曾被 floor 双重计入（pinned_total + 当前输入），
        30k pinned + 5k system 实际 35k 却报 60k 预算溢出。"""
        pinned = 'P' * 30_000
        messages = [
            UserMessage('q'),
            AssistantMessage('', '', (ToolCall('c1', 'read_skill', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c1', 'read_skill', pinned, pinned=True),
        ]
        wire, truncated = assemble('S' * 5_000, messages, max_chars=60_000)
        self.assertFalse(truncated)
        tool_contents = [m['content'] for m in wire if m['role'] == 'tool']
        self.assertEqual(tool_contents, [pinned])

    def test_pinned_group_survives_trimming(self):
        """回归：pinned（技能指令）曾随轮组被整组丢弃；实际总量 19k < 预算 25k 仍被丢。"""
        messages = [
            UserMessage('older ' + 'x' * 15_000), AssistantMessage('a'),
            UserMessage('old'), AssistantMessage('', '', (ToolCall('c1', 'read_skill', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c1', 'read_skill', 'SKILL_RULES_' + 'P' * 30_000, pinned=True),
            UserMessage('cur ' + 'y' * 27_000),
        ]
        wire, truncated = assemble('sys', messages, max_chars=75_000)
        self.assertTrue(truncated)  # 非指令的旧轮组确实被截
        self.assertFalse(any('older' in m.get('content', '') for m in wire))
        tool_contents = [m['content'] for m in wire if m['role'] == 'tool']
        self.assertEqual(len(tool_contents), 1)  # 指令性内容整组保留
        self.assertIn('SKILL_RULES_', tool_contents[0])


class CompactionTests(unittest.IsolatedAsyncioTestCase):
    """compaction（pi harness/compaction 语义移植）不变量。"""

    @staticmethod
    def _history(body: str, count: int = 3):
        return [m for i in range(count) for m in
                (UserMessage(f'q{i} {body}'), AssistantMessage(f'a{i}'))]

    def _summary_script(self, text='## Goal\n测试目标'):
        return [TextDelta(text), Finish(StopReason.STOP)]

    async def test_folds_old_keeps_recent_and_summarizes(self):
        provider = FakeProvider([
            self._summary_script(),                       # 摘要请求
            [TextDelta('完成'), Finish(StopReason.STOP)],  # 主 turn
        ])
        runtime = AgentRuntime(provider=provider, compaction=True,
                               max_context_chars=15_000, compaction_at=0.5,
                               compaction_keep_chars=6_000)
        events = []
        result = await runtime.run('现在继续', history=self._history('x' * 3600),
                                   on_event=events.append)
        self.assertEqual(result.status, 'done')
        # 折叠：最旧轮组进摘要，近期轮组保留原文
        self.assertTrue(result.messages[0].text.startswith('<context_summary>'))
        self.assertIn('测试目标', result.messages[0].text)
        texts = [m.text for m in result.messages if isinstance(m, UserMessage)]
        self.assertFalse(any('q0' in t for t in texts))
        self.assertTrue(any('q1' in t for t in texts))
        self.assertTrue(any('q2' in t for t in texts))
        self.assertTrue(any('现在继续' in t for t in texts))
        # 摘要请求格式：pi serializeConversation + 结构化提示，无 previous-summary
        summary_request = provider.requests[0]
        self.assertEqual(summary_request.messages[0]['role'], 'system')
        prompt = summary_request.messages[-1]['content']
        self.assertIn('<conversation>', prompt)
        self.assertIn('[User]: q0', prompt)
        self.assertNotIn('<previous-summary>', prompt)
        assemble('s', result.messages, max_chars=30_000)  # transcript 仍合法
        compaction_events = [e for e in events if e.name == 'compaction']
        self.assertEqual(len(compaction_events), 1)
        self.assertGreater(compaction_events[0].data['before_chars'],
                           compaction_events[0].data['after_chars'])

    async def test_usage_based_trigger(self):
        """触发估算优先真实用量：字符很小但 usage 大时也要压缩（pi estimateContextTokens）。"""
        history = [UserMessage('h1'), AssistantMessage('h2'),
                   UserMessage('h3'), AssistantMessage('h4')]
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})),
             Finish(StopReason.TOOL_CALLS, Usage(2400, 600))],  # usage_tokens=3000 → ~12000 字符
            self._summary_script(),
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, tools=[make_echo()], compaction=True,
                               max_context_chars=15_000, compaction_at=0.5,
                               compaction_keep_chars=10)
        result = await runtime.run('q', history=history)
        self.assertEqual(result.status, 'done')
        self.assertTrue(result.messages[0].text.startswith('<context_summary>'))  # 压缩已触发
        self.assertFalse(any(isinstance(m, UserMessage) and m.text == 'h1' for m in result.messages))

    async def test_iterates_previous_summary(self):
        """已有摘要走 UPDATE 路径（pi previousSummary）：跨 run 从历史摘要消息恢复。"""
        old_summary = '## Goal\n旧目标已达成'
        history = [
            UserMessage(wrap_summary(old_summary)),
            UserMessage('q1 ' + 'x' * 4200), AssistantMessage('a1'),
            UserMessage('q2 ' + 'x' * 4200), AssistantMessage('a2'),
        ]
        provider = FakeProvider([
            self._summary_script('## Goal\n新目标'),
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, compaction=True,
                               max_context_chars=15_000, compaction_at=0.5,
                               compaction_keep_chars=30)
        result = await runtime.run('继续', history=history)
        self.assertEqual(result.status, 'done')
        prompt = provider.requests[0].messages[-1]['content']
        self.assertIn('<previous-summary>', prompt)
        self.assertIn('旧目标已达成', prompt)          # 旧摘要走迭代通道
        self.assertIn('[User]: q1', prompt)            # 新消息正常并入
        self.assertNotIn('[User]: <context_summary>', prompt)  # 旧摘要不重复进对话
        self.assertIn('新目标', result.messages[0].text)

    async def test_pinned_group_exempt(self):
        pinned_content = 'SKILL_RULES_' + 'P' * 6000
        history = [
            UserMessage('q0'), AssistantMessage('', '', (ToolCall('c0', 'read_skill', {}),), StopReason.TOOL_CALLS),
            ToolResultMessage('c0', 'read_skill', pinned_content, pinned=True),
            UserMessage('q1 ' + 'x' * 5400), AssistantMessage('a1'),
            UserMessage('q2 ' + 'x' * 5400), AssistantMessage('a2'),
        ]
        provider = FakeProvider([
            self._summary_script('## Goal\n摘要'),
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, compaction=True,
                               max_context_chars=30_000, compaction_at=0.5,
                               compaction_keep_chars=30)
        result = await runtime.run('继续', history=history)
        self.assertEqual(result.status, 'done')
        pinned = [m for m in result.messages if isinstance(m, ToolResultMessage) and m.pinned]
        self.assertEqual(len(pinned), 1)                      # 指令性内容整组保留
        self.assertEqual(pinned[0].content, pinned_content)
        prompt = provider.requests[0].messages[-1]['content']
        self.assertNotIn('SKILL_RULES', prompt)               # 且不进摘要序列化
        assemble('s', result.messages, max_chars=30_000)      # tool 结果仍闭合其父

    async def test_file_ops_listed_in_summary(self):
        history = [
            UserMessage('q0'), AssistantMessage('', '', (
                ToolCall('c1', 'read_file', {'path': 'notes.md'}),
                ToolCall('c2', 'write_file', {'path': 'draft.md', 'content': 'x'}),
            ), StopReason.TOOL_CALLS),
            ToolResultMessage('c1', 'read_file', '内容'),
            ToolResultMessage('c2', 'write_file', '已写入'),
            UserMessage('q1 ' + 'x' * 7800), AssistantMessage('a1'),
        ]
        provider = FakeProvider([
            self._summary_script('## Goal\n摘要'),
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, compaction=True,
                               max_context_chars=15_000, compaction_at=0.5,
                               compaction_keep_chars=30)
        result = await runtime.run('继续', history=history)
        summary_text = result.messages[0].text
        self.assertIn('<read-files>', summary_text)
        self.assertIn('notes.md', summary_text)
        self.assertIn('<modified-files>', summary_text)
        self.assertIn('draft.md', summary_text)

    async def test_summary_failure_falls_back_to_deterministic_trim(self):
        provider = FakeProvider([
            [BusinessError(20004, '摘要失败')],        # 摘要请求失败
            [TextDelta('done'), Finish(StopReason.STOP)],
        ])
        runtime = AgentRuntime(provider=provider, compaction=True,
                               max_context_chars=15_000, compaction_at=0.5,
                               compaction_keep_chars=30)
        result = await runtime.run('继续', history=self._history('x' * 3600))
        self.assertEqual(result.status, 'done')  # 失败不炸 run：回退 assemble 确定性截断
        self.assertFalse(any(isinstance(m, UserMessage) and m.text.startswith('<context_summary>')
                             for m in result.messages))


class CompactionUnitTests(unittest.TestCase):
    def test_estimate_prefers_usage(self):
        messages = [
            UserMessage('q'), AssistantMessage('a', usage_tokens=500),
            ToolResultMessage('c1', 'echo', 'x' * 400),  # trailing 按字符估
        ]
        # usage 500×4 + trailing 400 = 2400（而非全量字符 ~410）
        self.assertEqual(estimate_context_chars(messages, system_chars=100), 2500)

    def test_extract_file_ops_merges_prior(self):
        messages = [AssistantMessage('', '', (
            ToolCall('c1', 'read_file', {'path': 'b.md'}),
            ToolCall('c2', 'edit_file', {'path': 'a.md', 'edits': []}),
        ), StopReason.TOOL_CALLS)]
        read, modified = extract_file_ops(messages, prior_read=['a.md'], prior_modified=['c.md'])
        self.assertEqual(read, {'a.md', 'b.md'})
        self.assertEqual(modified, {'a.md', 'c.md'})  # a.md 修改过 → 不再算只读

    def test_serialize_truncates_tool_results(self):
        result = serialize_conversation([ToolResultMessage('c1', 'echo', 'y' * 9_000)])
        self.assertIn('[Tool result]:', result)
        self.assertIn('more characters truncated', result)
        self.assertLess(len(result), 7_200)


class ServiceComposeTests(unittest.TestCase):
    """service 层组合回归：forced_skills 无 session 的 NameError、system 段互相覆盖、
    硬编码工具清单（现由 registry 动态生成，pi visibleTools 机制）。"""

    def setUp(self):
        env = patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
                                        'DASHSCOPE_API_KEY': ''})
        env.start()
        self.addCleanup(env.stop)

    @staticmethod
    def _tool_section(system: str) -> str:
        return system.split('可用工具：\n')[1].split('\n\n')[0]

    def test_forcing_a_missing_skill_is_rejected(self):
        """forced_skills 点名不存在的技能必须显式报错，而不是静默忽略。

        （技能库当前为空——技能已按需求全删；这里覆盖的是校验路径本身。）
        """
        from app.services.agent import service
        with self.assertRaises(BusinessError):
            service.build_run_runtime(owner='u1', forced_skills=['no-such-skill'])

    def test_sections_combine_not_overwrite(self):
        """工作区提示与上传说明按序追加、互不覆盖（此前三段各自整段重写会互相吞掉）。"""
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                runtime = service.build_run_runtime(owner='u1', session_id='ses_ut')
        self.assertIn('工作区已就绪', runtime.system)

    def test_upload_workspace_section_appears(self):
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                workspace_id = service.create_workspace(owner='u1')['workspace_id']
                runtime = service.build_run_runtime(owner='u1', workspace_id=workspace_id)
        self.assertIn('工作区已就绪', runtime.system)

    def test_session_and_upload_share_one_root(self):
        """会话 + 上传共用同一个工作区根：此前各挂一套同名工具，ToolRegistry 直接构造失败。"""
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                workspace_id = service.create_workspace(owner='u1')['workspace_id']
                service.write_workspace_file(workspace_id, 'u1', 'papers/demo.md', '证据'.encode())
                runtime = service.build_run_runtime(owner='u1', session_id='ses_mix',
                                                    workspace_id=workspace_id)
                root = workspace.ensure_session_workspace('u1', 'ses_mix')
                self.assertTrue((root / 'papers' / 'demo.md').is_file())  # 上传文件挂进工作台
        self.assertEqual(sorted(runtime.registry.tools),
                         sorted(set(runtime.registry.tools)))            # 工具无重名
        self.assertIn('已挂载上传工作区的 1 个文件', runtime.system)

    def test_tool_listing_dynamic(self):
        from app.services.agent import service
        from app.services.agent import workspace
        runtime = service.build_run_runtime(owner='u1')
        section = self._tool_section(runtime.system)
        listed = sorted(line[2:].split(':', 1)[0] for line in section.splitlines()
                        if line.startswith('- '))
        self.assertEqual(listed, sorted(runtime.registry.tools))  # 清单与 registry 恒同步
        # 取证通道常驻：全文、网页正文、公开检索是研究类任务的前提，不由前端开关决定
        for name in ('read_paper', 'fetch_url', 'web_search', 'ask_user'):
            self.assertIn(name, listed)


    def test_workspace_tools_listed_when_mounted(self):
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                runtime = service.build_run_runtime(owner='u1', session_id='ses_ut2')
        section = self._tool_section(runtime.system)
        for name in ('read_file', 'write_file', 'edit_file', 'run_command'):
            self.assertIn(name, section)  # 挂载才出现
        bare = service.build_run_runtime(owner='u1')
        self.assertNotIn('- read_file', self._tool_section(bare.system))  # 未挂载不出现


class WorkPromptTests(unittest.TestCase):
    """通用 work prompt 装配（pi buildSystemPrompt 骨架：身份→工具→准则→指针）。"""

    def test_base_prompt_is_generic(self):
        from app.services.agent import service
        from app.services.agent import workspace
        # 基线不含任何具体工具名与业务准则（通用性回归：业务专属内容不进基座）
        base = service.compose_agent_system(())
        self.assertIn('ShenzhiAi', base)
        self.assertNotIn('paper_search', base)
        self.assertNotIn('[n] 引用', base)
        self.assertNotIn('研究文献综述', base)
        self.assertNotIn('可用工具', base)

    def test_current_date_injected(self):
        """环境行注入当前日期（模型无时钟，harness 供日期——环境注入机制的成员）。"""
        from datetime import datetime
        from app.services.agent import service
        base = service.compose_agent_system(())
        self.assertIn(f"当前日期：{datetime.now().strftime('%Y-%m-%d')}", base)
        runtime = service.build_run_runtime(owner='u1')
        self.assertIn('当前日期：', runtime.system)

    def test_artifact_depth_guideline_with_workspace(self):
        """制品不瘦身准则随工作区挂载注入（write_file prompt_guidelines）。"""
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                mounted = service.build_run_runtime(owner='u1', session_id='ses_depth')
        self.assertIn('不约束写入文件的内容', mounted.system)
        self.assertNotIn('不约束写入文件的内容',
                         service.build_run_runtime(owner='u1').system)

    def test_prompt_is_skeleton_only(self):
        """基座提示词只有骨架：身份 + 工具清单 + 日期。

        不照搬任何现成 agent 的准则、也不预置写作风格或工作纪律——那些由工具自己的
        prompt_guidelines 与业务侧显式注入提供（此前照抄 pi 的一套准则已移除）。
        """
        from app.services.agent import service
        runtime = service.build_run_runtime(owner='u1')
        self.assertIn('ShenzhiAi', runtime.system)
        self.assertIn('可用工具：', runtime.system)
        self.assertIn('当前日期：', runtime.system)
        for removed in ('简洁回答', '[n] 引用', '摘要级 / 全文级', '不得静默择便'):
            with self.subTest(removed=removed):
                self.assertNotIn(removed, runtime.system)

    def test_tool_guidelines_appear_only_when_mounted(self):
        from app.services.agent import service
        from app.services.agent import workspace
        bare = service.build_run_runtime(owner='u1')
        self.assertNotIn('old_text 必须与文件内容精确匹配', bare.system)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                mounted = service.build_run_runtime(owner='u1', session_id='ses_gp')
        self.assertIn('old_text 必须与文件内容精确匹配', mounted.system)   # edit 准则随挂载注入
        self.assertIn('完整重写', mounted.system)                          # write 准则
        # pi edit 准则逐条在场
        self.assertIn('合并为一次 edit_file 调用', mounted.system)
        self.assertIn('不要提交互相重叠或嵌套的替换', mounted.system)
        self.assertIn('尽量短', mounted.system)
        # v3.7 新增：read_file 替代 cat（pi "Use read instead of cat or sed"）+ 专用工具优先
        self.assertIn('不要用 run_command 的 cat/type/sed', mounted.system)
        self.assertIn('文件操作优先用专用工具', mounted.system)
        self.assertNotIn('不要用 run_command 的 cat/type/sed', bare.system)

    def test_snippet_overrides_description_gloss(self):
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                runtime = service.build_run_runtime(owner='u1', session_id='ses_gp2')
        section = self._tool_section(runtime.system)
        edit_line = next(line for line in section.splitlines() if line.startswith('- edit_file:'))
        self.assertIn('精确文本替换编辑', edit_line)  # snippet 优先于 description 截断

    @staticmethod
    def _tool_section(system: str) -> str:
        return system.split('可用工具：\n')[1].split('\n\n')[0]


class RunControlTests(unittest.IsolatedAsyncioTestCase):
    """运行控制新能力：steer、parallel 工具执行、latent 工具。"""

    async def test_steer_injected_before_next_request(self):
        call = [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)]
        provider = FakeProvider([call, call, [TextDelta('done'), Finish(StopReason.STOP)]])
        channel = RunChannel()
        events = []

        def steer_after_first_tool(event):
            events.append(event)
            if event.name == 'tool_end' and not event.data['is_error'] and not channel.has_pending():
                channel.steer('换个方向查')

        runtime = AgentRuntime(provider=provider, tools=[make_echo()])
        result = await runtime.run('q', on_event=steer_after_first_tool, channel=channel)
        self.assertEqual(result.status, 'done')
        self.assertEqual(result.turns, 3)  # 插话没有打断工具轮，只是多了一轮
        texts = [m['content'] for m in provider.requests[1].messages if m['role'] == 'user']
        self.assertIn('换个方向查', texts)
        self.assertTrue(any(isinstance(m, UserMessage) and m.text == '换个方向查'
                            for m in result.messages))
        self.assertTrue(any(e.name == 'message' and e.data.get('kind') == 'steer' for e in events))

    async def test_parallel_tool_execution(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'a'})),
             ToolCallEvent(ToolCall('c2', 'echo', {'value': 'b'})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('done'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo(delay=0.2)],
                               tool_execution='parallel')
        started = time.monotonic()
        result = await runtime.run('q')
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, 'done')
        self.assertLess(elapsed, 0.35)  # 并发：两个 0.2s 的调用总耗时 < 串行的 0.4s
        contents = [m.content for m in result.messages if isinstance(m, ToolResultMessage)]
        self.assertEqual(contents, ['echo:a', 'echo:b'])  # 结果按调用顺序回填

    async def test_sequential_tool_marker_forces_batch_sequential(self):
        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'echo', {'value': 'a'})),
             ToolCallEvent(ToolCall('c2', 'echo', {'value': 'b'})),
             Finish(StopReason.TOOL_CALLS)],
            [TextDelta('done'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[make_echo(delay=0.2, name='echo')],
                               tool_execution='parallel')
        runtime.registry.tools['echo'].spec  # noqa - 只确认注册
        # 把 echo 标记为 sequential（pi executionMode 覆盖）
        object.__setattr__(runtime.registry.tools['echo'].spec, 'execution_mode', 'sequential')
        started = time.monotonic()
        result = await runtime.run('q')
        elapsed = time.monotonic() - started
        self.assertEqual(result.status, 'done')
        self.assertGreaterEqual(elapsed, 0.38)  # 整批退回顺序执行

    async def test_latent_tool_enabled_by_result(self):
        @tool(name='unlock', description='解锁工具', params=EchoParams)
        async def unlock(args):
            return ToolOutput(content='已解锁', added_tool_names=('hidden',))

        @tool(name='hidden', description='隐藏工具')
        async def hidden():
            return 'hidden ok'

        provider = FakeProvider([
            [ToolCallEvent(ToolCall('c1', 'unlock', {'value': 'x'})), Finish(StopReason.TOOL_CALLS)],
            [ToolCallEvent(ToolCall('c2', 'hidden', {})), Finish(StopReason.TOOL_CALLS)],
            [TextDelta('done'), Finish(StopReason.STOP)]])
        runtime = AgentRuntime(provider=provider, tools=[unlock, hidden], latent_tools=('hidden',))
        self.assertNotIn('hidden', runtime.registry.enabled)  # 初始 latent
        first_wire = {t['function']['name'] for t in runtime.registry.wire()}
        self.assertNotIn('hidden', first_wire)
        result = await runtime.run('q')
        self.assertEqual(result.status, 'done')
        self.assertIn('hidden', runtime.registry.enabled)  # 由结果启用
        second_wire = {t['function']['name'] for t in
                       [t for t in provider.requests[1].tools]}
        self.assertIn('hidden', second_wire)  # 下一轮 wire 出现
        self.assertIn('hidden ok', [m.content for m in result.messages
                                    if isinstance(m, ToolResultMessage)])


class ProviderObservabilityTests(unittest.IsolatedAsyncioTestCase):
    """重试退避与 wire 层观测钩子（pi maxRetryDelayMs / onPayload / onResponse）。"""

    @staticmethod
    def sse_text(text):
        return (f'data: {json.dumps({"choices": [{"delta": {"content": text}}]})}\n\n'
                'data: [DONE]\n\n')

    async def test_retry_backoff_and_max_retries(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(503, json={'error': 'down'})

        provider = OpenAICompatProvider(CONFIG, transport=httpx.MockTransport(handler),
                                        retry_delay=0.01, max_retries=3, max_retry_delay=0.02)
        with self.assertRaises(BusinessError):
            async for _ in provider.stream(ModelRequest('deepseek-chat', [])):
                pass
        self.assertEqual(len(calls), 4)  # 首次 + 3 次重试

    async def test_on_payload_and_on_response_hooks(self):
        payloads, responses = [], []

        provider = OpenAICompatProvider(
            CONFIG,
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, text=self.sse_text('hi'), headers={'content-type': 'text/event-stream'})),
            on_payload=payloads.append, on_response=responses.append)
        events = []
        async for event in provider.stream(ModelRequest('deepseek-chat',
                                                         [{'role': 'user', 'content': 'q'}])):
            events.append(event)
        self.assertEqual(payloads[0]['model'], 'deepseek-chat')      # 发出的 payload
        self.assertEqual(responses[0]['choices'][0]['delta']['content'], 'hi')  # 首帧
        self.assertTrue(any(isinstance(e, TextDelta) and e.text == 'hi' for e in events))

    async def test_observation_hook_error_never_breaks_request(self):
        def bad_hook(data):
            raise RuntimeError('observer boom')

        provider = OpenAICompatProvider(
            CONFIG,
            transport=httpx.MockTransport(lambda request: httpx.Response(
                200, text=self.sse_text('ok'), headers={'content-type': 'text/event-stream'})),
            on_payload=bad_hook, on_response=bad_hook)
        events = []
        async for event in provider.stream(ModelRequest('deepseek-chat', [])):
            events.append(event)
        self.assertTrue(any(isinstance(e, TextDelta) for e in events))  # 观测异常不影响请求


class ProjectContextTests(unittest.TestCase):
    """工作区项目指令注入（pi contextFiles / AGENTS.md 机制）。"""

    def setUp(self):
        env = patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test', 'DEEPSEEK_MODEL': 'deepseek-chat',
                                        'DASHSCOPE_API_KEY': ''})
        env.start()
        self.addCleanup(env.stop)

    def test_agents_md_wrapped_and_injected(self):
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                root = service.ensure_session_workspace('u1', 'ses_pc')
                (root / 'AGENTS.md').write_text('# 项目规范\n只用中文写作', encoding='utf-8')
                runtime = service.build_run_runtime(owner='u1', session_id='ses_pc')
        self.assertIn('<project_context>', runtime.system)
        self.assertIn('<project_instructions path="AGENTS.md">', runtime.system)
        self.assertIn('只用中文写作', runtime.system)

    def test_absent_when_no_file(self):
        from app.services.agent import service
        from app.services.agent import workspace
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(workspace, 'WORKSPACE_ROOT', Path(tmp)):
                service.ensure_session_workspace('u1', 'ses_pc2')
                runtime = service.build_run_runtime(owner='u1', session_id='ses_pc2')
        self.assertNotIn('<project_context>', runtime.system)


if __name__ == '__main__':
    unittest.main()
