"""Load and validate the controlled Topic Catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.topic import KnowledgeTopic


CATALOG_PATH = Path(__file__).resolve().parents[2] / 'data' / 'topic_catalog.json'
PROJECT_ROOT = CATALOG_PATH.parents[4]
WEB_PUBLIC_PATH = PROJECT_ROOT / 'apps' / 'web' / 'public'
EXPECTED_TOPIC_COUNT = 293
EXPECTED_CATEGORIES = {
    '大语言模型',
    '多模态',
    '机器学习',
    '计算机视觉',
    '生成式AI',
    '语音/音频处理',
    '智能体',
    '自然语言处理',
}


class TopicCatalogError(RuntimeError):
    """Raised when the controlled catalog cannot be loaded safely."""


@lru_cache(maxsize=1)
def load_topic_catalog() -> tuple[KnowledgeTopic, ...]:
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise TopicCatalogError('主题目录暂时不可用') from error

    if not isinstance(raw, list):
        raise TopicCatalogError('主题目录格式无效')

    topics: list[KnowledgeTopic] = []
    seen_ids: set[str] = set()
    seen_subject_queries: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise TopicCatalogError('主题目录记录格式无效')
        normalized: dict[str, Any] = dict(item)
        if 'descriptionEn' not in normalized and 'descriptionEh' in normalized:
            normalized['descriptionEn'] = normalized.pop('descriptionEh')
        try:
            topic = KnowledgeTopic.model_validate(normalized)
        except ValidationError as error:
            raise TopicCatalogError('主题目录字段无效') from error
        if topic.id in seen_ids:
            raise TopicCatalogError('主题目录包含重复 ID')
        normalized_subject_query = topic.subject_query.strip().casefold()
        if normalized_subject_query in seen_subject_queries:
            raise TopicCatalogError('主题目录包含重复 subjectQuery')
        if topic.image_path and not topic.image_path.startswith('/images/topics/'):
            raise TopicCatalogError('主题目录图片路径无效')
        if topic.image_path:
            image_file = WEB_PUBLIC_PATH.joinpath(*topic.image_path.lstrip('/').split('/'))
            if not image_file.is_file():
                raise TopicCatalogError('主题目录图片文件不存在')
        author_id = topic.author if isinstance(topic.author, str) else topic.author.id
        if author_id.strip().lower() != 'shenzhi':
            raise TopicCatalogError('主题目录作者 ID 无效')
        seen_ids.add(topic.id)
        seen_subject_queries.add(normalized_subject_query)
        topics.append(topic)
    enabled_topics = [topic for topic in topics if topic.enabled]
    if len(enabled_topics) != EXPECTED_TOPIC_COUNT:
        raise TopicCatalogError('主题目录数量不符合预期')
    if {topic.category for topic in enabled_topics} != EXPECTED_CATEGORIES:
        raise TopicCatalogError('主题目录分类不符合预期')
    return tuple(topics)

