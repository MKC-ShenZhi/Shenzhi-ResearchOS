"""Coordinate anonymous Chat and Agent session ownership migration.

The browser presents one migration decision, so the backend must apply the same
trusted anonymous-owner identity to both products.  Agent session directories
are copied before their database owner changes; otherwise a failed filesystem
operation could leave a claimed session unable to reach its report files.
"""
from __future__ import annotations

import logging

from app.services.agent import workspace as agent_workspace
from app.services.agent_sessions.repository import agent_session_repository
from app.services.chat.repository import repository as chat_repository

logger = logging.getLogger(__name__)


async def claim_anonymous_sessions(source_owner: str, target_owner: str) -> dict:
    prepared_ids = await agent_session_repository.claimable_session_ids(source_owner)
    for session_id in prepared_ids:
        # Copy/merge is intentionally non-destructive. A failed copy or DB
        # commit leaves the anonymous workspace available for a safe retry.
        agent_workspace.copy_session_workspace(source_owner, target_owner, session_id)

    chat_result = await chat_repository.claim_anonymous_sessions(source_owner, target_owner)
    agent_result = await agent_session_repository.claim_anonymous_sessions(
        source_owner, target_owner, session_ids=prepared_ids,
    )
    moved_ids = [str(item) for item in agent_result.get('moved_session_ids', [])]
    for session_id in moved_ids:
        try:
            agent_workspace.cleanup_session_workspace(source_owner, session_id)
        except Exception:
            # Ownership and the target copy are already committed. Retaining an
            # old anonymous directory is safer than reporting a false failure.
            logger.warning(
                'failed to clean claimed Agent session workspace %s',
                session_id,
                exc_info=True,
            )

    # Uploaded workspaces have a process-local registration lifecycle distinct
    # from session-id workspaces. Preserve their existing owner migration, but
    # do not turn a committed DB migration into a failed claim if cleanup fails.
    try:
        agent_workspace.migrate_owner_workspaces(source_owner, target_owner)
    except Exception:
        logger.warning('failed to migrate process-local uploaded workspaces', exc_info=True)
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
