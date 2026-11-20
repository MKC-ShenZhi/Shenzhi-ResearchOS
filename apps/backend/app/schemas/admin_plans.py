from typing import Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.services.agent_entitlements.policy import EntitlementPolicy


class AdminWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_id: str = Field(min_length=8, max_length=180)
    reason: str = Field(min_length=1, max_length=255)
    approval_ref: str | None = Field(default=None, max_length=255)


class PublishPlans(AdminWrite):
    policies: list[EntitlementPolicy] = Field(min_length=3, max_length=3)
    capabilities: dict[str, Any]
    risk_approval_ref: str | None = Field(default=None, max_length=255)


class AssignPlans(AdminWrite):
    user_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal['assign', 'disable', 'restore'] = 'assign'
    plan_id: Literal['basic','pro','research'] | None = None
    policy_revision: str | None = Field(default=None, max_length=255)
    initialize_only: bool = False
    preview: bool = True


class MigrationPreview(BaseModel):
    before: datetime
    limit: int = Field(default=100, ge=1, le=100)


class ReconcileGrant(AdminWrite):
    evidence_ref: str = Field(min_length=1, max_length=255)
    preview: bool = True
