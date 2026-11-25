"""Drain-only V1 task and worker routes for historical executions.

New production submissions use the V2 API. V1 shared service routes have been
removed; the remaining task/run and worker routes are retained only until the
legacy drain audit and deployment caller review allow their retirement.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent_app.api.auth import require_service
from agent_app.control import repository
from agent_app.errors import BusinessError
from agent_app.infrastructure.database import get_session
from agent_app.api.shared import task_json as _task_json
from agent_contracts import (
    BudgetLimits, ExecutionReport, PlatformEvent, RunStatus,
    RunSteerRequestWire, RunSteerResponseWire,
    TaskRunsResponseWire, TaskSubmission, WorkerHeartbeatRequestWire, WorkerHeartbeatResponseWire,
    EventIngestWire, ReportIngestWire, TaskSubmissionWire, UsageReport,
)


async def require_v1_record(request: Request, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from agent_app.infrastructure.metering_models import TaskMeteringRow
    from agent_app.infrastructure.models import RunRow
    task_id = request.path_params.get('task_id')
    run_id = request.path_params.get('run_id')
    if run_id:
        run = await session.scalar(select(RunRow).where(RunRow.run_id == run_id))
        task_id = run.task_id if run else None
    if task_id and await session.scalar(select(TaskMeteringRow).where(TaskMeteringRow.task_id == task_id)) is not None:
        raise BusinessError(20004, '任务协议不匹配', 404)


router = APIRouter(prefix='/internal/v1', dependencies=[Depends(require_service)])


SubmitBody = TaskSubmissionWire


class ClaimBody(BaseModel):
    worker_id: str = Field(min_length=1, max_length=255)
    demo_mode: bool = False


EventBody = EventIngestWire
ReportBody = ReportIngestWire


@router.post('/tasks')
async def submit_task(body: SubmitBody, session: AsyncSession = Depends(get_session)):
    demo_mode = os.getenv('AGENT_DEMO_MODE') == '1'
    if not demo_mode or os.getenv('AGENT_V1_ADMISSION', 'drain_only') != 'legacy':
        raise BusinessError(20004, '旧协议已停止新任务准入', 409)
    if (body.model == 'demo/m1') != demo_mode or (demo_mode and not body.session_id):
        raise BusinessError(20001, 'Mock 与正式任务不可混用', 409)
    submission = TaskSubmission(
        owner_id=body.owner_id, prompt=body.prompt, session_id=body.session_id,
        turn_id=body.turn_id, input_ref=body.input_ref,
        idempotency_key=body.idempotency_key, mode=body.mode, model=body.model,
        workspace_id=body.workspace_id, skills=tuple(body.skills),
        budget=BudgetLimits(**body.budget.model_dump()),
        history=tuple(body.history),
    )
    task = await repository.submit(session, submission)
    return _task_json(task)


@router.get('/tasks/{task_id}', dependencies=[Depends(require_v1_record)])
async def get_task(task_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    return _task_json(await repository.get_task(session, task_id, owner_id))


@router.get('/tasks/{task_id}/runs', dependencies=[Depends(require_v1_record)])
async def list_task_runs(task_id: str, owner_id: str,
                        session: AsyncSession = Depends(get_session)) -> TaskRunsResponseWire:
    return TaskRunsResponseWire(run_ids=await repository.list_task_runs(session, task_id, owner_id))


@router.get('/runs/{run_id}', dependencies=[Depends(require_v1_record)])
async def get_run(run_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    run, task = await repository.get_run(session, run_id, owner_id)
    return {'run_id': run.run_id, 'task_id': run.task_id, 'attempt': run.attempt,
            'status': run.status, 'created_at': run.created_at.isoformat(),
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            'report': run.report_json, 'task_status': task.status}


@router.post('/tasks/{task_id}/cancel', dependencies=[Depends(require_v1_record)])
async def cancel_task(task_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    return _task_json(await repository.request_cancel(session, task_id, owner_id))


@router.post('/runs/{run_id}/steer', dependencies=[Depends(require_v1_record)])
async def steer_run(run_id: str, body: RunSteerRequestWire,
                    session: AsyncSession = Depends(get_session)):
    if not body.text.strip():
        raise BusinessError(20001, '插话内容不能为空')
    return RunSteerResponseWire.model_validate(
        await repository.append_steer(session, run_id, body.owner_id, body.text.strip()),
    ).model_dump(mode='json')


@router.get('/runs/{run_id}/controls', dependencies=[Depends(require_v1_record)])
async def read_controls(run_id: str, owner_id: str,
                        after_seq: int = Query(default=0, ge=0),
                        session: AsyncSession = Depends(get_session)):
    return {'controls': await repository.list_controls(session, run_id, owner_id, after_seq)}


@router.get('/runs/{run_id}/events', dependencies=[Depends(require_v1_record)])
async def read_events(run_id: str, owner_id: str,
                      after_seq: int = Query(default=0, ge=0),
                      session: AsyncSession = Depends(get_session)):
    events = await repository.list_events(session, run_id, owner_id, after_seq)
    return {'events': [{'task_id': event.task_id, 'run_id': event.run_id,
                        'seq': event.seq, 'turn': event.turn, 'name': event.name,
                        'data': event.data, 'occurred_at': event.occurred_at.isoformat()}
                       for event in events]}


@router.post('/worker/claim')
async def claim(body: ClaimBody, session: AsyncSession = Depends(get_session)):
    demo_mode = os.getenv('AGENT_DEMO_MODE') == '1'
    if body.demo_mode != demo_mode:
        raise BusinessError(20001, 'Worker 与 Agent API 运行模式不匹配', 409)
    claimed = await repository.claim_run(session, body.worker_id, demo_mode=demo_mode)
    if claimed is None:
        return {'run': None}
    request, lease_token, event_seq = claimed
    return {'run': {'run_id': request.run_id, 'task_id': request.task_id,
                    'owner_id': request.owner_id, 'prompt': request.prompt,
                    'session_id': request.session_id, 'turn_id': request.turn_id,
                    'input_ref': request.input_ref, 'mode': request.mode,
                    'model': request.model, 'workspace_id': request.workspace_id,
                    'skills': list(request.skills),
                    'history': list(request.history),
                    'budget': {'max_duration_s': request.budget.max_duration_s,
                               'max_tool_calls': request.budget.max_tool_calls,
                               'max_model_tokens': request.budget.max_model_tokens}},
            'lease_token': lease_token, 'event_seq': event_seq}


@router.post('/runs/{run_id}/heartbeat', dependencies=[Depends(require_v1_record)])
async def heartbeat(run_id: str, body: WorkerHeartbeatRequestWire,
                    session: AsyncSession = Depends(get_session)) -> WorkerHeartbeatResponseWire:
    active, cancel_requested = await repository.heartbeat(
        session, run_id, body.worker_id, body.lease_token,
    )
    return WorkerHeartbeatResponseWire(active=active, cancel_requested=cancel_requested)


@router.post('/runs/{run_id}/events', dependencies=[Depends(require_v1_record)])
async def append_event(run_id: str, body: EventBody,
                       session: AsyncSession = Depends(get_session)):
    if run_id != body.run_id:
        raise BusinessError(20001, 'URL run_id 与事件 run_id 不匹配')
    event = PlatformEvent(body.task_id, body.run_id, body.seq, body.turn,
                          body.name, body.data, body.occurred_at)
    await repository.append_event(session, event, body.worker_id, body.lease_token)
    return {'stored': True}


@router.post('/runs/{run_id}/report', dependencies=[Depends(require_v1_record)])
async def record_report(run_id: str, body: ReportBody,
                        session: AsyncSession = Depends(get_session)):
    if run_id != body.run_id:
        raise BusinessError(20001, 'URL run_id 与报告 run_id 不匹配')
    report = ExecutionReport(
        run_id=body.run_id, task_id=body.task_id, status=body.status,
        result=body.result, usage=UsageReport(**body.usage.model_dump()),
        error_code=body.error_code, error_message=body.error_message,
    )
    await repository.record_report(session, report, body.worker_id, body.lease_token)
    return {'recorded': True}
