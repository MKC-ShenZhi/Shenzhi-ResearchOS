"""Agent-owned v2 identities and append-only call observations."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class TaskMeteringRow(Base):
    __tablename__ = 'agent_task_metering'
    __table_args__ = (UniqueConstraint('owner_id', 'submission_id', name='uq_agent_metering_submission'),)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255))
    submission_id: Mapped[str] = mapped_column(String(255))
    profile_id: Mapped[str] = mapped_column(String(255), unique=True)
    context: Mapped[str] = mapped_column(String(32))
    binding_status: Mapped[str] = mapped_column(String(32), index=True)
    envelope: Mapped[dict] = mapped_column(JSON)
    binding: Mapped[dict | None] = mapped_column(JSON)
    receipt: Mapped[dict | None] = mapped_column(JSON)
    current_grant: Mapped[dict | None] = mapped_column(JSON)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    usage_sequence: Mapped[int] = mapped_column(Integer, default=0)


class ExecutionRow(Base):
    __tablename__ = 'agent_executions'
    __table_args__ = (UniqueConstraint('run_id', 'lease_token', name='uq_agent_execution_lease'),)
    execution_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.run_id'), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    worker_id: Mapped[str] = mapped_column(String(255))
    lease_token: Mapped[int] = mapped_column(Integer)
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)


class CallRow(Base):
    __tablename__ = 'agent_calls'
    __table_args__ = (UniqueConstraint('task_id', 'activation_key', name='uq_agent_skill_activation'),)
    call_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey('agent_executions.execution_id'), index=True)
    activation_key: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32), index=True)
    intent: Mapped[dict] = mapped_column(JSON)
    permit: Mapped[dict | None] = mapped_column(JSON)
    backend_request: Mapped[dict | None] = mapped_column(JSON)
    remote_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    start_operation_id: Mapped[str | None] = mapped_column(String(255))
    start_fact: Mapped[dict | None] = mapped_column(JSON)
    start_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed_intent: Mapped[dict | None] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class ObservationRow(Base):
    __tablename__ = 'agent_usage_observations'
    __table_args__ = (
        UniqueConstraint('call_id', 'revision', name='uq_agent_call_observation_revision'),
        UniqueConstraint('call_id', 'submission_key', name='uq_agent_observation_submission'),
        UniqueConstraint('task_id', 'sequence', name='uq_agent_task_usage_sequence'),
    )
    measurement_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    call_id: Mapped[str] = mapped_column(ForeignKey('agent_calls.call_id'), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    submission_key: Mapped[str] = mapped_column(String(255))
    submission_digest: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)


class UsageOutboxRow(Base):
    __tablename__ = 'agent_usage_outbox'
    measurement_id: Mapped[str] = mapped_column(ForeignKey('agent_usage_observations.measurement_id'), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ack: Mapped[dict | None] = mapped_column(JSON)


class GrantHistoryRow(Base):
    __tablename__ = 'agent_grant_history'
    grant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class GrantRevocationRow(Base):
    __tablename__ = 'agent_grant_revocations'
    operation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class CloseManifestRow(Base):
    __tablename__ = 'agent_close_manifests'
    __table_args__ = (UniqueConstraint('task_id', 'usage_sequence', name='uq_agent_close_sequence'),)
    manifest_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('agent_tasks.task_id'), index=True)
    usage_sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    ack: Mapped[dict | None] = mapped_column(JSON)
