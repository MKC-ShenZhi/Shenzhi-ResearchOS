"""SQLAlchemy models for account-level paper likes and topic follows."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class PaperLikeRow(Base):
    """One row per (user, paper); revisiting the same pair never adds a second like."""

    __tablename__ = 'paper_likes'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    paper_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    __table_args__ = (
        Index('idx_paper_likes_paper', 'paper_id'),
        Index('idx_paper_likes_user_created', 'user_id', 'created_at'),
    )


class TopicFollowRow(Base):
    """One row per (user, catalog topic id); the catalog stays the source of truth."""

    __tablename__ = 'topic_follows'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    topic_id: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    __table_args__ = (
        Index('idx_topic_follows_topic', 'topic_id'),
        Index('idx_topic_follows_user_created', 'user_id', 'created_at'),
    )
