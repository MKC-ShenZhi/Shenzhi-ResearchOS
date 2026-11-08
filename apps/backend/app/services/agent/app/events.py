"""Bridge Agent runtime events to product streams and controls."""
from __future__ import annotations

import asyncio

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

from app.core.errors import BusinessError
from app.services.agent.execution.runtime import AgentRuntime
from app.services.agent.execution.types import (
    AgentEvent, AgentMessage, RUN_START, RunChannel, RunResult, StopReason,
)
from app.services.agent.extensions.workspace import ensure_session_workspace, read_session_file


# ---- 事件流桥接 ----

# 运行中的控制通道（run_id → owner/channel/stop）：单进程内 SSE run 的插话与停止入口。
# run 结束（含消费者断开取消）由 worker 的 finally 摘除，绝不泄漏。
_active_channels: dict[str, tuple[str | None, RunChannel, asyncio.Event]] = {}


def steer_run(run_id: str, text: str, owner: str | None = None) -> bool:
    """向运行中的 run 插话（下一模型请求前注入）；run 不存在返回 False。"""
    active = _active_channels.get(run_id)
    if active is None or (owner is not None and active[0] != owner):
        return False
    active[1].steer(text)
    return True


def stop_run(run_id: str, owner: str | None = None) -> bool:
    """Request a clean stop so the runtime can close and persist its partial transcript."""
    active = _active_channels.get(run_id)
    if active is None or (owner is not None and active[0] != owner):
        return False
    active[2].set()
    return True


def _latest_report_path(owner: str, session_id: str, result: Any) -> str | None:
    """找出本次 run 写出的报告文件路径。

    优先取工具调用记录里**最后一次 write_file / edit_file 的目标**——那是模型自己认定的交付物；
    没有记录时退回扫描会话工作区里最大的 markdown 文件（报告通常是最大的那个）。
    """
    from app.services.agent.execution.types import AssistantMessage
    candidate = ''
    for message in getattr(result, 'messages', ()) or ():
        if not isinstance(message, AssistantMessage):
            continue
        for call in message.tool_calls:
            if call.name not in ('write_file', 'edit_file'):
                continue
            path = ''
            if isinstance(call.arguments, dict):
                path = str(call.arguments.get('path') or '')
                if not path:
                    edits = call.arguments.get('edits')
                    if isinstance(edits, list) and edits and isinstance(edits[0], dict):
                        path = str(edits[0].get('path') or '')
            if path.lower().endswith(('.md', '.markdown')):
                candidate = path
    if candidate:
        return candidate
    try:
        root = ensure_session_workspace(owner, session_id)
    except (OSError, BusinessError):
        return None
    best, best_size = None, 0
    for path in root.rglob('*.md'):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > best_size:
            best, best_size = path.relative_to(root).as_posix(), size
    return best


async def run_events(runtime: AgentRuntime, prompt: str, history: Sequence[AgentMessage] = (),
                     meta: dict | None = None, *, owner: str | None = None,
                     session_id: str | None = None,
                     on_complete: Callable[[RunResult], Awaitable[None]] | None = None,
                     ) -> AsyncIterator[tuple[str, dict]]:
    """把 runtime.run 桥接为 (事件名, data) 流；先发 meta（如附件告警），末尾发 result。

    消费方断开时（生成器被关闭）取消运行任务并跳过 result——客户端已不在。
    运行期间持有 RunChannel 并按 run_id 注册，供 steer_run 插话。
    owner/session_id 由调用方显式传入（此前直接引用不存在的名字，报告回填一走到就 NameError）：
    报告全文读回需要它们，而它们在 run 时不可从 runtime 反查。
    """
    queue: asyncio.Queue = asyncio.Queue()
    box: dict[str, RunResult] = {}
    channel = RunChannel()
    stop_event = asyncio.Event()

    async def worker() -> None:
        def on_event(event: AgentEvent) -> None:
            if event.name == RUN_START:
                _active_channels[event.data['run_id']] = (owner, channel, stop_event)
            queue.put_nowait(event)
        try:
            result = await runtime.run(prompt, history=history, on_event=on_event,
                                       stop=stop_event, channel=channel)
            # 报告制品的回填（B 方案）：技能要求报告落盘成工作区文件，而模型回复里只给摘要与路径。
            if session_id and not (result.output or {}).get('report'):
                report_path = _latest_report_path(owner, session_id, result)
                if report_path:
                    try:
                        content, _ = read_session_file(owner, session_id, report_path)
                        result.output = {**(result.output or {}), 'kind': 'report',
                                         'report': content.decode('utf-8', 'replace'),
                                         'report_path': report_path}
                    except (OSError, BusinessError):
                        pass
            box['result'] = result
        finally:
            for key, registered in list(_active_channels.items()):
                if registered[1] is channel:
                    _active_channels.pop(key, None)
            await queue.put(None)

    task = asyncio.create_task(worker())
    try:
        if meta:
            yield ('meta', meta)
        while True:
            event = await queue.get()
            if event is None:
                break
            yield (event.name, {'turn': event.turn, **event.data})
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    result = box.get('result') or RunResult(stop_reason=StopReason.CANCELLED)
    # Persist only after every queued event has passed through the consumer. Session callers
    # build their UI timeline while consuming those events; completing inside ``worker`` can
    # otherwise race ahead and store a truncated timeline for very fast runs.
    if on_complete is not None:
        await on_complete(result)
    yield ('result', {
        'status': result.status,
        'stop_reason': result.stop_reason.value,  # 前端据此区分"到点了"与"你停的"
        'final_text': result.final_text,
        'output': result.output,
        # 等待用户回答时把问题提到顶层：调用方不必理解 output 的判别联合就能渲染选项
        'question': result.question,
        'turns': result.turns,
        'duration_ms': result.duration_ms,
        'prompt_tokens': result.prompt_tokens,
        'completion_tokens': result.completion_tokens,
        'truncated': result.truncated,
        'error': ({'code': result.error.code, 'message': result.error.message}
                  if result.error else None),
    })
