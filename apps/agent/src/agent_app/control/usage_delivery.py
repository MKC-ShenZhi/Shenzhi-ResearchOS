"""At-least-once Usage Outbox delivery. Claims are committed before network I/O."""
from datetime import timedelta

from sqlalchemy import select, or_

from agent_contracts.v2 import UsageBatch, UsageBatchAck
from agent_app.infrastructure.metering_models import ObservationRow, UsageOutboxRow
from .metering import now_utc, uid, check


async def settle_observation(db, backend, usage):
    """Fast path after the observation/outbox commit, using original IDs.

    Replay unacknowledged prior observations so Backend can verify sequence
    continuity even when the independent Outbox worker has not run yet.
    Failure leaves the durable Outbox intact and must not acknowledge completion.
    """
    rows = (await db.scalars(select(ObservationRow).join(
        UsageOutboxRow, UsageOutboxRow.measurement_id == ObservationRow.measurement_id).where(
        ObservationRow.task_id == usage.task_id, ObservationRow.sequence <= usage.task_usage_sequence,
        or_(UsageOutboxRow.state != 'delivered', ObservationRow.measurement_id == usage.measurement_id))
        .order_by(ObservationRow.sequence))).all()
    await db.commit()  # release the read transaction before Backend fact callbacks
    confirmed = False
    for offset in range(0, len(rows), 200):
        batch = UsageBatch(schema_version=1, batch_id=uid(), producer_id=usage.agent_audience,
                           items=[row.payload for row in rows[offset:offset + 200]])
        ack = UsageBatchAck.model_validate(await backend.request('POST', '/usage-deltas:batch', batch.model_dump(mode='json')))
        check(ack.batch_id == batch.batch_id, 'USAGE_ACK_BATCH_CONFLICT')
        expected = {item.measurement_id: item for item in batch.items}
        check(len(ack.results) == len(expected) and {r.measurement_id for r in ack.results} == set(expected),
              'USAGE_ACK_INCOMPLETE')
        for result in ack.results:
            item = expected[result.measurement_id]
            check((result.call_id, result.observation_revision) == (item.call_id, item.observation_revision),
                  'USAGE_ACK_IDENTITY_CONFLICT')
            check(result.durable and result.disposition in ('accepted', 'duplicate') and
                  result.applied_revision is not None and result.applied_revision >= item.observation_revision,
                  'USAGE_SETTLEMENT_UNCONFIRMED')
            if result.measurement_id == usage.measurement_id:
                confirmed = result.settlement_status != 'pending'
            row = await db.scalar(select(UsageOutboxRow).where(
                UsageOutboxRow.measurement_id == result.measurement_id).with_for_update())
            row.state, row.ack = 'delivered', result.model_dump(mode='json')
        await db.commit()
    check(confirmed, 'USAGE_SETTLEMENT_UNCONFIRMED')


async def deliver_once(factory, backend, *, producer_id, batch_size, max_attempts,
                       retry_base_seconds, retry_max_seconds):
    check(0 < batch_size <= 200 and max_attempts > 0 and retry_base_seconds > 0
          and retry_max_seconds >= retry_base_seconds, 'DELIVERY_POLICY_UNCONFIGURED')
    async with factory() as db:
        async with db.begin():
            rows = (await db.scalars(select(UsageOutboxRow).where(
                UsageOutboxRow.state.in_(('pending', 'quarantined')),
                UsageOutboxRow.available_at <= now_utc()).order_by(UsageOutboxRow.available_at)
                .with_for_update(skip_locked=True).limit(batch_size))).all()
            items = []
            for row in rows:
                if row.attempts >= max_attempts:
                    row.state = 'dead_letter'
                    continue
                row.attempts += 1
                row.available_at = now_utc() + timedelta(seconds=min(
                    retry_max_seconds, retry_base_seconds * 2**min(row.attempts - 1, 30)))
                observation = await db.get(ObservationRow, row.measurement_id)
                items.append(observation.payload)
    if not items:
        return 0
    batch = UsageBatch(schema_version=1, batch_id=uid(), producer_id=producer_id, items=items)
    # A failure leaves the persisted retry schedule and IDs intact.
    ack = UsageBatchAck.model_validate(await backend.request('POST', '/usage-deltas:batch', batch.model_dump(mode='json')))
    check(ack.batch_id == batch.batch_id, 'USAGE_ACK_BATCH_CONFLICT')
    expected = {i.measurement_id: i for i in batch.items}
    seen = set()
    async with factory() as db:
        async with db.begin():
            for result in ack.results:
                if result.measurement_id not in expected or result.measurement_id in seen:
                    raise ValueError('unexpected or repeated usage Ack')
                seen.add(result.measurement_id)
                original = expected[result.measurement_id]
                check((result.call_id, result.observation_revision) == (original.call_id, original.observation_revision), 'USAGE_ACK_IDENTITY_CONFLICT')
                row = await db.scalar(select(UsageOutboxRow).where(UsageOutboxRow.measurement_id == result.measurement_id).with_for_update())
                if row.state == 'delivered':
                    continue
                row.ack = result.model_dump(mode='json')
                if result.durable and result.disposition in ('accepted', 'duplicate'):
                    row.state = 'delivered'
                elif result.durable and result.disposition == 'quarantined':
                    row.state = 'quarantined'
                elif not result.retryable:
                    row.state = 'dead_letter'
    return len(seen)
