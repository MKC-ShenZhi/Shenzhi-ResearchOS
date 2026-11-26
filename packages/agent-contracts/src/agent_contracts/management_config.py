"""Immutable configuration and release contracts, independent of entitlement wire types."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_serializer, model_validator

from .canonical import digest
from .management_phase2 import Identifier, Revision, Strict

Hash = Annotated[str, StringConstraints(pattern=r'^sha256:[a-f0-9]{64}$')]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
SecretRef = Annotated[str, StringConstraints(pattern=r'^AGENT_PROVIDER_SECRET_[A-Z0-9_]{1,50}$')]


class ProviderConfigSpec(Strict):
    provider_id: Identifier
    protocol: Literal['openai_chat_completions'] = 'openai_chat_completions'
    base_url: str = Field(max_length=512)
    secret_ref: SecretRef
    enabled: bool = True

    @field_validator('base_url')
    @classmethod
    def endpoint(cls, value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)
                or '\\' in value or any(c.isspace() for c in value)):
            raise ValueError('HTTPS provider URL without credentials, query, or fragment required')
        return value.rstrip('/')


class Capabilities(Strict):
    chat: bool = True
    streaming: bool = True
    tool_calling: bool = False
    reasoning: bool = False
    temperature: bool = True
    thinking: Literal['none', 'enable_thinking', 'thinking'] = 'none'
    stream_options: bool = False
    chat_max_tokens: int = Field(default=4096, gt=0, le=10**7)
    agent_max_tokens: int = Field(default=32768, gt=0, le=10**7)
    max_output_tokens: int = Field(default=4096, gt=0, le=10**7)
    context_window_tokens: int | None = Field(default=None, gt=0, le=10**8)


class ModelConfigSpec(Strict):
    model_id: Identifier
    provider_id: Identifier
    upstream_model_id: Identifier
    label: Note
    brand: Identifier = 'platform'
    enabled: bool = True
    capabilities: Capabilities = Field(default_factory=Capabilities)
    thinking_enabled: bool | None = None


class Artifact(Strict):
    id: Identifier
    digest: Hash
    implementation_digest: Hash | None = None
    metadata_digest: Hash | None = None

    @model_serializer(mode='wrap')
    def serialize_metadata(self, serializer):
        fields = serializer(self)
        if self.metadata_digest is None:
            fields.pop('metadata_digest', None)
        return fields


class ConfigSpec(Strict):
    schema_version: Literal[1] = 1
    build_revision: Revision
    runtime_version: Revision
    providers: list[ProviderConfigSpec] = Field(min_length=1, max_length=30)
    models: list[ModelConfigSpec] = Field(min_length=1, max_length=120)
    defaults: dict[Literal['agent', 'chat'], Identifier] = Field(default_factory=dict)
    tools: list[Artifact] = Field(default_factory=list, max_length=200)
    skills: list[Artifact] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def references(self):
        providers = {p.provider_id: p for p in self.providers}
        models = {m.model_id: m for m in self.models}
        if len(providers) != len(self.providers) or len(models) != len(self.models):
            raise ValueError('duplicate Provider or Model')
        if any(m.provider_id not in providers or m.model_id == 'default' for m in self.models):
            raise ValueError('invalid Model reference')
        for purpose, model_id in self.defaults.items():
            m = models.get(model_id)
            if (not m or not m.enabled or not providers[m.provider_id].enabled or not m.capabilities.chat
                    or not m.capabilities.streaming or (purpose == 'agent' and not m.capabilities.tool_calling)):
                raise ValueError('invalid default Model')
        for items, prefix in ((self.tools, 'tool:'), (self.skills, 'skill:')):
            if len({item.id for item in items}) != len(items) or any(not item.id.startswith(prefix) for item in items):
                raise ValueError('invalid or duplicate artifact')
        return self

    def normalized(self):
        value = self.model_dump(mode='json')
        for name, key in [('providers', 'provider_id'), ('models', 'model_id'), ('tools', 'id'), ('skills', 'id')]:
            value[name] = sorted(value[name], key=lambda item: item[key])
        return value

    @property
    def config_digest(self):
        return digest(self.normalized())


class CapabilityVersion(Strict):
    id: Identifier
    version: Hash


class Candidate(Strict):
    operation_id: UUID
    base_revision: UUID | None
    reason: Note
    spec: ConfigSpec


class Proof(Strict):
    revision_id: UUID
    config_digest: Hash
    build_revision: Revision
    runtime_version: Revision
    observed_at: AwareDatetime
    capabilities: list[CapabilityVersion] = Field(min_length=1, max_length=512)
    network_verified: bool
    signature: Hash


class Validate(Strict):
    operation_id: UUID
    reason: Note
    expected_active_revision: UUID | None
    proof: Proof


class Approval(Strict):
    operation_id: UUID
    validation_id: UUID
    expected_active_revision: UUID | None
    reason: Note


class ActorApproval(Approval):
    actor: str


class Switch(Strict):
    operation_id: UUID
    reason: Note
    approval_ref: Note
    expected_active_revision: UUID | None
    validation_id: UUID
    worker_ids: list[Identifier] = Field(min_length=1, max_length=50)

    @field_validator('worker_ids')
    @classmethod
    def distinct(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('duplicate Worker')
        return sorted(value)


class Reconcile(Strict):
    operation_id: UUID
    reason: Note
    fencing_token: int | None = Field(default=None, ge=1)


class AdmissionChange(Reconcile):
    paused: bool
    expected_active_revision: UUID | None
    expected_pause_operation_id: UUID | None = None


class RevisionView(Strict):
    revision_id: UUID
    revision_number: int
    base_revision: UUID | None
    config_digest: Hash
    created_by: str
    created_at: datetime
    reason: Note
    spec: ConfigSpec
    status: str
    validation_id: UUID | None = None


class Impact(Strict):
    policies: list[str] = Field(default_factory=list)
    affected_grants: int
    impacted_owners: int
    unknown: bool = False


class Operation(Strict):
    operation_id: UUID
    action: str
    revision_id: UUID | None
    before_revision: UUID | None = None
    status: str
    blockers: list[str] = Field(default_factory=list)
    worker_ids: list[str] = Field(default_factory=list)
    confirmed_workers: list[str] = Field(default_factory=list)
    queued_tasks: int | None = None
    active_runs: int | None = None
    open_outbox: int | None = None
    fencing_token: int | None = None
    queued_requiring_prior_worker: int | None = None
    runs_requiring_prior_worker: int | None = None
    compatible_workers: int | None = None
    unconfirmed_workers: int | None = None
    impact: Impact | None = None
    approval_ref: str | None = None
    reason: str
    occurred_at: datetime
    validation_digest: Hash | None = None


class ConfigIndex(Strict):
    write_enabled: bool = False
    active_revision: UUID | None = None
    desired_revision: UUID | None = None
    admission_paused: bool = False
    pause_operation_id: UUID | None = None
    pause_reason: str | None = None
    deployment: Operation | None = None
    revisions: list[RevisionView] = Field(default_factory=list)
    history: list[Operation] = Field(default_factory=list)


class ActorCandidate(Candidate):
    actor: str


class ActorValidate(Validate):
    actor: str
    impact: Impact


class ActorSwitch(Switch):
    actor: str
    impact: Impact


class PreparedRelease(Strict):
    deployment_id: UUID
    operation_id: UUID
    fencing_token: int = Field(ge=1)
    target_revision: UUID
    validation_digest: Hash
    impact_digest: Hash
    prepared_at: AwareDatetime


class ActorReconcile(Reconcile):
    actor: str
    impact: Impact | None = None
    preparation: PreparedRelease | None = None


class ActorAdmissionChange(AdmissionChange):
    actor: str
