"""One execution attempt through the existing Agent application and runtime."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from app.services.agent_contracts.runs import ExecutionReport, RunRequest, report_from_result
from app.services.agent_contracts.events import PlatformEvent
from app.services.agent_contracts.protocols import EventSink
from app.services.agent.execution.types import AgentEvent

if TYPE_CHECKING:
    from app.services.agent.execution.runtime import AgentRuntime
    from app.services.agent.execution.types import RunResult


class RuntimeDriver(Protocol):
    async def run(self, prompt: str, *, stop: asyncio.Event,
                  on_event: Callable[[AgentEvent], None] | None = None) -> RunResult: ...


def _application_runtime(request: RunRequest) -> AgentRuntime:
    from app.services.agent.service import build_run_runtime

    return build_run_runtime(
        owner=request.owner_id, model=request.model, mode=request.mode,
        workspace_id=request.workspace_id, forced_skills=request.skills,
        allow_shell=False,
    )


class ApplicationWorkerExecutor:
    """In-process adapter for WorkerExecutor; no queue or durable claim is implied.

    Session-bound work needs a durable Task/Run/Turn mapping before this adapter can
    execute it. Explicit limits cannot silently override application policy.
    """

    def __init__(self, runtime_factory: Callable[[RunRequest], RuntimeDriver] = _application_runtime,
                 event_sink: EventSink | None = None):
        self._runtime_factory = runtime_factory
        self._event_sink = event_sink
        self._stops: dict[str, asyncio.Event] = {}

    async def execute(self, request: RunRequest) -> ExecutionReport:
        if request.session_id is not None:
            raise NotImplementedError('Session-bound tasks require durable Task/Run/Turn coordination')
        if request.budget.max_model_tokens is not None:
            raise NotImplementedError('Model token limit cannot be enforced reliably by the provider')
        if request.run_id in self._stops:
            raise ValueError(f'Run already executing: {request.run_id}')
        stop = asyncio.Event()
        self._stops[request.run_id] = stop
        try:
            runtime = self._runtime_factory(request)
            if request.budget.max_duration_s is not None:
                if not hasattr(runtime, 'deadline_s'):
                    raise NotImplementedError('Runtime has no enforceable duration limit')
                runtime.deadline_s = min(runtime.deadline_s, request.budget.max_duration_s)
                runtime.deadline_grace_s = 0
            if request.budget.max_tool_calls is not None:
                if not hasattr(runtime, 'max_tool_calls'):
                    raise NotImplementedError('Runtime has no tool dispatch guard')
                runtime.max_tool_calls = min(runtime.max_tool_calls, request.budget.max_tool_calls) if runtime.max_tool_calls is not None else request.budget.max_tool_calls
                runtime.strict_tool_budget = True
            queue: asyncio.Queue[PlatformEvent | None] = asyncio.Queue()
            failure: BaseException | None = None
            async def publish() -> None:
                nonlocal failure
                while (event := await queue.get()) is not None:
                    if failure is None:
                        try:
                            await self._event_sink.publish(event)  # type: ignore[union-attr]
                        except Exception as exc:
                            failure = exc
                            stop.set()
                    queue.task_done()
                queue.task_done()
            publisher = asyncio.create_task(publish()) if self._event_sink is not None else None
            last_seq = 0
            def on_event(event: AgentEvent) -> None:
                nonlocal last_seq, failure
                if event.seq <= last_seq:
                    failure = ValueError('Runtime event seq must increase within a Run')
                    stop.set()
                    return
                last_seq = event.seq
                queue.put_nowait(PlatformEvent(request.task_id, request.run_id, event))
            try:
                result = await runtime.run(request.prompt, stop=stop,
                                           on_event=on_event if publisher is not None else None)
            finally:
                if publisher is not None:
                    queue.put_nowait(None)
                    try:
                        await asyncio.shield(publisher)
                    except asyncio.CancelledError:
                        stop.set()
                        await publisher
                        raise
            if failure is not None:
                raise RuntimeError('Platform event delivery failed') from failure
            return report_from_result(request, result)
        finally:
            self._stops.pop(request.run_id, None)

    async def request_cancel(self, run_id: str) -> None:
        stop = self._stops.get(run_id)
        if stop is not None:
            stop.set()
