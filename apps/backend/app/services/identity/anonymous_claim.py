"""Coordinate anonymous Chat and Agent session ownership migration.

The browser presents one migration decision, so the backend must apply the same
trusted anonymous-owner identity to both products.  Agent session directories
are moved together with their database owner; otherwise a claimed session would
lose its report files when the owner hash changes.
"""
from __future__ import annotations

import os
import shutil

from app.services.agent import workspace as agent_workspace
from app.services.agent_sessions.repository import agent_session_repository
from app.services.chat.repository import repository as chat_repository


def _move_session_workspace(source_owner: str, target_owner: str, session_id: str) -> None:
    source = agent_workspace._owner_dir(source_owner) / session_id
    target = agent_workspace._owner_dir(target_owner) / session_id
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        os.replace(source, target)
        return
    # A retry or a previous partial migration must not discard either tree.
    shutil.copytree(source, target, dirs_exist_ok=True)
    shutil.rmtree(source)


async def claim_anonymous_sessions(source_owner: str, target_owner: str) -> dict:
    chat_result = await chat_repository.claim_anonymous_sessions(source_owner, target_owner)
    agent_result = await agent_session_repository.claim_anonymous_sessions(
        source_owner, target_owner,
    )
    agent_workspace.migrate_owner_workspaces(source_owner, target_owner)
    moved_ids = [str(item) for item in agent_result.get('moved_session_ids', [])]
    for session_id in moved_ids:
        _move_session_workspace(source_owner, target_owner, session_id)
    return {
        'moved_count': int(chat_result.get('moved_count', 0))
        + int(agent_result.get('moved_count', 0)),
        'skipped_streaming_count': int(chat_result.get('skipped_streaming_count', 0))
        + int(agent_result.get('skipped_running_count', 0)),
        # A claim is reported durable only when both product stores can persist it.
        'durable': bool(chat_result.get('durable')) and bool(agent_result.get('durable')),
    }


async def anonymous_session_counts(source_owner: str) -> dict:
    """Return a read-only preview for the browser migration prompt."""
    chat_count = 0
    agent_count = 0
    if chat_repository.is_durable:
        # Repositories intentionally expose no cross-owner list API.  A preview
        # count is best-effort and remains zero for ephemeral stores.
        try:
            chat_page = await chat_repository.list(source_owner)
            chat_count = len(chat_page)
        except Exception:
            chat_count = 0
    if agent_session_repository.is_durable:
        try:
            page = await agent_session_repository.list_page(source_owner, 50, None)
            agent_count = len(page.get('sessions', []))
        except Exception:
            agent_count = 0
    return {'count': chat_count + agent_count, 'chat_count': chat_count, 'agent_count': agent_count}
