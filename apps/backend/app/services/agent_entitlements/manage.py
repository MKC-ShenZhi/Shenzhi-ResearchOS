"""Explicit operator entry point, reads reviewed JSON files, never prints keys.

python -m app.services.agent_entitlements.manage ACTION --file <reviewed.json>
Actions: install-policy, assign, revoke, revise, adjust, recover-submission,
reprocess-usage. No test policies may be enabled by the production service.
"""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path

from app.core.database import session_scope
from app.models.agent_entitlements import EntitlementPolicyRow, OwnerEntitlementRow, UsageInboxRow, GrantRootRow, EntitlementAuditRow
from .config import entitlement_service
from .operations import adjust_usage
from .policy import EntitlementPolicy
from .service import require, now_utc, uid


async def execute(action, payload):
    service = entitlement_service()
    if action == 'recover-submission':
        from app.services.agent_gateway.gateway import AgentGateway
        task = await AgentGateway().recover_submission(payload['owner_id'], payload['client_key'])
        return {'task_id': task['task_id'], 'binding_status': task['binding_status']}
    if action == 'reprocess-usage':
        from agent_contracts.v2 import UsageDelta
        from app.services.agent_gateway.gateway import AgentGateway
        from .usage import UsageSettlement
        async with session_scope() as db:
            row = await db.get(UsageInboxRow, payload['measurement_id'])
            require(row is not None, 'MEASUREMENT_NOT_FOUND', 404)
            usage = UsageDelta.model_validate(row.payload)
        fact = await AgentGateway().start_fact(usage.task_id, usage.call_id)
        async with session_scope() as db:
            receipt = await UsageSettlement(service).ingest(db, usage, fact, principal=payload['principal'])
        return receipt.model_dump(mode='json')
    async with session_scope() as db:
        if action == 'install-policy':
            policy = EntitlementPolicy.model_validate(payload['policy'])
            require(policy.plan_id not in ('basic','pro','research'), 'FORMAL_PUBLICATION_REQUIRES_ADMIN_CONSOLE', 403)
            require(payload.get('approved') is True and payload.get('approval_ref'), 'POLICY_NOT_APPROVED')
            existing = await db.get(EntitlementPolicyRow, policy.policy_revision)
            require(existing is None, 'POLICY_REVISION_IMMUTABLE')
            db.add(EntitlementPolicyRow(policy_revision=policy.policy_revision, approved=True,
                test_only=payload.get('test_only', True), payload=policy.model_dump(mode='json')))
        elif action == 'assign':
            require(False, 'ASSIGNMENT_REQUIRES_ADMIN_CONSOLE', 403)
        elif action == 'revoke':
            await service.revoke(db, payload['grant_id'], payload['operation_id'], payload['principal'], payload['reason'],
                                 capability_id=payload.get('capability_id'), capability_version=payload.get('capability_version'))
            root = await db.get(GrantRootRow, payload['grant_id'])
            revocation = dict(schema_version=1, operation_id=payload['operation_id'],
                              submission_id=root.submission_id, reason_code=payload['reason'],
                              capability_id=payload.get('capability_id'), capability_version=payload.get('capability_version'))
        elif action == 'revise':
            grant = await service.revise(db, payload['grant_id'], expected_revision=payload['expected_revision'],
                expected_binding_revision=payload['expected_binding_revision'], expires_at=datetime.fromisoformat(payload['expires_at']))
        elif action == 'adjust':
            fields = dict(payload)
            fields['effective_started_at'] = datetime.fromisoformat(fields['effective_started_at'])
            await adjust_usage(db, service, **fields)
        else:
            raise ValueError('unknown action')
        if action in ('install-policy', 'assign', 'revise'):
            require(payload.get('operation_id') and payload.get('principal') and payload.get('approval_ref'), 'OPERATOR_AUDIT_REQUIRED')
            db.add(EntitlementAuditRow(audit_id=uid(), operation_id=payload['operation_id'], principal=payload['principal'],
                reason=action, payload=payload, created_at=now_utc()))
    if action == 'revise':
        from app.services.agent_gateway.gateway import AgentGateway
        await AgentGateway().request('POST', f'/internal/v2/grants/{grant.grant_id}/revisions', payload=grant.model_dump(mode='json'))
    if action == 'revoke':
        from app.services.agent_gateway.gateway import AgentGateway
        await AgentGateway().request('POST', f"/internal/v2/grants/{payload['grant_id']}/revocations", payload=revocation)
    return {'status': 'recorded'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install-policy', 'assign', 'revoke', 'revise', 'adjust', 'recover-submission', 'reprocess-usage'])
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(execute(args.action, json.loads(Path(args.file).read_text(encoding='utf-8')))), ensure_ascii=False))
