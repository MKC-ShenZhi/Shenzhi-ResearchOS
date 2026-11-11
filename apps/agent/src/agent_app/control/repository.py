"""Transactional Task/Run, durable queue, event and worker lease repository."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_app.errors import BusinessError
from agent_app.infrastructure.models import (
    OutboxRow, RunControlRow, RunEventRow, RunRow, TaskRow,
)
from agent_contracts import BudgetLimits, ExecutionReport, PlatformEvent, RunRequest, RunStatus
from agent_contracts.tasks import TaskRecord, TaskStatus, TaskSubmission


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _budget_dict(budget: BudgetLimits) -> dict[str, Any]:
    return {'max_duration_s': budget.max_duration_s, 'max_tool_calls': budget.max_tool_calls,
            'max_model_tokens': budget.max_model_tokens}


def _task_record(row: TaskRow) -> TaskRecord:
    raw = row.request_json
    submission = TaskSubmission(
        owner_id=row.owner_id, prompt=row.prompt, session_id=row.session_id,
        input_ref=row.input_ref, idempotency_key=row.idempotency_key, turn_id=row.turn_id,
        mode=raw.get('mode', 'fast'), model=raw.get('model'),
        workspace_id=raw.get('workspace_id'), skills=tuple(raw.get('skills') or ()),
        budget=BudgetLimits(**(raw.get('budget') or {})),
        history=tuple(raw.get('history') or ()),
    )
    return TaskRecord(row.task_id, submission, TaskStatus(row.status), row.created_at,
                      row.cancel_requested, row.current_run_id)


def _run_request(row: RunRow) -> RunRequest:
    data = row.request_json
    return RunRequest(
        run_id=row.run_id, task_id=row.task_id, owner_id=data['owner_id'],
        prompt=data['prompt'], session_id=data.get('session_id'), mode=data.get('mode', 'fast'),
        model=data.get('model'), workspace_id=data.get('workspace_id'),
        skills=tuple(data.get('skills') or ()), budget=BudgetLimits(**(data.get('budget') or {})),
        input_ref=data.get('input_ref'), turn_id=data.get('turn_id'),
        history=tuple(data.get('history') or ()),
    )


def _request_dict(request: RunRequest) -> dict[str, Any]:
    return {'run_id': request.run_id, 'task_id': request.task_id, 'owner_id': request.owner_id,
            'prompt': request.prompt, 'session_id': request.session_id, 'turn_id': request.turn_id,
            'mode': request.mode, 'model': request.model, 'workspace_id': request.workspace_id,
            'skills': list(request.skills), 'budget': _budget_dict(request.budget),
            'input_ref': request.input_ref, 'history': list(request.history)}


async def submit(session: AsyncSession, submission: TaskSubmission) -> TaskRecord:
    if submission.idempotency_key:
        existing = await session.scalar(select(TaskRow).where(
            TaskRow.owner_id == submission.owner_id,
            TaskRow.idempotency_key == submission.idempotency_key,
        ))
        if existing:
            if (existing.prompt != submission.prompt or existing.session_id != submission.session_id
                    or existing.turn_id != submission.turn_id
                    or existing.input_ref != submission.input_ref
                    or existing.request_json != {'mode': submission.mode, 'model': submission.model,
                                                  'workspace_id': submission.workspace_id,
                                                  'skills': list(submission.skills),
                                                  'budget': _budget_dict(submission.budget),
                                                  'history': list(submission.history)}):
                raise BusinessError(20001, '幂等键已用于不同的任务请求', 409)
            return _task_record(existing)
    now = _now()
    task_id, run_id = uuid.uuid4().hex, uuid.uuid4().hex
    task = TaskRow(
        task_id=task_id, owner_id=submission.owner_id, status=TaskStatus.QUEUED.value,
        prompt=submission.prompt, session_id=submission.session_id, turn_id=submission.turn_id,
        input_ref=submission.input_ref, idempotency_key=submission.idempotency_key,
        request_json={'mode': submission.mode, 'model': submission.model,
                      'workspace_id': submission.workspace_id, 'skills': list(submission.skills),
                      'budget': _budget_dict(submission.budget),
                      'history': list(submission.history)},
        current_run_id=run_id, cancel_requested=False, created_at=now,
    )
    request = RunRequest(
        run_id=run_id, task_id=task_id, owner_id=submission.owner_id, prompt=submission.prompt,
        session_id=submission.session_id, turn_id=submission.turn_id, mode=submission.mode,
        model=submission.model, workspace_id=submission.workspace_id, skills=submission.skills,
        budget=submission.budget, input_ref=submission.input_ref,
        history=submission.history,
    )
    session.add(task)
    # Flush each parent before adding its FK-dependent row, without committing.
    await session.flush()
    session.add(RunRow(run_id=run_id, task_id=task_id, attempt=1,
                       status=RunStatus.PENDING.value, request_json=_request_dict(request),
                       created_at=now, lease_token=0))
    await session.flush()
    session.add(OutboxRow(run_id=run_id, created_at=now, available_at=now,
                          delivery_attempts=0))
    await session.commit()
    return _task_record(task)


async def get_task(session: AsyncSession, task_id: str, owner_id: str) -> TaskRecord:
    row = await session.scalar(select(TaskRow).where(
        TaskRow.task_id == task_id, TaskRow.owner_id == owner_id))
    if row is None:
        raise BusinessError(20004, '任务不存在', 404)
    return _task_record(row)


async def get_run(session: AsyncSession, run_id: str, owner_id: str) -> tuple[RunRow, TaskRow]:
    found = (await session.execute(select(RunRow, TaskRow).join(
        TaskRow, TaskRow.task_id == RunRow.task_id).where(
            RunRow.run_id == run_id, TaskRow.owner_id == owner_id))).first()
    if found is None:
        raise BusinessError(20004, '运行不存在', 404)
    return found


async def claim_run(session: AsyncSession, worker_id: str, lease_seconds: int = 45):
    now = _now()
    query = (select(RunRow, TaskRow, OutboxRow).join(TaskRow, TaskRow.task_id == RunRow.task_id)
             .join(OutboxRow, OutboxRow.run_id == RunRow.run_id)
             .where(or_(and_(RunRow.status == RunStatus.PENDING.value,
                             TaskRow.status == TaskStatus.QUEUED.value,
                             OutboxRow.delivered_at.is_(None), OutboxRow.available_at <= now),
                        and_(RunRow.status == RunStatus.RUNNING.value,
                             TaskRow.status.in_((TaskStatus.RUNNING.value, TaskStatus.CANCELLING.value)),
                             RunRow.lease_expires_at <= now)))
             .order_by(RunRow.created_at).with_for_update(skip_locked=True).limit(1))
    found = (await session.execute(query)).first()
    if found is None:
        return None
    run, task, outbox = found
    run.status = RunStatus.RUNNING.value
    run.worker_id = worker_id
    run.lease_token += 1
    run.lease_expires_at = now + timedelta(seconds=lease_seconds)
    run.started_at = run.started_at or now
    task.status = TaskStatus.RUNNING.value
    outbox.delivered_at = outbox.delivered_at or now
    outbox.delivery_attempts += 1
    await session.commit()
    return _run_request(run), run.lease_token


async def heartbeat(session: AsyncSession, run_id: str, worker_id: str,
                    lease_token: int, lease_seconds: int = 45) -> tuple[bool, bool]:
    now = _now()
    row = await session.scalar(select(RunRow).where(
        RunRow.run_id == run_id, RunRow.worker_id == worker_id,
        RunRow.lease_token == lease_token, RunRow.status == RunStatus.RUNNING.value,
        RunRow.lease_expires_at > now).with_for_update())
    if row is None:
        return False, False
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    task = await session.scalar(select(TaskRow).where(TaskRow.task_id == row.task_id))
    cancel_requested = bool(task and task.cancel_requested)
    await session.commit()
    return True, cancel_requested


async def append_event(session: AsyncSession, event: PlatformEvent,
                       worker_id: str, lease_token: int) -> None:
    now = _now()
    run = await session.scalar(select(RunRow).where(
        RunRow.run_id == event.run_id, RunRow.task_id == event.task_id,
        RunRow.status == RunStatus.RUNNING.value, RunRow.worker_id == worker_id,
        RunRow.lease_token == lease_token, RunRow.lease_expires_at > now).with_for_update())
    if run is None:
        raise BusinessError(20009, 'Worker 租约已失效，事件被拒绝', 409)
    existing = await session.scalar(select(RunEventRow).where(
        RunEventRow.run_id == event.run_id, RunEventRow.seq == event.seq))
    if existing is not None:
        if (existing.task_id, existing.turn, existing.name, existing.data) != (
                event.task_id, event.turn, event.name, event.data):
            raise BusinessError(20009, '事件序号冲突', 409)
        return
    session.add(RunEventRow(task_id=event.task_id, run_id=event.run_id, seq=event.seq,
                            turn=event.turn, name=event.name, data=event.data,
                            occurred_at=event.occurred_at))
    await session.commit()


async def list_events(session: AsyncSession, run_id: str, owner_id: str, after_seq: int):
    await get_run(session, run_id, owner_id)
    rows = (await session.scalars(select(RunEventRow).where(
        RunEventRow.run_id == run_id, RunEventRow.seq > after_seq
    ).order_by(RunEventRow.seq))).all()
    return [PlatformEvent(row.task_id, row.run_id, row.seq, row.turn, row.name,
                          row.data, row.occurred_at) for row in rows]


async def append_steer(session: AsyncSession, run_id: str, owner_id: str,
                       message: str) -> dict[str, Any]:
    run = await session.scalar(select(RunRow).join(TaskRow).where(
        RunRow.run_id == run_id, TaskRow.owner_id == owner_id,
    ).with_for_update())
    if run is None:
        raise BusinessError(20004, '运行不存在', 404)
    if run.status != RunStatus.RUNNING.value or run.report_json is not None:
        raise BusinessError(20004, '该运行已结束或尚未开始', 409)
    seq = int(await session.scalar(select(func.coalesce(func.max(RunControlRow.seq), 0)).where(
        RunControlRow.run_id == run_id)) or 0) + 1
    row = RunControlRow(task_id=run.task_id, run_id=run_id, seq=seq, name='steer',
                        text=message, created_at=_now())
    session.add(row)
    await session.commit()
    return {'run_id': run_id, 'seq': seq, 'name': row.name}


async def list_controls(session: AsyncSession, run_id: str, owner_id: str, after_seq: int):
    await get_run(session, run_id, owner_id)
    rows = (await session.scalars(select(RunControlRow).where(
        RunControlRow.run_id == run_id, RunControlRow.seq > after_seq,
    ).order_by(RunControlRow.seq))).all()
    return [{'run_id': row.run_id, 'seq': row.seq, 'name': row.name,
             'text': row.text, 'created_at': row.created_at.isoformat()} for row in rows]


async def record_report(session: AsyncSession, report: ExecutionReport,
                        worker_id: str, lease_token: int) -> None:
    run = await session.scalar(select(RunRow).where(
        RunRow.run_id == report.run_id, RunRow.task_id == report.task_id).with_for_update())
    if run is None:
        raise BusinessError(20004, '运行不存在', 404)
    payload = {'run_id': report.run_id, 'task_id': report.task_id,
               'status': report.status.value, 'result': report.result,
               'usage': {'prompt_tokens': report.usage.prompt_tokens,
                         'completion_tokens': report.usage.completion_tokens,
                         'tool_calls': report.usage.tool_calls,
                         'duration_ms': report.usage.duration_ms},
               'error_code': report.error_code, 'error_message': report.error_message}
    if run.report_json is not None:
        if run.report_json != payload:
            raise BusinessError(20009, '同一运行收到冲突报告', 409)
        return
    now = _now()
    if (run.worker_id != worker_id or run.lease_token != lease_token
            or run.lease_expires_at is None or run.lease_expires_at <= now):
        raise BusinessError(20009, 'Worker 租约已失效，报告被拒绝', 409)
    run.status = report.status.value
    run.report_json = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    run.completed_at = now
    run.lease_expires_at = None
    task = await session.scalar(select(TaskRow).where(TaskRow.task_id == run.task_id).with_for_update())
    if task is None or task.current_run_id != run.run_id:
        raise BusinessError(20009, '运行已不是任务当前尝试', 409)
    terminal_task_status = {
        RunStatus.COMPLETED: TaskStatus.COMPLETED,
        RunStatus.FAILED: TaskStatus.FAILED,
        RunStatus.CANCELLED: TaskStatus.CANCELLED,
        RunStatus.TIMED_OUT: TaskStatus.FAILED,
        RunStatus.AWAITING_INPUT: TaskStatus.AWAITING_INPUT,
    }[report.status]
    if report.status in (RunStatus.FAILED, RunStatus.TIMED_OUT) and run.attempt < 3:
        previous_request = _run_request(run)
        next_run_id = uuid.uuid4().hex
        next_request = RunRequest(
            run_id=next_run_id, task_id=previous_request.task_id,
            owner_id=previous_request.owner_id, prompt=previous_request.prompt,
            session_id=previous_request.session_id, turn_id=previous_request.turn_id,
            mode=previous_request.mode, model=previous_request.model,
            workspace_id=previous_request.workspace_id, skills=previous_request.skills,
            budget=previous_request.budget, input_ref=previous_request.input_ref,
            history=previous_request.history,
        )
        task.current_run_id = next_run_id
        task.status = TaskStatus.QUEUED.value
        available = now + timedelta(seconds=2 ** run.attempt)
        session.add(RunRow(run_id=next_run_id, task_id=task.task_id,
                           attempt=run.attempt + 1, status=RunStatus.PENDING.value,
                           request_json=_request_dict(next_request), created_at=now,
                           lease_token=0))
        await session.flush()
        session.add(OutboxRow(run_id=next_run_id, created_at=now,
                              available_at=available, delivery_attempts=0))
    else:
        task.status = terminal_task_status.value
    await session.commit()


async def request_cancel(session: AsyncSession, task_id: str, owner_id: str) -> TaskRecord:
    task_row = await session.scalar(select(TaskRow).where(
        TaskRow.task_id == task_id, TaskRow.owner_id == owner_id).with_for_update())
    if task_row is None:
        raise BusinessError(20004, '任务不存在', 404)
    if task_row.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value,
                           TaskStatus.CANCELLED.value, TaskStatus.AWAITING_INPUT.value}:
        return _task_record(task_row)
    now = _now()
    if task_row.status == TaskStatus.QUEUED.value:
        run = await session.scalar(select(RunRow).where(
            RunRow.run_id == task_row.current_run_id).with_for_update())
        task_row.status = TaskStatus.CANCELLED.value
        task_row.cancel_requested = True
        if run is not None:
            run.status = RunStatus.CANCELLED.value
            run.completed_at = now
            run.report_json = {'run_id': run.run_id, 'task_id': task_row.task_id,
                               'status': RunStatus.CANCELLED.value, 'result': None,
                               'usage': {'prompt_tokens': None, 'completion_tokens': None,
                                         'tool_calls': None, 'duration_ms': None},
                               'error_code': None, 'error_message': None}
            outbox = await session.scalar(select(OutboxRow).where(OutboxRow.run_id == run.run_id))
            if outbox is not None:
                outbox.delivered_at = now
        await session.commit()
        return _task_record(task_row)
    task_row.cancel_requested = True
    task_row.status = TaskStatus.CANCELLING.value
    await session.commit()
    return _task_record(task_row)
