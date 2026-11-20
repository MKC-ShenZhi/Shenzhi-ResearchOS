"""Independent v2 candidate protocols. V1 wire models deliberately remain unchanged.

Nullable annotations have no defaults: absent and explicit null are different.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_serializer, field_validator, model_validator

from .canonical import SAFE_INTEGER, digest, request_digest_v1
from .wire import TaskSubmissionWire

ID = Annotated[str, Field(min_length=1, max_length=255)]
Digest = Annotated[str, Field(pattern=r'^sha256:[0-9a-f]{64}$')]
Units = Annotated[int, Field(strict=True, ge=0, le=SAFE_INTEGER)]
Positive = Annotated[int, Field(strict=True, ge=1, le=SAFE_INTEGER)]
Mode = Literal['authorized', 'observation_only']
Purpose = Literal['main', 'summary', 'tool', 'skill_activation']
Invocation = Literal['model_selected', 'forced', 'explicit_user', 'internal']
Metric = Literal['tokens', 'attempted_units', 'successful_units']
Unit = Literal['token', 'call', 'activation']


class V2(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1]

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('unsupported schema version')
        return value

    @field_serializer('*', when_used='json', check_fields=False)
    def serialize_utc(self, value):
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        return value


class ToolIdentity(V2):
    kind: Literal['tool']
    capability_id: ID
    implementation_build_digest: Digest
    parameter_schema_digest: Digest
    dependency_digests: list[Digest]


class SkillIdentity(V2):
    kind: Literal['skill']
    capability_id: ID
    resource_content_digest: Digest
    dependency_digests: list[Digest]


class ModelIdentity(V2):
    kind: Literal['model']
    capability_id: ID
    provider_id: ID
    registry_model_id: ID
    upstream_model: ID
    configuration_release_digest: Digest
    dependency_digests: list[Digest]


Identity = Annotated[ToolIdentity | SkillIdentity | ModelIdentity, Field(discriminator='kind')]


class CallIdentity(V2):
    agent_audience: ID
    task_id: ID
    run_id: ID
    execution_id: ID
    call_id: ID
    logical_call_id: ID
    metering_profile_id: ID
    metering_context: Mode
    submission_id_source: Literal['backend', 'agent_observation']
    submission_id: ID
    owner_id: ID
    control_attestation_id: ID
    started_at: AwareDatetime
    capability_id: ID
    capability_version: Digest
    capability_identity_profile: Literal['capability_identity_v1']
    capability_identity: Identity
    invocation_mode: Invocation
    purpose: Purpose
    parent_call_id: ID | None
    activation_id: ID | None
    grant_id: ID | None
    grant_revision: Positive | None
    reservation_id: ID | None
    permit_id: ID | None

    @model_validator(mode='after')
    def linkage(self):
        authorized = self.metering_context == 'authorized'
        if any((v is not None) != authorized for v in (
                self.grant_id, self.grant_revision, self.reservation_id, self.permit_id)):
            raise ValueError('mode and authorization linkage disagree')
        if self.submission_id_source != ('backend' if authorized else 'agent_observation'):
            raise ValueError('submission source disagrees with mode')
        if self.submission_id.startswith('obs:') == authorized:
            raise ValueError('submission namespace disagrees with mode')
        identity = self.capability_identity
        if identity.capability_id != self.capability_id or digest(identity.model_dump(mode='json')) != self.capability_version:
            raise ValueError('capability identity mismatch')
        if (identity.kind == 'skill') != (self.activation_id is not None):
            raise ValueError('activation identity required only for skill')
        expected = {'tool': {'tool'}, 'skill': {'skill_activation'}, 'model': {'main', 'summary'}}
        if self.purpose not in expected[identity.kind]:
            raise ValueError('capability purpose mismatch')
        return self


class CallStartFact(CallIdentity):
    fact_kind: Literal['started', 'activation']
    start_record_id: ID
    start_record_digest: Digest
    recorded_at: AwareDatetime

    def computed_digest(self) -> str:
        return digest(self.model_dump(mode='json', exclude={'start_record_digest'}))

    @model_validator(mode='after')
    def check_fact(self):
        if self.computed_digest() != self.start_record_digest:
            raise ValueError('start record digest mismatch')
        if (self.fact_kind == 'activation') != (self.activation_id is not None):
            raise ValueError('fact kind mismatch')
        return self


class UsageDelta(CallIdentity):
    measurement_id: ID
    observation_revision: Positive
    supersedes_measurement_id: ID | None
    logical_attempt: Positive
    transport_attempt: Positive
    provider_id: ID | None
    provider_request_id: ID | None
    phase: Literal['started', 'completed', 'activation']
    outcome: Literal['in_progress', 'succeeded', 'failed', 'timed_out', 'cancelled', 'unknown']
    prompt_tokens: Units | None
    completion_tokens: Units | None
    usage_status: Literal['measured', 'partial', 'unknown', 'estimated']
    usage_source: Literal['provider_usage', 'provider_reconciliation', 'local_estimate', 'not_applicable'] | None
    missing_reason: ID | None
    attempted_units: Units | None
    successful_units: Units | None
    ended_at: AwareDatetime | None
    observed_at: AwareDatetime
    task_usage_sequence: Positive

    @model_validator(mode='after')
    def observation(self):
        if (self.observation_revision == 1) != (self.supersedes_measurement_id is None):
            raise ValueError('invalid revision predecessor')
        tokens = (self.prompt_tokens, self.completion_tokens)
        is_model = self.capability_identity.kind == 'model'
        if is_model:
            if self.usage_status == 'measured' and (None in tokens or self.usage_source not in ('provider_usage', 'provider_reconciliation')):
                raise ValueError('measured requires complete evidence')
            if self.usage_status == 'unknown' and any(v is not None for v in tokens):
                raise ValueError('unknown must retain null tokens')
            if self.usage_status == 'partial' and not any(v is not None for v in tokens):
                raise ValueError('partial requires known evidence')
        elif any(v is not None for v in tokens) or self.usage_source != 'not_applicable':
            raise ValueError('nonmodel token usage is not applicable')
        if self.usage_status == 'estimated' and self.usage_source != 'local_estimate':
            raise ValueError('estimate source required')
        if self.successful_units is not None and (self.attempted_units is None or self.successful_units > self.attempted_units):
            raise ValueError('success exceeds attempts')
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError('end precedes start')
        return self


class UsageBatch(V2):
    batch_id: ID
    producer_id: ID
    items: Annotated[list[UsageDelta], Field(min_length=1, max_length=200)]


class UsageAck(V2):
    measurement_id: ID
    call_id: ID
    observation_revision: Positive
    disposition: Literal['accepted', 'duplicate', 'quarantined', 'rejected']
    durable: StrictBool
    applied_revision: Positive | None
    settlement_status: Literal['pending', 'settled', 'reconciliation_required', 'adjusted', 'not_applicable']
    reason_code: ID | None
    retryable: StrictBool
    retry_after_ms: Units | None
    missing_revisions: list[Positive]
    missing_sequences: list[Positive]


class UsageBatchAck(V2):
    batch_id: ID
    results: list[UsageAck]


class TaskMeteringBinding(V2):
    operation_id: ID
    metering_profile_id: ID
    agent_audience: ID
    task_id: ID
    owner_id: ID
    request_digest: Digest
    submission_id_source: Literal['backend', 'agent_observation']
    submission_id: ID


class TaskMeteringBindingReceipt(V2):
    metering_profile_id: ID
    task_id: ID
    metering_context: Mode
    submission_id_source: Literal['backend', 'agent_observation']
    submission_id: ID
    bound_at: AwareDatetime
    admission_revision: ID


class WindowRef(V2):
    window_id: ID
    rule_revision: ID
    window_type: Literal['fixed', 'natural', 'rolling']
    accounting_basis: ID
    start: AwareDatetime | None
    end: AwareDatetime | None
    duration_seconds: Positive | None
    timezone: ID | None
    anchor: AwareDatetime | None
    ledger_ref: ID | None

    @model_validator(mode='after')
    def bounds(self):
        if self.window_type == 'rolling':
            if self.duration_seconds is None or self.ledger_ref is None or self.start is not None or self.end is not None:
                raise ValueError('rolling window requires duration and ledger, not fixed bounds')
        elif self.start is None or self.end is None or self.end <= self.start:
            raise ValueError('fixed/natural window requires ordered bounds')
        if self.window_type == 'natural' and self.timezone is None:
            raise ValueError('natural window requires timezone')
        if self.window_type == 'fixed' and self.anchor is None:
            raise ValueError('fixed window requires anchor')
        return self


class CapabilityPermission(V2):
    capability_id: ID
    capability_version: Digest
    invocation_modes: Annotated[list[Invocation], Field(min_length=1)]
    purposes: Annotated[list[Purpose], Field(min_length=1)]
    max_attempts: Units | None
    dependency_versions: dict[ID, Digest]


class PermissionSnapshot(V2):
    permission_snapshot_id: ID
    policy_revision: ID
    catalog_revision: ID
    capabilities: list[CapabilityPermission]


class Allocation(V2):
    allocation_id: ID
    rule_id: ID
    metric: Metric
    unit: Unit
    scope: Literal['owner_window', 'capability_window']
    capability_id: ID | None
    purpose: Literal['main', 'summary', 'tool', 'skill_activation', 'all']
    reserved_units: Units
    window_ref: WindowRef

    @model_validator(mode='after')
    def dimensions(self):
        if (self.scope == 'capability_window') != (self.capability_id is not None):
            raise ValueError('scope requires explicit capability linkage')
        if (self.metric == 'tokens') != (self.unit == 'token'):
            raise ValueError('metric/unit mismatch')
        return self


class Signature(V2):
    kid: ID
    alg: Literal['EdDSA']
    compact_jws: Annotated[str, Field(min_length=1)]


class BudgetGrant(V2):
    grant_id: ID
    reservation_id: ID
    revision: Positive
    issuer: ID
    audience: ID
    owner_id: ID
    submission_id: ID
    task_id: ID | None
    binding_receipt_id: ID | None
    request_digest: Digest
    digest_profile: Literal['canonical_json_v1']
    policy_revision: ID
    catalog_revision: ID
    permission_snapshot_id: ID
    permission_snapshot_digest: Digest
    issued_at: AwareDatetime
    not_before: AwareDatetime
    expires_at: AwareDatetime
    capabilities: list[CapabilityPermission]
    allocations: Annotated[list[Allocation], Field(min_length=1)]
    execution_constraints: dict[str, str | int]
    signature: Signature

    @model_validator(mode='after')
    def validity(self):
        if (self.task_id is None) != (self.binding_receipt_id is None):
            raise ValueError('binding pair required')
        if self.submission_id.startswith('obs:') or self.expires_at <= self.not_before:
            raise ValueError('invalid grant identity/validity')
        if len({a.allocation_id for a in self.allocations}) != len(self.allocations):
            raise ValueError('duplicate allocation')
        return self


class GrantBindingReceipt(V2):
    receipt_id: ID
    issuer: ID
    audience: ID
    grant_id: ID
    grant_revision: Positive
    grant_payload_digest: Digest
    reservation_id: ID
    owner_id: ID
    submission_id: ID
    bound_task_id: ID
    request_digest: Digest
    bound_at: AwareDatetime
    binding_revision: Literal[1]
    signature: Signature

    @field_validator('binding_revision', mode='before')
    @classmethod
    def strict_binding_revision(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('unsupported binding revision')
        return value


class RequestedAllocation(V2):
    allocation_id: ID
    metric: Metric
    unit: Unit
    upper_bound_units: Units


class ModelCallBudgetRequest(V2):
    """Measured bytes are NOT a proven Token bound; risk approval is mandatory."""
    basis: Literal['risk_assessed_utf8_v1']
    input_bytes: Units
    requested_output_tokens: Positive
    model_max_output_tokens: Positive
    model_context_window: Positive | None


class ModelCallBudgetApproval(V2):
    basis: Literal['risk_assessed_utf8_v1']
    input_tokens: Units
    output_tokens: Positive
    reserved_tokens: Positive

    @model_validator(mode='after')
    def total(self):
        if self.reserved_tokens != self.input_tokens + self.output_tokens:
            raise ValueError('model budget total mismatch')
        return self


class CallPermitRequest(V2):
    model_budget: ModelCallBudgetRequest | None = Field(default=None, exclude_if=lambda v: v is None)
    call_id: ID
    logical_call_id: ID
    request_digest: Digest
    grant_id: ID
    grant_revision: Positive
    reservation_id: ID
    binding_receipt_id: ID
    owner_id: ID
    submission_id: ID
    task_id: ID
    run_id: ID
    execution_id: ID
    control_attestation_id: ID
    capability_id: ID
    capability_version: Digest
    invocation_mode: Invocation
    purpose: Purpose
    requested_allocations: Annotated[list[RequestedAllocation], Field(min_length=1)]
    input_bound_evidence_ref: ID | None
    output_bound_evidence_ref: ID | None
    risk_profile: ID | None


class PermitStart(V2):
    start_operation_id: ID
    execution_id: ID
    control_attestation_id: ID


class PermitAllocation(Allocation):
    held_units: Units


class CallPermit(V2):
    model_budget: ModelCallBudgetApproval | None = Field(default=None, exclude_if=lambda v: v is None)
    permit_id: ID
    call_id: ID
    status: Literal['authorized', 'start_committed', 'completed', 'unknown', 'void', 'expired']
    grant_id: ID
    grant_revision: Positive
    owner_id: ID
    submission_id: ID
    task_id: ID
    run_id: ID
    execution_id: ID
    capability_id: ID
    capability_version: Digest
    invocation_mode: Invocation
    purpose: Purpose
    policy_revision: ID
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    start_before: AwareDatetime
    allocations: Annotated[list[PermitAllocation], Field(min_length=1)]

    @model_validator(mode='after')
    def cutoff(self):
        if self.start_before > self.expires_at or any(
                a.window_ref.end is not None and self.start_before > a.window_ref.end for a in self.allocations):
            raise ValueError('permit exceeds its time window')
        return self


class CallPermitResponse(V2):
    call_id: ID
    request_digest: Digest
    decision: Literal['authorized', 'denied']
    reason_code: ID | None
    retryable: StrictBool
    current_grant_revision: Positive
    permit: CallPermit | None

    @model_validator(mode='after')
    def decision_linkage(self):
        if (self.decision == 'authorized') != (self.permit is not None):
            raise ValueError('permit decision mismatch')
        if self.permit and self.permit.call_id != self.call_id:
            raise ValueError('permit call mismatch')
        return self


class VoidProof(V2):
    void_operation_id: ID
    permit_id: ID
    call_id: ID
    execution_id: ID
    control_attestation_id: ID
    sealed_intent_revision: Positive
    sealed_at: AwareDatetime
    start_operation_id: ID | None
    backend_start_authorization_id: ID | None
    local_started_record_absent: Literal[True]
    local_start_receipt_never_issued: Literal[True]
    reason_code: ID

    @field_validator('local_started_record_absent', 'local_start_receipt_never_issued', mode='before')
    @classmethod
    def strict_proof(cls, value):
        if value is not True:
            raise ValueError('strict true proof required')
        return value


class TaskSubmissionV2(V2):
    metering_profile_id: ID
    metering_context: Mode
    agent_audience: ID
    owner_id: ID
    request_digest: Digest
    submission_id: ID | None
    budget_grant: BudgetGrant | None
    permission_snapshot: PermissionSnapshot | None
    call_bounds: dict[ID, Units]
    request: TaskSubmissionWire

    @model_validator(mode='after')
    def submission(self):
        if self.owner_id != self.request.owner_id or request_digest_v1(self.request.model_dump(mode='json')) != self.request_digest:
            raise ValueError('business request identity mismatch')
        if self.metering_context == 'authorized':
            if self.budget_grant is None or self.submission_id is None or self.permission_snapshot is None:
                raise ValueError('authorized submission requires grant and snapshot')
            g = self.budget_grant
            if (g.owner_id, g.submission_id, g.audience, g.request_digest) != (self.owner_id, self.submission_id, self.agent_audience, self.request_digest):
                raise ValueError('grant submission mismatch')
            if digest(self.permission_snapshot.model_dump(mode='json')) != g.permission_snapshot_digest:
                raise ValueError('permission snapshot digest mismatch')
            snapshot = self.permission_snapshot
            if (snapshot.permission_snapshot_id, snapshot.policy_revision, snapshot.catalog_revision) != (
                    g.permission_snapshot_id, g.policy_revision, g.catalog_revision):
                raise ValueError('permission snapshot reference mismatch')
            for permission in g.capabilities:
                base = next((p for p in snapshot.capabilities if (p.capability_id, p.capability_version) ==
                             (permission.capability_id, permission.capability_version)), None)
                if (base is None or not set(permission.invocation_modes) <= set(base.invocation_modes)
                        or not set(permission.purposes) <= set(base.purposes)
                        or permission.dependency_versions != base.dependency_versions
                        or base.max_attempts is not None and (permission.max_attempts is None or permission.max_attempts > base.max_attempts)):
                    raise ValueError('grant exceeds permission snapshot')
        elif self.budget_grant is not None or self.submission_id is not None or self.permission_snapshot is not None or self.call_bounds:
            raise ValueError('observation mode cannot carry authorization')
        return self


class TaskCloseManifest(V2):
    manifest_id: ID
    agent_audience: ID
    owner_id: ID
    submission_id: ID
    grant_id: ID
    task_id: ID
    run_ids: list[ID]
    execution_ids: list[ID]
    call_ids: list[ID]
    permit_ids: list[ID]
    call_count: Units
    last_task_usage_sequence: Units
    outbox_ack_high_watermark: Units
    missing_sequences: list[Positive]
    unknown_call_ids: list[ID]
    all_executions_sealed: StrictBool
    no_startable_permits: StrictBool
    closed_at: AwareDatetime


class ErrorV2(V2):
    code: int
    message: str
    reason_code: ID
    retryable: StrictBool
    request_id: ID
    retry_after_ms: Units | None
