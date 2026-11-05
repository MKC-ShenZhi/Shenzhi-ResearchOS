"""One current immutable payload plus durable scheduling metadata."""

from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ConferenceSnapshotRow(Base):
    __tablename__ = "conference_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(Text)
    upstream_sha: Mapped[str | None] = mapped_column(Text)
    data_as_of: Mapped[date | None] = mapped_column(Date)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("id = 1", name="conference_snapshot_singleton"),)
