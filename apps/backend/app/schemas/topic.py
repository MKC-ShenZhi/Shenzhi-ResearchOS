"""Stable public contract for the Topic Catalog capability."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.knowledge import KnowledgeModel


class KnowledgeTopicAuthor(KnowledgeModel):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, validation_alias='avatarUrl', serialization_alias='avatarUrl')
    is_verified: bool = Field(default=False, validation_alias='isVerified', serialization_alias='isVerified')


class KnowledgeCreator(KnowledgeModel):
    """Platform creator profile used by topic cards."""

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, validation_alias='avatarUrl', serialization_alias='avatarUrl')
    bio: str = Field(min_length=1, max_length=1000)
    topic_count: int = Field(ge=0, validation_alias='topicCount', serialization_alias='topicCount')
    is_verified: bool = Field(default=False, validation_alias='isVerified', serialization_alias='isVerified')


class KnowledgeTopic(KnowledgeModel):
    @field_validator('id', 'name_zh', 'name_en', 'description_zh', 'description_en', 'category', 'subject_query')
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Topic text must not be blank')
        return value

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
    author: str | KnowledgeTopicAuthor
    description_zh: str = Field(
        min_length=1,
        max_length=2000,
        validation_alias='descriptionZh',
        serialization_alias='descriptionZh',
    )
    description_detail: str | None = Field(
        default=None,
        max_length=10000,
        validation_alias='descriptionDetail',
        serialization_alias='descriptionDetail',
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
    is_following: bool = Field(default=False, validation_alias='isFollowing', serialization_alias='isFollowing')
    icon_key: str | None = Field(default=None, validation_alias='iconKey', serialization_alias='iconKey')
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

