"""Explicit retention command for behavior facts and recommendation snapshots."""

import asyncio
import logging
import sys
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.core.database import dispose_engine, session_scope
from app.core.time import utc_now
from app.models.recommendation import BehaviorEventRow, RecommendationSnapshotRow

EVENT_RETENTION_DAYS = 90
logger = logging.getLogger(__name__)


async def purge_expired(now: datetime | None = None) -> tuple[int, int]:
    current = now or utc_now()
    cutoff = current - timedelta(days=EVENT_RETENTION_DAYS)
    async with session_scope() as session:
        events = await session.execute(delete(BehaviorEventRow).where(
            BehaviorEventRow.received_at < cutoff,
        ))
        snapshots = await session.execute(delete(RecommendationSnapshotRow).where(
            RecommendationSnapshotRow.expires_at < current,
        ))
        return int(events.rowcount or 0), int(snapshots.rowcount or 0)


async def main() -> int:
    try:
        events, snapshots = await purge_expired()
        print(f'deleted_events={events} deleted_recommendation_snapshots={snapshots}')
        return 0
    except Exception:
        logger.exception('Recommendation retention cleanup failed')
        return 1
    finally:
        await dispose_engine()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
