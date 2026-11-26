"""Configuration deployment state. No entitlement or historical Run columns."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class ConfigRevisionRow(Base):
    __tablename__ = 'agent_config_revisions'
    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_number: Mapped[int] = mapped_column(Integer, unique=True)
    base_revision: Mapped[str | None] = mapped_column(String(36))
    config_digest: Mapped[str] = mapped_column(String(71))
    spec: Mapped[dict] = mapped_column(JSON)
    principal: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConfigControlRow(Base):
    __tablename__ = 'agent_config_control'
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    active_revision: Mapped[str | None] = mapped_column(String(36))
    desired_revision: Mapped[str | None] = mapped_column(String(36))
    deployment_id: Mapped[str | None] = mapped_column(String(36))
    admission_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    pause_operation_id: Mapped[str | None] = mapped_column(String(36))
    pause_reason: Mapped[str | None] = mapped_column(String(256))


class ConfigOperationRow(Base):
    __tablename__ = 'agent_config_operations'
    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action: Mapped[str] = mapped_column(String(24))
    revision_id: Mapped[str | None] = mapped_column(String(36), index=True)
    fingerprint: Mapped[str] = mapped_column(String(71))
    result: Mapped[dict] = mapped_column(JSON)
    details: Mapped[dict] = mapped_column(JSON)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TaskExecutionConstraintRow(Base):
    __tablename__ = 'agent_task_execution_constraints'
    task_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(36), index=True)
    spec_digest: Mapped[str] = mapped_column(String(71))
    build_revision: Mapped[str] = mapped_column(String(100))
    runtime_version: Mapped[str] = mapped_column(String(100))
    capability_manifest_digest: Mapped[str] = mapped_column(String(71))
    required_capabilities: Mapped[list] = mapped_column(JSON)
    constraint_version: Mapped[int] = mapped_column(Integer, default=1)
