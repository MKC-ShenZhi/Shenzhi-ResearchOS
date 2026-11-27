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


class States(Wire):
    registered: Evidence = Field(default_factory=Evidence)
    configured: Evidence = Field(default_factory=Evidence)
    loaded: Evidence = Field(default_factory=Evidence)


class Provider(Wire):
    provider_id: Key
    protocol: str
    base_url: str | None
    credential_present: bool
    enabled: bool
    model_ids: list[str]
    states: States


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
    description: str
    request_params: dict
    capabilities: ModelCapabilities
    default_purposes: list[Literal['agent', 'chat']]
    enabled: bool
    config_revision: str | None
    capability_version: str | None
    states: States


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
    dependencies: list[str] | None = None
    metadata: dict | None = None
    resources: list[Resource] = Field(max_length=100)
    states: States


class Document(Wire):
    name: Key
    resource_digest: Key
    render_safe_markdown: str = Field(max_length=65_536)


class Pagination(Wire):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=1024)


class CatalogQuery(Pagination):
    search: str = Field(default='', max_length=100)
    order: Literal['asc', 'desc'] = 'asc'
