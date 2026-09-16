"""Persistence model for authenticated personal profiles."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.models.chat import Base


class UserProfileRow(Base):
    __tablename__ = 'user_profiles'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    avatar_key: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('false'),
    )
    bio: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    achievements: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    educations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    biography: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    institutions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text('now()'),
    )

    __table_args__ = (
        CheckConstraint(
            "avatar_key IN ('avatar-01', 'avatar-02', 'avatar-03', 'avatar-04', 'avatar-05')",
            name='chk_user_profiles_avatar_key',
        ),
    )
