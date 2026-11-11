"""Coordinate anonymous Agent session, workspace and upload ownership migration.

Agent session directories are copied before their database owner changes;
otherwise a failed filesystem operation could leave a claimed session unable to
reach its report files.
"""
from __future__ import annotations

import logging

from app.services.agent_gateway.client import agent_gateway
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_uploads import agent_upload_store

logger = logging.getLogger(__name__)


async def claim_anonymous_sessions(source_owner: str, target_owner: str) -> dict:
    prepared_ids = await agent_session_repository.claimable_session_ids(source_owner)
    # Copy/merge is intentionally non-destructive. A failed copy or DB commit
    # leaves the anonymous workspace available for a safe retry.
    prepared = await agent_gateway.prepare_workspace_claim(
        source_owner, target_owner, prepared_ids,
    )
    prepared_ids = list(prepared.get('prepared_session_ids') or [])

    agent_result = await agent_session_repository.claim_anonymous_sessions(
        source_owner, target_owner, session_ids=prepared_ids,
    )
    await agent_upload_store.claim_owner(source_owner, target_owner)
    moved_ids = [str(item) for item in agent_result.get('moved_session_ids', [])]
    # Uploaded workspace directories are moved after the Backend ownership
    # transaction commits. Agent retains the owner-scoped registry and performs
    # this filesystem operation inside its own boundary.
    try:
        await agent_gateway.commit_workspace_claim(source_owner, target_owner, moved_ids)
    except Exception:
        logger.warning('failed to finalize Agent workspace ownership claim', exc_info=True)
    return {
        'moved_count': int(agent_result.get('moved_count', 0)),
        'skipped_streaming_count': int(agent_result.get('skipped_running_count', 0)),
        'durable': bool(agent_result.get('durable')),
    }

