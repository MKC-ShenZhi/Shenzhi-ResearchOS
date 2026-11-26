"""Tamper-evident, purpose-limited management audit and probe admission."""
import asyncio
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from agent_contracts.canonical import canonical_json_v1, digest
from agent_contracts.management_phase2 import AuditEntry, DiagnosticResult, ProbeResult
from app.core.database import get_session_factory
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.models.agent_management import ManagementAuditRow as Audit

_gate = asyncio.Lock()
MAX_DAILY_TOKENS = 4096
PROBE_RESERVATION = 1024
PENDING_SECONDS = 20


def now():
    return datetime.now(timezone.utc)


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def secret():
    value = os.getenv('ADMIN_AGENT_AUDIT_SECRET', '').strip()
    if len(value) < 32 or value == os.getenv('ADMIN_SESSION_SECRET', ''):
        raise BusinessError(10002, 'AGENT_AUDIT_UNCONFIGURED', 503)
    return value.encode()


def seal(row):
    payload = {
        field: getattr(row, field) for field in ('audit_id', 'request_id', 'online_probe', 'principal', 'action', 'target_kind', 'target_id',
                                                 'target_fingerprint', 'request_digest', 'state', 'reason', 'reserved_tokens', 'outcome')
    }
    payload['created_at'] = aware(row.created_at).isoformat()
    return hmac.new(secret(), canonical_json_v1(payload), hashlib.sha256).hexdigest()


def verified(row):
    if not hmac.compare_digest(row.seal, seal(row)):
        raise BusinessError(10002, 'AGENT_AUDIT_INTEGRITY_FAILURE', 503)


def entry(row):
    verified(row)
    state, reason = row.state, row.reason
    if state == 'pending' and aware(row.created_at) < now() - timedelta(seconds=PENDING_SECONDS):
        state, reason = 'unknown', 'RESULT_UNAVAILABLE'
    return AuditEntry(audit_id=UUID(row.audit_id), request_id=UUID(row.request_id), principal=row.principal,
                      action=row.action, target_kind=row.target_kind, target_id=row.target_id,
                      created_at=aware(row.created_at), state=state, reason=reason,
                      check=row.outcome if row.action == 'check' else None,
                      diagnostic=row.outcome if row.action == 'diagnose' else None,
                      config_event=row.outcome if row.action in ('config', 'control') else None)


async def lock(db):
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(719201202)'))


async def prune(db, observed):
    await db.execute(delete(Audit).where(Audit.created_at < observed - timedelta(days=90))
                     .execution_options(synchronize_session=False))


async def admit(principal, action, request, request_id, *, online=False, reserve=0):
    secret()
    audit_id = str(request.operation_id)
    payload_hash = digest(request.model_dump(mode='json'))
    target_fingerprint = digest(request.target_id)
    observed = now()
    try:
        async with _gate, asyncio.timeout(3), get_session_factory()() as db, db.begin():
            await lock(db)
            prior = await db.get(Audit, audit_id)
            if prior:
                verified(prior)
                if (prior.principal, prior.action, prior.request_digest) != (principal, action, payload_hash):
                    raise BusinessError(10001, 'AGENT_OPERATION_CONFLICT', 409)
                return entry(prior)
            await prune(db, observed)
            state, reason = 'pending', None
            if online:
                pending = await db.scalar(select(func.count()).select_from(Audit).where(
                    Audit.action == 'check', Audit.online_probe.is_(True), Audit.state == 'pending',
                    Audit.created_at >= observed - timedelta(seconds=PENDING_SECONDS)))
                recent = await db.scalar(select(func.count()).select_from(Audit).where(
                    Audit.action == 'check', Audit.online_probe.is_(True),
                    Audit.target_fingerprint == target_fingerprint, Audit.target_kind == request.kind,
                    Audit.created_at >= observed - timedelta(seconds=60),
                    Audit.state.in_(['pending', 'pass', 'unknown', 'fail', 'unsupported']),
                    Audit.reason.is_distinct_from('PROBE_RATE_LIMIT')))
                spent = await db.scalar(select(func.coalesce(func.sum(Audit.reserved_tokens), 0)).where(
                    Audit.created_at >= observed.replace(hour=0, minute=0, second=0, microsecond=0)))
                if pending or recent or spent + reserve > MAX_DAILY_TOKENS:
                    state, reason, reserve = 'fail', 'PROBE_RATE_LIMIT', 0
            row = Audit(audit_id=audit_id, request_id=request_id, online_probe=online, principal=principal,
                        action=action, target_kind=request.kind, target_fingerprint=target_fingerprint,
                        target_id='unverified:' + target_fingerprint, created_at=observed, request_digest=payload_hash,
                        state=state, reason=reason, reserved_tokens=reserve, outcome=None)
            row.seal = seal(row)
            db.add(row)
            if state != 'pending':
                return entry(row)
        return None
    except (SQLAlchemyError, TimeoutError, RuntimeError, OSError):
        raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503) from None


