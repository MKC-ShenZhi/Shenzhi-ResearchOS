"""Stable Agent-owned runtime factory API for the CLI and embedding tools."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_app.application import composition
from agent_app.application.policies import compose_agent_system, run_deadline_s
from agent_app.execution.runtime import AgentRuntime
from agent_app.extensions.skills import default_store
from agent_app.extensions import workspace


def default_runtime(**kwargs: Any) -> AgentRuntime:
    return composition.default_runtime(**kwargs)


def build_run_runtime(*, owner: str, model: str | None = None, mode: str = 'fast',
                      workspace_id: str | None = None, forced_skills: Sequence[str] = (),
                      session_id: str | None = None, allow_shell: bool = True) -> AgentRuntime:
    return composition.build_runtime(
        owner=owner, model=model, mode=mode, workspace_id=workspace_id,
        forced_skills=forced_skills, session_id=session_id, allow_shell=allow_shell,
        runtime_factory=default_runtime,
    )


create_workspace = workspace.create_workspace
ensure_session_workspace = workspace.ensure_session_workspace
read_session_file = workspace.read_session_file
write_workspace_file = workspace.write_workspace_file
