"""Compatibility checks used by the existing Task/Run transaction."""
import hmac
import logging
import os
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import exists, false, select, text

from agent_contracts.canonical import digest
from agent_contracts.management_config import Proof
from agent_app.config_deployment import capability_digest, mode, pointer, versions
from agent_app.control.metering import GateDenied, now_utc
from agent_app.infrastructure.config_management_models import ConfigRevisionRow, TaskExecutionConstraintRow
from agent_app.infrastructure.management_models import WorkerManifestRow, WorkerSnapshotRow
from agent_app.infrastructure.models import TaskRow
from agent_app.management_workers import require_reporter, snapshot

logger = logging.getLogger(__name__)
_schema_cache = WeakKeyDictionary()


async def has_constraints(db):
    bind = db.bind
    if bind is None:
        return False
    available = _schema_cache.get(bind)
    if available is None:
        table = TaskExecutionConstraintRow.__tablename__
        if bind.dialect.name == 'sqlite':
            query = text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :table")
        else:
            query = text("SELECT to_regclass(:table) IS NOT NULL")
        available = bool(await db.scalar(query, {'table': table}))
        if available:
            _schema_cache[bind] = available
    return available


async def admission(db, task_id, submission, metering):
    if os.getenv('AGENT_CONFIG_WORKER_ROLE') == 'candidate':
        raise GateDenied('CANDIDATE_EXECUTION_DISABLED', 403)
    enforce = mode() == 'enforce'
    if not enforce and os.getenv('AGENT_CONFIG_WRITE_ENABLED', '').lower() != 'true':
        if not await has_constraints(db):
            return None
        configured = await pointer(db)
        if configured and configured.active_revision:
            raise GateDenied('CONFIG_ENFORCEMENT_REQUIRED', 503)
        return None
    # Serialize admission against active pointer changes. No legacy task is retroactively pinned.
    current = await pointer(db, create=True)
    if current.admission_paused:
        raise GateDenied('CONFIG_ADMISSION_PAUSED', 503)
    if not enforce:
        if current.active_revision:
            raise GateDenied('CONFIG_ENFORCEMENT_REQUIRED', 503)
        return None
    if not current.active_revision or not metering or not metering.budget_grant:
        raise GateDenied('CONFIG_EXECUTION_CONSTRAINT_REQUIRED', 503)
    active = await db.get(ConfigRevisionRow, current.active_revision)
    deployment = None
    # The active revision's proof is the last activated proof, not a subsequent draft validation.
    from agent_app.infrastructure.config_management_models import ConfigOperationRow
    candidates = (await db.scalars(select(ConfigOperationRow).where(
        ConfigOperationRow.revision_id == current.active_revision,
        ConfigOperationRow.action.in_(('activate', 'rollback')),
    ).order_by(ConfigOperationRow.happened_at.desc()).limit(100))).all()
    for item in candidates:
        if item.result['status'] in ('active', 'rolled_back'):
            deployment = item
            break
    if not active or not deployment:
        raise GateDenied('CONFIG_ACTIVE_EVIDENCE_MISSING', 503)
    proof = Proof.model_validate(deployment.details['proof'])
    facts = {item.id: item.version for item in proof.capabilities}
    grant = metering.budget_grant
    model = 'model:' + (submission.model or '')
    permitted = {item.capability_id: item.capability_version for item in grant.capabilities}
    if model not in permitted or facts.get(model) != permitted[model]:
        raise GateDenied('CONFIG_MODEL_POLICY_INCOMPATIBLE', 409)
    required = {model: permitted[model]}
    for name in submission.skills:
        key = 'skill:' + name
        if key not in permitted or facts.get(key) != permitted[key]:
            raise GateDenied('CONFIG_SKILL_POLICY_INCOMPATIBLE', 409)
        required[key] = permitted[key]
    for key, version in permitted.items():
        if key.startswith('tool:') and key in facts:
            if facts[key] != version:
                raise GateDenied('CONFIG_TOOL_POLICY_INCOMPATIBLE', 409)
            required[key] = version
    return TaskExecutionConstraintRow(
        task_id=task_id, revision_id=active.revision_id, spec_digest=active.config_digest,
        build_revision=proof.build_revision, runtime_version=proof.runtime_version,
        capability_manifest_digest=capability_digest(facts),
        required_capabilities=[{'id': key, 'version': value} for key, value in sorted(required.items())],
        constraint_version=1,
    )


