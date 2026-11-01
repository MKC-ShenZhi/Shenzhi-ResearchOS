"""One stored daily edition (the ``daily`` home source) per Shanghai day."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class HomeDailyEditionRow(Base):
    __tablename__ = 'home_daily_editions'

    edition_date: Mapped[date] = mapped_column(Date, primary_key=True)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )
