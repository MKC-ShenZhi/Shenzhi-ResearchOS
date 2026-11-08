"""Public contract and fake-side wiring without model, database or Redis."""
from __future__ import annotations

import asyncio
import unittest

from app.services.agent_contracts import (
    BudgetLimits, RunRecord, RunRequest, RunStatus, TaskRecord, TaskStatus, TaskSubmission,
)
from app.services.agent_contracts.events import PlatformEvent
from app.services.agent_contracts.protocols import BudgetManager, Dispatcher, TaskManager, WorkerExecutor
from app.services.agent_contracts.runs import report_from_result
from app.services.agent.execution.types import AgentEvent, RunResult, StopReason
from app.services.agent_workers import ApplicationWorkerExecutor


class FakeControl:
    def __init__(self) -> None:
        self.task: TaskRecord | None = None
        self.report = None

    async def submit(self, submission: TaskSubmission) -> TaskRecord:
        self.task = TaskRecord('task-1', submission, TaskStatus.QUEUED)
        return self.task

    async def get(self, task_id: str, owner_id: str) -> TaskRecord:
        assert self.task is not None and self.task.task_id == task_id
        assert self.task.owner_id == owner_id
        return self.task

    async def create_run(self, task_id: str, owner_id: str,
                         limits: BudgetLimits) -> RunRequest:
        task = await self.get(task_id, owner_id)
        return RunRequest('run-1', task.task_id, task.owner_id,
                          task.submission.prompt, budget=limits)

    async def pause(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def resume(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def request_cancel(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def record_report(self, report) -> TaskRecord:
        self.report = report
        return await self.get(report.task_id, 'user:1')

    async def get_report(self, run_id: str, owner_id: str):
        return self.report if self.report and self.report.run_id == run_id else None

    async def authorize(self, task: TaskRecord) -> BudgetLimits:
        return BudgetLimits()

    async def record_usage(self, report) -> None:
        self.report = report


class FakeDispatcher:
    def __init__(self) -> None:
        self.requests: list[RunRequest] = []

    async def submit(self, request: RunRequest) -> None:
        self.requests.append(request)

    async def request_cancel(self, task_id: str, run_id: str) -> None:
        return None


class FakeRuntime:
    async def run(self, prompt: str, *, stop: asyncio.Event) -> RunResult:
        return RunResult(stop_reason=StopReason.CANCELLED if stop.is_set() else StopReason.STOP,
                         final_text=prompt, prompt_tokens=3, completion_tokens=4)


class BlockingRuntime:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, prompt: str, *, stop: asyncio.Event) -> RunResult:
        self.started.set()
        await stop.wait()
        return RunResult(stop_reason=StopReason.CANCELLED)


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_sides_connect_without_shared_implementation(self) -> None:
        control = FakeControl()
        task_manager: TaskManager = control
        budget_manager: BudgetManager = control
        dispatcher: Dispatcher = FakeDispatcher()
        worker: WorkerExecutor = ApplicationWorkerExecutor(lambda _request: FakeRuntime())
        task = await task_manager.submit(TaskSubmission(owner_id='user:1', prompt='research'))
        limits = await budget_manager.authorize(task)
        request = await task_manager.create_run(task.task_id, task.owner_id, limits)
        await dispatcher.submit(request)
        report = await worker.execute(dispatcher.requests.pop())
        await task_manager.record_report(report)
        await budget_manager.record_usage(report)
        self.assertEqual(report.status, RunStatus.COMPLETED)
        self.assertEqual((await task_manager.get_report('run-1', 'user:1')).status,
                         RunStatus.COMPLETED)
        self.assertEqual(report.usage.model_tokens, 7)
        self.assertIs(report.result.stop_reason, StopReason.STOP)
        self.assertIsNotNone(task.created_at.tzinfo)
        self.assertEqual(RunRecord(request, attempt=1).status, RunStatus.PENDING)

    async def test_unsupported_work_is_rejected_explicitly(self) -> None:
        worker = ApplicationWorkerExecutor(lambda _request: FakeRuntime())
        with self.assertRaises(NotImplementedError):
            await worker.execute(RunRequest('run-1', 'task-1', 'user:1', 'prompt',
                                            session_id='ses-1'))
        with self.assertRaises(NotImplementedError):
            await worker.execute(RunRequest('run-2', 'task-1', 'user:1', 'prompt',
                                            budget=BudgetLimits(max_model_tokens=10)))

    async def test_local_cancel_reaches_existing_runtime(self) -> None:
        runtime = BlockingRuntime()
        worker = ApplicationWorkerExecutor(lambda _request: runtime)
        request = RunRequest('run-1', 'task-1', 'user:1', 'prompt')
        running = asyncio.create_task(worker.execute(request))
        await runtime.started.wait()
        await worker.request_cancel(request.run_id)
        report = await running
        self.assertEqual(report.status, RunStatus.CANCELLED)

    def test_runtime_events_and_results_are_authoritative(self) -> None:
        event = AgentEvent(seq=2, turn=1, name='delta', data={'text': 'hello'})
        envelope = PlatformEvent('task-1', 'run-1', event)
        self.assertEqual((envelope.sequence, envelope.name), (event.seq, event.name))
        request = RunRequest('run-1', 'task-1', 'user:1', 'prompt')
        report = report_from_result(request, RunResult(stop_reason=StopReason.TIMEOUT))
        self.assertEqual(report.status, RunStatus.TIMED_OUT)
        with self.assertRaises(ValueError):
            BudgetLimits(max_duration_s=0)
        with self.assertRaises(ValueError):
            RunRecord(request, attempt=0)


if __name__ == '__main__':
    unittest.main()
