"""Domain access for the controlled Topic Catalog."""

from __future__ import annotations

from app.schemas.topic import KnowledgeCreator, KnowledgeTopic, KnowledgeTopicListResponse
from app.services.topics.catalog import load_topic_catalog


class TopicRegistryError(RuntimeError):
    """Raised for a catalog lookup that cannot be completed."""


CREATOR_ALIASES = {'shenzhi', '深知'}


class TopicRegistry:
    def __init__(self, topics: tuple[KnowledgeTopic, ...] | None = None):
        self._topics = topics if topics is not None else load_topic_catalog()

    def list_topics(self) -> KnowledgeTopicListResponse:
        items = [topic for topic in self._topics if topic.enabled]
        categories = list(dict.fromkeys(topic.category for topic in items))
        return KnowledgeTopicListResponse(items=items, total=len(items), categories=categories)

    def get_topic(self, topic_id: str) -> KnowledgeTopic:
        topic = next(
            (item for item in self._topics if item.enabled and item.id == topic_id),
            None,
        )
        if topic is None:
            raise TopicRegistryError('未找到对应主题')
        return topic

    def get_creator(self, creator_id: str) -> KnowledgeCreator:
        normalized = creator_id.strip().lower()
        if normalized not in CREATOR_ALIASES:
            raise TopicRegistryError('未找到对应创作者')

        topic_count = sum(
            1
            for topic in self._topics
            if topic.enabled
            and (
                (isinstance(topic.author, str) and topic.author.strip().lower() in CREATOR_ALIASES)
                or (
                    not isinstance(topic.author, str)
                    and topic.author.id.strip().lower() in CREATOR_ALIASES
                )
            )
        )
        return KnowledgeCreator(
            id='shenzhi',
            name='ShenZhi',
            avatar_url='/brand/logo-night.png',
            bio='深知 ShenZhi · Research OS，整理和维护面向科研工作的知识主题。',
            topic_count=topic_count,
            is_verified=True,
        )

