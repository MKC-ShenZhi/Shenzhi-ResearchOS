"""Worker identity binding and persisted evidence. Never updates a Run or lease."""
import asyncio
import hashlib
import hmac
import json
import os
from datetime import timedelta

from fastapi import Header
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError

from agent_contracts.canonical import digest
from agent_contracts.management_phase2 import CapabilityEvidence, ManifestEvidence, WorkerSnapshot
from agent_app.control.metering import GateDenied, now_utc
from agent_app.infrastructure.management_models import WorkerLifecycleRow, WorkerManifestRow, WorkerSnapshotRow
from agent_app.infrastructure.management_models import WorkerRuntimeRow, WorkerAlertRow
from agent_app.management_observations import reading, utc


def setting(name, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def revision(name):
    value = os.getenv(name, '').strip()
    if value and len(value) <= 100 and all(c.isascii() and (c.isalnum() or c in '_.:+-') for c in value):
        return value
    return None


def require_reporter(worker_id: str, authorization: str | None = Header(default=None)):
    token = (authorization or '').removeprefix('Bearer ')
    try:
        keyring = json.loads(os.getenv('AGENT_WORKER_REPORT_IDENTITIES', '{}'))
        expected = keyring.get(worker_id, '')
    except (ValueError, AttributeError):
        expected = ''
        keyring = {}
    reserved = {os.getenv(name, '').strip() for name in (
        'AGENT_MANAGEMENT_TOKEN', 'AGENT_CONFIG_MANAGEMENT_TOKEN', 'AGENT_WORKER_TOKEN', 'AGENT_SERVICE_TOKEN', 'AGENT_CONTROL_TOKEN',
        'AGENT_GATEWAY_TOKEN', 'AGENT_FACT_READER_TOKEN',
    )}
    if (not (authorization or '').startswith('Bearer ') or len(token) < 32 or token in reserved
            or not isinstance(expected, str) or len(expected) != 64
            or list(keyring.values()).count(expected) != 1
            or not hmac.compare_digest(expected.encode(), hashlib.sha256(token.encode()).hexdigest().encode())):
        raise GateDenied('WORKER_REPORT_UNAUTHORIZED', 403)


def snapshot(row, manifest, now):
    observed = utc(row.observed_at)
    stale = setting('AGENT_WORKER_STALE_SECONDS', 45, 5, 3600)
    offline = setting('AGENT_WORKER_OFFLINE_SECONDS', 90, stale, 7200)
    age = max(0, int((now - observed).total_seconds()))
    state = 'offline' if row.lifecycle == 'offline' or age >= offline else 'stale' if age >= stale else 'online'
    return WorkerSnapshot(
        worker_id=row.worker_id, instance_id=row.instance_id, started_at=utc(row.started_at), observed_at=observed,
        expires_at=observed + timedelta(seconds=stale), age_seconds=age, state=state, health=row.health,
        active_run_id=row.active_run_id, run_tool_ids=row.run_tool_ids, manifest_digest=row.manifest_digest, manifest=manifest,
        capability_count=len(manifest['capabilities']) if manifest else 0,
    )


_write_lock = asyncio.Lock()


async def save(worker_id, report):
    now = now_utc()
    fingerprint = digest(report.model_dump(mode='json'))
    if report.started_at > now + timedelta(seconds=30):
        raise GateDenied('WORKER_CLOCK_SKEW', 422)
    if report.manifest:
        body = report.manifest.model_dump(mode='json')
        legacy = dict(body)
        if legacy.get('config_digest') is None:
            legacy.pop('config_digest', None)
        if report.manifest_digest not in {digest(body), digest(legacy)}:
            raise GateDenied('WORKER_MANIFEST_MISMATCH', 422)
    instance = str(report.instance_id)
    async with _write_lock, reading() as db, db.begin():
        if db.bind.dialect.name == 'postgresql':
            await db.execute(text('SELECT pg_advisory_xact_lock(719201201)'))
        row = await db.get(WorkerSnapshotRow, worker_id)
        if row and row.instance_id == instance:
            if report.sequence == row.sequence and hmac.compare_digest(row.request_digest, fingerprint):
                return {'accepted_seq': row.sequence, 'observed_at': utc(row.observed_at), 'want_manifest': bool(report.manifest_digest and row.manifest_digest is None)}
            if report.sequence <= row.sequence or row.lifecycle == 'offline':
                raise GateDenied('WORKER_SEQUENCE_CONFLICT', 409)
            if utc(row.started_at) != report.started_at:
                raise GateDenied('WORKER_INSTANCE_CONFLICT', 409)
        elif row and report.started_at <= utc(row.started_at):
            raise GateDenied('WORKER_INSTANCE_SUPERSEDED', 409)
        keep_after = now - timedelta(days=setting('AGENT_WORKER_REPORT_RETENTION_DAYS', 7, 1, 90))
        await db.execute(delete(WorkerSnapshotRow).where(
            WorkerSnapshotRow.observed_at < keep_after, WorkerSnapshotRow.worker_id != worker_id)
            .execution_options(synchronize_session=False))
        active = select(WorkerSnapshotRow.manifest_digest).where(
            WorkerSnapshotRow.worker_id == WorkerManifestRow.worker_id,
            WorkerSnapshotRow.manifest_digest == WorkerManifestRow.digest,
        )
        await db.execute(delete(WorkerManifestRow).where(WorkerManifestRow.last_seen < keep_after, ~active.exists()).execution_options(synchronize_session=False))
        saved = await db.get(WorkerManifestRow, (worker_id, report.manifest_digest)) if report.manifest_digest else None
        if report.manifest and not saved:
            saved = WorkerManifestRow(worker_id=worker_id, digest=report.manifest_digest,
                                      manifest=report.manifest.model_dump(mode='json'), last_seen=now)
            db.add(saved)
        if saved:
            saved.last_seen = now
        values = dict(instance_id=instance, sequence=report.sequence, request_digest=fingerprint,
                      started_at=report.started_at, observed_at=now, lifecycle=report.lifecycle,
                      health=report.health, active_run_id=report.active_run_id,
                      run_tool_ids=report.run_tool_ids if report.active_run_id else [],
                      manifest_digest=saved.digest if saved else None)
        await record_lifecycle(db, worker_id, row, values, keep_after)
        if report.active_run_id:
            # Only the Worker holding this Run's live lease can attest runtime tools.
            from agent_app.infrastructure.models import RunRow
            run = await db.get(RunRow, report.active_run_id)
            if run and run.worker_id == worker_id and run.lease_expires_at and utc(run.lease_expires_at) > now:
                runtime = await db.get(WorkerRuntimeRow, (report.active_run_id, worker_id))
                evidence = dict(instance_id=instance, observed_at=now, manifest_digest=values['manifest_digest'],
                                enabled_tools=report.run_tool_ids, latent_tools=report.run_latent_tool_ids,
                                complete=report.run_tools_complete)
                if runtime:
                    for field, value in evidence.items():
                        setattr(runtime, field, value)
                else:
                    db.add(WorkerRuntimeRow(run_id=report.active_run_id, worker_id=worker_id, **evidence))
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            db.add(WorkerSnapshotRow(worker_id=worker_id, **values))
        return {'accepted_seq': report.sequence, 'observed_at': now,
                'want_manifest': bool(report.manifest_digest and not saved)}


async def record_lifecycle(db, worker_id, previous, current, keep_after):
    await db.execute(delete(WorkerLifecycleRow).where(WorkerLifecycleRow.observed_at < keep_after))
    events = {}
    if not previous or previous.instance_id != current['instance_id']:
        events['registered'] = None
    if not previous or previous.lifecycle != current['lifecycle'] or previous.instance_id != current['instance_id']:
        events['offline' if current['lifecycle'] == 'offline' else 'online'] = None
    if previous:
        prior = snapshot(previous, None, current['observed_at'])
        if prior.state in ('stale', 'offline') and previous.lifecycle != 'offline':
            recorded = await db.get(WorkerLifecycleRow, (worker_id, previous.instance_id,
                                    previous.sequence, 'heartbeat_timeout'))
            if not recorded:
                events['heartbeat_timeout'] = previous.active_run_id
            if current['lifecycle'] != 'offline':
                events['heartbeat_recovered'] = current['active_run_id']
            if prior.state == 'offline':
                alert_id = digest([worker_id, previous.instance_id, previous.sequence])
                incident = await db.get(WorkerAlertRow, alert_id)
                recovered = current['observed_at'] if current['lifecycle'] != 'offline' else None
                if incident:
                    incident.recovered_at = recovered
                    if recovered and incident.state == 'open':
                        incident.state = 'recovered'
                else:
                    db.add(WorkerAlertRow(alert_id=alert_id, worker_id=worker_id,
                        instance_id=previous.instance_id, sequence=previous.sequence,
                        state='recovered' if recovered else 'open', opened_at=current['observed_at'],
                        recovered_at=recovered))
        if previous.health != current['health']:
            events['healthy' if current['health'] == 'ok' else 'degraded'] = current['active_run_id']
    if current['manifest_digest'] and (not previous or previous.manifest_digest != current['manifest_digest']):
        events['manifest_changed'] = None
    if not previous or previous.active_run_id != current['active_run_id']:
        if previous and previous.active_run_id:
            events['run_unlinked'] = previous.active_run_id
        if current['active_run_id']:
            events['run_linked'] = current['active_run_id']
    for kind, run in events.items():
        key = (worker_id, current['instance_id'], current['sequence'], kind)
        if await db.get(WorkerLifecycleRow, key):
            continue
        db.add(WorkerLifecycleRow(worker_id=worker_id, instance_id=current['instance_id'],
                                  sequence=current['sequence'], kind=kind, run_id=run,
                                  observed_at=current['observed_at'], manifest_digest=current['manifest_digest']))


async def manifest_history(worker_id, offset, size):
    async with reading() as db:
        items = (await db.scalars(select(WorkerManifestRow).where(WorkerManifestRow.worker_id == worker_id)
                                  .order_by(WorkerManifestRow.last_seen.desc(), WorkerManifestRow.digest)
                                  .offset(offset).limit(size))).all()
    return [ManifestEvidence(digest=item.digest, last_seen=utc(item.last_seen),
                             config_revision=item.manifest.get('config_revision'),
                             build_revision=item.manifest.get('build_revision'),
                             capability_count=len(item.manifest['capabilities'])) for item in items]


async def capability_evidence(kind, target_id, offset, size):
    workers = await list_workers(offset, size, include_manifest=True)
    data = []
    for worker in workers:
        manifest = worker.manifest
        facts = manifest.capabilities if manifest else []
        ids = {target_id}
        if kind == 'skill':
            ids = {target_id.removeprefix('skill:'), 'skill:' + target_id.removeprefix('skill:')}
        fact = next((item for item in facts if item.kind == kind and item.id in ids), None)
        data.append(CapabilityEvidence(worker_id=worker.worker_id, state=worker.state, observed_at=worker.observed_at,
                                       manifest_digest=worker.manifest_digest,
                                       config_revision=manifest.config_revision if manifest else None, capability=fact))
    return data


async def list_workers(offset, limit, worker_id=None, include_manifest=False):
    try:
        async with reading() as db:
            query = select(WorkerSnapshotRow, WorkerManifestRow.manifest).outerjoin(
                WorkerManifestRow, (WorkerManifestRow.worker_id == WorkerSnapshotRow.worker_id)
                & (WorkerManifestRow.digest == WorkerSnapshotRow.manifest_digest))
            if worker_id:
                query = query.where(WorkerSnapshotRow.worker_id == worker_id)
            rows = (await db.execute(query.order_by(WorkerSnapshotRow.worker_id).offset(offset).limit(limit))).all()
            data = []
            for row, manifest in rows:
                item = snapshot(row, manifest, now_utc())
                if not include_manifest:
                    item.manifest = None
                data.append(item)
            return data
    except (GateDenied, SQLAlchemyError):
        # Deployments without the additive migration can still use lease evidence.
        raise GateDenied('WORKER_EVIDENCE_UNAVAILABLE', 503) from None
