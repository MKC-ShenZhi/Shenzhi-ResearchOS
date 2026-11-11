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

    @field_validator('history')
    @classmethod
    def valid_history(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return validate_history(value)

    @model_validator(mode='after')
    def linked_session_turn(self):
        if (self.session_id is None) != (self.turn_id is None):
            raise ValueError('session_id and turn_id must be provided together')
        return self


def validate_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate the durable Agent transcript shape before it crosses a service boundary."""
    stop_reasons = {
        'stop', 'length', 'tool_calls', 'max_turns', 'error', 'cancelled',
        'timeout', 'awaiting_input',
    }
    for index, message in enumerate(history):
        if not isinstance(message, dict):
            raise ValueError(f'history[{index}] must be an object')
        kind = message.get('kind')
        if kind == 'user':
            if not isinstance(message.get('text'), str):
                raise ValueError(f'history[{index}].text must be a string')
        elif kind == 'assistant':
            for field in ('content', 'reasoning'):
                if field in message and not isinstance(message[field], str):
                    raise ValueError(f'history[{index}].{field} must be a string')
            reason = message.get('stop_reason', 'stop')
            if not isinstance(reason, str) or reason not in stop_reasons:
                raise ValueError(f'history[{index}].stop_reason is invalid')
            calls = message.get('tool_calls', [])
            if not isinstance(calls, list):
                raise ValueError(f'history[{index}].tool_calls must be a list')
            for call_index, call in enumerate(calls):
                if (not isinstance(call, dict)
                        or not isinstance(call.get('call_id'), str)
                        or not isinstance(call.get('name'), str)
                        or not isinstance(call.get('arguments', {}), (dict, str))):
                    raise ValueError(f'history[{index}].tool_calls[{call_index}] is invalid')
            usage = message.get('usage_tokens', 0)
            if isinstance(usage, bool) or not isinstance(usage, int) or usage < 0:
                raise ValueError(f'history[{index}].usage_tokens must be a non-negative integer')
        elif kind == 'tool':
            if any(not isinstance(message.get(field), str)
                   for field in ('call_id', 'name', 'content')):
                raise ValueError(f'history[{index}] tool result is invalid')
            if any(field in message and not isinstance(message[field], bool)
                   for field in ('is_error', 'pinned')):
                raise ValueError(f'history[{index}] tool result flags must be booleans')
        else:
            raise ValueError(f'history[{index}].kind is invalid')
    return history


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
