"""Management-only Agent evidence, isolated from task leasing."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class WorkerSnapshotRow(Base):
    __tablename__ = 'agent_management_worker_instances'
    worker_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    request_digest: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lifecycle: Mapped[str] = mapped_column(String(16))
    health: Mapped[str] = mapped_column(String(16))
    active_run_id: Mapped[str | None] = mapped_column(String(255))
    run_tool_ids: Mapped[list[str]] = mapped_column(JSON)
    manifest_digest: Mapped[str | None] = mapped_column(String(100))


class WorkerManifestRow(Base):
    __tablename__ = 'agent_management_worker_manifests'
    worker_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    digest: Mapped[str] = mapped_column(String(100), primary_key=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WorkerLifecycleRow(Base):
    __tablename__ = 'agent_management_worker_events'
    worker_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    manifest_digest: Mapped[str | None] = mapped_column(String(100))
    run_id: Mapped[str | None] = mapped_column(String(255))
