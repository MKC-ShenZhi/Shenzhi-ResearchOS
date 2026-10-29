"""User-owned recommendation facts and materialized interest profiles."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class BehaviorEventRow(Base):
    __tablename__ = 'behavior_events'

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text)
    query_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    rank: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        Index('idx_behavior_events_user_time', 'user_id', received_at.desc()),
        Index('idx_behavior_events_user_entity', 'user_id', 'entity_type', 'entity_id'),
        Index('idx_behavior_events_received', received_at),
    )


class UserInterestProfileRow(Base):
    __tablename__ = 'user_interest_profiles'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    profile_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class RecommendationSnapshotRow(Base):
    __tablename__ = 'recommendation_snapshots'

    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    items: Mapped[list] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index('idx_recommendation_snapshots_user_expiry', 'user_id', 'expires_at'),
        Index('idx_recommendation_snapshots_expiry', 'expires_at'),
    )
