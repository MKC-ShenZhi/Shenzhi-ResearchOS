"""SQLAlchemy models for the daily platform statistics snapshot.

Only aggregates live here. No user id, folder id, or per-user action is copied
into these tables, so the read-only service contract can expose them safely.
"""
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class StatsSnapshotRunRow(Base):
    """Publication state for one platform day.

    ``status='completed'`` means the day's rows were written and committed
    atomically and may be served. ``failure_reason`` only describes the latest
    build attempt, so a failed re-run never hides an already published day.
    """

    __tablename__ = 'stats_snapshot_runs'

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_version: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status in ('completed', 'failed')", name='ck_stats_snapshot_runs_status'),
    )


class PaperStatDailyRow(Base):
    __tablename__ = 'paper_stats_daily'

    snapshot_date: Mapped[date] = mapped_column(
        Date, ForeignKey('stats_snapshot_runs.snapshot_date', ondelete='CASCADE'), primary_key=True,
    )
    paper_id: Mapped[str] = mapped_column(Text, primary_key=True)
    collector_count: Mapped[int] = mapped_column(Integer, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint('collector_count >= 0', name='ck_paper_stats_daily_collector_count'),
        CheckConstraint('like_count >= 0', name='ck_paper_stats_daily_like_count'),
    )


class TopicStatDailyRow(Base):
    __tablename__ = 'topic_stats_daily'

    snapshot_date: Mapped[date] = mapped_column(
        Date, ForeignKey('stats_snapshot_runs.snapshot_date', ondelete='CASCADE'), primary_key=True,
    )
    topic_id: Mapped[str] = mapped_column(Text, primary_key=True)
    follower_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint('follower_count >= 0', name='ck_topic_stats_daily_follower_count'),
    )
