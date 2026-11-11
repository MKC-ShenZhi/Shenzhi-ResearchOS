"""Active Topic directory shared by Knowledge and account interactions."""

from __future__ import annotations

import asyncio
from time import monotonic

from app.integrations.knowledge.adapter import KnowledgeAdapter, is_openalex_topic_id
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.schemas.knowledge import PaperBrowseResponse
from app.schemas.topic import OpenAlexTopic, OpenAlexTopicListResponse

CATALOG_TTL_SECONDS = 300


class OpenAlexTopicRegistry:
    def __init__(self, adapter: KnowledgeAdapter | None = None):
        self._adapter = adapter
        self._catalog: OpenAlexTopicListResponse | None = None
        self._expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    @property
    def adapter(self) -> KnowledgeAdapter:
        if self._adapter is None:
            self._adapter = KnowledgeAdapter()
        return self._adapter

    async def list_topics(self) -> OpenAlexTopicListResponse:
        if self._catalog is not None and monotonic() < self._expires_at:
            return self._catalog
        async with self._refresh_lock:
            if self._catalog is not None and monotonic() < self._expires_at:
                return self._catalog
            try:
                self._catalog = await self.adapter.topic_catalog()
            except KnowledgeIntegrationError as error:
                if error.status_code == 404:
                    raise KnowledgeIntegrationError.contract_violation() from error
                raise
            self._expires_at = monotonic() + CATALOG_TTL_SECONDS
            return self._catalog

    async def require_topic(self, topic_id: str) -> OpenAlexTopic:
        if is_openalex_topic_id(topic_id):
            catalog = await self.list_topics()
            for topic in catalog.items:
                if topic.id == topic_id:
                    return topic
        raise KnowledgeIntegrationError.not_found()

    async def get_topic(self, topic_id: str) -> OpenAlexTopic:
        return await self.adapter.topic(await self.require_topic(topic_id))

    async def papers(self, topic_id: str, *, limit: int, offset: int) -> PaperBrowseResponse:
        await self.require_topic(topic_id)
        return await self.adapter.topic_papers(topic_id, limit=limit, offset=offset)


openalex_topics = OpenAlexTopicRegistry()
