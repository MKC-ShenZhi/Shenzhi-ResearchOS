"""Agent-owned Task, Run, Event, Outbox and fencing lease tables."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = 'agent_tasks'
    __table_args__ = (UniqueConstraint('owner_id', 'idempotency_key', name='uq_agent_task_owner_idempotency'),)

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(128))
    turn_id: Mapped[str | None] = mapped_column(String(128))
    input_ref: Mapped[str | None] = mapped_column(String(2048))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_run_id: Mapped[str | None] = mapped_column(String(32))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    runs: Mapped[list['RunRow']] = relationship(back_populates='task')


class RunRow(Base):
    __tablename__ = 'agent_runs'
    __table_args__ = (UniqueConstraint('task_id', 'attempt', name='uq_agent_run_attempt'),)

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id', ondelete='CASCADE'), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    report_json: Mapped[dict | None] = mapped_column(JSON)
    worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task: Mapped[TaskRow] = relationship(back_populates='runs')


class RunEventRow(Base):
    __tablename__ = 'agent_run_events'
    __table_args__ = (UniqueConstraint('run_id', 'seq', name='uq_agent_event_run_seq'),)

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.run_id', ondelete='CASCADE'), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunControlRow(Base):
    __tablename__ = 'agent_run_controls'
    __table_args__ = (UniqueConstraint('run_id', 'seq', name='uq_agent_control_run_seq'),)

    control_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.run_id', ondelete='CASCADE'),
                                        nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxRow(Base):
    __tablename__ = 'agent_outbox'

    outbox_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.run_id', ondelete='CASCADE'), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
