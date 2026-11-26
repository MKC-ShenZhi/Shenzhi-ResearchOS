"""Transactional release coordination for immutable Worker deployment artifacts."""
import asyncio
import hashlib
import hmac
import os
from datetime import timedelta
from time import time

from sqlalchemy import func, select, text

from agent_contracts.canonical import canonical_json_v1, digest
from agent_contracts.management_config import ConfigIndex, Operation, Proof, RevisionView
from agent_app.control.metering import GateDenied, now_utc
from agent_app.infrastructure.config_management_models import (
    ConfigControlRow, ConfigOperationRow, ConfigRevisionRow, TaskExecutionConstraintRow,
)
from agent_app.infrastructure.management_models import WorkerManifestRow, WorkerSnapshotRow
from agent_app.infrastructure.metering_models import UsageOutboxRow
from agent_app.infrastructure.models import RunRow, TaskRow
from agent_app.management_observations import reading, utc
from agent_app.management_workers import snapshot

_lock = asyncio.Lock()
CONFIG_LOCK = 'SELECT pg_advisory_xact_lock(719201303)'
ACTIVE_TASKS = ('queued', 'running', 'cancelling', 'awaiting_input', 'paused')


def enabled():
    if os.getenv('AGENT_CONFIG_WRITE_ENABLED', '').lower() != 'true':
        raise GateDenied('CONFIG_WRITE_DISABLED', 403)


def mode():
    return os.getenv('AGENT_CONFIG_SCHEDULING', 'off').strip().lower()


async def pointer(db, create=False):
    if create and db.bind.dialect.name == 'postgresql':
        await db.execute(text(CONFIG_LOCK))
    current = await db.get(ConfigControlRow, 'current', with_for_update=create)
    if current is None and create:
        current = ConfigControlRow(name='current', admission_paused=False)
        db.add(current)
        await db.flush()
    return current


def proof_signature(proof):
    key = os.getenv('AGENT_CONFIG_VALIDATOR_SECRET', '').strip()
    if len(key) < 32 or key in {os.getenv('AGENT_CONFIG_MANAGEMENT_TOKEN', ''), os.getenv('AGENT_MANAGEMENT_TOKEN', '')}:
        raise GateDenied('CONFIG_VALIDATOR_NOT_CONFIGURED', 503)
    body = proof.model_dump(mode='json', exclude={'signature'})
    return 'sha256:' + hmac.new(key.encode(), canonical_json_v1(body), hashlib.sha256).hexdigest()


def verified_proof(proof, row):
    if str(proof.revision_id) != row.revision_id or (proof.config_digest, proof.build_revision, proof.runtime_version) != (
        row.config_digest, row.spec['build_revision'], row.spec['runtime_version'],
    ):
        raise GateDenied('CONFIG_PROOF_TARGET_MISMATCH', 422)
    if not hmac.compare_digest(proof.signature, proof_signature(proof)):
        raise GateDenied('CONFIG_PROOF_SIGNATURE_INVALID', 403)
    if not (-30 <= time() - proof.observed_at.timestamp() <= 3600):
        raise GateDenied('CONFIG_PROOF_STALE', 409)
    mapping = {item.id: item.version for item in proof.capabilities}
    if len(mapping) != len(proof.capabilities):
        raise GateDenied('CONFIG_PROOF_CAPABILITY_CONFLICT', 422)
    for key, value in [(tool['id'], tool['digest']) for tool in row.spec['tools']]:
        if mapping.get(key) != value:
            raise GateDenied('CONFIG_PROOF_ARTIFACT_MISMATCH', 422)


async def latest_validation(db, revision):
    return await db.scalar(select(ConfigOperationRow).where(
        ConfigOperationRow.revision_id == revision, ConfigOperationRow.action == 'validate',
    ).order_by(ConfigOperationRow.happened_at.desc(), ConfigOperationRow.operation_id.desc()).limit(1))


async def revision_view(db, row, control):
    validated = await latest_validation(db, row.revision_id)
    state = validated.result['status'] if validated else 'draft'
    if control and row.revision_id == control.active_revision:
        state = 'active'
    elif control and row.revision_id == control.desired_revision and control.deployment_id:
        item = await db.get(ConfigOperationRow, control.deployment_id)
        state = item.result['status']
    return RevisionView(revision_id=row.revision_id, revision_number=row.revision_number,
                        base_revision=row.base_revision, config_digest=row.config_digest, spec=row.spec,
                        created_by=row.principal, reason=row.reason, created_at=utc(row.created_at),
                        status=state, validation_id=validated.operation_id if validated else None)


