"""SQLAlchemy models for durable Chat sessions (Backend-only, separate from Auth DB)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass


class ChatSessionRow(Base):
    __tablename__ = 'chat_sessions'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    messages: Mapped[list['ChatMessageRow']] = relationship(
        back_populates='session',
        order_by='ChatMessageRow.created_at',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        Index('idx_chat_sessions_owner', 'owner', favorite.desc(), updated_at.desc()),
        Index(
            'idx_chat_sessions_anonymous_expiry',
            'updated_at',
            postgresql_where=text("owner LIKE 'anon:%'"),
        ),
    )


class ChatMessageRow(Base):
    __tablename__ = 'chat_messages'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    attachment_context: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    message_refs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    followups: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session: Mapped[ChatSessionRow] = relationship(back_populates='messages')

    __table_args__ = (
        CheckConstraint(
            "status IN ('streaming', 'done', 'stopped', 'failed')",
            name='chk_chat_messages_status',
        ),
        Index('idx_chat_messages_session', 'session_id', 'created_at'),
        Index(
            'uq_chat_messages_active',
            'session_id',
            unique=True,
            postgresql_where=text("status = 'streaming'"),
        ),
    )
