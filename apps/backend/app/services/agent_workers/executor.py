"""One execution attempt through the existing Agent application and runtime."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from app.services.agent_contracts.runs import ExecutionReport, RunRequest, report_from_result

if TYPE_CHECKING:
    from app.services.agent.execution.runtime import AgentRuntime
    from app.services.agent.execution.types import RunResult


class RuntimeDriver(Protocol):
    async def run(self, prompt: str, *, stop: asyncio.Event) -> RunResult: ...


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

    def __init__(self, runtime_factory: Callable[[RunRequest], RuntimeDriver] = _application_runtime):
        self._runtime_factory = runtime_factory
        self._stops: dict[str, asyncio.Event] = {}

    async def execute(self, request: RunRequest) -> ExecutionReport:
        if request.session_id is not None:
            raise NotImplementedError('Session-bound tasks require durable Task/Run/Turn coordination')
        if any(value is not None for value in (
            request.budget.max_duration_s, request.budget.max_tool_calls,
            request.budget.max_model_tokens,
        )):
            raise NotImplementedError('Authorized platform limits are not wired to the runtime yet')
        if request.run_id in self._stops:
            raise ValueError(f'Run already executing: {request.run_id}')
        stop = asyncio.Event()
        self._stops[request.run_id] = stop
        try:
            runtime = self._runtime_factory(request)
            result = await runtime.run(request.prompt, stop=stop)
            return report_from_result(request, result)
        finally:
            self._stops.pop(request.run_id, None)

    async def request_cancel(self, run_id: str) -> None:
        stop = self._stops.get(run_id)
        if stop is not None:
            stop.set()