async def view(revision=None, offset=0):
    async with reading() as db:
        control = await pointer(db)
        if revision:
            row = await db.get(ConfigRevisionRow, revision)
            if not row:
                raise GateDenied('CONFIG_REVISION_NOT_FOUND', 404)
            return await revision_view(db, row, control)
        rows = (await db.scalars(select(ConfigRevisionRow).order_by(ConfigRevisionRow.revision_number.desc())
                                 .offset(offset).limit(20))).all()
        operations = (await db.scalars(select(ConfigOperationRow).order_by(ConfigOperationRow.happened_at.desc())
                                       .offset(offset).limit(30))).all()
        deployment = await db.get(ConfigOperationRow, control.deployment_id) if control and control.deployment_id else None
        return ConfigIndex(write_enabled=os.getenv('AGENT_CONFIG_WRITE_ENABLED', '').lower() == 'true',
                           active_revision=control.active_revision if control else None,
                           desired_revision=control.desired_revision if control else None,
                           admission_paused=control.admission_paused if control else False,
                           pause_operation_id=control.pause_operation_id if control else None,
                           pause_reason=control.pause_reason if control else None,
                           deployment=deployment.result if deployment else None,
                           revisions=[await revision_view(db, row, control) for row in rows],
                           history=[op.result for op in operations])


async def read_proof(validation_id):
    async with reading() as db:
        item = await db.get(ConfigOperationRow, validation_id)
        if not item or item.action != 'validate':
            raise GateDenied('CONFIG_VALIDATION_NOT_FOUND', 404)
        return Proof.model_validate(item.details['proof'])


async def deployment_proof(operation_id):
    async with reading() as db:
        row = await db.get(ConfigOperationRow, operation_id)
        if row is None or row.action not in ('activate', 'rollback'):
            raise GateDenied('CONFIG_DEPLOYMENT_NOT_FOUND', 404)
        return Proof.model_validate(row.details['proof'])


async def result_for(operation_id, original=False):
    async with reading() as db:
        row = await db.get(ConfigOperationRow, operation_id)
        if row is None:
            raise GateDenied('CONFIG_OPERATION_NOT_FOUND', 404)
        return Operation.model_validate(row.details.get('receipt', row.result) if original else row.result)


async def workloads(db):
    queue = await db.scalar(select(func.count()).select_from(TaskRow).where(TaskRow.status == 'queued'))
    running = await db.scalar(select(func.count()).select_from(RunRow).where(RunRow.status == 'running'))
    outbox = await db.scalar(select(func.count()).select_from(UsageOutboxRow).where(UsageOutboxRow.state != 'delivered'))
    legacy = await db.scalar(select(func.count()).select_from(TaskRow).outerjoin(
        TaskExecutionConstraintRow, TaskExecutionConstraintRow.task_id == TaskRow.task_id
    ).where(TaskRow.status.in_(ACTIVE_TASKS), TaskExecutionConstraintRow.task_id.is_(None)))
    return queue, running, outbox, legacy


def versions(manifest):
    return {('model:' + item.id if item.kind == 'model' else item.id): item.version
            for item in manifest.capabilities if item.version}


def capability_digest(mapping):
    return digest([{'id': key, 'version': value} for key, value in sorted(mapping.items())])


async def comparison_fields(db, revision, proof, workers):
    constraint = TaskExecutionConstraintRow
    prior = (constraint.revision_id != revision.revision_id) | constraint.task_id.is_(None)
    queued = await db.scalar(select(func.count()).select_from(TaskRow).outerjoin(
        constraint, constraint.task_id == TaskRow.task_id,
    ).where(TaskRow.status == 'queued', prior))
    runs = await db.scalar(select(func.count()).select_from(RunRow).outerjoin(
        constraint, constraint.task_id == RunRow.task_id,
    ).where(RunRow.status == 'running', prior))
    required = [item.model_dump(mode='json') for item in proof.capabilities]
    confirmed = sum(agrees(worker, revision, required, exact=True) for worker in workers)
    return dict(queued_requiring_prior_worker=queued, runs_requiring_prior_worker=runs,
                compatible_workers=confirmed, unconfirmed_workers=len(workers) - confirmed)


def agrees(worker, rev, required, *, exact=False):
    if worker.state != 'online' or worker.health != 'ok' or worker.manifest is None:
        return False
    observed = worker.manifest
    if (observed.config_revision, observed.config_digest, observed.build_revision, observed.runtime_version) != (
        rev.revision_id, rev.config_digest, rev.spec['build_revision'], rev.spec['runtime_version'],
    ):
        return False
    actual = versions(observed)
    expected = {item['id']: item['version'] for item in required}
    return actual == expected if exact else all(actual.get(key) == value for key, value in expected.items())


