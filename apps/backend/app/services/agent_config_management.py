"""Backend approval boundary, read-only entitlement impact, and sealed receipts."""
import asyncio
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from agent_contracts.canonical import digest
from agent_contracts.management_config import Impact, Operation, PreparedRelease, Proof
from app.core.database import get_session_factory
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.models.agent_entitlements import (
    EntitlementPolicyRow, GrantRevisionRow, GrantRootRow, OwnerEntitlementRow, PlanReleaseRow,
)
from . import agent_management_audit as audit
from .agent_config_barrier import barrier

MAX_EVIDENCE_ROWS = 5000


def incompatible(capabilities, expected):
    return any(expected.get(item['capability_id']) != item['capability_version'] for item in capabilities)


async def impact(proof):
    expected = {item.id: item.version for item in proof.capabilities}
    try:
        async with asyncio.timeout(3), get_session_factory()() as db:
            policies = (await db.execute(select(EntitlementPolicyRow.policy_revision, EntitlementPolicyRow.payload)
                        .where(EntitlementPolicyRow.approved.is_(True), EntitlementPolicyRow.test_only.is_(False))
                        .limit(MAX_EVIDENCE_ROWS + 1))).all()
            releases = set((await db.scalars(select(PlanReleaseRow.policy_revision).distinct()
                                             .limit(MAX_EVIDENCE_ROWS + 1))).all())
            owners = (await db.execute(select(OwnerEntitlementRow.policy_revision).where(
                OwnerEntitlementRow.enabled.is_(True)).limit(MAX_EVIDENCE_ROWS + 1))).scalars().all()
            grants = (await db.execute(select(GrantRevisionRow.payload).select_from(GrantRootRow).outerjoin(
                GrantRevisionRow, and_(GrantRevisionRow.grant_id == GrantRootRow.grant_id,
                                       GrantRevisionRow.revision == GrantRootRow.current_revision),
            ).where(GrantRootRow.status != 'closed').limit(MAX_EVIDENCE_ROWS + 1))).scalars().all()
        if max(len(policies), len(owners), len(grants), len(releases)) > MAX_EVIDENCE_ROWS or any(g is None for g in grants):
            return Impact(affected_grants=0, impacted_owners=0, unknown=True)
        permitted = {key for key, _ in policies}
        if not set(owners).issubset(permitted) or not releases.issubset(permitted):
            return Impact(affected_grants=0, impacted_owners=0, unknown=True)
        changed = {key for key, value in policies
                   if incompatible(value['permission_snapshot']['capabilities'], expected)}
        return Impact(policies=sorted(changed.intersection(releases | set(owners))),
                      affected_grants=sum(incompatible(grant['capabilities'], expected) for grant in grants),
                      impacted_owners=sum(key in changed for key in owners))
    except (TimeoutError, RuntimeError, OSError, SQLAlchemyError, TypeError, AttributeError, KeyError):
        return Impact(affected_grants=0, impacted_owners=0, unknown=True)


class ConfigAuditRequest(BaseModel):
    operation_id: UUID
    target_id: str
    kind: str = 'config'
    action: str
    fingerprint: str


async def read(path, response, params=None):
    return await agent.request('GET', '/config' + path, response, query=params, config_role=True)


async def perform(action, path, target, body, principal, request_id):
    envelope = body.model_dump(mode='json')
    for key in ('fencing_token', 'expected_pause_operation_id'):
        if envelope.get(key) is None:
            envelope.pop(key, None)
    audit_request = ConfigAuditRequest(operation_id=body.operation_id, target_id=target, action=action,
                                       fingerprint=digest(envelope))
    prior = await audit.admit(principal, 'config', audit_request, request_id)
    if prior:
        try:
            found = await read('/operations/' + str(body.operation_id), Operation, {'original': 'true'})
        except BusinessError as exc:
            if exc.status == 404 and prior.state == 'fail':
                raise BusinessError(10001, prior.reason or 'CONFIG_OPERATION_REJECTED', 409) from exc
            if exc.status != 404 or prior.state not in ('unknown', 'pending'):
                raise
        else:
            if action in ('reconcile', 'pause'):
                await barrier(target, str(body.operation_id), release=True, abort=action == 'pause', factory=get_session_factory())
            await finish(found)
            return found
    deployment = None
    if action in ('reconcile', 'pause'):
        deployment = await read('/operations/' + target, Operation)
        if deployment.fencing_token is not None and 'fencing_token' not in envelope:
            envelope['fencing_token'] = deployment.fencing_token
    if action == 'validate':
        envelope['impact'] = (await impact(body.proof)).model_dump(mode='json')
    elif action in ('activate', 'rollback', 'reconcile'):
        try:
            reference = f'/deployments/{target}/proof' if action == 'reconcile' else '/validations/' + str(body.validation_id)
            proof = await read(reference, Proof)
        except BusinessError as exc:
            await audit.complete(body.operation_id, 'fail' if exc.status < 500 else 'unknown',
                                 'CONFIG_VALIDATION_LOOKUP_FAILED', reopen_unknown=True)
            raise
        if action == 'reconcile' and deployment.fencing_token is not None:
            await barrier(target, str(body.operation_id), factory=get_session_factory())
        envelope['impact'] = (await impact(proof)).model_dump(mode='json')
        if action == 'reconcile' and deployment.fencing_token is not None:
            prepared = PreparedRelease(
                deployment_id=target, operation_id=body.operation_id, fencing_token=deployment.fencing_token,
                target_revision=deployment.revision_id, validation_digest=deployment.validation_digest,
                impact_digest=digest(envelope['impact']), prepared_at=datetime.now(timezone.utc),
            )
            envelope['preparation'] = await audit.prepare_config(body.operation_id, prepared.model_dump(mode='json'))
    try:
        result = await agent.request('POST', '/config' + path, Operation,
                                     payload={**envelope, 'actor': principal}, config_role=True)
    except BusinessError as exc:
        if action == 'reconcile' and exc.status < 500:
            await barrier(target, str(body.operation_id), release=True, factory=get_session_factory())
        await audit.complete(body.operation_id, 'fail' if exc.status < 500 else 'unknown',
                             exc.message if exc.status < 500 else 'CONFIG_RESULT_UNCONFIRMED', reopen_unknown=True)
        raise
    if action in ('reconcile', 'pause'):
        await barrier(target, str(body.operation_id), release=True, abort=action == 'pause', factory=get_session_factory())
    await finish(result)
    return result


async def finish(result):
    target = str(result.revision_id or result.operation_id)
    event = {
        'target_id': target, 'action': result.action, 'status': result.status,
        'before_revision': str(result.before_revision) if result.before_revision else None,
        'after_revision': str(result.revision_id) if result.revision_id else None,
        'reason': result.reason, 'approval_ref': result.approval_ref,
        'validation_digest': result.validation_digest, 'fencing_token': result.fencing_token,
        'confirmed_workers': result.confirmed_workers, 'blockers': result.blockers,
    }
    await audit.complete(result.operation_id, 'fail' if result.status == 'blocked' else 'pass', result.status,
                         event, verified_target=True, reopen_unknown=True)
