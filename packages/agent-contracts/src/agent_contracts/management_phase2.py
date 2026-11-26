"""Explicit wire contracts for Worker evidence, active checks, and audit."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from .management import Key, Wire

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9][A-Za-z0-9_./:@+-]*$')]
Revision = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:+-]+$')]
Target = Literal['provider', 'model', 'tool', 'skill']
DiagnosticTarget = Literal['worker', 'provider', 'model', 'tool', 'skill', 'task', 'run']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Capability(Strict):
    kind: Target
    id: Identifier
    version: Revision | None = None
    scope: Literal['loaded', 'base', 'conditional']
    conditions: list[Literal['non_fast', 'workspace_or_session', 'nonempty_skill_store']] = Field(default_factory=list, max_length=3)


class WorkerManifest(Strict):
    config_digest: Revision | None = None
    registry_digest: Revision | None = None
    build_revision: Revision | None = None
    config_revision: Revision | None = None
    runtime_version: Revision
    capabilities: list[Capability] = Field(max_length=512)


class WorkerReport(Strict):
    instance_id: UUID
    sequence: int = Field(ge=1, le=2_147_483_647)
    started_at: AwareDatetime
    lifecycle: Literal['running', 'offline']
    health: Literal['ok', 'degraded', 'unknown']
    active_run_id: Identifier | None = None
    run_tool_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    manifest_digest: Revision | None = None
    manifest: WorkerManifest | None = None


class WorkerSnapshot(Wire):
    worker_id: Identifier
    instance_id: UUID
    started_at: AwareDatetime
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    age_seconds: int
    state: Literal['online', 'stale', 'offline']
    health: Literal['ok', 'degraded', 'unknown']
    active_run_id: Identifier | None
    run_tool_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    manifest_digest: Revision | None
    manifest: WorkerManifest | None
    capability_count: int


class ManifestEvidence(Wire):
    digest: Revision
    last_seen: AwareDatetime
    config_revision: Revision | None = None
    build_revision: Revision | None = None
    capability_count: int


class CapabilityEvidence(Wire):
    worker_id: Identifier
    state: Literal['online', 'stale', 'offline']
    observed_at: AwareDatetime
    manifest_digest: Revision | None
    config_revision: Revision | None
    capability: Capability | None


class ProbeRequest(Strict):
    kind: Target
    target_id: Identifier
    profile: Literal['static', 'network', 'completion', 'streaming', 'tool_calling'] = 'static'


class StartProbe(ProbeRequest):
    operation_id: UUID


class DiagnosticRequest(Strict):
    operation_id: UUID
    kind: DiagnosticTarget
    target_id: Identifier


class CheckStep(Wire):
    name: Revision
    state: Literal['pass', 'fail', 'unknown', 'unsupported']
    reason: Revision | None = None


class ProbeResult(Wire):
    kind: Target
    target_id: Identifier
    profile: Literal['static', 'network', 'completion', 'streaming', 'tool_calling']
    state: Literal['pass', 'fail', 'unknown', 'unsupported']
    reason: Revision
    source: Literal['agent_api'] = 'agent_api'
    instance_id: Revision
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    duration_ms: int
    build_revision: Revision | None = None
    config_revision: Revision | None = None
    capability_version: Revision | None = None
    budget_tokens: int = 0
    steps: list[CheckStep] = Field(default_factory=list, max_length=30)


class DiagnosticResult(Wire):
    kind: DiagnosticTarget
    target_id: Identifier
    source: Revision
    observed_at: AwareDatetime
    reason: Revision
    worker_id: Identifier | None = None
    run_id: Identifier | None = None
    call_id: Identifier | None = None
    build_revision: Revision | None = None
    config_revision: Revision | None = None
    occurred_at: AwareDatetime | None = None


class AuditEntry(Wire):
    audit_id: UUID
    request_id: UUID
    principal: Key
    action: Literal['check', 'diagnose', 'diagnostic_view', 'config']
    target_kind: DiagnosticTarget | Literal['config']
    target_id: Identifier
    created_at: AwareDatetime
    state: Literal['pending', 'pass', 'fail', 'unknown', 'unsupported']
    reason: Revision | None = None
    source: Literal['admin_console'] = 'admin_console'
    check: ProbeResult | None = None
    diagnostic: DiagnosticResult | None = None
    config_event: dict | None = None
