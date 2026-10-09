"""Stable public contract for the Topic Catalog capability."""

from __future__ import annotations

from pydantic import Field

from app.schemas.knowledge import KnowledgeModel


class KnowledgeTopic(KnowledgeModel):
    id: str = Field(min_length=1, max_length=200)
    image_path: str | None = Field(
        default=None,
        validation_alias='imagePath',
        serialization_alias='imagePath',
    )
    name_zh: str = Field(
        min_length=1,
        max_length=200,
        validation_alias='nameZh',
        serialization_alias='nameZh',
    )
    name_en: str = Field(
        min_length=1,
        max_length=200,
        validation_alias='nameEn',
        serialization_alias='nameEn',
    )
    author: str = Field(min_length=1, max_length=200)
    description_zh: str = Field(
        min_length=1,
        max_length=2000,
        validation_alias='descriptionZh',
        serialization_alias='descriptionZh',
    )
    description_en: str = Field(
        min_length=1,
        max_length=2000,
        validation_alias='descriptionEn',
        serialization_alias='descriptionEn',
    )
    followers_count: int = Field(
        default=0,
        ge=0,
        validation_alias='followersCount',
        serialization_alias='followersCount',
    )
    category: str = Field(min_length=1, max_length=200)
    subject_query: str = Field(
        min_length=1,
        max_length=500,
        validation_alias='subjectQuery',
        serialization_alias='subjectQuery',
    )
    paper_count: int = Field(
        ge=0,
        validation_alias='paperCount',
        serialization_alias='paperCount',
    )
    enabled: bool = True


class KnowledgeTopicListResponse(KnowledgeModel):
    items: list[KnowledgeTopic] = Field(default_factory=list)
    total: int = Field(ge=0)
    categories: list[str] = Field(default_factory=list)