async def live_workers(db):
    pairs = (await db.execute(select(WorkerSnapshotRow, WorkerManifestRow.manifest).join(
        WorkerManifestRow, (WorkerManifestRow.worker_id == WorkerSnapshotRow.worker_id)
        & (WorkerManifestRow.digest == WorkerSnapshotRow.manifest_digest)
    ).order_by(WorkerSnapshotRow.worker_id).limit(500))).all()
    return [snapshot(row, manifest, now_utc()) for row, manifest in pairs]


async def status_for(db, body, action, revision, control, details):
    current = control.active_revision
    queue, running, outbox, legacy = await workloads(db)
    fields = dict(queued_tasks=queue, active_runs=running, open_outbox=outbox)
    if action == 'create':
        base = str(body.base_revision) if body.base_revision else None
        if control.active_revision and not base:
            raise GateDenied('CONFIG_ACTIVE_BASE_REQUIRED', 409)
        if base and not await db.get(ConfigRevisionRow, base):
            raise GateDenied('CONFIG_REVISION_NOT_FOUND', 404)
        number = (await db.scalar(select(func.max(ConfigRevisionRow.revision_number))) or 0) + 1
        db.add(ConfigRevisionRow(revision_id=revision, revision_number=number, base_revision=base,
                                 config_digest=body.spec.config_digest, spec=body.spec.normalized(),
                                 principal=body.actor, reason=body.reason, created_at=now_utc()))
        return 'draft', fields
    if action == 'admission':
        expect(control, body)
        expected_pause = str(body.expected_pause_operation_id) if body.expected_pause_operation_id else None
        if control.pause_operation_id != expected_pause:
            raise GateDenied('CONFIG_ADMISSION_FENCE_CONFLICT', 409)
        if control.deployment_id and control.pause_operation_id == control.deployment_id:
            raise GateDenied('CONFIG_DEPLOYMENT_OWNS_ADMISSION', 409)
        control.admission_paused = body.paused
        control.pause_operation_id = str(body.operation_id) if body.paused else None
        control.pause_reason = body.reason if body.paused else None
        return ('admission_paused' if body.paused else 'admission_open'), fields
    if action in ('pause', 'reconcile'):
        return await reconcile(db, action, revision, control, fields, legacy, body, details)
    row = await db.get(ConfigRevisionRow, revision)
    if not row:
        raise GateDenied('CONFIG_REVISION_NOT_FOUND', 404)
    expect(control, body)
    fields['impact'] = getattr(body, 'impact', None)
    if action == 'validate':
        verified_proof(body.proof, row)
        details['proof'] = body.proof.model_dump(mode='json')
        fields.update(await comparison_fields(db, row, body.proof, await live_workers(db)))
        blockers = []
        if not body.proof.network_verified:
            blockers.append('ISOLATED_NETWORK_PROOF_REQUIRED')
        if body.impact.unknown:
            blockers.append('POLICY_EVIDENCE_UNKNOWN')
        if body.impact.policies or body.impact.impacted_owners:
            blockers.append('REQUIRES_POLICY_RELEASE')
        if body.impact.affected_grants:
            blockers.append('AFFECTED_GRANTS_REQUIRE_DRAIN')
        if legacy:
            blockers.append('LEGACY_TASKS_REQUIRE_DRAIN')
        fields['blockers'] = blockers
        return ('blocked' if blockers else 'validated'), fields
    if action == 'approve':
        check = await approved_validation(db, row, str(body.validation_id), current)
        verified_proof(Proof.model_validate(check.details['proof']), row)
        if require_separate_approval() and row.principal == body.actor:
            raise GateDenied('CONFIG_APPROVER_MUST_BE_DISTINCT', 403)
        validation_digest = digest([row.config_digest, check.details['proof'], check.result])
        details.update(validation_id=check.operation_id, validation_digest=validation_digest, actor=body.actor)
        fields['validation_digest'] = validation_digest
        return 'approved', fields
    if control.deployment_id:
        pending = await db.get(ConfigOperationRow, control.deployment_id)
        if pending.result['status'] in ('deploying', 'partially_deployed', 'rollback_pending', 'pending_reconcile'):
            raise GateDenied('CONFIG_DEPLOYMENT_IN_PROGRESS', 409)
    if mode() != 'enforce':
        raise GateDenied('CONFIG_ENFORCEMENT_REQUIRED', 409)
    check = await approved_validation(db, row, str(body.validation_id), current)
    approval = await db.get(ConfigOperationRow, body.approval_ref)
    validation_digest = digest([row.config_digest, check.details['proof'], check.result])
    if require_separate_approval() or approval is not None:
        if (not approval or approval.action != 'approve' or approval.revision_id != revision
                or approval.details.get('validation_id') != check.operation_id
                or approval.details.get('validation_digest') != validation_digest):
            raise GateDenied('CONFIG_APPROVAL_REQUIRED', 409)
        if require_separate_approval() and approval.details.get('actor') in (row.principal, body.actor):
            raise GateDenied('CONFIG_APPROVER_MUST_BE_DISTINCT', 403)
    proof = Proof.model_validate(check.details['proof'])
    verified_proof(proof, row)
    fields.update(await comparison_fields(db, row, proof, await live_workers(db)))
    if body.impact.unknown or body.impact.policies or body.impact.impacted_owners:
        raise GateDenied('CONFIG_POLICY_EVIDENCE_CHANGED', 409)
    if legacy or body.impact.affected_grants or (current is None and outbox):
        raise GateDenied('CONFIG_DRAIN_REQUIRED', 409)
    details['proof'] = check.details['proof']
    details['deadline'] = (now_utc() + timedelta(minutes=10)).isoformat()
    control.fencing_token += 1
    control.desired_revision = revision
    control.deployment_id = str(body.operation_id)
    if not control.admission_paused:
        control.admission_paused = True
        control.pause_operation_id = control.deployment_id
        control.pause_reason = body.reason
    fields.update(worker_ids=body.worker_ids, approval_ref=body.approval_ref, fencing_token=control.fencing_token,
                  validation_digest=validation_digest)
    return ('rollback_pending' if action == 'rollback' else 'deploying'), fields


