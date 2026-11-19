"""Worker-Control envelopes. Lease tokens stay inside this service boundary."""
from typing import Literal
from pydantic import AwareDatetime, model_validator, field_validator
from .wire import EventIngestWire, ReportIngestWire, RunSteerRequestWire

from .v2 import ID, Digest, Identity, Invocation, Positive, Purpose, Units, V2, CallPermitRequest


class WorkerIdentity(V2):
    worker_id: ID
    lease_token: Positive
    execution_id: ID


class CallIntent(WorkerIdentity):
    call_id: ID
    logical_call_id: ID
    capability_identity: Identity
    invocation_mode: Invocation
    purpose: Purpose
    parent_call_id: ID | None
    activation_id: ID | None
    logical_attempt: Positive
    transport_attempt: Positive
    provider_id: ID | None
    request_digest: Digest
    input_bound_evidence_ref: ID | None
    output_bound_evidence_ref: ID | None
    risk_profile: ID | None


class ObservationSubmission(WorkerIdentity):
    observation_submission_id: ID
    call_id: ID
    outcome: Literal['in_progress', 'succeeded', 'failed', 'timed_out', 'cancelled', 'unknown']
    prompt_tokens: Units | None
    completion_tokens: Units | None
    usage_status: Literal['measured', 'partial', 'unknown', 'estimated']
    usage_source: Literal['provider_usage', 'provider_reconciliation', 'local_estimate', 'not_applicable'] | None
    missing_reason: ID | None
    attempted_units: Units | None
    successful_units: Units | None
    provider_request_id: ID | None
    ended_at: AwareDatetime | None


class GrantBindRequest(V2):
    task_id: ID
    owner_id: ID
    submission_id: ID
    request_digest: Digest
    expected_revision: Positive
    expected_binding_revision: Units


class EventIngestV2(EventIngestWire):
    schema_version: Literal[1]
    execution_id: ID


class ReportIngestV2(ReportIngestWire):
    schema_version: Literal[1]
    execution_id: ID


class RunSteerV2(RunSteerRequestWire):
    schema_version: Literal[1]


class AbandonCall(V2):
    request: CallPermitRequest
    void_operation_id: ID
    sealed_intent_revision: Positive
    sealed_at: AwareDatetime
    local_started_record_absent: Literal[True]
    local_start_receipt_never_issued: Literal[True]
    start_operation_id: None
    reason_code: ID

    @field_validator('local_started_record_absent', 'local_start_receipt_never_issued', mode='before')
    @classmethod
    def strict_proof(cls, value):
        if value is not True:
            raise ValueError('strict true proof required')
        return value


class GrantRevocation(V2):
    operation_id: ID
    submission_id: ID
    reason_code: ID
    capability_id: ID | None
    capability_version: Digest | None

    @model_validator(mode='after')
    def scope(self):
        if (self.capability_id is None) != (self.capability_version is None):
            raise ValueError('exact revocation version required')
        return self
