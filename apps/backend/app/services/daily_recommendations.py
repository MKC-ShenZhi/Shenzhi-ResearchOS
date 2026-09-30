"""Generate and serve the small PostgreSQL-backed daily recommendation pool."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import dispose_engine, session_scope
from app.core.identity import RequestIdentity
from app.core.time import utc_now
from app.models.daily_recommendation import DailyRecommendationRow
from app.schemas.discovery import DailyRecommendationResponse, DiscoveryFeedTab
from app.schemas.knowledge import KnowledgeSearchRequest, PaperSearchResult
from app.services.knowledge.service import KnowledgeService


logger = logging.getLogger(__name__)

# These are the same broad topics used by the former browser-side random feed.
# Five searches yield at most 100 candidates before de-duplication.
DAILY_RECOMMENDATION_QUERIES = (
    'machine learning',
    'deep learning',
    'large language model',
    'computer vision',
    'natural language processing',
)
SEARCH_TOP_K = 20
MAX_POOL_SIZE = 100


def _stable_rank(identity: RequestIdentity, day: date, tab: DiscoveryFeedTab, paper_id: str) -> bytes:
    value = f'{identity.kind}:{identity.subject_id}:{day.isoformat()}:{tab}:{paper_id}'
    return hashlib.sha256(value.encode('utf-8')).digest()


def select_recommendations(
    items: list[PaperSearchResult],
    *,
    identity: RequestIdentity,
    day: date,
    tab: DiscoveryFeedTab,
    limit: int,
) -> list[PaperSearchResult]:
    candidates = items
    if tab == 'frontier':
        recent_year = day.year - 1
        candidates = [item for item in items if item.year is not None and item.year >= recent_year]

    return sorted(
        candidates,
        key=lambda item: (_stable_rank(identity, day, tab, item.id), item.id),
    )[:limit]


class DailyRecommendationService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def refresh(self, recommendation_date: date | None = None) -> int:
        """Fetch a complete pool first, then atomically upsert it for one day."""
        target_date = recommendation_date or utc_now().date()
        by_id: dict[str, PaperSearchResult] = {}

        for query in DAILY_RECOMMENDATION_QUERIES:
            response = await self.knowledge.search(KnowledgeSearchRequest(
                query=query,
                topK=SEARCH_TOP_K,
            ))
            for item in response.results:
                by_id.setdefault(item.id, item)

        if not by_id:
            raise RuntimeError('Knowledge search returned no recommendation candidates')

        candidates = list(by_id.values())[:MAX_POOL_SIZE]
        payload = [item.model_dump(mode='json', by_alias=True) for item in candidates]
        generated_at = utc_now()
        async with session_scope() as session:
            statement = insert(DailyRecommendationRow).values(
                recommendation_date=target_date,
                payload=payload,
                created_at=generated_at,
            )
            await session.execute(statement.on_conflict_do_update(
                index_elements=['recommendation_date'],
                set_={'payload': payload, 'created_at': generated_at},
            ))
        return len(candidates)

    async def recommendations(
        self,
        identity: RequestIdentity,
        *,
        tab: DiscoveryFeedTab,
        limit: int,
        day: date | None = None,
    ) -> DailyRecommendationResponse:
        target_date = day or utc_now().date()
        async with session_scope() as session:
            row = await session.scalar(
                select(DailyRecommendationRow)
                .where(DailyRecommendationRow.recommendation_date <= target_date)
                .order_by(DailyRecommendationRow.recommendation_date.desc())
                .limit(1)
            )

        if row is None:
            return DailyRecommendationResponse(date=target_date, items=[])

        pool = [PaperSearchResult.model_validate(item) for item in row.payload]
        return DailyRecommendationResponse(
            date=target_date,
            items=select_recommendations(
                pool,
                identity=identity,
                day=target_date,
                tab=tab,
                limit=limit,
            ),
        )


async def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        count = await DailyRecommendationService().refresh()
    except Exception:
        logger.exception('Daily recommendation refresh failed')
        return 1
    else:
        logger.info('Daily recommendation refresh completed candidates=%s', count)
        print(f'candidates={count}')
        return 0
    finally:
        await dispose_engine()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