def require_separate_approval():
    return os.getenv('AGENT_CONFIG_REQUIRE_SEPARATE_APPROVAL', '').lower() == 'true'


async def approved_validation(db, row, validation_id, current):
    check = await latest_validation(db, row.revision_id)
    if not check or check.operation_id != validation_id or check.result['status'] != 'validated':
        raise GateDenied('CONFIG_VALIDATION_REQUIRED', 409)
    if check.result['before_revision'] != current:
        raise GateDenied('CONFIG_VALIDATION_BASE_CHANGED', 409)
    return check


def expect(control, body):
    if control.active_revision != (str(body.expected_active_revision) if body.expected_active_revision else None):
        raise GateDenied('CONFIG_CAS_CONFLICT', 409)


async def reconcile(db, action, revision, control, fields, legacy, body, details):
    impact = body.impact
    fencing_token = body.fencing_token
    deployment = await db.get(ConfigOperationRow, revision)
    if not deployment or control.deployment_id != revision:
        raise GateDenied('CONFIG_DEPLOYMENT_NOT_FOUND', 404)
    view = Operation.model_validate(deployment.result)
    if view.status not in ('deploying', 'partially_deployed', 'rollback_pending', 'pending_reconcile'):
        raise GateDenied('CONFIG_DEPLOYMENT_ALREADY_TERMINAL', 409)
    if action == 'reconcile' and view.fencing_token is None:
        raise GateDenied('CONFIG_LEGACY_DEPLOYMENT_REQUIRES_RESTAGE', 409)
    if view.fencing_token is not None and (view.fencing_token != fencing_token or fencing_token != control.fencing_token):
        raise GateDenied('CONFIG_DEPLOYMENT_FENCE_CONFLICT', 409)
    if view.fencing_token is not None and not control.admission_paused:
        raise GateDenied('CONFIG_ADMISSION_PAUSE_REQUIRED', 409)
    fields['fencing_token'] = view.fencing_token
    fields['validation_digest'] = view.validation_digest
    if action == 'reconcile' and view.fencing_token is not None:
        prep = body.preparation
        evidence = (prep.deployment_id, prep.operation_id, prep.fencing_token, prep.target_revision,
                    prep.validation_digest, prep.impact_digest) if prep else None
        expected = (view.operation_id, body.operation_id, view.fencing_token, view.revision_id,
                    view.validation_digest, digest(impact.model_dump(mode='json')) if impact else None)
        if evidence != expected or not -30 <= time() - prep.prepared_at.timestamp() <= 120:
            raise GateDenied('CONFIG_PREPARATION_REQUIRED', 409)
        details['preparation'] = prep.model_dump(mode='json')
    row = await db.get(ConfigRevisionRow, str(view.revision_id))
    proof = Proof.model_validate(deployment.details['proof'])
    required = [item.model_dump(mode='json') for item in proof.capabilities]
    workers = await live_workers(db)
    fields.update(await comparison_fields(db, row, proof, workers))
    confirmed = sorted(w.worker_id for w in workers if w.worker_id in view.worker_ids and agrees(w, row, required, exact=True))
    blockers = []
    if impact is None or impact.unknown or impact.policies or impact.impacted_owners:
        blockers.append('CONFIG_POLICY_EVIDENCE_CHANGED')
    if impact and impact.affected_grants:
        blockers.append('AFFECTED_GRANTS_REQUIRE_DRAIN')
    if control.active_revision is None and fields['open_outbox']:
        blockers.append('CONFIG_DRAIN_REQUIRED')
    if legacy:
        blockers.append('LEGACY_TASKS_REQUIRE_DRAIN')
    if len(confirmed) != len(view.worker_ids):
        blockers.append('WAITING_FOR_EFFECTIVE_WORKERS')
    try:
        verified_proof(proof, row)
    except GateDenied as exc:
        blockers.append(exc.reason)
    pending = (await db.execute(select(TaskExecutionConstraintRow.revision_id, func.count()).join(
        TaskRow, TaskRow.task_id == TaskExecutionConstraintRow.task_id
    ).where(TaskRow.status.in_(ACTIVE_TASKS), TaskExecutionConstraintRow.revision_id != row.revision_id)
     .group_by(TaskExecutionConstraintRow.revision_id))).all()
    for old_id, _ in pending:
        old = await db.get(ConfigRevisionRow, old_id)
        old_requirements = (await db.execute(select(
            TaskExecutionConstraintRow.required_capabilities, TaskExecutionConstraintRow.capability_manifest_digest,
        ).join(
            TaskRow, TaskRow.task_id == TaskExecutionConstraintRow.task_id).where(
            TaskExecutionConstraintRow.revision_id == old_id, TaskRow.status.in_(ACTIVE_TASKS),
        ).limit(501))).all()
        # Beyond the bounded diagnostic scan, pause rather than infer compatibility.
        if not old or len(old_requirements) > 500 or any(
            not any(agrees(worker, old, required) and capability_digest(versions(worker.manifest)) == manifest_digest
                    for worker in workers)
            for required, manifest_digest in old_requirements
        ):
            blockers.append('REQUIRES_OLD_WORKER')
            break
    if action == 'pause':
        state = 'paused'
        control.desired_revision = control.active_revision
    elif not blockers:
        control.active_revision = row.revision_id
        state = 'rolled_back' if view.action == 'rollback' else 'active'
    elif now_utc().isoformat() > deployment.details['deadline']:
        state = 'pending_reconcile'
    else:
        state = 'partially_deployed' if confirmed else view.status
    if state in ('paused', 'active', 'rolled_back') and control.pause_operation_id == revision:
        control.admission_paused = False
        control.pause_operation_id = None
        control.pause_reason = None
    update = dict(status=state, confirmed_workers=confirmed, blockers=blockers, **fields)
    # Original request receipt is kept; current status is on the deployment receipt.
    deployment.result = view.model_copy(update=update).model_dump(mode='json')
    return state, dict(worker_ids=view.worker_ids, approval_ref=view.approval_ref,
                       confirmed_workers=confirmed, blockers=blockers, **fields)


