"""HTTP request contracts for Agent runs and persistent sessions."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import MAX_FILES


class AgentAttachment(BaseModel):
    kind: Literal['file', 'paper', 'patent', 'funding', 'scholar', 'institution', 'session', 'project']
    file_id: str | None = Field(default=None, max_length=100)
    ref_id: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=500)


class AgentSessionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    model: str | None = None
    mode: Literal['fast', 'deep', 'idea', 'doubt'] = 'fast'
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_FILES)
    skills: list[str] = Field(default_factory=list, max_length=10)
    workspace_id: str | None = None
    branched_from: str | None = Field(default=None, max_length=64)


class AgentSessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AgentSessionRun(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    model: str | None = None
    mode: Literal['fast', 'deep', 'idea', 'doubt'] = 'fast'
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_FILES)
    workspace_id: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=10)


class AgentRunBody(BaseModel):
    """Stateless Agent run request contract."""
    prompt: str = Field(min_length=1, max_length=10_000)
    history: list[dict] = Field(default_factory=list, max_length=200)
    model: str | None = None
    # mode 决定温度、运行预算，以及未显式选择技能时的快速回答技能与工具集。
    mode: Literal['fast', 'deep', 'idea', 'doubt'] = 'fast'
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_FILES)
    workspace_id: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=10)
    session_id: str | None = None


class SteerBody(BaseModel):
    """Inject a follow-up into the active run before its next model request."""
    text: str = Field(min_length=1, max_length=4_000)


class LegacyAgentSessionImport(BaseModel):
    import_key: str = Field(min_length=1, max_length=160)
    title: str = Field(default='本地会话', max_length=200)
    created_at: float | None = None
    updated_at: float | None = None
    branched_from: str | None = Field(default=None, max_length=160)
    turns: list[dict[str, Any]] = Field(default_factory=list, max_length=400)
