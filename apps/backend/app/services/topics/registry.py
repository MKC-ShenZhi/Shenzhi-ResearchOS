"""Domain access for the controlled Topic Catalog."""

from __future__ import annotations

from app.schemas.topic import KnowledgeTopic, KnowledgeTopicListResponse
from app.services.topics.catalog import load_topic_catalog


class TopicRegistryError(RuntimeError):
    """Raised for a catalog lookup that cannot be completed."""


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

