"""Shared meeting directory for the knowledge paper library."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeConferenceSnapshotRow(Base):
    __tablename__ = 'knowledge_conference_snapshot'
    __table_args__ = (CheckConstraint('id = 1', name='knowledge_conference_snapshot_singleton'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    items: Mapped[list[dict] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
