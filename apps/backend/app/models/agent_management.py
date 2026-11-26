"""Phase 2 management audit and health history. No entitlement dependencies."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ManagementAuditRow(Base):
    __tablename__ = 'agent_management_audit'
    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36))
    online_probe: Mapped[bool] = mapped_column(Boolean)
    principal: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(24))
    target_kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(255))
    target_fingerprint: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_digest: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(100))
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[dict | None] = mapped_column(JSON)
    seal: Mapped[str] = mapped_column(String(64))
