"""Allow-listed, read-only Agent management wire projections."""
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Key = Annotated[str, StringConstraints(min_length=1, max_length=255)]
State = Literal['yes', 'no', 'unknown', 'not_applicable']
T = TypeVar('T')


class Wire(BaseModel):
    model_config = ConfigDict(extra='ignore')


class Result(Wire, Generic[T]):
    schema_version: Literal[1]
    data: T


class Page(Wire, Generic[T]):
    items: list[T] = Field(max_length=100)
    next_cursor: str | None = None
    observed_at: datetime


class Evidence(Wire):
    state: State = 'unknown'
    source: str | None = None
    observed_at: datetime | None = None
    config_revision: str | None = None
    worker_id: str | None = None


class States(Wire):
    registered: Evidence = Field(default_factory=Evidence)
    configured: Evidence = Field(default_factory=Evidence)
    loaded: Evidence = Field(default_factory=Evidence)
    deployed: Evidence = Field(default_factory=Evidence)
    reachable: Evidence = Field(default_factory=Evidence)
    healthy: Evidence = Field(default_factory=Evidence)
    authorized: Evidence = Field(default_factory=Evidence)


class Snapshot(Wire):
    status: Literal['ok', 'degraded', 'unavailable', 'unknown']
    observed_at: datetime
    source: str
    reason_code: str | None = None


class Api(Snapshot):
    build_revision: str | None = None
    response_ms: int | None = None


class Workspace(Snapshot):
    readable: State = 'unknown'
    writable: State = 'unknown'


class Execution(Wire):
    execution_id: Key
    worker_id: Key
    sealed: bool


class Run(Wire):
    run_id: Key
    task_id: Key
    attempt: int
    status: str
    worker_id: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    lease_status: Literal['active', 'expired', 'unknown', 'not_applicable']
    error_code: str | None
    execution: Execution | None = None
    executions: list[Execution] = Field(default_factory=list, max_length=100)
    executions_truncated: bool = False


class Worker(Wire):
    worker_id: Key
    latest_run: Run
    last_activity: datetime
    active_executions: int
    expired_leases: int
    state: Literal['lease_observed', 'unknown']


class Runtime(Snapshot):
    runs: list[Run] = Field(default_factory=list, max_length=20)


class Counts(Snapshot):
    window_start: datetime
    window_end: datetime
    queued_tasks: int | None = None
    running_runs: int | None = None
    failed_tasks: int | None = None
    expired_leases: int | None = None
    recent_failures: list[Run] = Field(default_factory=list, max_length=10)


class Overview(Wire):
    api: Api
    agent_db: Snapshot
    backend_db: Snapshot | None = None
    workspace: Workspace
    runtime: Runtime
    workers: Snapshot
    counts: Counts


class ModelObservation(Wire):
    model_id: Key
    capability_version: Key
    observed_at: datetime
    outcome: Literal['succeeded', 'failed', 'timed_out', 'cancelled', 'unknown']
    source: Literal['agent_usage_observation'] = 'agent_usage_observation'


class Provider(Wire):
    provider_id: Key
    protocol: str
    base_url: str | None
    credential_present: bool
    enabled: bool
    model_ids: list[str]
    states: States
    latest_observation: ModelObservation | None = None


class ModelCapabilities(Wire):
    chat: bool
    streaming: bool
    tool_calling: bool
    reasoning: bool
    temperature: bool
    thinking: str
    stream_options: bool
    chat_max_tokens: int
    agent_max_tokens: int
    max_output_tokens: int
    context_window_tokens: int | None = None


class Model(Wire):
    model_id: Key
    provider_id: Key
    upstream_model_id: Key
    label: str
    brand: str
    capabilities: ModelCapabilities
    default_purposes: list[Literal['agent', 'chat']]
    enabled: bool
    config_revision: str | None
    capability_version: str | None
    states: States
    latest_observation: ModelObservation | None = None


class Call(Wire):
    call_id: Key
    run_id: Key
    execution_id: Key
    kind: Literal['model', 'tool', 'skill', 'unknown']
    capability_id: str | None
    capability_version: str | None
    status: str
    started_at: datetime | None
    duration_ms: int | None
    usage_status: Literal['measured', 'partial', 'unknown', 'unsettled', 'estimated', 'not_applicable']
    known_tokens: int | None
    failure_reason: str | None = None


class Tool(Wire):
    tool_id: Key
    name: str
    description: str
    source: str
    parameters_schema: dict | None
    schema_digest: str | None
    capability_version: str | None
    conditions: list[str]
    registration: Literal['base', 'conditional', 'observed_only']
    latent: State = 'unknown'
    run_callable: State = 'unknown'
    latest_call: Call | None = None
    runtime_evidence: dict | None = None
    states: States


class Resource(Wire):
    name: str
    kind: Literal['reference', 'script']
    size: int


class Skill(Wire):
    name: Key
    description: str
    source: Literal['builtin', 'vendor', 'unknown']
    configuration_source: str | None = None
    resource_digest: str | None
    integrity: State
    discovered: State
    activated: State
    executable: State
    dependency_healthy: State
    dependencies: list[str] | None = None
    metadata: dict | None = None
    activation_contexts: list[dict] = Field(default_factory=list, max_length=20)
    resources: list[Resource] = Field(max_length=100)
    states: States


class Document(Wire):
    name: Key
    resource_digest: Key
    render_safe_markdown: str = Field(max_length=65_536)


class Usage(Wire):
    status: Literal['measured', 'partial', 'unknown', 'unsettled', 'estimated', 'not_applicable']
    measured_tokens: int | None = None
    known_tokens: int | None = None
    accounted_tokens: int | None = None
    held_tokens: int | None = None
    settlement_status: str | None = None


class Task(Wire):
    cancel_requested: bool | None = None
    task_id: Key
    owner_id: Key
    mode: str | None
    requested_model: str | None
    status: str
    created_at: datetime
    latest_run: Run | None
    error_code: str | None
    observed_usage: Usage | None = None
    backend_usage: Usage | None = None
    execution_config_revision: str | None = None
    execution_wait_reason: str | None = None


class Event(Wire):
    seq: int
    turn: int
    name: str
    occurred_at: datetime


class Pagination(Wire):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=1024)


class CatalogQuery(Pagination):
    search: str = Field(default='', max_length=100)
    policy_revision: Key | None = None
    order: Literal['asc', 'desc'] = 'asc'


class TaskQuery(Pagination):
    task_id: Key | None = None
    run_id: Key | None = None
    user_id: Key | None = None
    worker_id: Key | None = None
    status: Key | None = None
    model_id: Key | None = None
    tool_id: Key | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    order: Literal['asc', 'desc'] = 'desc'


class EventQuery(Pagination):
    after_seq: int | None = Field(default=None, ge=0)


class CallQuery(Pagination):
    kind: Literal['model', 'tool', 'skill'] | None = None
