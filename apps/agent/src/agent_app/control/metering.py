"""Control-owned call facts and v2 authorization Saga. No Backend DB access."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import select

from agent_contracts.canonical import digest
from agent_contracts.execution_v2 import CallIntent, ObservationSubmission, WorkerIdentity
from agent_contracts.signing import verify_signed
from agent_contracts.v2 import (
    BudgetGrant, CallIdentity, CallPermitRequest, CallPermitResponse, CallStartFact, GrantBindingReceipt,
    PermitStart, RequestedAllocation, TaskCloseManifest, UsageDelta,
)
from agent_app.infrastructure.models import RunRow, TaskRow
from agent_app.infrastructure.metering_models import (
    CallRow, ExecutionRow, ObservationRow, TaskMeteringRow, UsageOutboxRow,
)


def now_utc():
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def uid():
    return uuid.uuid4().hex


class GateDenied(Exception):
    def __init__(self, reason, status=403):
        self.reason, self.status = reason, status
        super().__init__(reason)


def check(condition, reason):
    if not condition:
        logging.getLogger('agent.authorization').warning('Execution gate denied reason=%s', reason)
        raise GateDenied(reason)


class MeteringControl:
    def __init__(self, *, issuer, audience, public_keys, outbox_capacity: int):
        check(outbox_capacity > 0, 'OUTBOX_CAPACITY_REQUIRED')
        self.issuer, self.audience, self.public_keys = issuer, audience, public_keys
        self.outbox_capacity = outbox_capacity

    def verify_grant(self, grant):
        check(grant.execution_constraints.get('reservation_mode', 'task_fixed') in ('task_fixed', 'per_call'),
              'RESERVATION_MODE_UNSUPPORTED')
        verify_signed(grant, issuer=self.issuer, audience=self.audience, public_keys=self.public_keys)
        check(grant.not_before <= now_utc() < grant.expires_at, 'GRANT_EXPIRED')

    def verify_receipt(self, grant, receipt, task_id, historical_grant=None):
        verify_signed(receipt, issuer=self.issuer, audience=self.audience, public_keys=self.public_keys)
        historical = historical_grant or grant
        verify_signed(historical, issuer=self.issuer, audience=self.audience, public_keys=self.public_keys)
        check((receipt.grant_id, receipt.grant_revision, receipt.owner_id, receipt.submission_id,
               receipt.reservation_id, receipt.request_digest, receipt.bound_task_id) ==
              (grant.grant_id, historical.revision, grant.owner_id, grant.submission_id,
               grant.reservation_id, grant.request_digest, task_id), 'BINDING_RECEIPT_CONFLICT')
        check((historical.grant_id, historical.owner_id, historical.submission_id, historical.reservation_id,
               historical.request_digest) == (grant.grant_id, grant.owner_id, grant.submission_id, grant.reservation_id,
                                               grant.request_digest), 'HISTORICAL_GRANT_CONFLICT')
        check(grant.task_id in (None, task_id) and grant.binding_receipt_id in (None, receipt.receipt_id), 'ROOT_BINDING_CONFLICT')
        check(receipt.grant_payload_digest == digest(historical.model_dump(mode='json', exclude={'signature'})), 'BINDING_DIGEST_CONFLICT')

    async def lock_execution(self, db, identity: WorkerIdentity, *, run_id=None, task_id=None,
                             allow_cancel_requested=False):
        execution = await db.get(ExecutionRow, identity.execution_id)
        check(execution is not None, 'EXECUTION_NOT_FOUND')
        # Task -> Run -> Call is also the claim/cancel/report order.
        task = await db.scalar(select(TaskRow).where(TaskRow.task_id == execution.task_id).with_for_update().execution_options(populate_existing=True))
        execution = await db.get(ExecutionRow, identity.execution_id, populate_existing=True)
        run = await db.scalar(select(RunRow).where(RunRow.run_id == execution.run_id).with_for_update().execution_options(populate_existing=True))
        profile = await db.get(TaskMeteringRow, execution.task_id, populate_existing=True)
        check(task is not None and profile is not None and run is not None, 'TASK_NOT_FOUND')
        check(run_id is None or run.run_id == run_id, 'RUN_CONFLICT')
        check(task_id is None or task.task_id == task_id, 'TASK_CONFLICT')
        check((execution.worker_id, execution.lease_token) == (identity.worker_id, identity.lease_token), 'EXECUTION_CONFLICT')
        task_active = task.status == 'running' or (
            allow_cancel_requested and task.status == 'cancelling' and task.cancel_requested)
        check(not execution.sealed and run.status == 'running' and task_active
              and (allow_cancel_requested or not task.cancel_requested) and run.worker_id == identity.worker_id
              and run.lease_token == identity.lease_token and run.lease_expires_at is not None
              and run.lease_expires_at.replace(tzinfo=timezone.utc) > now_utc(), 'LEASE_INACTIVE')
        check(profile.binding_status == 'bound' and not profile.revoked, 'TASK_BINDING_PENDING')
        return execution, task, run, profile

    async def intent(self, db, run_id: str, body: CallIntent):
        execution, task, run, profile = await self.lock_execution(db, body, run_id=run_id)
        # Unsettled calls retain their reservations in Backend. A pending
        # receipt must not block every task of this owner; each new permit
        # still checks used + held under the owner lock and the outbox cap.
        from sqlalchemy import func
        backlog = await db.scalar(select(func.count()).select_from(UsageOutboxRow).where(
            UsageOutboxRow.state != 'delivered'))
        check(backlog < self.outbox_capacity, 'USAGE_OUTBOX_BACKPRESSURE')
        existing = await db.get(CallRow, body.call_id)
        raw = body.model_dump(mode='json')
        if existing:
            check(existing.intent == raw, 'CALL_ID_CONFLICT')
            return existing
        capability = body.capability_identity
        version = digest(capability.model_dump(mode='json'))
        check([capability.capability_id, version] not in profile.revoked_capabilities, 'CAPABILITY_REVOKED')
        if profile.context == 'authorized':
            grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
            self.verify_grant(grant)
            check(profile.receipt is not None, 'GRANT_BINDING_PENDING')
            permission = next((p for p in grant.capabilities if (p.capability_id, p.capability_version) ==
                               (capability.capability_id, version)), None)
            if permission is None:
                logging.getLogger('agent.authorization').warning(
                    'Capability mismatch task_id=%s policy=%s capability=%s requested_version=%s granted_version=%s',
                    task.task_id, grant.policy_revision, capability.capability_id, version,
                    next((p.capability_version for p in grant.capabilities
                          if p.capability_id == capability.capability_id), None))
            check(permission is not None and body.purpose in permission.purposes
                  and body.invocation_mode in permission.invocation_modes, 'CAPABILITY_NOT_AUTHORIZED')
            permitted = {(p.capability_id, p.capability_version) for p in grant.capabilities
                         if [p.capability_id, p.capability_version] not in profile.revoked_capabilities}
            check(all((k, v) in permitted for k, v in permission.dependency_versions.items()), 'DEPENDENCY_NOT_AUTHORIZED')
        if capability.kind == 'skill':
            activation_key = digest([capability.capability_id, version])
            prior = await db.scalar(select(CallRow).where(CallRow.task_id == task.task_id,
                                                          CallRow.activation_key == activation_key))
            if prior:
                check(prior.start_fact is not None and prior.state == 'completed', 'SKILL_ACTIVATION_PENDING')
                return prior
        else:
            activation_key = None
        if body.parent_call_id is not None:
            parent = await db.get(CallRow, body.parent_call_id)
            check(parent is not None and parent.task_id == task.task_id and parent.execution_id == execution.execution_id
                  and parent.start_fact is not None, 'PARENT_CALL_CONFLICT')
        row = CallRow(call_id=body.call_id, task_id=task.task_id, execution_id=execution.execution_id,
                      activation_key=activation_key, state='requesting' if profile.context == 'authorized' else 'authorized',
                      intent=raw, revision=0)
        db.add(row)
        await db.flush()
        return row

    async def permit_request(self, db, call_id):
        row = await db.get(CallRow, call_id)
        check(row is not None and row.state == 'requesting', 'CALL_NOT_REQUESTING')
        body = CallIntent.model_validate(row.intent)
        execution, task, run, profile = await self.lock_execution(db, body)
        if row.backend_request is not None:
            return CallPermitRequest.model_validate(row.backend_request)
        grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
        receipt = GrantBindingReceipt.model_validate(profile.receipt)
        # Legacy upper bounds come from the deployment policy. In dynamic_v1,
        # Token allocations identify the bucket only; Backend computes held units
        # from model_budget under the owner lock (zero here is NOT a free call).
        bounds = profile.envelope.get('call_bounds', {})
        allocations = [a for a in grant.allocations if (a.capability_id is None or a.capability_id == body.capability_identity.capability_id)
                       and a.purpose in ('all', body.purpose)
                       and (a.unit == 'token' and body.purpose in ('main', 'summary') or
                            a.unit == 'activation' and body.purpose == 'skill_activation' or
                            a.unit == 'call' and body.purpose != 'skill_activation')]
        check(all(a.rule_id in bounds for a in allocations), 'CALL_BOUND_UNCONFIGURED')
        request = CallPermitRequest(schema_version=1, call_id=row.call_id, logical_call_id=body.logical_call_id,
            request_digest=body.request_digest, grant_id=grant.grant_id, grant_revision=grant.revision,
            reservation_id=grant.reservation_id, binding_receipt_id=receipt.receipt_id,
            owner_id=task.owner_id, submission_id=grant.submission_id, task_id=task.task_id,
            run_id=run.run_id, execution_id=execution.execution_id, control_attestation_id=row.call_id,
            capability_id=body.capability_identity.capability_id, capability_version=digest(body.capability_identity.model_dump(mode='json')),
            invocation_mode=body.invocation_mode, purpose=body.purpose,
            requested_allocations=[RequestedAllocation(schema_version=1, allocation_id=a.allocation_id, metric=a.metric,
                unit=a.unit, upper_bound_units=bounds[a.rule_id]) for a in allocations],
            input_bound_evidence_ref=body.input_bound_evidence_ref, output_bound_evidence_ref=body.output_bound_evidence_ref,
            risk_profile=body.risk_profile, model_budget=body.model_budget)
        row.backend_request = request.model_dump(mode='json')
        return request

    async def attach_permit(self, db, call_id, response):
        response = CallPermitResponse.model_validate(response).model_dump(mode='json')
        row = await db.get(CallRow, call_id)
        body = CallIntent.model_validate(row.intent)
        await self.lock_execution(db, body)
        check(response['call_id'] == call_id and response['request_digest'] == body.request_digest, 'PERMIT_RESPONSE_CONFLICT')
        if response['decision'] != 'authorized':
            row.state, row.permit = 'void', response
            return False
        if row.permit is not None:
            check(row.permit == response, 'PERMIT_RESPONSE_CONFLICT')
        budget = response['permit'].get('model_budget')
        if budget:
            check(body.model_budget is not None and budget['basis'] == body.model_budget.basis
                  and budget['output_tokens'] <= min(body.model_budget.requested_output_tokens, body.model_budget.model_max_output_tokens),
                  'MODEL_BUDGET_CONFLICT')
            token_allocations = [a for a in response['permit']['allocations'] if a['unit'] == 'token']
            check(bool(token_allocations) and all(a['held_units'] == budget['reserved_tokens'] for a in token_allocations),
                  'MODEL_BUDGET_CONFLICT')
        row.permit, row.state = response, 'authorized'
        return True

    async def prepare_start(self, db, call_id, identity: WorkerIdentity):
        _, _, _, profile = await self.lock_execution(db, identity)
        row = await db.scalar(select(CallRow).where(CallRow.call_id == call_id).with_for_update().execution_options(populate_existing=True))
        check(row is not None and row.execution_id == identity.execution_id, 'CALL_EXECUTION_CONFLICT')
        if row.start_fact:
            return row, None
        check(row.state in ('authorized', 'starting'), 'CALL_NOT_AUTHORIZED')
        row.state = 'starting'
        row.start_operation_id = row.start_operation_id or uid()
        return row, PermitStart(schema_version=1, start_operation_id=row.start_operation_id, execution_id=row.execution_id,
                                 control_attestation_id=row.call_id)

    async def commit_start(self, db, call_id, identity, backend_start=None):
        execution, task, run, profile = await self.lock_execution(db, identity)
        row = await db.scalar(select(CallRow).where(CallRow.call_id == call_id).with_for_update().execution_options(populate_existing=True))
        check(row is not None and row.execution_id == identity.execution_id, 'CALL_EXECUTION_CONFLICT')
        if row.start_fact:
            return {'schema_version': 1, 'may_send': False, 'already_started': True, 'fact': row.start_fact}
        check(row.state == 'starting', 'CALL_NOT_STARTING')
        now = now_utc()
        grant = None
        if profile.context == 'authorized':
            grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
            self.verify_grant(grant)
            check(backend_start is not None and backend_start['start_operation_id'] == row.start_operation_id, 'START_NOT_COMMITTED')
            check(row.permit['permit']['grant_revision'] == grant.revision, 'GRANT_REVISION_CONFLICT')
            cutoff = datetime.fromisoformat(backend_start['start_before'])
            check(now < cutoff, 'START_DEADLINE_EXCEEDED')
            row.start_before = cutoff
        body = CallIntent.model_validate(row.intent)
        data = dict(schema_version=1, agent_audience=self.audience, task_id=task.task_id, run_id=run.run_id,
                    execution_id=execution.execution_id, call_id=row.call_id, logical_call_id=body.logical_call_id,
                    metering_profile_id=profile.profile_id, metering_context=profile.context,
                    submission_id_source='backend' if grant else 'agent_observation', submission_id=profile.submission_id,
                    owner_id=task.owner_id, control_attestation_id=row.call_id, started_at=now,
                    capability_id=body.capability_identity.capability_id,
                    capability_version=digest(body.capability_identity.model_dump(mode='json')),
                    capability_identity_profile='capability_identity_v1', capability_identity=body.capability_identity.model_dump(mode='json'),
                    invocation_mode=body.invocation_mode, purpose=body.purpose, parent_call_id=body.parent_call_id,
                    activation_id=body.activation_id, grant_id=grant.grant_id if grant else None,
                    grant_revision=grant.revision if grant else None, reservation_id=grant.reservation_id if grant else None,
                    permit_id=row.permit['permit']['permit_id'] if grant else None,
                    fact_kind='activation' if body.activation_id else 'started', start_record_id=uid(), recorded_at=now)
        # Construct once using canonical time formatting before hashing.
        from agent_contracts.canonical import canonical_json_v1, parse_canonical
        data = parse_canonical(canonical_json_v1(data))
        fact = CallStartFact.model_validate({**data, 'start_record_digest': digest(data)})
        row.start_fact = fact.model_dump(mode='json')
        row.state = 'started'
        is_model = body.capability_identity.kind == 'model'
        await self.append(db, row, profile, 'control:start', dict(
            outcome='in_progress', prompt_tokens=None, completion_tokens=None,
            usage_status='unknown' if is_model else 'measured', usage_source=None if is_model else 'not_applicable',
            missing_reason='pending_completion' if is_model else None, attempted_units=1, successful_units=None,
            provider_request_id=None, ended_at=None), phase='started')
        return {'schema_version': 1, 'may_send': True, 'already_started': False, 'fact': row.start_fact,
                'start_before': row.start_before.isoformat() if row.start_before else None,
                **({'model_budget': row.permit['permit']['model_budget']}
                   if row.permit and row.permit.get('permit', {}).get('model_budget') else {})}

    async def append(self, db, row, profile, key, observation, *, phase='completed'):
        content_digest = digest(observation)
        existing = await db.scalar(select(ObservationRow).where(
            ObservationRow.call_id == row.call_id, ObservationRow.submission_key == key))
        if existing:
            check(existing.submission_digest == content_digest, 'OBSERVATION_SUBMISSION_CONFLICT')
            return UsageDelta.model_validate(existing.payload)
        previous = await db.scalar(select(ObservationRow).where(ObservationRow.call_id == row.call_id)
                                    .order_by(ObservationRow.revision.desc()).limit(1))
        fact = CallStartFact.model_validate(row.start_fact)
        body = CallIntent.model_validate(row.intent)
        row.revision += 1
        profile.usage_sequence += 1
        fields = {k: fact.model_dump(mode='json')[k] for k in CallIdentity.model_fields}
        usage = UsageDelta.model_validate(dict(fields, **observation, measurement_id=uid(),
            observation_revision=row.revision, supersedes_measurement_id=previous.measurement_id if previous else None,
            logical_attempt=body.logical_attempt, transport_attempt=body.transport_attempt, provider_id=body.provider_id,
            phase=phase, observed_at=now_utc(), task_usage_sequence=profile.usage_sequence))
        db.add(ObservationRow(measurement_id=usage.measurement_id, call_id=row.call_id, task_id=row.task_id,
                              revision=usage.observation_revision, sequence=usage.task_usage_sequence,
                              submission_key=key, submission_digest=content_digest, payload=usage.model_dump(mode='json')))
        await db.flush()
        db.add(UsageOutboxRow(measurement_id=usage.measurement_id, state='pending', attempts=0, available_at=now_utc()))
        return usage

    async def observe(self, db, body: ObservationSubmission):
        # Historical execution credentials may finish ONLY an existing started call.
        execution = await db.get(ExecutionRow, body.execution_id)
        check(execution is not None and (execution.worker_id, execution.lease_token) ==
              (body.worker_id, body.lease_token), 'HISTORICAL_EXECUTION_CONFLICT')
        await db.scalar(select(TaskRow).where(TaskRow.task_id == execution.task_id).with_for_update().execution_options(populate_existing=True))
        profile = await db.get(TaskMeteringRow, execution.task_id, populate_existing=True)
        row = await db.scalar(select(CallRow).where(CallRow.call_id == body.call_id).with_for_update().execution_options(populate_existing=True))
        check(row is not None and row.execution_id == execution.execution_id and row.start_fact is not None
              and row.state in ('started', 'unknown', 'completed'), 'CALL_NOT_STARTED')
        observation = body.model_dump(mode='json', exclude={'schema_version', 'worker_id', 'lease_token',
            'execution_id', 'observation_submission_id', 'call_id'})
        usage = await self.append(db, row, profile, body.observation_submission_id, observation,
                                  phase='activation' if row.activation_key else 'completed')
        row.state = 'unknown' if body.usage_status in ('unknown', 'partial') else 'completed'
        return usage

    async def recover_execution(self, db, execution_id):
        """Conservative crash recovery; never invent an observation or a new send right."""
        execution = await db.get(ExecutionRow, execution_id)
        check(execution is not None, 'EXECUTION_NOT_FOUND')
        task = await db.scalar(select(TaskRow).where(TaskRow.task_id == execution.task_id).with_for_update().execution_options(populate_existing=True))
        run = await db.scalar(select(RunRow).where(RunRow.run_id == execution.run_id).with_for_update().execution_options(populate_existing=True))
        check(run.lease_token != execution.lease_token or run.lease_expires_at is None or
              run.lease_expires_at.replace(tzinfo=timezone.utc) <= now_utc(), 'EXECUTION_STILL_ACTIVE')
        execution.sealed = True
        if task.cancel_requested and run.lease_token == execution.lease_token and run.report_json is None:
            run.status, task.status = 'cancelled', 'cancelled'
            run.completed_at, run.lease_expires_at = now_utc(), None
            run.report_json = dict(run_id=run.run_id, task_id=task.task_id, status='cancelled', result=None,
                usage=dict(prompt_tokens=None, completion_tokens=None, tool_calls=None, duration_ms=None),
                error_code='execution_cancelled', error_message='执行权已封闭；用量继续对账')
        calls = (await db.scalars(select(CallRow).where(CallRow.execution_id == execution_id).with_for_update().execution_options(populate_existing=True))).all()
        for row in calls:
            if row.state in ('starting', 'started', 'requesting', 'authorized'):
                row.state = 'unknown'  # no proof of no side effects: no void/refund

    async def seal_unstarted(self, db, call_id):
        """Permanent local no-receipt proof, serialized against commit_start.

        Backend querying/voiding happens AFTER this transaction commits.
        Unknown remote permit IDs remain held for reconciliation.
        """
        call = await db.get(CallRow, call_id)
        check(call is not None, 'CALL_NOT_FOUND')
        task = await db.scalar(select(TaskRow).where(TaskRow.task_id == call.task_id).with_for_update().execution_options(populate_existing=True))
        execution = await db.get(ExecutionRow, call.execution_id)
        run = await db.scalar(select(RunRow).where(RunRow.run_id == execution.run_id).with_for_update().execution_options(populate_existing=True))
        row = await db.scalar(select(CallRow).where(CallRow.call_id == call_id).with_for_update().execution_options(populate_existing=True))
        inactive = (execution.sealed or run.lease_token != execution.lease_token or run.lease_expires_at is None
                    or run.lease_expires_at.replace(tzinfo=timezone.utc) <= now_utc() or task.cancel_requested)
        check(inactive and row.start_fact is None, 'VOID_NOT_PROVEN')
        unknown_request = row.permit is None and row.backend_request is not None and row.start_operation_id is None
        check(unknown_request or row.permit is not None and row.permit.get('permit') is not None, 'REMOTE_PERMIT_UNKNOWN')
        if row.sealed_intent is None:
            row.sealed_intent = dict(void_operation_id=uid(), permit_id=row.permit['permit']['permit_id'] if row.permit else None,
                call_id=call_id, execution_id=row.execution_id, control_attestation_id=call_id,
                sealed_intent_revision=1, sealed_at=now_utc().isoformat(), start_operation_id=row.start_operation_id,
                local_started_record_absent=True, local_start_receipt_never_issued=True,
                reason_code='execution_sealed_before_local_start')
        row.state = 'void'
        return row.sealed_intent

    async def close_manifest(self, db, task_id):
        task = await db.scalar(select(TaskRow).where(TaskRow.task_id == task_id).with_for_update().execution_options(populate_existing=True))
        profile = await db.get(TaskMeteringRow, task_id)
        check(profile is not None and profile.context == 'authorized', 'AUTHORIZED_TASK_REQUIRED')
        grant = BudgetGrant.model_validate(profile.current_grant or profile.envelope['budget_grant'])
        executions = (await db.scalars(select(ExecutionRow).where(ExecutionRow.task_id == task_id))).all()
        runs = (await db.scalars(select(RunRow).where(RunRow.task_id == task_id))).all()
        calls = (await db.scalars(select(CallRow).where(CallRow.task_id == task_id))).all()
        observations = (await db.scalars(select(ObservationRow).where(ObservationRow.task_id == task_id)
                                         .order_by(ObservationRow.sequence))).all()
        hwm = 0
        for observation in observations:
            outbox = await db.get(UsageOutboxRow, observation.measurement_id)
            if observation.sequence != hwm + 1 or outbox.state != 'delivered':
                break
            hwm += 1
        terminal = task.status in ('completed', 'failed', 'cancelled', 'awaiting_input')
        return TaskCloseManifest(schema_version=1, manifest_id=uid(), agent_audience=self.audience, owner_id=task.owner_id,
            submission_id=profile.submission_id, grant_id=grant.grant_id, task_id=task_id,
            run_ids=[r.run_id for r in runs], execution_ids=[e.execution_id for e in executions],
            call_ids=[c.call_id for c in calls if c.start_fact],
            permit_ids=[c.permit['permit']['permit_id'] for c in calls if c.permit and c.permit.get('permit')],
            call_count=sum(c.start_fact is not None for c in calls), last_task_usage_sequence=profile.usage_sequence,
            outbox_ack_high_watermark=hwm, missing_sequences=[],
            unknown_call_ids=[c.call_id for c in calls if c.state == 'unknown'],
            all_executions_sealed=terminal and all(e.sealed for e in executions),
            no_startable_permits=terminal and all(c.state in ('completed', 'unknown', 'void') and
                (c.sealed_intent is None or c.remote_closed) for c in calls),
            closed_at=now_utc())
