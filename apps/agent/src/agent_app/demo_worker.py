"""Explicit, offline M1 demonstration Worker. Uses the normal persisted Control path."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid

from agent_app.errors import BusinessError
from agent_app.execution.types import AgentEvent, AssistantMessage, RunResult, StopReason, UserMessage
from agent_app.extensions.workspace import Workspace, ensure_session_workspace
from agent_app.worker.host import run_worker_forever

DEMO_WARNING = 'Mock 演示：受控模拟执行，未调用真实模型或检索服务，不构成科研结论。'


class DemoRuntime:
    strict_tool_budget = True

    def __init__(self, *, owner, session_id, mode, model, forced_skills=(), **_):
        if model != 'demo/m1' or not session_id:
            raise ValueError('Mock Worker 只接受 demo/m1 模型和产品 Session 任务')
        self.owner, self.session_id = owner, session_id
        self.report = mode == 'deep' or 'deep-research' in forced_skills

    async def run(self, prompt, *, history, stop, on_event, channel):
        started = time.monotonic()
        seq = 0
        messages = [*history, UserMessage(prompt)]

        def emit(event_name, **data):
            nonlocal seq
            seq += 1
            on_event(AgentEvent(seq, 1, event_name, {'turn': 1, **data}))

        emit('meta', warnings=[DEMO_WARNING])
        emit('delta', text='', reasoning='正在演示问题分析、过程事件与结果交付。')
        # Enough time to refresh or switch Sessions while events are in flight.
        steps = 4 if prompt.startswith(('[失败]', '[超时]')) else 32
        for _ in range(steps):
            await asyncio.sleep(0.5)
            for message in channel.drain_steering():
                messages.append(message)
                emit('message', kind='steer', text=message.text)
            if stop.is_set():
                result = RunResult(stop_reason=StopReason.CANCELLED, final_text='Mock 演示已停止。')
                break
        else:
            if prompt.startswith('[失败]'):
                result = RunResult(stop_reason=StopReason.ERROR,
                                   error=BusinessError(20004, 'Mock 演示：模拟上游服务不可用，请稍后重试。'))
            elif prompt.startswith('[超时]'):
                result = RunResult(stop_reason=StopReason.TIMEOUT,
                                   final_text='Mock 演示：任务达到模拟时间上限。')
            else:
                text = f'Mock 演示已完成：{prompt[:200]}。可刷新页面或切换会话验证历史恢复。'
                output = None
                if self.report:
                    report = ('# Mock 演示研究报告\n\n> ' + DEMO_WARNING
                              + '\n\n## 研究问题\n\n' + prompt
                              + '\n\n## 方法对比（示意）\n\n| 方案 | 评估方向 |\n| --- | --- |\n'
                              + '| LoRA | 参数效率与效果 |\n| QLoRA | 显存占用与量化误差 |\n'
                              + '\n## 后续工作\n\n真实结论需要经授权的模型与检索服务验证。本演示没有真实文献来源。\n')
                    path = f'reports/m1-demo-{uuid.uuid4().hex}.md'
                    emit('tool_call', tool_call_id='demo-write', name='write_file',
                         arguments=json.dumps({'path': path}))
                    workspace = Workspace(ensure_session_workspace(self.owner, self.session_id))
                    target = workspace.resolve(path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(report.encode('utf-8'))
                    emit('tool_end', tool_call_id='demo-write', name='write_file', is_error=False,
                         duration_ms=1, summary='已保存 Mock 演示报告')
                    output = {'kind': 'report', 'report': report, 'report_path': path, 'sources': []}
                emit('delta', text=text, reasoning='')
                result = RunResult(stop_reason=StopReason.STOP, final_text=text, output=output)
        messages.append(AssistantMessage(content=result.final_text, stop_reason=result.stop_reason))
        result.messages = messages
        result.turns = 1
        result.tool_calls = 1 if result.output else 0
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result


def main():
    if os.getenv('AGENT_DEMO_MODE') != '1':
        raise RuntimeError('请通过隔离演示启动器运行；需要 AGENT_DEMO_MODE=1')
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_forever(runtime_factory=DemoRuntime))


if __name__ == '__main__':
    main()
