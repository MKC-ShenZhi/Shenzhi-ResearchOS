"""Dedicated usage recovery/delivery process: python -m agent_app.usage_worker."""
import asyncio
import logging
import os

from sqlalchemy import select, or_

from agent_app.api.v2 import metering_control
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.metering_models import CallRow, CloseManifestRow, ExecutionRow, TaskMeteringRow
from agent_app.integrations.backend.entitlements import EntitlementClient
from agent_app.control.usage_delivery import deliver_once


async def run():
    from agent_app.infrastructure import database
    # Initialize the existing Agent-owned session factory only.
    async for db in get_session():
        break
    control, backend = metering_control(), EntitlementClient()
    options = dict(producer_id=os.environ['AGENT_AUDIENCE'], batch_size=int(os.environ['AGENT_USAGE_BATCH_SIZE']),
                   max_attempts=int(os.environ['AGENT_USAGE_MAX_ATTEMPTS']),
                   retry_base_seconds=int(os.environ['AGENT_USAGE_RETRY_BASE_SECONDS']),
                   retry_max_seconds=int(os.environ['AGENT_USAGE_RETRY_MAX_SECONDS']))
    while True:
        try:
            async with database.SessionFactory() as db:
                ids = list((await db.scalars(select(ExecutionRow.execution_id))).all())
            for execution_id in ids:
                async with database.SessionFactory() as db:
                    try:
                        await control.recover_execution(db, execution_id)
                        await db.commit()
                    except Exception:
                        await db.rollback()  # active execution is expected
            await deliver_once(database.SessionFactory, backend, **options)
            async with database.SessionFactory() as db:
                call_ids = list((await db.scalars(select(CallRow.call_id).where(
                    CallRow.start_fact.is_(None), CallRow.remote_closed.is_(False),
                    or_(CallRow.permit.is_not(None), CallRow.backend_request.is_not(None)),
                    or_(CallRow.state != 'void', CallRow.sealed_intent.is_not(None))))).all())
            for call_id in call_ids:
                async with database.SessionFactory() as db:
                    try:
                        seal = await control.seal_unstarted(db, call_id)
                        await db.commit()
                    except Exception:
                        await db.rollback()
                        continue
                if seal['permit_id'] is None:
                    async with database.SessionFactory() as db:
                        row = await db.get(CallRow, call_id)
                        request = row.backend_request
                    proof = {k: seal[k] for k in ('void_operation_id', 'sealed_intent_revision', 'sealed_at',
                        'start_operation_id', 'local_started_record_absent', 'local_start_receipt_never_issued', 'reason_code')}
                    response = await backend.request('POST', '/call-permits/abandon', dict(schema_version=1, request=request, **proof))
                else:
                    remote = await backend.request('GET', f"/call-permits/{seal['permit_id']}")
                    proof = dict(schema_version=1, **seal, backend_start_authorization_id=(
                        remote['start']['start_authorization_id'] if remote.get('start') else None))
                    await backend.request('POST', f"/call-permits/{seal['permit_id']}/void", proof)
                    response = None
                async with database.SessionFactory() as db:
                    row = await db.get(CallRow, call_id)
                    if response:
                        row.permit = response['response']
                    row.remote_closed = True
                    await db.commit()
            async with database.SessionFactory() as db:
                ids = list((await db.scalars(select(TaskMeteringRow.task_id).where(TaskMeteringRow.context == 'authorized'))).all())
            for task_id in ids:
                async with database.SessionFactory() as db:
                    manifest = await control.close_manifest(db, task_id)
                    if not (manifest.all_executions_sealed and manifest.no_startable_permits
                            and manifest.outbox_ack_high_watermark == manifest.last_task_usage_sequence):
                        continue
                    existing = await db.scalar(select(CloseManifestRow).where(
                        CloseManifestRow.task_id == task_id, CloseManifestRow.usage_sequence == manifest.last_task_usage_sequence))
                    if existing is None:
                        existing = CloseManifestRow(manifest_id=manifest.manifest_id, task_id=task_id,
                            usage_sequence=manifest.last_task_usage_sequence, payload=manifest.model_dump(mode='json'))
                        db.add(existing)
                        await db.commit()
                    if existing.ack is not None:
                        continue
                    payload = existing.payload
                ack = await backend.request('POST', f'/grants/{manifest.grant_id}/close', payload)
                async with database.SessionFactory() as db:
                    row = await db.get(CloseManifestRow, payload['manifest_id'])
                    row.ack = ack
                    await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger('agent.usage').exception('Usage delivery/recovery failed')
        await asyncio.sleep(float(os.environ['AGENT_USAGE_POLL_SECONDS']))


if __name__ == '__main__':
    asyncio.run(run())
