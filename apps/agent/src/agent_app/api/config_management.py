"""Backend-only deployment API. Candidate attestation runs outside the serving pool."""
import asyncio
import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from agent_contracts.management_config import (
    ActorAdmissionChange, ActorApproval, ActorCandidate, ActorReconcile, ActorSwitch, ActorValidate, CapabilityVersion, Proof,
)
from agent_contracts.management_phase2 import ProbeRequest
from agent_app import config_deployment as config
from agent_app.config_artifact_history import artifact_history
from agent_app.control.metering import GateDenied, now_utc
from agent_app.execution.config_profile import load_profile
from agent_app.fleet_history import history, lifecycle
from agent_app.management_checks import check
from agent_app.worker.management_reporter import manifest
from .management import NoStoreRoute, reject_report_role_reuse, result
from .v2 import role


def distinct_role():
    token = os.getenv('AGENT_CONFIG_MANAGEMENT_TOKEN', '').strip()
    if token == os.getenv('AGENT_MANAGEMENT_TOKEN', '').strip():
        raise GateDenied('ROLE_CREDENTIALS_NOT_ISOLATED', 403)
    reject_report_role_reuse('AGENT_CONFIG_MANAGEMENT_TOKEN')


router = APIRouter(prefix='/internal/v2/management/config', route_class=NoStoreRoute,
                   dependencies=[Depends(role('AGENT_CONFIG_MANAGEMENT_TOKEN')), Depends(distinct_role)])


@router.get('/fleet')
async def fleet(worker_id: str | None = None, build: str | None = None, config_revision: str | None = None,
                since: AwareDatetime | None = None, until: AwareDatetime | None = None,
                offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                limit: Annotated[int, Query(ge=1, le=10)] = 5):
    return result(await history(worker_id, build, config_revision, since, until, offset, limit))


@router.get('/fleet/events')
async def fleet_events(worker_id: Annotated[str | None, Query(max_length=255)] = None,
                       offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                       limit: Annotated[int, Query(ge=1, le=50)] = 20):
    return result(await lifecycle(worker_id, offset, limit))


@router.get('/revisions')
async def index(offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    return result(await config.view(offset=offset))


@router.get('/revisions/{revision}')
async def revision_view(revision: UUID):
    return result(await config.view(str(revision)))


@router.get('/revisions/{revision}/artifacts')
async def artifact(revision: UUID, kind: Literal['tool', 'skill'],
                   artifact_id: Annotated[str, Query(min_length=1, max_length=255)],
                   resource: Annotated[str | None, Query(pattern=r'^sha256:[a-f0-9]{64}$')] = None):
    return result(await artifact_history(revision, kind, artifact_id, resource))


@router.get('/operations/{operation_id}')
async def operation(operation_id: UUID, original: bool = False):
    return result(await config.result_for(str(operation_id), original=original))


@router.get('/validations/{operation_id}')
async def validation(operation_id: UUID):
    return result(await config.read_proof(str(operation_id)))


@router.get('/deployments/{operation_id}/proof')
async def deployment_proof(operation_id: UUID):
    return result(await config.deployment_proof(str(operation_id)))


@router.post('/revisions')
async def create(body: ActorCandidate):
    return result(await config.mutate('create', body))


@router.post('/revisions/{revision}/validate')
async def validate(revision: UUID, body: ActorValidate):
    return result(await config.mutate('validate', body, str(revision)))


@router.post('/revisions/{revision}/approve')
async def approve(revision: UUID, body: ActorApproval):
    return result(await config.mutate('approve', body, str(revision)))


@router.post('/revisions/{revision}/activate')
async def activate(revision: UUID, body: ActorSwitch):
    return result(await config.mutate('activate', body, str(revision)))


@router.post('/revisions/{revision}/rollback')
async def rollback(revision: UUID, body: ActorSwitch):
    return result(await config.mutate('rollback', body, str(revision)))


@router.post('/deployments/{deployment}/reconcile')
async def reconcile(deployment: UUID, body: ActorReconcile):
    return result(await config.mutate('reconcile', body, str(deployment)))


@router.post('/deployments/{deployment}/pause')
async def pause(deployment: UUID, body: ActorReconcile):
    return result(await config.mutate('pause', body, str(deployment)))


@router.post('/admission')
async def admission(body: ActorAdmissionChange):
    return result(await config.mutate('admission', body))


@router.post('/attest')
async def attest():
    config.enabled()
    if os.getenv('AGENT_CONFIG_WORKER_ROLE') != 'candidate':
        raise GateDenied('CONFIG_ISOLATED_VALIDATOR_REQUIRED', 403)
    profile = load_profile()
    if not profile:
        raise GateDenied('CONFIG_CANDIDATE_ARTIFACT_REQUIRED', 422)
    revision, spec = profile
    actual = await asyncio.to_thread(manifest)
    facts = config.versions(actual)
    network_verified = False
    if os.getenv('AGENT_CONFIG_ATTEST_NETWORK', '').lower() == 'true':
        enabled_providers = {provider.provider_id for provider in spec.providers if provider.enabled}
        enabled_models = [model for model in spec.models if model.enabled and model.provider_id in enabled_providers]
        if not 1 <= len(enabled_models) <= 12:
            raise GateDenied('CONFIG_PROBE_MODEL_COUNT_LIMIT', 422)
        try:
            async with asyncio.timeout(45):
                network_verified = True
                for model in enabled_models:
                    assessment = await check(ProbeRequest(kind='model', target_id=model.model_id, profile='completion'))
                    if assessment.state != 'pass' or assessment.capability_version != facts.get('model:' + model.model_id):
                        network_verified = False
                        break
        except TimeoutError:
            network_verified = False
    proof = Proof(revision_id=UUID(revision), config_digest=spec.config_digest, build_revision=spec.build_revision,
                  runtime_version=spec.runtime_version, observed_at=now_utc(),
                  network_verified=network_verified, signature='sha256:' + '0' * 64,
                  capabilities=[CapabilityVersion(id=key, version=value) for key, value in sorted(facts.items())])
    return result(proof.model_copy(update={'signature': config.proof_signature(proof)}))
