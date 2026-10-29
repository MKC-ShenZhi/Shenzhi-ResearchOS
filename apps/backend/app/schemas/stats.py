"""Read-only public contract for the daily platform aggregates."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class StatsMetaResponse(BaseModel):
    """Which platform day the statistics service currently publishes."""

    published: bool
    snapshot_date: date | None = None
    snapshot_version: str | None = None
    computed_at: datetime | None = None


class PaperStatsItem(BaseModel):
    paper_id: str
    collector_count: int = Field(ge=0)
    like_count: int = Field(ge=0)


class PaperStatsPage(BaseModel):
    snapshot_date: date
    snapshot_version: str
    computed_at: datetime
    items: list[PaperStatsItem] = Field(default_factory=list)
    total: int = Field(ge=0)
    next_cursor: str | None = None
    has_more: bool = False
    # Explicit zero counts for requested ids without a row in this snapshot.
    missing_paper_ids: list[str] = Field(default_factory=list)


class TopicStatsItem(BaseModel):
    topic_id: str
    follower_count: int = Field(ge=0)


class TopicStatsPage(BaseModel):
    snapshot_date: date
    snapshot_version: str
    computed_at: datetime
    items: list[TopicStatsItem] = Field(default_factory=list)
    total: int = Field(ge=0)
    next_cursor: str | None = None
    has_more: bool = False
    missing_topic_ids: list[str] = Field(default_factory=list)
