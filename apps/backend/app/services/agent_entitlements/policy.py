"""Explicit, versioned policy inputs. There are no production quota defaults."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from agent_contracts.canonical import digest
from agent_contracts.v2 import ID, Units, Positive, V2, WindowRef, PermissionSnapshot


class EntitlementRule(V2):
    rule_id: ID
    metric: Literal['tokens', 'attempted_units', 'successful_units']
    unit: Literal['token', 'call', 'activation']
    capability_id: ID | None
    purpose: Literal['main', 'summary', 'tool', 'skill_activation', 'all']
    limit_units: Units
    reservation_units: Units
    call_upper_bound: Units
    accounting_basis: Literal['trusted_start', 'free']
    window_type: Literal['fixed', 'natural', 'rolling']
    duration_seconds: Positive | None
    timezone: ID | None
    anchor: AwareDatetime | None
    quota_pool: ID | None = None

    @model_validator(mode='after')
    def constraints(self):
        if self.accounting_basis == 'free' and any((self.limit_units, self.reservation_units, self.call_upper_bound)):
            raise ValueError('free rule must explicitly reserve and charge zero')
        if self.reservation_units > self.limit_units or self.call_upper_bound > self.reservation_units:
            raise ValueError('invalid reservation/call bound')
        if (self.metric == 'tokens') != (self.unit == 'token'):
            raise ValueError('metric and unit disagree')
        if self.window_type == 'natural':
            if self.timezone is None:
                raise ValueError('timezone required')
            ZoneInfo(self.timezone)
        elif self.duration_seconds is None:
            raise ValueError('duration required')
        if self.window_type == 'fixed' and self.anchor is None:
            raise ValueError('anchor required')
        return self

    def window(self, owner: str, revision: str, now: datetime) -> WindowRef:
        start = end = None
        if self.window_type == 'natural':
            local = now.astimezone(ZoneInfo(self.timezone))
            start = local.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif self.window_type == 'fixed':
            offset = int((now - self.anchor).total_seconds()) // self.duration_seconds
            start = self.anchor + timedelta(seconds=offset * self.duration_seconds)
            end = start + timedelta(seconds=self.duration_seconds)
        key = digest([owner, self.quota_pool or revision, self.rule_id, start, end])
        return WindowRef(schema_version=1, window_id=key, rule_revision=revision, window_type=self.window_type,
                         accounting_basis=self.accounting_basis, start=start, end=end,
                         duration_seconds=self.duration_seconds, timezone=self.timezone,
                         anchor=self.anchor, ledger_ref=key if self.window_type == 'rolling' else None)


class ModelBudgetProfile(V2):
    """Deployment-reviewed assumptions, never a tokenizer proof or plan quota."""
    input_basis: Literal['risk_assessed_utf8_v1']
    input_overhead_tokens: Positive
    # Explicit deployment risk assumption. Historical policies keep 1 byte per
    # Token; 2 reduces conservative over-reservation without changing the wire
    # measurement, the daily limit or the real-usage settlement.
    input_bytes_per_token: Literal[1, 2] = 1
    # Historical local window retained for Policy JSON compatibility. It is
    # not a verified model limit and no longer acts as a second input quota.
    # Real context limits, if known, come from the Worker model registry.
    context_window_tokens: Positive
    max_output_tokens: Positive
    output_limit_semantics: Literal['completion_including_reasoning']


class EntitlementPolicy(V2):
    reservation_mode: Literal['task_fixed', 'per_call'] = 'task_fixed'
    dynamic_model_budget: bool = False
    model_budget_profiles: dict[str, ModelBudgetProfile] = Field(default_factory=dict)
    policy_revision: ID
    plan_id: ID
    permission_snapshot: PermissionSnapshot
    rules: list[EntitlementRule] = Field(min_length=1)
    grant_ttl_seconds: Positive
    permit_ttl_seconds: Positive
    start_ttl_seconds: Positive
    conservative_clock_skew_ms: Units
    token_scope: Literal['prompt_plus_completion', 'prompt_only', 'completion_only']
    missing_usage_strategy: Literal['hold_and_reconcile']
    overage_strategy: Literal['record_and_block']
    unused_release_strategy: Literal['sealed_complete_only', 'disabled']
    model_risk_profile: ID | None
    disable_scope: Literal['new_submissions', 'every_start']
    emergency_scope: Literal['grant_root', 'grant_capability']

    @model_validator(mode='after')
    def policy_identity(self):
        if self.permission_snapshot.policy_revision != self.policy_revision:
            raise ValueError('permission policy revision mismatch')
        if len({r.rule_id for r in self.rules}) != len(self.rules):
            raise ValueError('duplicate rule identity')
        return self
