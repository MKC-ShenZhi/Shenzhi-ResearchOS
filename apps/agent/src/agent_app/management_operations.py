"""Durable Worker controls and heartbeat incident lifecycle."""
import asyncio
import logging
import os
from datetime import timedelta
from sqlalchemy import select, text
from agent_contracts.canonical import digest
from agent_app.control.metering import GateDenied, now_utc
from agent_app.management_observations import reading, utc
from agent_app.management_workers import _write_lock, snapshot
from agent_app.infrastructure.management_models import (
    ManagementOperationRow, WorkerAlertRow, WorkerControlRow, WorkerLifecycleRow, WorkerSnapshotRow,
)
from agent_app.infrastructure.models import RunRow


async def worker_lock(db, worker_id):
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:worker))'), {'worker': 'drain:' + worker_id})


async def draining(db, worker_id):
    await worker_lock(db, worker_id)
    control = await db.get(WorkerControlRow, worker_id, populate_existing=True)
    return bool(control and control.draining)


async def drain_state(worker_id):
    async with reading() as db:
        control = await db.get(WorkerControlRow, worker_id)
        active = (await db.scalars(select(RunRow.run_id).where(RunRow.worker_id == worker_id,
            RunRow.status == 'running').limit(101))).all()
        state = 'accepting'
        if control and control.draining:
            state = 'drained' if not active else 'timed_out' if utc(control.deadline) <= now_utc() else 'draining'
        return dict(worker_id=worker_id, state=state, active_runs=active[:100],
                    deadline=utc(control.deadline).isoformat() if control else None,
                    reason=control.reason if control else None)


async def act(body):
    identity = str(body.operation_id)
    fingerprint = digest(body.model_dump(mode='json'))
    async with _write_lock, reading() as db, db.begin():
        if db.bind.dialect.name == 'postgresql':
            await db.execute(text('SELECT pg_advisory_xact_lock(719201201)'))
        old = await db.get(ManagementOperationRow, identity)
        if old:
            if old.request_digest != fingerprint:
                raise GateDenied('MANAGEMENT_OPERATION_CONFLICT', 409)
            return old.result
        if body.kind == 'worker' and body.action in ('drain', 'resume'):
            await worker_lock(db, body.target_id)
            if not await db.get(WorkerSnapshotRow, body.target_id):
                raise GateDenied('WORKER_NOT_OBSERVED', 404)
            row = await db.get(WorkerControlRow, body.target_id)
            values = dict(draining=body.action == 'drain', requested_at=now_utc(),
                          deadline=now_utc() + timedelta(seconds=body.timeout_seconds), reason=body.reason)
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                db.add(WorkerControlRow(worker_id=body.target_id, **values))
        elif body.kind == 'alert' and body.action in ('acknowledge', 'close'):
            row = await db.get(WorkerAlertRow, body.target_id, with_for_update=True)
            if not row:
                raise GateDenied('ALERT_NOT_FOUND', 404)
            if body.action == 'close':
                if row.recovered_at is None:
                    raise GateDenied('ALERT_STILL_ACTIVE', 409)
                row.state, row.closed_by = 'closed', body.actor
            elif row.state != 'closed':
                row.state, row.acknowledged_by = 'acknowledged', body.actor
        else:
            raise GateDenied('MANAGEMENT_ACTION_UNSUPPORTED', 422)
        result = dict(target_id=body.target_id, action=body.action, state='accepted', reason=body.reason,
                      operation_id=identity, actor=body.actor)
        db.add(ManagementOperationRow(operation_id=identity, request_digest=fingerprint, result=result))
        return result


async def inspect_heartbeats():
    async with _write_lock, reading() as db, db.begin():
        if db.bind.dialect.name == 'postgresql':
            await db.execute(text('SELECT pg_advisory_xact_lock(719201201)'))
        now = now_utc()
        workers = (await db.scalars(select(WorkerSnapshotRow))).all()
        incidents = (await db.scalars(select(WorkerAlertRow).where(WorkerAlertRow.recovered_at.is_(None)))).all()
        for row in workers:
            state = snapshot(row, None, now)
            for incident in incidents:
                if incident.worker_id == row.worker_id and (incident.instance_id != row.instance_id or state.state == 'online'):
                    incident.recovered_at = now
                    if incident.state == 'open':
                        incident.state = 'recovered'
                    key = (row.worker_id, row.instance_id, row.sequence, 'heartbeat_recovered')
                    if not await db.get(WorkerLifecycleRow, key):
                        db.add(WorkerLifecycleRow(worker_id=row.worker_id, instance_id=row.instance_id,
                            sequence=row.sequence, kind='heartbeat_recovered', observed_at=now,
                            manifest_digest=row.manifest_digest, run_id=row.active_run_id))
            if state.state == 'offline' and row.lifecycle != 'offline':
                alert_id = digest([row.worker_id, row.instance_id, row.sequence])
                if not await db.get(WorkerAlertRow, alert_id):
                    db.add(WorkerAlertRow(alert_id=alert_id, worker_id=row.worker_id, instance_id=row.instance_id,
                        sequence=row.sequence, state='open', opened_at=now))
                key = (row.worker_id, row.instance_id, row.sequence, 'heartbeat_timeout')
                if not await db.get(WorkerLifecycleRow, key):
                    db.add(WorkerLifecycleRow(worker_id=row.worker_id, instance_id=row.instance_id,
                        sequence=row.sequence, kind='heartbeat_timeout', observed_at=now,
                        manifest_digest=row.manifest_digest, run_id=row.active_run_id))


async def alerts(offset=0, limit=20):
    async with reading() as db:
        rows = (await db.scalars(select(WorkerAlertRow).order_by(WorkerAlertRow.opened_at.desc(),
            WorkerAlertRow.alert_id).offset(offset).limit(limit + 1))).all()
        return dict(items=[dict(alert_id=row.alert_id, worker_id=row.worker_id, instance_id=row.instance_id,
            state=row.state, opened_at=utc(row.opened_at).isoformat(),
            recovered_at=utc(row.recovered_at).isoformat() if row.recovered_at else None,
            acknowledged_by=row.acknowledged_by, closed_by=row.closed_by) for row in rows[:limit]],
            next_offset=offset + limit if len(rows) > limit else None,
            inspector_enabled=os.getenv('AGENT_MANAGEMENT_INSPECTOR_ENABLED', '').lower() == 'true')


async def watch():
    while True:
        try:
            await inspect_heartbeats()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).warning('Worker heartbeat inspection unavailable')
        await asyncio.sleep(10)
