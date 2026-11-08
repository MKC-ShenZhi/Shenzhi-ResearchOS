"""Stable application entry point for Agent HTTP, sessions, and CLI callers."""
from __future__ import annotations

from collections.abc import Sequence

from app.services.agent.execution.runtime import AgentRuntime
from app.services.agent.app import composition
from app.services.agent.app.composition import (
    decode_history, default_runtime, load_project_context, resolve_attachments,
)
from app.services.agent.app.events import run_events, steer_run, stop_run
from app.services.agent.app.policies import compose_agent_system, run_deadline_s
from app.services.agent.extensions.skills import default_store
from app.services.agent.extensions.workspace import (
    create_workspace, ensure_session_workspace, read_session_file, write_workspace_file,
)

__all__ = [
    'build_run_runtime', 'create_workspace', 'decode_history', 'default_store',
    'read_session_file', 'resolve_attachments', 'run_deadline_s', 'run_events',
    'steer_run', 'stop_run', 'write_workspace_file', 'compose_agent_system',
]


def build_run_runtime(*, owner: str, model: str | None = None, mode: str = 'fast',
                      workspace_id: str | None = None, forced_skills: Sequence[str] = (),
                      session_id: str | None = None, allow_shell: bool = True) -> AgentRuntime:
    """Retain the service entry point and injectable runtime factory."""
    return composition.build_run_runtime(
        owner=owner, model=model, mode=mode, workspace_id=workspace_id,
        forced_skills=forced_skills, session_id=session_id, allow_shell=allow_shell,
        runtime_factory=default_runtime,
    )
