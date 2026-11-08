"""Public contract and fake-side wiring without model, database or Redis."""
from __future__ import annotations

import asyncio
import unittest

from app.core.errors import BusinessError
from app.services.agent_contracts import (
    BudgetLimits, ExecutionReport, RunRecord, RunRequest, RunStatus, TaskRecord,
    TaskStatus, TaskSubmission, UsageReport,
)
from app.services.agent_contracts.events import PlatformEvent
from app.services.agent_contracts.protocols import (
    BudgetManager, Dispatcher, EventSink, RunReporter, TaskManager, WorkerExecutor,
)
from app.services.agent_contracts.runs import report_from_result
from app.services.agent.execution.types import AgentEvent, RunResult, StopReason
from app.services.agent_workers import ApplicationWorkerExecutor


class FakeControl:
    def __init__(self) -> None:
        self.task: TaskRecord | None = None
        self.last_report: ExecutionReport | None = None
        self.runs: list[RunRecord] = []
        self.reports: dict[str, ExecutionReport] = {}

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
        attempt = len(self.runs) + 1
        request = RunRequest(f'run-{attempt}', task.task_id, task.owner_id,
                             task.submission.prompt, session_id=task.session_id,
                             turn_id=task.turn_id, budget=limits)
        self.runs.append(RunRecord(request, attempt=attempt))
        return request

    async def pause(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def resume(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def request_cancel(self, task_id: str, owner_id: str) -> TaskRecord:
        return await self.get(task_id, owner_id)

    async def record_report(self, report) -> TaskRecord:
        if report.run_id in self.reports:
            if self.reports[report.run_id] != report:
                raise ValueError('conflicting report')
            return await self.get(report.task_id, 'user:1')
        self.last_report = report
        self.reports[report.run_id] = report
        return await self.get(report.task_id, 'user:1')

    async def get_report(self, run_id: str, owner_id: str):
        assert self.task is not None and self.task.owner_id == owner_id
        return self.reports.get(run_id)

    async def report(self, report: ExecutionReport) -> None:
        await self.record_report(report)

    async def authorize(self, task: TaskRecord) -> BudgetLimits:
        return BudgetLimits()

    async def record_usage(self, report) -> None:
        self.last_report = report


class FakeDispatcher:
    def __init__(self) -> None:
        self.requests: list[RunRequest] = []

    async def submit(self, request: RunRequest) -> None:
        self.requests.append(request)

    async def request_cancel(self, task_id: str, run_id: str) -> None:
        return None


class FakeEventSink:
    def __init__(self) -> None:
        self.events: list[PlatformEvent] = []

    async def publish(self, event: PlatformEvent) -> None:
        self.events.append(event)


class FakeExecution:
    async def execute(self, request: RunRequest) -> ExecutionReport:
        return report_from_result(request, RunResult(stop_reason=StopReason.STOP,
                                                     final_text=request.prompt))

    async def request_cancel(self, run_id: str) -> None:
        return None


class FakeRuntime:
    async def run(self, prompt: str, *, stop: asyncio.Event, on_event=None) -> RunResult:
        if on_event:
            on_event(AgentEvent(1, 0, 'run_start', {}))
        return RunResult(stop_reason=StopReason.CANCELLED if stop.is_set() else StopReason.STOP,
                         final_text=prompt, prompt_tokens=3, completion_tokens=4,
                         usage_measured=True, tool_calls=0)


class BlockingRuntime:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, prompt: str, *, stop: asyncio.Event, on_event=None) -> RunResult:
        self.started.set()
        await stop.wait()
        return RunResult(stop_reason=StopReason.CANCELLED)


class EmittingRuntime:
    async def run(self, prompt: str, *, stop: asyncio.Event, on_event=None) -> RunResult:
        for seq in (1, 2, 3):
            if on_event:
                on_event(AgentEvent(seq, 1, 'delta', {'text': str(seq)}))
        await asyncio.sleep(0)
        return RunResult(stop_reason=StopReason.STOP, tool_calls=0)


class SlowSink(FakeEventSink):
    async def publish(self, event: PlatformEvent) -> None:
        await asyncio.sleep(0.01)
        await super().publish(event)


class FailingSink(FakeEventSink):
    async def publish(self, event: PlatformEvent) -> None:
        raise RuntimeError('sink unavailable')


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_delivery_is_ordered_and_drained_before_report(self) -> None:
        sink = SlowSink()
        worker = ApplicationWorkerExecutor(lambda _: EmittingRuntime(), sink)
        for run_id in ('run-1', 'run-2'):
            report = await worker.execute(RunRequest(run_id, 'task-1', 'user:1', 'x'))
            self.assertEqual(report.status, RunStatus.COMPLETED)
            self.assertEqual([e.seq for e in sink.events[-3:]], [1, 2, 3])
        self.assertEqual(len({e.event_key for e in sink.events}), 6)
        self.assertTrue(all(e.occurred_at.tzinfo for e in sink.events))

    async def test_event_failure_prevents_success_report(self) -> None:
        worker = ApplicationWorkerExecutor(lambda _: EmittingRuntime(), FailingSink())
        with self.assertRaisesRegex(RuntimeError, 'delivery failed'):
            await worker.execute(RunRequest('run-1', 'task-1', 'user:1', 'x'))

    async def test_unknown_usage_is_not_zero(self) -> None:
        report = await ApplicationWorkerExecutor(lambda _: EmittingRuntime()).execute(
            RunRequest('run-1', 'task-1', 'user:1', 'x'))
        self.assertIsNone(report.usage.model_tokens)
        self.assertEqual(report.usage.tool_calls, 0)

    async def test_unsupported_budget_rejected_before_run(self) -> None:
        worker = ApplicationWorkerExecutor(lambda _: EmittingRuntime())
        with self.assertRaises(NotImplementedError):
            await worker.execute(RunRequest('run-1', 'task-1', 'user:1', 'x',
                                            budget=BudgetLimits(max_tool_calls=1)))

    async def test_two_sides_connect_without_shared_implementation(self) -> None:
        control = FakeControl()
        task_manager: TaskManager = control
        budget_manager: BudgetManager = control
        dispatcher: Dispatcher = FakeDispatcher()
        event_sink: EventSink = FakeEventSink()
        run_reporter: RunReporter = control
        worker: WorkerExecutor = ApplicationWorkerExecutor(lambda _request: FakeRuntime(), event_sink)
        task = await task_manager.submit(TaskSubmission(owner_id='user:1', prompt='research'))
        limits = await budget_manager.authorize(task)
        request = await task_manager.create_run(task.task_id, task.owner_id, limits)
        await dispatcher.submit(request)
        report = await worker.execute(dispatcher.requests.pop())
        await run_reporter.report(report)
        self.assertEqual(report.status, RunStatus.COMPLETED)
        self.assertEqual((await task_manager.get_report('run-1', 'user:1')).status,
                         RunStatus.COMPLETED)
        self.assertEqual(report.usage.model_tokens, 7)
        self.assertEqual(event_sink.events[0].event_key, ('run-1', 1))
        self.assertIs(report.result.stop_reason, StopReason.STOP)
        self.assertIsNotNone(task.created_at.tzinfo)
        self.assertEqual(RunRecord(request, attempt=1).status, RunStatus.PENDING)
        await run_reporter.report(report)
        with self.assertRaises(ValueError):
            await run_reporter.report(ExecutionReport(report.run_id, report.task_id, RunStatus.FAILED))

    async def test_unsupported_work_is_rejected_explicitly(self) -> None:
        worker = ApplicationWorkerExecutor(lambda _request: FakeRuntime())
        with self.assertRaises(NotImplementedError):
            await worker.execute(RunRequest('run-1', 'task-1', 'user:1', 'prompt',
                                            session_id='ses-1', turn_id='turn-1'))
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

    async def test_session_bound_task_and_run_share_both_links(self) -> None:
        control: TaskManager = FakeControl()
        task = await control.submit(TaskSubmission(owner_id='user:1', prompt='research',
                                                   session_id='ses-1', turn_id='turn-1'))
        request = await control.create_run(task.task_id, task.owner_id, BudgetLimits())
        self.assertEqual((task.session_id, task.turn_id), ('ses-1', 'turn-1'))
        self.assertEqual((request.task_id, request.session_id, request.turn_id),
                         (task.task_id, 'ses-1', 'turn-1'))

    def test_session_and_turn_must_be_provided_together(self) -> None:
        for session_id, turn_id in (('ses-1', None), (None, 'turn-1')):
            with self.subTest(session_id=session_id, turn_id=turn_id):
                with self.assertRaises(ValueError):
                    TaskSubmission(owner_id='user:1', prompt='research',
                                   session_id=session_id, turn_id=turn_id)
                with self.assertRaises(ValueError):
                    RunRequest('run-1', 'task-1', 'user:1', 'research',
                               session_id=session_id, turn_id=turn_id)

    def test_task_submission_preserves_legacy_positional_arguments(self) -> None:
        for session_id in (None, 'ses-1'):
            with self.subTest(session_id=session_id):
                turn_kwargs = {} if session_id is None else {'turn_id': 'turn-1'}
                submission = TaskSubmission('user:1', 'research', session_id,
                                            'input-1', 'idem-1', **turn_kwargs)
                self.assertEqual((submission.owner_id, submission.prompt,
                                  submission.session_id, submission.input_ref,
                                  submission.idempotency_key),
                                 ('user:1', 'research', session_id, 'input-1', 'idem-1'))
                self.assertEqual(submission.turn_id,
                                 None if session_id is None else 'turn-1')

    def test_run_request_preserves_legacy_positional_arguments(self) -> None:
        limits = BudgetLimits(max_model_tokens=10)
        for session_id in (None, 'ses-1'):
            with self.subTest(session_id=session_id):
                turn_kwargs = {} if session_id is None else {'turn_id': 'turn-1'}
                request = RunRequest('run-1', 'task-1', 'user:1', 'research',
                                     session_id, 'deep', 'model-1', 'workspace-1',
                                     ('skill-1',), limits, 'input-1', **turn_kwargs)
                self.assertEqual((request.run_id, request.task_id, request.owner_id,
                                  request.prompt, request.session_id, request.mode,
                                  request.model, request.workspace_id, request.skills,
                                  request.budget, request.input_ref),
                                 ('run-1', 'task-1', 'user:1', 'research', session_id,
                                  'deep', 'model-1', 'workspace-1', ('skill-1',),
                                  limits, 'input-1'))
                self.assertEqual(request.turn_id,
                                 None if session_id is None else 'turn-1')

    def test_legacy_positional_arguments_keep_session_turn_validation(self) -> None:
        for session_id, turn_id in (('ses-1', None), (None, 'turn-1')):
            with self.subTest(session_id=session_id, turn_id=turn_id):
                with self.assertRaises(ValueError):
                    TaskSubmission('user:1', 'research', session_id,
                                   'input-1', 'idem-1', turn_id=turn_id)
                with self.assertRaises(ValueError):
                    RunRequest('run-1', 'task-1', 'user:1', 'research', session_id,
                               'deep', 'model-1', 'workspace-1', ('skill-1',),
                               BudgetLimits(), 'input-1', turn_id=turn_id)

    async def test_retry_keeps_each_run_and_report(self) -> None:
        control = FakeControl()
        task_manager: TaskManager = control
        run_reporter: RunReporter = control
        worker: WorkerExecutor = FakeExecution()
        task = await task_manager.submit(TaskSubmission(owner_id='user:1', prompt='research'))
        first = await task_manager.create_run(task.task_id, task.owner_id, BudgetLimits())
        second = await task_manager.create_run(task.task_id, task.owner_id, BudgetLimits())
        self.assertEqual((first.session_id, first.turn_id), (None, None))
        self.assertEqual((first.run_id, second.run_id), ('run-1', 'run-2'))
        self.assertEqual([(run.task_id, run.attempt) for run in control.runs],
                         [('task-1', 1), ('task-1', 2)])
        first_report = await worker.execute(first)
        second_report = await worker.execute(second)
        await run_reporter.report(first_report)
        await run_reporter.report(second_report)
        self.assertIs(await task_manager.get_report(first.run_id, task.owner_id), first_report)
        self.assertIs(await task_manager.get_report(second.run_id, task.owner_id), second_report)

    async def test_event_sink_preserves_runtime_event_identity(self) -> None:
        sink: EventSink = FakeEventSink()
        event = AgentEvent(seq=2, turn=1, name='delta', data={'text': 'hello'})
        envelope = PlatformEvent('task-1', 'run-1', event)
        await sink.publish(envelope)
        self.assertEqual((envelope.task_id, envelope.run_id, envelope.seq),
                         ('task-1', 'run-1', 2))
        self.assertEqual(envelope.event_key, ('run-1', 2))
        self.assertIs(envelope.runtime_event, event)
        self.assertEqual(PlatformEvent('task-1', 'run-1', event).event_key,
                         envelope.event_key)
        self.assertNotEqual(PlatformEvent('task-1', 'run-2', event).event_key,
                            envelope.event_key)

    def test_usage_unknown_and_invalid_values(self) -> None:
        unknown = UsageReport()
        self.assertEqual((unknown.prompt_tokens, unknown.completion_tokens,
                          unknown.tool_calls, unknown.duration_ms),
                         (None, None, None, None))
        self.assertIsNone(UsageReport().model_tokens)
        self.assertIsNone(UsageReport(prompt_tokens=3).model_tokens)
        self.assertEqual(UsageReport(prompt_tokens=3, completion_tokens=4).model_tokens, 7)
        for limits in (dict(max_duration_s=0), dict(max_tool_calls=-1),
                       dict(max_model_tokens=-1)):
            with self.assertRaises(ValueError):
                BudgetLimits(**limits)
        for usage in (dict(prompt_tokens=-1), dict(completion_tokens=-1),
                      dict(tool_calls=-1), dict(duration_ms=-1)):
            with self.assertRaises(ValueError):
                UsageReport(**usage)

    def test_execution_report_preserves_failure_and_rejects_nonterminal_status(self) -> None:
        request = RunRequest('run-1', 'task-1', 'user:1', 'research')
        result = RunResult(stop_reason=StopReason.ERROR,
                           error=BusinessError(10001, 'runtime failed', 500))
        report = report_from_result(request, result)
        self.assertEqual((report.run_id, report.task_id, report.status),
                         ('run-1', 'task-1', RunStatus.FAILED))
        self.assertIs(report.result, result)
        self.assertEqual((report.error_code, report.error_message),
                         ('10001', 'runtime failed'))
        self.assertIsNone(report.usage.tool_calls)
        with self.assertRaises(ValueError):
            ExecutionReport('run-1', 'task-1', RunStatus.RUNNING)


if __name__ == '__main__':
    unittest.main()
