"""Retained Worker manifests and current instance evidence."""
from sqlalchemy import select

from agent_app.infrastructure.management_models import WorkerLifecycleRow, WorkerManifestRow, WorkerSnapshotRow
from agent_app.management_observations import reading, utc


async def history(worker_id, build, config, since, until, offset, limit):
    manifest = WorkerManifestRow
    instance = WorkerSnapshotRow
    query = select(manifest, instance).outerjoin(instance, instance.worker_id == manifest.worker_id)
    filters = (
        (worker_id, manifest.worker_id == worker_id),
        (build, manifest.manifest['build_revision'].as_string() == build),
        (config, manifest.manifest['config_revision'].as_string() == config),
    )
    for value, criterion in filters:
        if value:
            query = query.where(criterion)
    if since:
        query = query.where(manifest.last_seen >= since)
    if until:
        query = query.where(manifest.last_seen <= until)
    rows = query.order_by(manifest.last_seen.desc(), manifest.worker_id, manifest.digest).offset(offset).limit(limit + 1)
    async with reading() as db:
        records = (await db.execute(rows)).all()
    items = []
    for saved, current in records[:limit]:
        matches = current is not None and current.manifest_digest == saved.digest
        items.append({'worker_id': saved.worker_id, 'digest': saved.digest, 'last_seen': utc(saved.last_seen),
                      'manifest': saved.manifest, 'current_instance_id': current.instance_id if matches else None,
                      'current_started_at': utc(current.started_at) if matches else None,
                      'current_lifecycle': current.lifecycle if matches else None, 'current_health': current.health if matches else None,
                      'current_run_id': current.active_run_id if matches else None})
    return {'items': items, 'next_offset': offset + limit if len(records) > limit else None}


async def lifecycle(worker_id, offset, limit):
    async with reading() as db:
        query = select(WorkerLifecycleRow)
        if worker_id:
            query = query.where(WorkerLifecycleRow.worker_id == worker_id)
        rows = (await db.scalars(query.order_by(WorkerLifecycleRow.observed_at.desc(),
                    WorkerLifecycleRow.worker_id, WorkerLifecycleRow.instance_id, WorkerLifecycleRow.sequence.desc(),
                    WorkerLifecycleRow.kind).offset(offset).limit(limit + 1))).all()
    return {'items': [{'worker_id': item.worker_id, 'instance_id': item.instance_id,
                       'observed_at': utc(item.observed_at), 'kind': item.kind, 'sequence': item.sequence,
                       'manifest_digest': item.manifest_digest, 'run_id': item.run_id} for item in rows[:limit]],
            'next_offset': offset + limit if len(rows) > limit else None}
