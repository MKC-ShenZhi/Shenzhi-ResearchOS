"""Public schemas for account-level likes, topic follows and public counters."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.knowledge import PaperDetail


MAX_BATCH_IDS = 100
MAX_ID_LENGTH = 300


def _normalize_ids(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('ids must contain non-empty strings')
        item = value.strip()
        if len(item) > MAX_ID_LENGTH:
            raise ValueError('id is too long')
        if item not in normalized:
            normalized.append(item)
    return normalized


class PaperInteractionsRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=1, max_length=MAX_BATCH_IDS)

    @field_validator('paper_ids')
    @classmethod
    def validate_paper_ids(cls, value: list[str]) -> list[str]:
        return _normalize_ids(value)


class PaperInteractionItem(BaseModel):
    paper_id: str
    collector_count: int = Field(ge=0)
    like_count: int = Field(ge=0)
    # Personal fields are filled only for an authenticated identity.
    folder_ids: list[int] | None = None
    liked: bool | None = None


class PaperInteractionsResponse(BaseModel):
    authenticated: bool
    # Echo of the identity used for this response, so a client can detect an
    # account switch that happened while the batch was in flight.
    user_id: str | None = None
    items: list[PaperInteractionItem]


class TopicInteractionsRequest(BaseModel):
    topic_ids: list[str] = Field(min_length=1, max_length=MAX_BATCH_IDS)

    @field_validator('topic_ids')
    @classmethod
    def validate_topic_ids(cls, value: list[str]) -> list[str]:
        return _normalize_ids(value)


class TopicInteractionItem(BaseModel):
    topic_id: str
    follower_count: int = Field(ge=0)
    is_following: bool | None = None


class TopicInteractionsResponse(BaseModel):
    authenticated: bool
    user_id: str | None = None
    items: list[TopicInteractionItem]


class LikeStateResponse(BaseModel):
    paper_id: str
    liked: bool
    like_count: int = Field(ge=0)


class TopicFollowStateResponse(BaseModel):
    topic_id: str
    is_following: bool
    follower_count: int = Field(ge=0)


class TopicFollowItem(BaseModel):
    topic_id: str
    followed_at: datetime


class TopicFollowListResponse(BaseModel):
    items: list[TopicFollowItem]
    total: int = Field(ge=0)


class LikedPaperItem(PaperDetail):
    paper_id: str
    liked_at: datetime
    is_available: bool = True


class LikedPaperListResponse(BaseModel):
    items: list[LikedPaperItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
