"""HTTP contracts for persistent Agent product sessions."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import MAX_FILES


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


class LegacyAgentSessionImport(BaseModel):
    import_key: str = Field(min_length=1, max_length=160)
    title: str = Field(default='本地会话', max_length=200)
    created_at: float | None = None
    updated_at: float | None = None
    branched_from: str | None = Field(default=None, max_length=160)
    turns: list[dict[str, Any]] = Field(default_factory=list, max_length=400)
