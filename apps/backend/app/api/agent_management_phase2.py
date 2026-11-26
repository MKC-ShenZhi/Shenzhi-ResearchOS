"""Admin Phase 2 checks, Worker evidence, and independently audited diagnostics."""
import os
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request

from agent_contracts.management import Key, Page
from agent_contracts.management_phase2 import (
    CapabilityEvidence, DiagnosticRequest, Identifier, ManifestEvidence, StartProbe, Target, WorkerSnapshot,
)
from app.core.admin_auth import PATH, require_admin, require_admin_write
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.services import agent_management_audit as audit
from .agent_management import response

router = APIRouter(prefix=PATH + '/agent', tags=['agent-management-phase2'], dependencies=[Depends(require_admin)])


def sensitive(request: Request):
    principal = require_admin_write(request)
    if os.getenv('ADMIN_AGENT_DIAGNOSTICS', '').lower() != 'true':
        raise BusinessError(10001, 'AGENT_SENSITIVE_DIAGNOSTICS_DISABLED', 403)
    return principal


@router.get('/worker-evidence')
async def workers(limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: str | None = None):
    return response(await agent.read('/worker-evidence', Page[WorkerSnapshot], {
        'limit': limit, **({'cursor': cursor} if cursor else {}),
    }))


@router.get('/worker-evidence/{worker_id}')
async def worker(worker_id: Identifier):
    return response(await agent.read(agent.management_path('/worker-evidence/{worker_id}', {'worker_id': worker_id}),
                                     WorkerSnapshot, {}))


@router.get('/worker-evidence/{worker_id}/manifests')
async def manifests(worker_id: Identifier, cursor: Annotated[str | None, Query(max_length=1024)] = None):
    path = agent.management_path('/worker-evidence/{worker_id}/manifests', {'worker_id': worker_id})
    return response(await agent.read(path, Page[ManifestEvidence], {'cursor': cursor} if cursor else {}))


@router.get('/capability-evidence')
async def capability_evidence(kind: Target, target_id: Identifier,
                              cursor: Annotated[str | None, Query(max_length=1024)] = None):
    return response(await agent.read('/capability-evidence', Page[CapabilityEvidence], {
        'kind': kind, 'target_id': target_id, **({'cursor': cursor} if cursor else {}),
    }))


def request_id(request):
    try:
        return str(UUID(getattr(request.state, 'request_id', '')))
    except (ValueError, AttributeError, TypeError):
        return str(uuid4())


@router.post('/checks')
async def check(body: StartProbe, request: Request, principal=Depends(require_admin_write)):
    item = await audit.run_check(principal, body, request_id(request))
    if item.reason == 'PROBE_RATE_LIMIT':
        raise BusinessError(10001, 'PROBE_RATE_LIMIT', 429)
    return response(item)


@router.post('/diagnostics')
async def diagnose(body: DiagnosticRequest, request: Request, principal=Depends(sensitive)):
    item = await audit.run_diagnostic(principal, body, request_id(request))
    # Result retrieval is a separate auditable operation.
    return response(item.model_copy(update={'diagnostic': None}))


async def find(audit_id):
    items = await audit.rows(0, 1, audit_id=str(audit_id))
    if not items:
        raise BusinessError(10001, 'AGENT_AUDIT_NOT_FOUND', 404)
    return items[0]


@router.post('/diagnostics/{audit_id}/view')
async def view_diagnostic(audit_id: UUID, request: Request, principal=Depends(sensitive)):
    return response(await audit.diagnostic_view(principal, await find(audit_id), request_id(request)))


def summary(item):
    return item.model_copy(update={'diagnostic': None})


def validate_dates(*values):
    if any(value and value.utcoffset() is None for value in values):
        raise BusinessError(20001, 'TIMEZONE_REQUIRED', 422)
    if all(values) and values[0] > values[1]:
        raise BusinessError(20001, 'TIME_WINDOW_INVALID', 422)


@router.get('/audit')
async def history(principal: Key | None = None, action: Key | None = None, target_kind: Key | None = None,
                  target_id: Identifier | None = None, state: Key | None = None, from_at: datetime | None = None,
                  to_at: datetime | None = None, offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                  limit: Annotated[int, Query(ge=1, le=100)] = 20):
    validate_dates(from_at, to_at)
    entries = await audit.rows(offset, limit + 1, principal=principal, action=action, target_kind=target_kind,
                               target_id=target_id, state=state, from_at=from_at, to_at=to_at)
    return response(Page(items=[summary(item) for item in entries[:limit]],
                         next_cursor=str(offset + limit) if len(entries) > limit and offset + limit <= 10000 else None,
                         observed_at=audit.now()))


@router.get('/audit/{audit_id}')
async def audit_detail(audit_id: UUID):
    return response(summary(await find(audit_id)))
