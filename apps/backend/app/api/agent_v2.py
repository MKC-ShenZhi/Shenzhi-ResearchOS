"""Thin v2 product and authenticated Control endpoints, isolated from v1."""
from __future__ import annotations

import hmac
import json
import os
import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select

from agent_contracts.execution_v2 import GrantBindRequest, AbandonCall
from agent_contracts.canonical import digest
from agent_contracts.v2 import (
    CallPermitRequest, PermitStart, TaskCloseManifest, TaskMeteringBinding, UsageBatch, UsageBatchAck, V2, VoidProof,
)
from app.core.database import session_scope
from app.core.identity import request_owner
from app.core.errors import BusinessError
from app.models.agent_entitlements import (
    CallPermitRow, EntitlementPolicyRow, GrantRevisionRow, GrantRootRow, MeteringProfileRow,
    OwnerEntitlementRow, UsageInboxRow, UsageLedgerRow, WindowCounterRow,
)
from app.services.agent_entitlements.config import entitlement_service
from app.services.agent_entitlements.policy import EntitlementPolicy
from app.services.agent_entitlements.service import EntitlementError, require
from app.services.agent_entitlements.service import now_utc
from app.services.agent_entitlements.usage import UsageSettlement
from app.services.agent_gateway.v2 import AgentGatewayV2
from app.schemas.agent import AgentRunBody
from app.services.agent_attachments import resolve_agent_attachments


