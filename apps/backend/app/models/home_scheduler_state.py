"""Shared timing state for the home feed jobs."""

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HomeSchedulerStateRow(Base):
    __tablename__ = 'home_scheduler_state'

    job: Mapped[str] = mapped_column(Text, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