async def worker_evidence(db, worker_id, instance_id, token):
    if not instance_id or not token:
        return None
    try:
        instance_id = str(UUID(instance_id))
        require_reporter(worker_id, 'Bearer ' + token)
    except (ValueError, GateDenied):
        return None
    row = await db.get(WorkerSnapshotRow, worker_id, with_for_update={'read': True})
    if not row or row.instance_id != instance_id or not row.manifest_digest:
        return None
    record = await db.get(WorkerManifestRow, (worker_id, row.manifest_digest))
    if not record:
        return None
    evidence = snapshot(row, record.manifest, now_utc())
    return evidence.manifest if evidence.state == 'online' and evidence.health == 'ok' else None


def predicate(evidence):
    if evidence is None:
        return false()
    c = TaskExecutionConstraintRow
    return exists(select(c.task_id).where(
        c.task_id == TaskRow.task_id, c.constraint_version == 1, c.revision_id == evidence.config_revision,
        c.spec_digest == evidence.config_digest, c.build_revision == evidence.build_revision,
        c.runtime_version == evidence.runtime_version, c.capability_manifest_digest == capability_digest(versions(evidence)),
    ))


async def describe_wait(db, task, run):
    if not await has_constraints(db):
        return None, None
    from agent_app.management_observations import utc
    row = await db.get(TaskExecutionConstraintRow, task.task_id)
    waiting = task.status == 'queued' or (run is not None and run.status == 'running'
                 and run.lease_expires_at is not None and utc(run.lease_expires_at) <= now_utc())
    if row is None:
        return None, 'LEGACY_EXECUTION_VERSION_UNKNOWN' if waiting and mode() == 'enforce' else None
    if not waiting:
        return row.revision_id, None
    from agent_app.config_deployment import agrees, live_workers
    revision = await db.get(ConfigRevisionRow, row.revision_id)
    if revision and any(agrees(worker, revision, row.required_capabilities) and
                        capability_digest(versions(worker.manifest)) == row.capability_manifest_digest
                        for worker in await live_workers(db)):
        return row.revision_id, 'WAITING_FOR_COMPATIBLE_LEASE'
    return row.revision_id, 'NO_COMPATIBLE_WORKER'


async def shadow(db, task_id, worker_id, evidence):
    eligible = await db.scalar(select(TaskRow.task_id).where(TaskRow.task_id == task_id, predicate(evidence)))
    logger.info('Agent config shadow: task=%s worker=%s compatible=%s reason=%s', task_id, worker_id, bool(eligible),
                'MATCH' if eligible else 'CONFIG_EVIDENCE_OR_CONSTRAINT_MISMATCH')


async def claim_constraint(db, task_id):
    row = await db.get(TaskExecutionConstraintRow, task_id)
    if not row:
        return None
    return dict(revision_id=row.revision_id, spec_digest=row.spec_digest, build_revision=row.build_revision,
                runtime_version=row.runtime_version, capability_manifest_digest=row.capability_manifest_digest,
                required_capabilities=row.required_capabilities, constraint_version=row.constraint_version)


def verify_local(constraint):
    from agent_app.worker.management_reporter import manifest
    observed = manifest()
    actual = (observed.config_revision, observed.config_digest, observed.build_revision, observed.runtime_version,
              capability_digest(versions(observed)))
    needed = (constraint['revision_id'], constraint['spec_digest'], constraint['build_revision'],
              constraint['runtime_version'], constraint['capability_manifest_digest'])
    if not hmac.compare_digest(digest(actual), digest(needed)):
        raise GateDenied('CONFIG_LOCAL_EXECUTION_MISMATCH', 409)
