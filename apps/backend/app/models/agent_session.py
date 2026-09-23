"""SQLAlchemy models for durable Agent product sessions and completed runs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.models.chat import Base


class AgentSessionRow(Base):
    __tablename__ = 'agent_sessions'

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    branched_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text('now()'))
    turns: Mapped[list['AgentTurnRow']] = relationship(
        back_populates='session',
        order_by=lambda: (AgentTurnRow.created_at, AgentTurnRow.id),
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        Index('idx_agent_sessions_owner_updated', 'owner', updated_at.desc(), id.desc()),
        Index('uq_agent_sessions_owner_import_key', 'owner', 'import_key', unique=True,
              postgresql_where=text('import_key IS NOT NULL')),
    )


class AgentTurnRow(Base):
    __tablename__ = 'agent_turns'

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey('agent_sessions.id', ondelete='CASCADE'), nullable=False,
    )
    user_content: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    assistant_content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    process: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    steers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    question: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    transcript: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text('now()'))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session: Mapped[AgentSessionRow] = relationship(back_populates='turns')

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'stopped', 'failed', 'timeout', 'awaiting_input')",
            name='chk_agent_turns_status',
        ),
        Index('idx_agent_turns_session_created', 'session_id', 'created_at', 'id'),
        Index('uq_agent_turns_active', 'session_id', unique=True,
              postgresql_where=text("status = 'running'")),
    )
