"""Versioned HTTP wire schemas shared by Backend and Agent Platform."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .runs import RunStatus


class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class BudgetLimitsWire(WireModel):
    max_duration_s: float | None = Field(default=None, gt=0)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_model_tokens: int | None = Field(default=None, ge=0)


class AgentConfigWire(WireModel):
    models: list[dict[str, Any]] = Field(default_factory=list)
    default_model: str | None = None
    skills: list[dict[str, str]] = Field(default_factory=list)


class OwnerQueryWire(WireModel):
    owner_id: str = Field(min_length=1, max_length=255)


class RunEventsQueryWire(OwnerQueryWire):
    after_seq: int = Field(default=0, ge=0)


class SessionFileReadRequestWire(OwnerQueryWire):
    path: str = Field(min_length=1, max_length=2_000)


class WorkspaceCreateRequestWire(WireModel):
    owner_id: str = Field(min_length=1, max_length=255)


class WorkspaceCreateResponseWire(WireModel):
    workspace_id: str = Field(min_length=12, max_length=12)


class WorkspaceClaimRequestWire(WireModel):
    source_owner: str = Field(min_length=1, max_length=255)
    target_owner: str = Field(min_length=1, max_length=255)
    session_ids: list[str] = Field(default_factory=list, max_length=500)


class WorkspaceClaimPrepareResponseWire(WireModel):
    prepared_session_ids: list[str] = Field(default_factory=list)


class WorkspaceClaimCommitResponseWire(WireModel):
    cleaned_session_ids: list[str] = Field(default_factory=list)
    moved_workspaces: int = Field(default=0, ge=0)


class WorkspaceFileWriteRequestWire(WireModel):
    owner_id: str = Field(min_length=1, max_length=255)
    workspace_id: str = Field(min_length=12, max_length=12)
    path: str = Field(min_length=1, max_length=2_000)
    content_base64: str = Field(max_length=25_000_000)


class WorkspaceFileWriteResponseWire(WireModel):
    path: str
    size: int = Field(ge=0)


class SessionFileReadResponseWire(WireModel):
    content_base64: str
    media_type: str = Field(min_length=1, max_length=255)


class RunSteerRequestWire(WireModel):
    owner_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=20_000)


class RunSteerResponseWire(WireModel):
    run_id: str
    seq: int = Field(ge=1)
    name: str


class TaskSubmissionWire(WireModel):
    owner_id: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=100_000)
    session_id: str | None = Field(default=None, max_length=255)
    turn_id: str | None = Field(default=None, max_length=255)
    input_ref: str | None = Field(default=None, max_length=2_048)
    idempotency_key: str | None = Field(default=None, max_length=255)
    mode: str = Field(default='fast', min_length=1, max_length=40)
    model: str | None = Field(default=None, max_length=255)
    workspace_id: str | None = Field(default=None, max_length=255)
    skills: list[str] = Field(default_factory=list, max_length=100)
    budget: BudgetLimitsWire = Field(default_factory=BudgetLimitsWire)
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=200)

    @field_validator('owner_id', 'prompt')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('value must not be blank')
        return value

    @model_validator(mode='after')
    def linked_session_turn(self):
        if (self.session_id is None) != (self.turn_id is None):
            raise ValueError('session_id and turn_id must be provided together')
        return self


class TaskRecordWire(WireModel):
    task_id: str
    owner_id: str
    session_id: str | None
    turn_id: str | None
    status: str
    current_run_id: str | None
    cancel_requested: bool = False
    created_at: datetime


class RunRecordWire(WireModel):
    run_id: str
    task_id: str
    attempt: int = Field(ge=1)
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report: ExecutionReportWire | None = None
    task_status: str


class PlatformEventWire(WireModel):
    task_id: str
    run_id: str
    seq: int = Field(gt=0)
    turn: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    data: dict[str, Any]
    occurred_at: datetime


class UsageReportWire(WireModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    tool_calls: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


class ExecutionReportWire(WireModel):
    run_id: str
    task_id: str
    status: RunStatus
    result: dict[str, Any] | None = None
    usage: UsageReportWire = Field(default_factory=UsageReportWire)
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode='after')
    def terminal_status(self):
        if self.status in (RunStatus.PENDING, RunStatus.RUNNING):
            raise ValueError('execution report requires a terminal status')
        return self


class EventIngestWire(PlatformEventWire):
    worker_id: str
    lease_token: int = Field(gt=0)


class ReportIngestWire(ExecutionReportWire):
    worker_id: str
    lease_token: int = Field(gt=0)