async def prepare_config(operation_id, evidence):
    try:
        async with asyncio.timeout(3), get_session_factory()() as db, db.begin():
            row = await db.get(Audit, str(operation_id), with_for_update=True)
            if row is None:
                raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503)
            verified(row)
            if row.action != 'config' or row.state not in ('pending', 'unknown'):
                raise BusinessError(10001, 'CONFIG_PREPARE_STATE_CONFLICT', 409)
            previous = (row.outcome or {}).get('preparation')
            if previous:
                if any(previous.get(key) != value for key, value in evidence.items() if key != 'prepared_at'):
                    raise BusinessError(10001, 'CONFIG_PREPARE_EVIDENCE_CHANGED', 409)
                return previous
            row.outcome = {'preparation': evidence}
            row.seal = seal(row)
            return evidence
    except (SQLAlchemyError, TimeoutError, RuntimeError, OSError):
        raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503) from None


async def complete(operation_id, state, reason, data=None, *, verified_target=False, reopen_unknown=False):
    try:
        async with asyncio.timeout(3), get_session_factory()() as db, db.begin():
            row = await db.get(Audit, str(operation_id), with_for_update=True)
            if not row:
                raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503)
            verified(row)
            if row.state == 'pending' or (reopen_unknown and row.state == 'unknown'):
                row.state, row.reason = state, reason
                if data is not None:
                    if verified_target and digest(data['target_id']) == row.target_fingerprint:
                        row.target_id = data['target_id']
                    row.outcome = {**(row.outcome or {}), **data, 'target_id': row.target_id}
                row.seal = seal(row)
            return entry(row)
    except (SQLAlchemyError, TimeoutError, RuntimeError, OSError):
        raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503) from None


async def run_check(principal, request, request_id):
    online = request.kind in ('model', 'provider') and request.profile != 'static'
    reserve = PROBE_RESERVATION if request.kind == 'model' and request.profile in (
        'completion', 'streaming', 'tool_calling') else 0
    prior = await admit(principal, 'check', request, request_id, online=online, reserve=reserve)
    if prior:
        return prior
    payload = request.model_dump(mode='json', exclude={'operation_id'})
    try:
        result = await agent.request('POST', '/checks', ProbeResult, payload=payload)
        if (result.kind, result.target_id, result.profile) != (request.kind, request.target_id, request.profile):
            raise BusinessError(10002, 'PROBE_TARGET_MISMATCH', 503)
        verified_target = any(step.state == 'pass' and step.name in (
            'configuration', 'frontmatter', 'tool_parameters',
        ) for step in result.steps)
        return await complete(request.operation_id, result.state, result.reason, result.model_dump(mode='json'),
                              verified_target=verified_target)
    except BusinessError:
        return await complete(request.operation_id, 'unknown', 'CHECK_SERVICE_UNAVAILABLE')


async def run_diagnostic(principal, request, request_id):
    prior = await admit(principal, 'diagnose', request, request_id)
    if prior:
        return prior
    try:
        result = await agent.request('POST', '/diagnostics', DiagnosticResult, payload=request.model_dump(mode='json'))
        if (result.kind, result.target_id) != (request.kind, request.target_id):
            raise BusinessError(10002, 'DIAGNOSTIC_TARGET_MISMATCH', 503)
        return await complete(request.operation_id, 'pass', result.reason, result.model_dump(mode='json'),
                              verified_target=result.source in ('run_metadata', 'usage_observation',
                                                                'worker_heartbeat', 'call_metadata'))
    except BusinessError:
        return await complete(request.operation_id, 'fail', 'DIAGNOSTIC_EVIDENCE_UNAVAILABLE')


async def rows(offset, limit, **filters):
    secret()
    clauses = [Audit.created_at >= now() - timedelta(days=90)]
    for field, value in filters.items():
        if value is None:
            continue
        if field == 'from_at':
            clauses.append(Audit.created_at >= value)
        elif field == 'to_at':
            clauses.append(Audit.created_at <= value)
        elif field == 'target_id':
            clauses.append(Audit.target_fingerprint == digest(value))
        else:
            clauses.append(getattr(Audit, field) == value)
    try:
        async with asyncio.timeout(3), get_session_factory()() as db:
            values = (await db.scalars(select(Audit).where(*clauses)
                                       .order_by(Audit.created_at.desc(), Audit.audit_id.desc())
                                       .offset(offset).limit(limit))).all()
            return [entry(row) for row in values]
    except (SQLAlchemyError, TimeoutError, RuntimeError, OSError):
        raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503) from None


async def diagnostic_view(principal, item, request_id):
    if item.action != 'diagnose' or item.diagnostic is None:
        raise BusinessError(10001, 'DIAGNOSTIC_NOT_FOUND', 404)
    audit_id = str(uuid4())
    try:
        async with asyncio.timeout(3), get_session_factory()() as db, db.begin():
            row = Audit(audit_id=audit_id, request_id=request_id, online_probe=False, principal=principal,
                        action='diagnostic_view', target_kind=item.target_kind,
                        target_id=item.target_id, target_fingerprint=digest(item.target_id),
                        created_at=now(), request_digest=digest(str(item.audit_id)),
                        state='pass', reason='DIAGNOSTIC_VIEWED', reserved_tokens=0,
                        outcome=None)
            row.seal = seal(row)
            db.add(row)
    except (SQLAlchemyError, TimeoutError, RuntimeError, OSError):
        raise BusinessError(10002, 'AGENT_AUDIT_UNAVAILABLE', 503) from None
    return item.diagnostic