class V2Route(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handle(request):
            try:
                return await original(request)
            except (EntitlementError, BusinessError, ValidationError, RequestValidationError, ValueError) as exc:
                reason = exc.reason if isinstance(exc, EntitlementError) else 'REQUEST_REJECTED' if isinstance(exc, BusinessError) else 'PROTOCOL_INVALID'
                status = exc.status if isinstance(exc, (EntitlementError, BusinessError)) else 422
                return JSONResponse(status_code=status, content={'error': dict(schema_version=1, code=exc.code if isinstance(exc, BusinessError) else 20004,
                    message=reason, reason_code=reason, retryable=status == 503,
                    request_id=uuid.uuid4().hex, retry_after_ms=None)})
        return handle


async def control_role(authorization: str | None = Header(default=None)):
    expected = os.getenv('AGENT_CONTROL_TOKEN', '').strip()
    others = [os.getenv(n, '').strip() for n in ('AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN', 'AGENT_SERVICE_TOKEN')]
    require(expected and expected not in others, 'ROLE_CREDENTIALS_NOT_ISOLATED', 503)
    require(hmac.compare_digest(authorization or '', f'Bearer {expected}'), 'ROLE_UNAUTHORIZED', 401)


router = APIRouter(prefix='/api/v2/agent', route_class=V2Route)
internal = APIRouter(prefix='/internal', dependencies=[Depends(control_role)], route_class=V2Route)


class ProductRun(AgentRunBody, V2):
    pass


def client_fingerprint(body):
    return digest(json.dumps(body.model_dump(mode='json'), sort_keys=True, ensure_ascii=False,
                             allow_nan=False, separators=(',', ':')))


@router.post('/submissions')
async def run_product(body: ProductRun, owner: str = Depends(request_owner),
                      client_key: str = Header(alias='Idempotency-Key', min_length=1, max_length=200)):
    require(body.session_id is None, 'USE_SESSION_RUN_ENDPOINT', 422)
    gateway = AgentGatewayV2()
    # A persisted original request wins over expiring attachments on retries.
    async with session_scope() as db:
        from app.models.agent_entitlements import SubmissionRow, ObservationAdmissionRow
        existing = await db.scalar(select(SubmissionRow).where(SubmissionRow.owner_id == owner,
                                                              SubmissionRow.client_key == client_key))
        if existing is None:
            existing = await db.scalar(select(ObservationAdmissionRow).where(ObservationAdmissionRow.owner_id == owner,
                                                                            ObservationAdmissionRow.client_key == client_key))
        if existing:
            require(existing.client_request_digest == client_fingerprint(body), 'IDEMPOTENCY_CONFLICT')
    if existing:
        task = await gateway.recover_submission(owner, client_key)
        return dict(schema_version=1, task=task, warnings=[])
    text, warnings, _files = await resolve_agent_attachments(body.attachments, owner)
    task = await gateway.submit(dict(owner_id=owner, prompt=body.prompt + text, history=body.history,
        mode=body.mode, model=body.model, workspace_id=body.workspace_id, skills=body.skills,
        idempotency_key=client_key), client_request_digest=client_fingerprint(body))
    return dict(schema_version=1, task=task, warnings=warnings)


@internal.get('/protocol-capabilities')
async def protocol_capabilities():
    return dict(schema_version=1, http_versions=[2], message_schema_versions=[1],
                execution_modes=['observation_only', 'authorized'], deployment=os.getenv('AGENT_AUDIENCE', ''),
                build_revision=os.getenv('BACKEND_BUILD_REVISION', 'unconfigured'))


@internal.post('/task-metering-bindings')
async def bind_metering(body: TaskMeteringBinding, service=Depends(entitlement_service)):
    async with session_scope() as db:
        receipt = await service.bind_metering(db, body)
    return receipt.model_dump(mode='json')


@internal.get('/task-metering-bindings/{profile_id}')
async def get_binding(profile_id: str):
    async with session_scope() as db:
        row = await db.get(MeteringProfileRow, profile_id)
        require(row is not None and row.binding is not None, 'BINDING_NOT_FOUND', 404)
        return row.binding


@internal.post('/grants/{grant_id}/bind')
async def bind_grant(grant_id: str, body: GrantBindRequest, service=Depends(entitlement_service)):
    async with session_scope() as db:
        receipt = await service.bind_grant(db, grant_id=grant_id, **body.model_dump(exclude={'schema_version'}))
    return receipt.model_dump(mode='json')


@internal.get('/grants/{grant_id}/authorization')
async def authorization(grant_id: str, service=Depends(entitlement_service)):
    async with session_scope() as db:
        owner, root, grant = await service.lock_grant(db, grant_id)
        row = await db.get(EntitlementPolicyRow, grant.policy_revision)
        policy = EntitlementPolicy.model_validate(row.payload)
        status = 'expired' if root.status == 'active' and now_utc() >= grant.expires_at else root.status
        return dict(schema_version=1, status=status, current_revision=root.current_revision,
                    binding_revision=root.binding_revision, bound_task_id=root.bound_task_id,
                    overage=root.overage, model_risk_profile=policy.model_risk_profile,
                    revoked_capabilities=root.revoked_capabilities)


@internal.get('/grants/{grant_id}/revisions/{revision}')
async def grant_history(grant_id: str, revision: int):
    async with session_scope() as db:
        row = await db.get(GrantRevisionRow, (grant_id, revision))
        require(row is not None, 'GRANT_REVISION_NOT_FOUND', 404)
        return row.payload


@internal.post('/call-permits')
async def permit(body: CallPermitRequest, service=Depends(entitlement_service)):
    async with session_scope() as db:
        return await service.permit(db, body)


@internal.post('/call-permits/abandon')
async def abandon_permit(body: AbandonCall, service=Depends(entitlement_service)):
    async with session_scope() as db:
        return await service.abandon_request(db, body)


@internal.get('/call-permits/{permit_id}')
async def get_permit(permit_id: str):
    async with session_scope() as db:
        row = await db.get(CallPermitRow, permit_id)
        require(row is not None, 'PERMIT_NOT_FOUND', 404)
        return dict(schema_version=1, state=row.state, response=row.response, start=row.start)


@internal.post('/call-permits/{permit_id}/start')
async def start_permit(permit_id: str, body: PermitStart, service=Depends(entitlement_service)):
    async with session_scope() as db:
        return await service.start(db, permit_id, body)


@internal.post('/call-permits/{permit_id}/void')
async def void_permit(permit_id: str, body: VoidProof, service=Depends(entitlement_service)):
    require(permit_id == body.permit_id, 'PERMIT_ID_CONFLICT')
    async with session_scope() as db:
        await service.void(db, body)
    return dict(schema_version=1, state='void')


@internal.post('/usage-deltas:batch')
async def usage_batch(body: UsageBatch, service=Depends(entitlement_service)):
    require(body.producer_id == service.audience, 'PRODUCER_AUDIENCE_CONFLICT', 403)
    results = []
    gateway = AgentGatewayV2()
    for item in body.items:
        fact, error = None, None
        try:
            fact = await gateway.start_fact(item.task_id, item.call_id)
        except Exception:
            error = 'START_FACT_UNAVAILABLE'
        # Each receipt is its own durable transaction. A partial batch response
        # loss is safe; every original measurement_id is retransmitted.
        async with session_scope() as db:
            results.append(await UsageSettlement(service).ingest(db, item, fact, verification_error=error))
    return UsageBatchAck(schema_version=1, batch_id=body.batch_id, results=results).model_dump(mode='json')


@internal.post('/grants/{grant_id}/close')
async def close(grant_id: str, body: TaskCloseManifest, service=Depends(entitlement_service)):
    require(grant_id == body.grant_id, 'GRANT_ID_CONFLICT')
    async with session_scope() as db:
        status = await UsageSettlement(service).close(db, body)
    return dict(schema_version=1, settlement_status=status)


@router.get('/entitlements')
async def current_entitlements(owner: str = Depends(request_owner), service=Depends(entitlement_service)):
    async with session_scope() as db:
        row = await service.owner(db, owner)
        policy = await service.policy(db, row)
        windows = []
        for rule in policy.rules:
            window = rule.window(owner, policy.policy_revision, now_utc())
            counter = await db.get(WindowCounterRow, window.window_id)
            if counter:
                await service.refresh_rolling(db, counter, now_utc())
            held, used = (counter.held, counter.used) if counter else (0, 0)
            if rule.quota_pool:
                from app.services.agent_entitlements.admin import daily_balance
                used, held = await daily_balance(db, owner, window)
            windows.append(dict(window_ref=window.model_dump(mode='json'), rule_id=rule.rule_id,
                metric=rule.metric, unit=rule.unit, limit_units=rule.limit_units, held_units=held,
                used_units=used, remaining_units=max(0, rule.limit_units-held-used)))
        return dict(schema_version=1, owner_id=owner, plan_id=row.plan_id, policy_revision=policy.policy_revision,
                    token_scope=policy.token_scope, permission_snapshot=policy.permission_snapshot.model_dump(mode='json'), windows=windows)


@router.get('/tasks/{task_id}/usage')
async def task_usage(task_id: str, owner: str = Depends(request_owner), service=Depends(entitlement_service)):
    async with session_scope() as db:
        return await UsageSettlement(service).task_usage(db, task_id=task_id, owner_id=owner)


@router.get('/tasks/{task_id}/ledger')
async def task_ledger(task_id: str, owner: str = Depends(request_owner), service=Depends(entitlement_service)):
    async with session_scope() as db:
        await UsageSettlement(service).task_usage(db, task_id=task_id, owner_id=owner)
        root = await db.scalar(select(GrantRootRow).where(GrantRootRow.bound_task_id == task_id))
        entries = (await db.scalars(select(UsageLedgerRow).where(UsageLedgerRow.grant_id == root.grant_id)
                                   .order_by(UsageLedgerRow.created_at, UsageLedgerRow.entry_id))).all() if root else []
        return dict(schema_version=1, entries=[dict(entry_id=e.entry_id, allocation_id=e.allocation_id,
                    measurement_id=e.measurement_id, kind=e.kind, held_delta=e.held_delta, used_delta=e.used_delta,
                    evidence=e.evidence, created_at=e.created_at.isoformat()) for e in entries])


router.include_router(internal)
