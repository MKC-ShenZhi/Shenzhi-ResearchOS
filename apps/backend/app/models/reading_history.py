"""Durable reading history for authenticated users."""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class ReadingHistoryRow(Base):
    __tablename__ = 'reading_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    paper_id: Mapped[str] = mapped_column(Text, nullable=False)
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )

    __table_args__ = (
        UniqueConstraint('user_id', 'paper_id', name='uq_reading_history_user_paper'),
        Index('idx_reading_history_user_viewed', 'user_id', last_viewed_at.desc()),
    )