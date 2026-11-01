"""Knowledge papers eligible for the home feed, synced offline from the knowledge base."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class DiscoveryPoolPaperRow(Base):
    __tablename__ = 'discovery_pool_papers'

    paper_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    # Always a displayable knowledge image path; papers without one are never stored.
    image_id: Mapped[str] = mapped_column(Text, nullable=False)
    subjects: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index('idx_discovery_pool_papers_year_synced', 'year', 'synced_at'),
    )
