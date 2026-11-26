"""Isolated v2 Gateway, fact-reader and Worker routes."""
from __future__ import annotations

import hmac
import json
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError, model_validator
from sqlalchemy import select

from agent_contracts import BudgetLimits, TaskSubmission, TaskSubmissionWire, ExecutionReport, UsageReport, PlatformEvent
from agent_contracts.execution_v2 import CallIntent, ObservationSubmission, WorkerIdentity, EventIngestV2, ReportIngestV2, RunSteerV2, GrantRevocation
from agent_contracts.v2 import (
    BudgetGrant, GrantBindingReceipt, TaskMeteringBinding, TaskMeteringBindingReceipt, TaskSubmissionV2, ID, Digest, V2,
)
from agent_app.control import repository
from agent_app.errors import BusinessError
from agent_app.control.metering import MeteringControl, GateDenied, check, uid
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.models import RunRow, TaskRow
from agent_app.infrastructure.metering_models import CallRow, ExecutionRow, TaskMeteringRow, GrantHistoryRow, GrantRevocationRow
from agent_app.integrations.backend.entitlements import EntitlementClient
from .routes import _task_json


class V2Route(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handle(request):
            try:
                return await original(request)
            except (GateDenied, BusinessError, ValidationError, RequestValidationError, ValueError) as exc:
                reason = exc.reason if isinstance(exc, GateDenied) else 'REQUEST_REJECTED' if isinstance(exc, BusinessError) else 'PROTOCOL_INVALID'
                status = exc.status if isinstance(exc, (GateDenied, BusinessError)) else 422
                return JSONResponse(status_code=status, content={'error': dict(schema_version=1, code=exc.code if isinstance(exc, BusinessError) else 20004,
                    message=reason, reason_code=reason, retryable=status == 503, request_id=uid(), retry_after_ms=None)})
        return handle


def role(env):
    async def dependency(authorization: str | None = Header(default=None)):
        expected = os.getenv(env, '').strip()
        others = [os.getenv(n, '').strip() for n in ('AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN',
                  'AGENT_WORKER_TOKEN', 'AGENT_CONTROL_TOKEN', 'AGENT_SERVICE_TOKEN') if n != env]
        check(expected and expected not in others, 'ROLE_CREDENTIALS_NOT_ISOLATED')
        check(hmac.compare_digest(authorization or '', f'Bearer {expected}'), 'ROLE_UNAUTHORIZED')
    return dependency


gateway = role('AGENT_GATEWAY_TOKEN')
worker = role('AGENT_WORKER_TOKEN')
fact_reader = role('AGENT_FACT_READER_TOKEN')
router = APIRouter(prefix='/internal/v2', route_class=V2Route)


def metering_control():
    issuer, audience = os.getenv('AGENT_GRANT_ISSUER', ''), os.getenv('AGENT_AUDIENCE', '')
    check(issuer and audience, 'AUTHORIZATION_ENVIRONMENT_UNCONFIGURED')
    keys = {}
    manifest = os.getenv('AGENT_GRANT_PUBLIC_KEYS_FILE', '')
    if manifest:
        # Map kid -> PEM, no URL-based or message-supplied key discovery.
        for kid, pem in json.loads(Path(manifest).read_text(encoding='utf-8')).items():
            key = serialization.load_pem_public_key(pem.encode())
            check(isinstance(key, Ed25519PublicKey), 'SIGNING_ALGORITHM_INVALID')
            keys[kid] = key
    return MeteringControl(issuer=issuer, audience=audience, public_keys=keys,
                          outbox_capacity=int(os.getenv('AGENT_USAGE_OUTBOX_CAPACITY', '0')))


async def task_v2(db, task_id, owner):
    task = await repository.get_task(db, task_id, owner, v2=True)
    profile = await db.get(TaskMeteringRow, task_id)
    return dict(_task_json(task), schema_version=1, metering_profile_id=profile.profile_id,
                metering_context=profile.context, submission_id=profile.submission_id,
                binding_status=profile.binding_status)


@router.get('/protocol-capabilities', dependencies=[Depends(gateway)])
async def protocols():
    return dict(schema_version=1, http_versions=[2], message_schema_versions=[1],
                execution_modes=['observation_only', 'authorized'], deployment=os.getenv('AGENT_AUDIENCE', ''),
                build_revision=os.getenv('AGENT_BUILD_REVISION', 'unconfigured'))


@router.get('/config-admission', dependencies=[Depends(gateway)])
async def configuration_admission(db=Depends(get_session)):
    from agent_app.config_deployment import mode, pointer
    from agent_app.config_scheduling import has_constraints
    if not await has_constraints(db):
        return {'schema_version': 1, 'open': mode() != 'enforce'}
    current = await pointer(db)
    is_open = not (current and current.admission_paused)
    if mode() == 'enforce':
        is_open = bool(is_open and current and current.active_revision)
    elif current and current.active_revision:
        is_open = False
    return {'schema_version': 1, 'open': is_open}


@router.post('/tasks', dependencies=[Depends(gateway)])
async def submit(body: TaskSubmissionV2, db=Depends(get_session), control=Depends(metering_control)):
    check(body.agent_audience == control.audience, 'AUDIENCE_CONFLICT')
    if body.budget_grant:
        check(os.getenv('AGENT_V1_ADMISSION') == 'drain_only', 'LEGACY_ADMISSION_NOT_DRAINED')
        control.verify_grant(body.budget_grant)
    # Profile identity supplies stable submission idempotency even before binding.
    raw = body.request.model_dump(mode='json')
    raw['idempotency_key'] = 'v2:' + body.metering_profile_id
    request = TaskSubmissionWire.model_validate(raw)
    task = await repository.submit(db, TaskSubmission(**dict(request.model_dump(exclude={'budget', 'skills', 'history'}),
        skills=tuple(request.skills), history=tuple(request.history), budget=BudgetLimits(**request.budget.model_dump()))), metering=body)
    profile = await db.scalar(select(TaskMeteringRow).where(TaskMeteringRow.task_id == task.task_id)
                              .with_for_update().execution_options(populate_existing=True))
    check(profile is not None and {k:v for k,v in profile.envelope.items() if k != 'budget_grant'} ==
          body.model_dump(mode='json', exclude={'budget_grant'}), 'SUBMISSION_ENVELOPE_CONFLICT')
    if body.budget_grant:
        previous = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
        check(previous.grant_id == body.budget_grant.grant_id, 'GRANT_ROOT_CONFLICT')
        if previous.revision == body.budget_grant.revision:
            check(previous == body.budget_grant, 'GRANT_REVISION_CONFLICT')
        else:
            check(profile.binding_status == 'pending' and body.budget_grant.revision > previous.revision, 'GRANT_REVISION_CONFLICT')
            profile.current_grant = body.budget_grant.model_dump(mode='json')
        for revision in (previous, body.budget_grant):
            if await db.get(GrantHistoryRow, (revision.grant_id, revision.revision)) is None:
                db.add(GrantHistoryRow(grant_id=revision.grant_id, revision=revision.revision, task_id=task.task_id,
                                       payload=revision.model_dump(mode='json')))
                await db.flush()
    # Network outside any local write transaction. A crash leaves pending.
    await db.commit()
    client = EntitlementClient()
    binding = TaskMeteringBinding(schema_version=1, operation_id=profile.profile_id, metering_profile_id=profile.profile_id,
        agent_audience=control.audience, task_id=task.task_id, owner_id=body.owner_id,
        request_digest=body.request_digest, submission_id_source='backend' if body.budget_grant else 'agent_observation',
        submission_id=profile.submission_id)
    confirmed = TaskMeteringBindingReceipt.model_validate(await client.request('POST', '/task-metering-bindings', binding.model_dump(mode='json')))
    check((confirmed.metering_profile_id, confirmed.task_id, confirmed.metering_context,
           confirmed.submission_id_source, confirmed.submission_id) == (binding.metering_profile_id,
           binding.task_id, body.metering_context, binding.submission_id_source, binding.submission_id), 'METERING_BINDING_CONFLICT')
    receipt = None
    if body.budget_grant:
        grant = body.budget_grant
        receipt = GrantBindingReceipt.model_validate(await client.request('POST', f'/grants/{grant.grant_id}/bind', dict(
            schema_version=1, task_id=task.task_id, owner_id=body.owner_id, submission_id=body.submission_id,
            request_digest=body.request_digest, expected_revision=grant.revision, expected_binding_revision=0)))
        historical_row = await db.get(GrantHistoryRow, (grant.grant_id, receipt.grant_revision))
        if historical_row:
            historical = BudgetGrant.model_validate(historical_row.payload)
        else:
            historical = BudgetGrant.model_validate(await client.request('GET',
                f'/grants/{grant.grant_id}/revisions/{receipt.grant_revision}'))
        control.verify_receipt(grant, receipt, task.task_id, historical)
    profile = await db.scalar(select(TaskMeteringRow).where(TaskMeteringRow.task_id == task.task_id).with_for_update().execution_options(populate_existing=True))
    check(not profile.revoked, 'GRANT_REVOKED')
    if profile.receipt:
        check(receipt is not None and profile.receipt == receipt.model_dump(mode='json'), 'BINDING_RECEIPT_CONFLICT')
    profile.binding, profile.receipt = confirmed.model_dump(mode='json'), receipt.model_dump(mode='json') if receipt else None
    profile.binding_status = 'bound'
    await db.commit()
    return await task_v2(db, task.task_id, body.owner_id)


@router.get('/tasks/{task_id}', dependencies=[Depends(gateway)])
async def task(task_id: str, owner_id: str, db=Depends(get_session)):
    return await task_v2(db, task_id, owner_id)


@router.get('/submissions/{submission_id}', dependencies=[Depends(gateway)])
async def submission(submission_id: str, owner_id: str, db=Depends(get_session)):
    check(not submission_id.startswith('obs:'), 'FORMAL_SUBMISSION_REQUIRED')
    profile = await db.scalar(select(TaskMeteringRow).where(TaskMeteringRow.submission_id == submission_id,
                                                           TaskMeteringRow.owner_id == owner_id,
                                                           TaskMeteringRow.context == 'authorized'))
    check(profile is not None, 'SUBMISSION_NOT_FOUND')
    return await task_v2(db, profile.task_id, owner_id)


@router.get('/tasks/{task_id}/runs', dependencies=[Depends(gateway)])
async def runs(task_id: str, owner_id: str, db=Depends(get_session)):
    await task_v2(db, task_id, owner_id)
    return dict(schema_version=1, run_ids=list((await db.scalars(select(RunRow.run_id).where(RunRow.task_id == task_id)
                                                                              .order_by(RunRow.attempt))).all()))


@router.get('/tasks/{task_id}/call-facts/{call_id}', dependencies=[Depends(fact_reader)])
async def fact(task_id: str, call_id: str, db=Depends(get_session)):
    row = await db.get(CallRow, call_id)
    if row is None or row.task_id != task_id or row.start_fact is None:
        raise GateDenied('START_FACT_NOT_FOUND', 404)
    return row.start_fact


@router.get('/tasks/{task_id}/close-facts', dependencies=[Depends(fact_reader)])
async def close_facts(task_id: str, db=Depends(get_session), control=Depends(metering_control)):
    task = await db.scalar(select(TaskRow).where(TaskRow.task_id == task_id)
                           .with_for_update().execution_options(populate_existing=True))
    if task is None:
        raise GateDenied('TASK_NOT_FOUND', 404)
    # This read creates no manifest/outbox records and does not seal anything.
    manifest = await control.close_manifest(db, task_id)
    return dict(task_status=task.status, manifest=manifest.model_dump(mode='json'))


@router.post('/worker/claim', dependencies=[Depends(worker)])
async def claim(body: dict, db=Depends(get_session), control=Depends(metering_control),
                x_worker_instance: str | None = Header(default=None),
                x_worker_report_token: str | None = Header(default=None)):
    check(set(body) == {'schema_version', 'worker_id'} and body['schema_version'] == 1 and bool(body['worker_id']), 'PROTOCOL_INVALID')
    # Claim only locally bound v2 tasks. Authorized current-state online check
    # precedes execution; every real call still repeats Backend start validation.
    claimed = await repository.claim_run(db, body['worker_id'], v2=True, worker_instance=x_worker_instance,
                                         worker_report_token=x_worker_report_token)
    if claimed is None:
        return {'schema_version': 1, 'run': None}
    request, lease_token, event_seq = claimed
    profile = await db.get(TaskMeteringRow, request.task_id)
    execution = await db.scalar(select(ExecutionRow).where(ExecutionRow.run_id == request.run_id,
                                                         ExecutionRow.lease_token == lease_token))
    if profile.context == 'authorized':
        grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
        try:
            control.verify_grant(grant)
            await db.commit()
            state = await EntitlementClient().request('GET', f'/grants/{grant.grant_id}/authorization')
            check(state['status'] == 'active' and state['current_revision'] == grant.revision and not state['overage'], 'GRANT_INACTIVE')
        except (GateDenied, ValueError) as exc:
            if not isinstance(exc, GateDenied) or exc.status != 503:
                from agent_contracts import RunStatus
                await repository.record_report(db, ExecutionReport(run_id=request.run_id, task_id=request.task_id,
                    status=RunStatus.FAILED, usage=UsageReport(), error_code='authorization_denied',
                    error_message='执行授权无效'), body['worker_id'], lease_token)
            raise
        await control.lock_execution(db, WorkerIdentity(schema_version=1, worker_id=body['worker_id'], lease_token=lease_token,
                                                        execution_id=execution.execution_id))
        await db.commit()
    from agent_app.config_deployment import mode
    from agent_app.config_scheduling import claim_constraint
    constraint = await claim_constraint(db, request.task_id) if mode() == 'enforce' else None
    return dict(**({'execution_config': constraint} if constraint else {}),
                schema_version=1, run=repository._request_dict(request), lease_token=lease_token,
                event_seq=event_seq, execution_id=execution.execution_id,
                metering_context=profile.context, metering_profile_id=profile.profile_id,
                risk_profile=state['model_risk_profile'] if profile.context == 'authorized' else None,
                dynamic_model_budget=(grant.execution_constraints.get('model_call_budget') == 'dynamic_v1'
                                      if profile.context == 'authorized' else False))


@router.post('/runs/{run_id}/call-intents', dependencies=[Depends(worker)])
@router.post('/runs/{run_id}/calls/authorize', dependencies=[Depends(worker)])
async def intent(run_id: str, body: CallIntent, request: Request, db=Depends(get_session), control=Depends(metering_control)):
    execution = await db.get(ExecutionRow, body.execution_id)
    check(execution is not None, 'EXECUTION_NOT_FOUND')
    profile = await db.get(TaskMeteringRow, execution.task_id)
    check((profile.context == 'authorized') == request.url.path.endswith('/authorize'), 'METERING_MODE_CONFLICT')
    row = await control.intent(db, run_id, body)
    if row.call_id != body.call_id:
        if profile.context == 'authorized':
            grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
            await db.commit()
            state = await EntitlementClient().request('GET', f'/grants/{grant.grant_id}/authorization')
            check(state['status'] == 'active' and state['current_revision'] == grant.revision and
                  [body.capability_identity.capability_id, row.start_fact['capability_version']] not in state['revoked_capabilities'],
                  'GRANT_INACTIVE')
        return dict(schema_version=1, call_id=row.call_id, activation_already_recorded=True)
    await db.commit()
    if profile.context == 'authorized' and row.state == 'requesting':
        permit_request = await control.permit_request(db, row.call_id)
        await db.commit()
        response = await EntitlementClient().request('POST', '/call-permits', permit_request.model_dump(mode='json'))
        accepted = await control.attach_permit(db, row.call_id, response)
        await db.commit()
        check(accepted, response.get('reason_code') or 'CALL_DENIED')
    return dict(schema_version=1, call_id=row.call_id, state=row.state, activation_already_recorded=False,
        **({'model_budget': row.permit['permit']['model_budget']}
           if row.permit and row.permit.get('permit', {}).get('model_budget') else {}))


@router.post('/calls/{call_id}/start', dependencies=[Depends(worker)])
async def start(call_id: str, body: WorkerIdentity, db=Depends(get_session), control=Depends(metering_control)):
    row, operation = await control.prepare_start(db, call_id, body)
    await db.commit()
    if operation is None:
        return dict(schema_version=1, may_send=False, already_started=True, fact=row.start_fact)
    backend_start = None
    if row.permit:
        permit_id = row.permit['permit']['permit_id']
        backend_start = await EntitlementClient().request('POST', f'/call-permits/{permit_id}/start', operation.model_dump(mode='json'))
    result = await control.commit_start(db, call_id, body, backend_start)
    await db.commit()  # fact + first observation + outbox BEFORE issuing send receipt
    return result


@router.post('/usage-observations', dependencies=[Depends(worker)])
async def observe(body: ObservationSubmission, db=Depends(get_session), control=Depends(metering_control)):
    usage = await control.observe(db, body)
    await db.commit()
    if usage.metering_context == 'authorized':
        from agent_app.control.usage_delivery import settle_observation
        try:
            await settle_observation(db, EntitlementClient(), usage)
        except GateDenied as exc:
            if exc.status < 500 and exc.reason != 'USAGE_SETTLEMENT_UNCONFIRMED':
                raise
            await db.rollback()
            # Observation and Outbox were committed above. Acknowledge durable
            # ingestion; pending reserves remain held until delivery settles.
            logging.getLogger('agent.usage').warning(
                'Settlement deferred to Outbox task_id=%s measurement_id=%s reason=%s',
                usage.task_id, usage.measurement_id, exc.reason)
    return usage.model_dump(mode='json')


@router.get('/runs/{run_id}', dependencies=[Depends(gateway)])
async def run(run_id: str, owner_id: str, db=Depends(get_session)):
    row, task = await repository.get_run(db, run_id, owner_id, v2=True)
    return dict(schema_version=1, run_id=run_id, task_id=task.task_id, attempt=row.attempt,
                status=row.status, task_status=task.status, report=row.report_json,
                created_at=row.created_at.isoformat(), started_at=row.started_at.isoformat() if row.started_at else None,
                completed_at=row.completed_at.isoformat() if row.completed_at else None)


@router.get('/runs/{run_id}/events', dependencies=[Depends(gateway)])
async def events(run_id: str, owner_id: str, after_seq: int = 0, db=Depends(get_session)):
    await repository.get_run(db, run_id, owner_id, v2=True)
    from agent_app.infrastructure.models import RunEventRow
    rows = (await db.scalars(select(RunEventRow).where(RunEventRow.run_id == run_id,
                RunEventRow.seq > after_seq).order_by(RunEventRow.seq))).all()
    return dict(schema_version=1, events=[dict(task_id=e.task_id, run_id=e.run_id, seq=e.seq,
                turn=e.turn, name=e.name, data=e.data, occurred_at=e.occurred_at.isoformat()) for e in rows])


@router.post('/tasks/{task_id}/cancel', dependencies=[Depends(gateway)])
async def cancel(task_id: str, owner_id: str, db=Depends(get_session)):
    await repository.get_task(db, task_id, owner_id, v2=True)
    await repository.request_cancel(db, task_id, owner_id)
    return await task_v2(db, task_id, owner_id)


@router.post('/runs/{run_id}/steer', dependencies=[Depends(gateway)])
async def steer(run_id: str, body: RunSteerV2, db=Depends(get_session)):
    await repository.get_run(db, run_id, body.owner_id, v2=True)
    result = await repository.append_steer(db, run_id, body.owner_id, body.text)
    return dict(result, schema_version=1)


@router.post('/runs/{run_id}/heartbeat', dependencies=[Depends(worker)])
async def heartbeat(run_id: str, body: WorkerIdentity, db=Depends(get_session), control=Depends(metering_control)):
    await control.lock_execution(db, body, run_id=run_id)
    active, cancelled = await repository.heartbeat(db, run_id, body.worker_id, body.lease_token)
    return dict(schema_version=1, active=active, cancel_requested=cancelled)


@router.get('/runs/{run_id}/controls', dependencies=[Depends(worker)])
async def controls(run_id: str, worker_id: str, lease_token: int, execution_id: str,
                   after_seq: int = 0, db=Depends(get_session), control=Depends(metering_control)):
    body = WorkerIdentity(schema_version=1, worker_id=worker_id, lease_token=lease_token, execution_id=execution_id)
    execution, _, _, _ = await control.lock_execution(db, body, run_id=run_id)
    from agent_app.infrastructure.models import RunControlRow
    rows = (await db.scalars(select(RunControlRow).where(RunControlRow.run_id == run_id,
                    RunControlRow.seq > after_seq).order_by(RunControlRow.seq))).all()
    return dict(schema_version=1, controls=[dict(run_id=e.run_id, seq=e.seq, name=e.name,
                                               text=e.text, created_at=e.created_at.isoformat()) for e in rows])


@router.post('/runs/{run_id}/events', dependencies=[Depends(worker)])
async def append_event(run_id: str, body: EventIngestV2, db=Depends(get_session), control=Depends(metering_control)):
    await control.lock_execution(db, WorkerIdentity.model_validate(body.model_dump(include={'schema_version','worker_id','lease_token','execution_id'})), run_id=run_id)
    check(run_id == body.run_id, 'RUN_CONFLICT')
    await repository.append_event(db, PlatformEvent(body.task_id, body.run_id, body.seq,
        body.turn, body.name, body.data, body.occurred_at), body.worker_id, body.lease_token)
    return dict(schema_version=1, stored=True)


@router.post('/runs/{run_id}/report', dependencies=[Depends(worker)])
async def report(run_id: str, body: ReportIngestV2, db=Depends(get_session)):
    execution = await db.get(ExecutionRow, body.execution_id)
    check(execution is not None and (execution.run_id, execution.task_id, execution.worker_id, execution.lease_token) ==
          (run_id, body.task_id, body.worker_id, body.lease_token), 'EXECUTION_CONFLICT')
    check(body.run_id == run_id, 'RUN_CONFLICT')
    await repository.record_report(db, ExecutionReport(run_id=run_id, task_id=body.task_id, status=body.status,
        result=body.result, usage=UsageReport(**body.usage.model_dump()), error_code=body.error_code,
        error_message=body.error_message), body.worker_id, body.lease_token)
    return dict(schema_version=1, stored=True)


@router.post('/grants/{grant_id}/revisions', dependencies=[Depends(gateway)])
async def grant_revision(grant_id: str, body: BudgetGrant, db=Depends(get_session), control=Depends(metering_control)):
    check(body.grant_id == grant_id, 'GRANT_ID_CONFLICT')
    control.verify_grant(body)
    state = await EntitlementClient().request('GET', f'/grants/{grant_id}/authorization')
    check(state['status'] == 'active' and state['current_revision'] == body.revision, 'GRANT_INACTIVE')
    profile = await db.scalar(select(TaskMeteringRow).where(TaskMeteringRow.submission_id == body.submission_id,
                                                           TaskMeteringRow.context == 'authorized').with_for_update().execution_options(populate_existing=True))
    check(profile is not None and not profile.revoked and profile.receipt is not None, 'GRANT_BINDING_PENDING')
    previous = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
    check((body.owner_id, body.submission_id, body.grant_id, body.reservation_id, body.request_digest,
           body.task_id, body.binding_receipt_id) == (previous.owner_id, previous.submission_id, previous.grant_id,
           previous.reservation_id, previous.request_digest, profile.task_id, profile.receipt['receipt_id']), 'GRANT_BINDING_CONFLICT')
    old = await db.get(GrantHistoryRow, (grant_id, body.revision))
    if old:
        check(old.payload == body.model_dump(mode='json'), 'GRANT_REVISION_CONFLICT')
    else:
        check(body.revision > previous.revision, 'GRANT_REVISION_CONFLICT')
        # Keep the original null revision as signed, including its original key.
        if await db.get(GrantHistoryRow, (grant_id, previous.revision)) is None:
            db.add(GrantHistoryRow(grant_id=grant_id, revision=previous.revision, task_id=profile.task_id,
                                   payload=previous.model_dump(mode='json')))
        db.add(GrantHistoryRow(grant_id=grant_id, revision=body.revision, task_id=profile.task_id,
                               payload=body.model_dump(mode='json')))
        profile.current_grant = body.model_dump(mode='json')
    await db.commit()
    return dict(schema_version=1, current_revision=max(body.revision, previous.revision))


@router.post('/grants/{grant_id}/revocations', dependencies=[Depends(gateway)])
async def revocation(grant_id: str, body: GrantRevocation, db=Depends(get_session)):
    profile = await db.scalar(select(TaskMeteringRow).where(TaskMeteringRow.submission_id == body.submission_id,
                                                           TaskMeteringRow.context == 'authorized').with_for_update().execution_options(populate_existing=True))
    check(profile is not None and profile.envelope['budget_grant']['grant_id'] == grant_id, 'GRANT_ID_CONFLICT')
    old = await db.get(GrantRevocationRow, body.operation_id)
    if old:
        check(old.task_id == profile.task_id and old.payload == body.model_dump(mode='json'), 'REVOCATION_CONFLICT')
    else:
        db.add(GrantRevocationRow(operation_id=body.operation_id, task_id=profile.task_id, payload=body.model_dump(mode='json')))
    if body.capability_id is None:
        profile.revoked = True
    else:
        pair = [body.capability_id, body.capability_version]
        if pair not in profile.revoked_capabilities:
            profile.revoked_capabilities = [*profile.revoked_capabilities, pair]
    await db.commit()
    if body.capability_id is None:
        await repository.request_cancel(db, profile.task_id, profile.owner_id)
    return dict(schema_version=1, revoked=profile.revoked, revoked_capabilities=profile.revoked_capabilities)
