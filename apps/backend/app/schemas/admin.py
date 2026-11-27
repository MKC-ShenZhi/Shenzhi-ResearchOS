"""Read-only administrator user projection; units come from entitlement storage."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminUsageWindow(BaseModel):
    rule_id: str
    metric: str
    purpose: str
    capability_id: str | None
    limit: int = Field(ge=0)
    used: int = Field(ge=0)
    held: int = Field(ge=0)
    remaining: int = Field(ge=0)
    window_start: datetime | None
    window_end: datetime | None
    window_type: str
    duration_seconds: int | None
    accounting_basis: str


class AdminUser(BaseModel):
    user_id: str
    name: str | None
    email: str
    created_at: datetime
    plan_id: str | None
    policy_revision: str | None
    entitlement_enabled: bool | None
    expires_at: datetime | None = None
    source: str | None = None
    entitlement_status: Literal['ready', 'abnormal', 'pending_initialization', 'expired', 'expiry_pending']
    model_calls_enabled: bool
    usage_windows: list[AdminUsageWindow]


class AdminUserStats(BaseModel):
    total_users: int
    free_users: int
    abnormal_users: int


class AdminUsersResponse(BaseModel):
    items: list[AdminUser]
    total: int
    page: int
    page_size: int
    stats: AdminUserStats
    plans: list[str]
    updated_at: datetime
    usage_status: Literal['near_realtime']
    usage_note: str
