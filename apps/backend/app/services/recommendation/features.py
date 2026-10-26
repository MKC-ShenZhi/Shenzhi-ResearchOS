"""Bounded paper metadata enrichment through the existing Knowledge service."""

import asyncio
import logging

from app.schemas.knowledge import PaperDetail
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError

logger = logging.getLogger(__name__)


class PaperFeatureService:
    def __init__(self, knowledge: KnowledgeService | None = None):
        self.knowledge = knowledge or KnowledgeService()

    async def get_many(self, paper_ids: list[str]) -> dict[str, PaperDetail]:
        ids = list(dict.fromkeys(paper_ids))
        if not ids:
            return {}
        semaphore = asyncio.Semaphore(4)

        async def load(paper_id: str) -> tuple[str, PaperDetail | None]:
            async with semaphore:
                try:
                    return paper_id, await asyncio.wait_for(self.knowledge.get_paper(paper_id), timeout=4)
                except (KnowledgeServiceError, TimeoutError):
                    # Missing metadata never invents an interest feature. The
                    # behavior fact remains durable for a later rebuild.
                    logger.debug('Recommendation paper metadata unavailable')
                    return paper_id, None

        tasks = [asyncio.create_task(load(paper_id)) for paper_id in ids]
        done, pending = await asyncio.wait(tasks, timeout=6)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        results = [task.result() for task in done if not task.cancelled()]
        return {paper_id: paper for paper_id, paper in results if paper is not None}
