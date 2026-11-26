"""Administrator-only configuration revision and rollout endpoints."""
import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, RootModel

from agent_contracts.management_config import AdmissionChange, Approval, Candidate, ConfigIndex, Operation, Reconcile, RevisionView, Switch, Validate
from app.core.admin_auth import PATH, require_admin, require_admin_write
from app.core.errors import BusinessError
from app.services import agent_config_management as config
from .agent_management import response
from .agent_management_phase2 import request_id

router = APIRouter(prefix=PATH + '/agent/config', tags=['agent-management-config'],
                   dependencies=[Depends(require_admin)])


class ManagementEvidence(RootModel[dict]):
    pass


def writes_enabled():
    return os.getenv('ADMIN_AGENT_CONFIG_WRITE_ENABLED', '').lower() == 'true'


def write_permission(request: Request):
    principal = require_admin_write(request)
    if not writes_enabled():
        raise BusinessError(10001, 'CONFIG_WRITE_DISABLED', 403)
    return principal


@router.post('/preview')
async def preview(body: Candidate, _principal=Depends(require_admin_write)):
    return response(ManagementEvidence(await config.preview(body)))


@router.get('/fleet')
async def fleet(worker_id: str | None = None, build: str | None = None, config_revision: str | None = None,
                since: AwareDatetime | None = None, until: AwareDatetime | None = None,
                offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                limit: Annotated[int, Query(ge=1, le=10)] = 5):
    params = {'offset': offset, 'limit': limit}
    for key, value in (('worker_id', worker_id), ('build', build), ('config_revision', config_revision),
                       ('since', since.isoformat() if since else None), ('until', until.isoformat() if until else None)):
        if value:
            params[key] = value
    return response(await config.read('/fleet', ManagementEvidence, params))


@router.get('/fleet/events')
async def fleet_events(worker_id: Annotated[str | None, Query(max_length=255)] = None,
                       offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                       limit: Annotated[int, Query(ge=1, le=50)] = 20):
    params = {'offset': offset, 'limit': limit}
    if worker_id:
        params['worker_id'] = worker_id
    return response(await config.read('/fleet/events', ManagementEvidence, params))


@router.get('/revisions')
async def index(offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    index = await config.read('/revisions', ConfigIndex, {'offset': offset})
    return response(index.model_copy(update={'write_enabled': index.write_enabled and writes_enabled()}))


@router.get('/revisions/{revision}')
async def detail(revision: UUID):
    return response(await config.read(f'/revisions/{revision}', RevisionView))


@router.get('/revisions/{revision}/artifacts')
async def artifact(revision: UUID, kind: Literal['tool', 'skill'],
                   artifact_id: Annotated[str, Query(min_length=1, max_length=255)],
                   resource: Annotated[str | None, Query(pattern=r'^sha256:[a-f0-9]{64}$')] = None):
    params = {'kind': kind, 'artifact_id': artifact_id}
    if resource:
        params['resource'] = resource
    return response(await config.read(f'/revisions/{revision}/artifacts', ManagementEvidence, params))


@router.get('/operations/{operation_id}')
async def operation(operation_id: UUID):
    return response(await config.read(f'/operations/{operation_id}', Operation))


@router.post('/revisions')
async def create(body: Candidate, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('create', '/revisions', str(body.operation_id), body, principal, request_id(request)))


@router.post('/revisions/{revision}/validate')
async def validate(revision: UUID, body: Validate, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('validate', f'/revisions/{revision}/validate', str(revision),
                                         body, principal, request_id(request)))


@router.post('/revisions/{revision}/approve')
async def approve(revision: UUID, body: Approval, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('approve', f'/revisions/{revision}/approve', str(revision), body,
                                         principal, request_id(request)))


@router.post('/revisions/{revision}/activate')
async def activate(revision: UUID, body: Switch, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('activate', f'/revisions/{revision}/activate', str(revision),
                                         body, principal, request_id(request)))


@router.post('/revisions/{revision}/rollback')
async def rollback(revision: UUID, body: Switch, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('rollback', f'/revisions/{revision}/rollback', str(revision),
                                         body, principal, request_id(request)))


@router.post('/deployments/{deployment}/reconcile')
async def reconcile(deployment: UUID, body: Reconcile, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('reconcile', f'/deployments/{deployment}/reconcile', str(deployment),
                                         body, principal, request_id(request)))


@router.post('/deployments/{deployment}/pause')
async def pause(deployment: UUID, body: Reconcile, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('pause', f'/deployments/{deployment}/pause', str(deployment),
                                         body, principal, request_id(request)))


@router.post('/admission')
async def admission(body: AdmissionChange, request: Request, principal=Depends(write_permission)):
    return response(await config.perform('admission', '/admission', str(body.operation_id), body, principal, request_id(request)))
