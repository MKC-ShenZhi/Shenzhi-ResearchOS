"""Persistence model for authenticated user preferences."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.models.chat import Base


class UserSettingsRow(Base):
    __tablename__ = 'user_settings'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'zh-CN'"))
    theme_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'system'"))
    notify_activity: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    notify_subscription: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    notify_interaction: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    notify_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )

    __table_args__ = (
        CheckConstraint("locale IN ('zh-CN', 'en')", name='chk_user_settings_locale'),
        CheckConstraint(
            "theme_mode IN ('light', 'dark', 'system')",
            name='chk_user_settings_theme_mode',
        ),
    )
