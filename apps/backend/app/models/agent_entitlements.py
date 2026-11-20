"""Backend authority: policy, reservations, authorization and settlement history.

No foreign keys refer to Agent-owned databases or ephemeral product sessions.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EntitlementPolicyRow(Base):
    __tablename__ = 'agent_entitlement_policies'
    policy_revision: Mapped[str] = mapped_column(String(255), primary_key=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    test_only: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSON)


class OwnerEntitlementRow(Base):
    __tablename__ = 'agent_owner_entitlements'
    owner_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    policy_revision: Mapped[str] = mapped_column(ForeignKey('agent_entitlement_policies.policy_revision'))
    plan_id: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MeteringProfileRow(Base):
    __tablename__ = 'agent_metering_profiles'
    __table_args__ = (UniqueConstraint('audience', 'task_id', name='uq_backend_metering_task'),
                      UniqueConstraint('owner_id', 'client_key', name='uq_backend_metering_client_key'))
    profile_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    audience: Mapped[str] = mapped_column(String(255))
    context: Mapped[str] = mapped_column(String(32))
    provenance: Mapped[str] = mapped_column(String(64))
    admission_revision: Mapped[str] = mapped_column(String(255))
    request_digest: Mapped[str] = mapped_column(String(80))
    client_key: Mapped[str | None] = mapped_column(String(255))
    backend_submission_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    observation_submission_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    task_id: Mapped[str | None] = mapped_column(String(255))
    enrollment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    binding: Mapped[dict | None] = mapped_column(JSON)


class SubmissionRow(Base):
    __tablename__ = 'agent_submissions'
    __table_args__ = (UniqueConstraint('owner_id', 'client_key', name='uq_backend_submission_key'),)
    submission_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('agent_owner_entitlements.owner_id'), index=True)
    client_key: Mapped[str] = mapped_column(String(255))
    request_digest: Mapped[str] = mapped_column(String(80))
    request: Mapped[dict] = mapped_column(JSON)
    client_request_digest: Mapped[str | None] = mapped_column(String(80))
    profile_id: Mapped[str] = mapped_column(ForeignKey('agent_metering_profiles.profile_id'), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ObservationAdmissionRow(Base):
    """A1 admission namespace, never a formal Submission/reservation."""
    __tablename__ = 'agent_observation_admissions'
    __table_args__ = (UniqueConstraint('owner_id', 'client_key', name='uq_backend_observation_admission'),)
    admission_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    client_key: Mapped[str] = mapped_column(String(255))
    profile_id: Mapped[str] = mapped_column(ForeignKey('agent_metering_profiles.profile_id'), unique=True)
    request_digest: Mapped[str] = mapped_column(String(80))
    client_request_digest: Mapped[str | None] = mapped_column(String(80))
    request: Mapped[dict] = mapped_column(JSON)


class GrantRootRow(Base):
    __tablename__ = 'agent_grant_roots'
    grant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('agent_submissions.submission_id'), unique=True)
    reservation_id: Mapped[str] = mapped_column(String(255), unique=True)
    current_revision: Mapped[int] = mapped_column(Integer)
    binding_revision: Mapped[int] = mapped_column(Integer, default=0)
    bound_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    receipt: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    settlement_status: Mapped[str] = mapped_column(String(40), default='held')
    overage: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_capabilities: Mapped[list] = mapped_column(JSON, default=list)


class GrantRevisionRow(Base):
    __tablename__ = 'agent_grant_revisions'
    grant_id: Mapped[str] = mapped_column(ForeignKey('agent_grant_roots.grant_id'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_digest: Mapped[str] = mapped_column(String(80))


class WindowCounterRow(Base):
    __tablename__ = 'agent_entitlement_windows'
    __table_args__ = (CheckConstraint('held >= 0 AND used >= 0', name='ck_backend_window_nonnegative'),)
    window_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('agent_owner_entitlements.owner_id'), index=True)
    rule_id: Mapped[str] = mapped_column(String(255), index=True)
    window_ref: Mapped[dict] = mapped_column(JSON)
    limit_units: Mapped[int] = mapped_column(BigInteger)
    held: Mapped[int] = mapped_column(BigInteger, default=0)
    used: Mapped[int] = mapped_column(BigInteger, default=0)


class ReservationAllocationRow(Base):
    __tablename__ = 'agent_reservation_allocations'
    __table_args__ = (CheckConstraint('task_held >= 0', name='ck_backend_reservation_nonnegative'),)
    allocation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey('agent_grant_roots.grant_id'), index=True)
    window_id: Mapped[str] = mapped_column(ForeignKey('agent_entitlement_windows.window_id'), index=True)
    allocation: Mapped[dict] = mapped_column(JSON)
    task_held: Mapped[int] = mapped_column(BigInteger)


class CallPermitRow(Base):
    __tablename__ = 'agent_call_permits'
    __table_args__ = (UniqueConstraint('audience', 'call_id', name='uq_backend_permit_call'),)
    permit_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    audience: Mapped[str] = mapped_column(String(255))
    call_id: Mapped[str] = mapped_column(String(255), index=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey('agent_grant_roots.grant_id'), index=True)
    request_digest: Mapped[str] = mapped_column(String(80))
    request: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), index=True)
    held: Mapped[dict] = mapped_column(JSON)
    adopted: Mapped[dict] = mapped_column(JSON, default=dict)
    start: Mapped[dict | None] = mapped_column(JSON)
    void_proof: Mapped[dict | None] = mapped_column(JSON)


class UsageInboxRow(Base):
    __tablename__ = 'agent_usage_inbox'
    __table_args__ = (
        UniqueConstraint('call_id', 'revision', name='uq_backend_usage_revision'),
        UniqueConstraint('task_id', 'sequence', name='uq_backend_usage_sequence'),
    )
    measurement_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(255), index=True)
    task_id: Mapped[str] = mapped_column(String(255), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    content_digest: Mapped[str] = mapped_column(String(80))
    verification_status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UsageProjectionRow(Base):
    __tablename__ = 'agent_usage_projections'
    call_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    start_fact: Mapped[dict] = mapped_column(JSON)
    settlement_status: Mapped[str] = mapped_column(String(40))


class UsageLedgerRow(Base):
    __tablename__ = 'agent_usage_ledger'
    entry_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(255), unique=True)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey('agent_grant_roots.grant_id'), index=True)
    allocation_id: Mapped[str] = mapped_column(ForeignKey('agent_reservation_allocations.allocation_id'), index=True)
    measurement_id: Mapped[str | None] = mapped_column(ForeignKey('agent_usage_inbox.measurement_id'))
    kind: Mapped[str] = mapped_column(String(40))
    held_delta: Mapped[int] = mapped_column(BigInteger)
    used_delta: Mapped[int] = mapped_column(BigInteger)
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntitlementAuditRow(Base):
    __tablename__ = 'agent_entitlement_audit'
    audit_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(255), unique=True)
    principal: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskCloseRow(Base):
    __tablename__ = 'agent_task_closes'
    manifest_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey('agent_grant_roots.grant_id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40))

class PlanReleaseRow(Base):
    """Current publication pointer; immutable policy and historical audits remain."""
    __tablename__ = 'agent_plan_releases'
    plan_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    policy_revision: Mapped[str] = mapped_column(ForeignKey('agent_entitlement_policies.policy_revision'))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
