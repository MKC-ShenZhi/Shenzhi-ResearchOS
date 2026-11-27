"""Protocol-neutral handlers shared by the V1 compatibility and V2 APIs."""
from __future__ import annotations

import base64
import os
from typing import Any

from agent_app.errors import BusinessError
from agent_app.extensions.skills import default_store
from agent_app.extensions.workspace import (
    cleanup_session_workspace, copy_session_workspace, create_workspace,
    migrate_owner_workspaces, read_session_file, write_workspace_file,
)
from agent_app.integrations.llm.resolver import load_registry
from agent_contracts import (
    AgentConfigWire, SessionFileReadResponseWire, WorkspaceClaimCommitResponseWire,
    WorkspaceClaimPrepareResponseWire, WorkspaceClaimRequestWire,
    WorkspaceCreateRequestWire, WorkspaceCreateResponseWire,
    WorkspaceFileWriteRequestWire, WorkspaceFileWriteResponseWire,
)


async def agent_config() -> dict:
    if os.getenv('AGENT_DEMO_MODE') == '1':
        return AgentConfigWire(
            models=[{'value': 'demo/m1', 'label': 'Mock 演示（无模型调用）',
                     'provider': 'platform', 'enabled': True}], default_model='demo/m1',
            skills=[{'name': 'deep-research', 'description': 'Mock 演示报告，不执行真实研究'}],
        ).model_dump(mode='json')
    registry = load_registry()
    store = default_store()
    skills = [{'name': skill.name, 'description': skill.description}
              for name in store.names()
              for skill in [store.get(name)]
              if skill and not skill.disable_model_invocation]
    return AgentConfigWire(
        models=registry.public_models('agent'),
        default_model=registry.public_default('agent'), skills=skills,
    ).model_dump(mode='json')


async def new_workspace(body: WorkspaceCreateRequestWire) -> dict:
    return WorkspaceCreateResponseWire.model_validate(
        create_workspace(body.owner_id),
    ).model_dump(mode='json')


async def prepare_workspace_claim(body: WorkspaceClaimRequestWire) -> dict:
    prepared = []
    for session_id in dict.fromkeys(body.session_ids):
        if copy_session_workspace(body.source_owner, body.target_owner, session_id):
            prepared.append(session_id)
    return WorkspaceClaimPrepareResponseWire(
        prepared_session_ids=prepared,
    ).model_dump(mode='json')


async def commit_workspace_claim(body: WorkspaceClaimRequestWire) -> dict:
    cleaned = []
    for session_id in dict.fromkeys(body.session_ids):
        try:
            cleanup_session_workspace(body.source_owner, session_id)
            cleaned.append(session_id)
        except Exception:
            # Ownership is already committed; stale source data is safer than
            # turning a successful claim into a reported failure.
            continue
    moved_workspaces = migrate_owner_workspaces(body.source_owner, body.target_owner)
    return WorkspaceClaimCommitResponseWire(
        cleaned_session_ids=cleaned, moved_workspaces=moved_workspaces,
    ).model_dump(mode='json')


async def put_workspace_file(workspace_id: str, body: WorkspaceFileWriteRequestWire) -> dict:
    if body.workspace_id != workspace_id:
        raise BusinessError(20001, 'URL workspace_id 与请求不匹配')
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise BusinessError(20001, '文件内容编码无效') from exc
    return WorkspaceFileWriteResponseWire.model_validate(
        write_workspace_file(workspace_id, body.owner_id, body.path, content),
    ).model_dump(mode='json')


async def get_session_file(session_id: str, owner_id: str, path: str) -> dict:
    content, media_type = read_session_file(owner_id, session_id, path)
    return SessionFileReadResponseWire(
        content_base64=base64.b64encode(content).decode('ascii'), media_type=media_type,
    ).model_dump(mode='json')


def task_json(record) -> dict[str, Any]:
    return {'task_id': record.task_id, 'owner_id': record.owner_id,
            'session_id': record.session_id, 'turn_id': record.turn_id,
            'status': record.status.value, 'current_run_id': record.current_run_id,
            'cancel_requested': record.cancel_requested,
            'created_at': record.created_at.isoformat()}