async def mutate(action, body, revision=None):
    enabled()
    operation_id = str(body.operation_id)
    revision = revision or (operation_id if action == 'create' else None)
    # Read-only impact may change between retries; bind only the administrator's request.
    request = body.model_dump(mode='json', exclude={'impact', 'preparation'})
    for key in ('fencing_token', 'expected_pause_operation_id'):
        if request.get(key) is None:
            request.pop(key, None)
    fingerprint = digest([action, revision, request])
    async with _lock, reading() as db, db.begin():
        control = await pointer(db, create=True)
        existing = await db.get(ConfigOperationRow, operation_id)
        if existing:
            if existing.fingerprint != fingerprint:
                raise GateDenied('CONFIG_OPERATION_CONFLICT', 409)
            return Operation.model_validate(existing.details.get('receipt', existing.result))
        before = control.active_revision
        details = {}
        state, fields = await status_for(db, body, action, revision, control, details)
        item = Operation(operation_id=operation_id, action=action, revision_id=revision, before_revision=before,
                         status=state, reason=body.reason, occurred_at=now_utc(), **fields)
        payload = item.model_dump(mode='json')
        details['receipt'] = payload
        db.add(ConfigOperationRow(operation_id=operation_id, action=action, revision_id=revision, fingerprint=fingerprint,
                                  result=payload, details=details, happened_at=item.occurred_at))
        return item
