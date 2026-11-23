"""Internal task, worker, report and replay routes."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agent_app.api.auth import require_service
from agent_app.control import repository
from agent_app.errors import BusinessError
from agent_app.infrastructure.database import get_session
from agent_app.extensions.skills import default_store
from agent_app.integrations.llm.resolver import load_registry
from agent_app.extensions.workspace import (
    cleanup_session_workspace, copy_session_workspace, create_workspace,
    migrate_owner_workspaces, read_session_file, write_workspace_file,
)
from agent_contracts import (
    AgentConfigWire, BudgetLimits, ExecutionReport, PlatformEvent, RunStatus,
    RunSteerRequestWire, RunSteerResponseWire, SessionFileReadResponseWire,
    TaskSubmission, WorkerHeartbeatRequestWire, WorkerHeartbeatResponseWire,
    WorkspaceClaimCommitResponseWire,
    WorkspaceClaimPrepareResponseWire, WorkspaceClaimRequestWire,
    WorkspaceCreateRequestWire, WorkspaceCreateResponseWire,
    WorkspaceFileWriteRequestWire, WorkspaceFileWriteResponseWire,
    EventIngestWire, ReportIngestWire, TaskSubmissionWire, UsageReport,
)


router = APIRouter(prefix='/internal/v1', dependencies=[Depends(require_service)])


SubmitBody = TaskSubmissionWire


class ClaimBody(BaseModel):
    worker_id: str = Field(min_length=1, max_length=255)


EventBody = EventIngestWire
ReportBody = ReportIngestWire


@router.get('/config')
async def agent_config():
    registry = load_registry()
    store = default_store()
    skills = [{'name': skill.name, 'description': skill.description}
              for name in store.names()
              for skill in [store.get(name)]
              if skill and not skill.disable_model_invocation]
    return AgentConfigWire(
        models=registry.public_models('agent'),
        default_model=registry.public_default('agent'), skills=skills,
    ).model_dump(mode='json')


@router.post('/workspaces')
async def new_workspace(body: WorkspaceCreateRequestWire):
    return WorkspaceCreateResponseWire.model_validate(
        create_workspace(body.owner_id),
    ).model_dump(mode='json')


@router.post('/workspaces/claim/prepare')
async def prepare_workspace_claim(body: WorkspaceClaimRequestWire):
    prepared = []
    for session_id in dict.fromkeys(body.session_ids):
        if copy_session_workspace(body.source_owner, body.target_owner, session_id):
            prepared.append(session_id)
    return WorkspaceClaimPrepareResponseWire(
        prepared_session_ids=prepared,
    ).model_dump(mode='json')


@router.post('/workspaces/claim/commit')
async def commit_workspace_claim(body: WorkspaceClaimRequestWire):
    cleaned = []
    for session_id in dict.fromkeys(body.session_ids):
        try:
            cleanup_session_workspace(body.source_owner, session_id)
            cleaned.append(session_id)
        except Exception:
            # Ownership is already committed; stale source data is safer than
            # turning a successful claim into a reported failure.
            continue
    moved_workspaces = migrate_owner_workspaces(body.source_owner, body.target_owner)
    return WorkspaceClaimCommitResponseWire(
        cleaned_session_ids=cleaned, moved_workspaces=moved_workspaces,
    ).model_dump(mode='json')


@router.post('/workspaces/{workspace_id}/files')
async def put_workspace_file(workspace_id: str, body: WorkspaceFileWriteRequestWire):
    if body.workspace_id != workspace_id:
        raise BusinessError(20001, 'URL workspace_id 与请求不匹配')
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise BusinessError(20001, '文件内容编码无效') from exc
    return WorkspaceFileWriteResponseWire.model_validate(
        write_workspace_file(workspace_id, body.owner_id, body.path, content),
    ).model_dump(mode='json')


@router.get('/sessions/{session_id}/files')
async def get_session_file(session_id: str, owner_id: str, path: str):
    content, media_type = read_session_file(owner_id, session_id, path)
    return SessionFileReadResponseWire(
        content_base64=base64.b64encode(content).decode('ascii'), media_type=media_type,
    ).model_dump(mode='json')


def _task_json(record) -> dict[str, Any]:
    return {'task_id': record.task_id, 'owner_id': record.owner_id,
            'session_id': record.session_id, 'turn_id': record.turn_id,
            'status': record.status.value, 'current_run_id': record.current_run_id,
            'cancel_requested': record.cancel_requested,
            'created_at': record.created_at.isoformat()}


@router.post('/tasks')
async def submit_task(body: SubmitBody, session: AsyncSession = Depends(get_session)):
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


@router.get('/tasks/{task_id}')
async def get_task(task_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    return _task_json(await repository.get_task(session, task_id, owner_id))


@router.get('/runs/{run_id}')
async def get_run(run_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    run, task = await repository.get_run(session, run_id, owner_id)
    return {'run_id': run.run_id, 'task_id': run.task_id, 'attempt': run.attempt,
            'status': run.status, 'created_at': run.created_at.isoformat(),
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'completed_at': run.completed_at.isoformat() if run.completed_at else None,
            'report': run.report_json, 'task_status': task.status}


@router.post('/tasks/{task_id}/cancel')
async def cancel_task(task_id: str, owner_id: str, session: AsyncSession = Depends(get_session)):
    return _task_json(await repository.request_cancel(session, task_id, owner_id))


@router.post('/runs/{run_id}/steer')
async def steer_run(run_id: str, body: RunSteerRequestWire,
                    session: AsyncSession = Depends(get_session)):
    if not body.text.strip():
        raise BusinessError(20001, '插话内容不能为空')
    return RunSteerResponseWire.model_validate(
        await repository.append_steer(session, run_id, body.owner_id, body.text.strip()),
    ).model_dump(mode='json')


@router.get('/runs/{run_id}/controls')
async def read_controls(run_id: str, owner_id: str,
                        after_seq: int = Query(default=0, ge=0),
                        session: AsyncSession = Depends(get_session)):
    return {'controls': await repository.list_controls(session, run_id, owner_id, after_seq)}


@router.get('/runs/{run_id}/events')
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
    claimed = await repository.claim_run(session, body.worker_id)
    if claimed is None:
        return {'run': None}
    request, lease_token = claimed
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
            'lease_token': lease_token}


@router.post('/runs/{run_id}/heartbeat')
async def heartbeat(run_id: str, body: WorkerHeartbeatRequestWire,
                    session: AsyncSession = Depends(get_session)) -> WorkerHeartbeatResponseWire:
    active, cancel_requested = await repository.heartbeat(
        session, run_id, body.worker_id, body.lease_token,
    )
    return WorkerHeartbeatResponseWire(active=active, cancel_requested=cancel_requested)


@router.post('/runs/{run_id}/events')
async def append_event(run_id: str, body: EventBody,
                       session: AsyncSession = Depends(get_session)):
    if run_id != body.run_id:
        raise BusinessError(20001, 'URL run_id 与事件 run_id 不匹配')
    event = PlatformEvent(body.task_id, body.run_id, body.seq, body.turn,
                          body.name, body.data, body.occurred_at)
    await repository.append_event(session, event, body.worker_id, body.lease_token)
    return {'stored': True}


@router.post('/runs/{run_id}/report')
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
