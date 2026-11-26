"""Independent Admin projections. Never use entitlement mutation or locking services."""
import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

from agent_contracts.management import Api, Counts, Evidence, Overview, Runtime, Skill, Snapshot, Usage, Workspace
from agent_contracts.canonical import digest
from agent_contracts.v2 import SkillIdentity, TaskMeteringBindingReceipt
from app.core.database import get_session_factory
from app.core.errors import BusinessError
from app.integrations import agent_management as agent
from app.models.agent_entitlements import (
    EntitlementPolicyRow, GrantRootRow, MeteringProfileRow, ReservationAllocationRow, UsageLedgerRow,
    UsageProjectionRow,
)


def now():
    return datetime.now(timezone.utc)


def status(source, state='ok', reason=None):
    return dict(status=state, source=source, observed_at=now(), reason_code=reason)


def time_window(from_at, to_at):
    if any(value is not None and value.utcoffset() is None for value in (from_at, to_at)):
        raise BusinessError(20001, 'TIMEZONE_REQUIRED', 422)
    end = to_at or now()
    start = from_at or end - timedelta(days=1)
    if start >= end or end - start > timedelta(days=31):
        raise BusinessError(20001, 'TIME_WINDOW_INVALID', 422)
    return start, end


async def backend_db_health():
    try:
        async with asyncio.timeout(2), get_session_factory()() as db:
            await db.execute(text('SELECT 1'))
        return Snapshot(**status('backend_entitlements_database_select_1'))
    except (TimeoutError, SQLAlchemyError, RuntimeError, OSError):
        return Snapshot(**status('backend_entitlements_database_select_1', 'unavailable', 'BACKEND_DATABASE_UNAVAILABLE'))


async def overview(query, from_at, to_at):
    start, end = time_window(from_at, to_at)

    async def remote():
        sent = perf_counter()
        try:
            data = await agent.read('/overview', Overview, query)
            data.api.response_ms = round((perf_counter() - sent) * 1000)
            return data
        except BusinessError:
            unavailable = status('backend_to_agent_management', 'unavailable', 'AGENT_MANAGEMENT_UNAVAILABLE')
            unknown = status('agent_management', 'unknown', 'AGENT_NOT_OBSERVED')
            return Overview(api=Api(**unavailable), agent_db=Snapshot(**unknown),
                            workspace=Workspace(**unknown), runtime=Runtime(**unknown),
                            workers=Snapshot(**unknown), counts=Counts(**unknown, window_start=start, window_end=end))

    result, result_db = await asyncio.gather(remote(), backend_db_health())
    result.backend_db = result_db
    return result


async def task_usage(task):
    """Verify Backend binding by task and owner before exposing any totals."""
    try:
        async with asyncio.timeout(2), get_session_factory()() as db:
            profiles = (await db.scalars(select(MeteringProfileRow).where(
                MeteringProfileRow.task_id == task.task_id, MeteringProfileRow.owner_id == task.owner_id,
                MeteringProfileRow.binding.is_not(None),
            ).limit(2))).all()
            if len(profiles) != 1:
                return Usage(status='unknown')
            profile = profiles[0]
            binding = TaskMeteringBindingReceipt.model_validate(profile.binding)
            expected_submission = profile.backend_submission_id or profile.observation_submission_id
            if (binding.task_id, binding.metering_profile_id, binding.metering_context, binding.submission_id) != (
                task.task_id, profile.profile_id, profile.context, expected_submission,
            ):
                return Usage(status='unknown')
            p = UsageProjectionRow.payload
            token_status = p['usage_status'].as_string()
            prompt, completion = p['prompt_tokens'].as_integer(), p['completion_tokens'].as_integer()
            known = func.coalesce(prompt, 0) + func.coalesce(completion, 0)
            count, measured, total, partial, unknown, estimated, pending = (await db.execute(select(
                func.count(), func.sum(known).filter(token_status == 'measured'),
                func.sum(case((or_(prompt.is_not(None), completion.is_not(None)), known))).filter(token_status != 'estimated'),
                func.count().filter(token_status == 'partial'), func.count().filter(token_status == 'unknown'),
                func.count().filter(token_status == 'estimated'),
                func.count().filter(p['phase'].as_string() == 'started'),
            ).where(UsageProjectionRow.task_id == task.task_id,
                    p['owner_id'].as_string() == task.owner_id,
                    p['metering_profile_id'].as_string() == profile.profile_id,
                    p['agent_audience'].as_string() == profile.audience,
                    p['submission_id'].as_string() == binding.submission_id,
                    p['capability_identity']['kind'].as_string() == 'model'))).one()
            root = None
            if profile.backend_submission_id:
                root = await db.scalar(select(GrantRootRow).where(
                    GrantRootRow.submission_id == profile.backend_submission_id,
                    GrantRootRow.bound_task_id == task.task_id))
            used, held = None, None
            if root:
                used, held = (await db.execute(select(func.sum(UsageLedgerRow.used_delta),
                    func.sum(UsageLedgerRow.held_delta)).join(
                    ReservationAllocationRow, ReservationAllocationRow.allocation_id == UsageLedgerRow.allocation_id,
                ).where(UsageLedgerRow.grant_id == root.grant_id, UsageLedgerRow.owner_id == task.owner_id,
                        ReservationAllocationRow.allocation['metric'].as_string() == 'tokens'))).one()
            state = ('unsettled' if pending else 'partial' if partial or (unknown and measured is not None)
                     else 'unknown' if unknown or not count else 'estimated' if estimated else 'measured')
            return Usage(status=state, measured_tokens=measured, known_tokens=total, accounted_tokens=used,
                         held_tokens=held, settlement_status=root.settlement_status if root else 'not_applicable')
    except (TimeoutError, SQLAlchemyError, RuntimeError, OSError, ValidationError):
        return Usage(status='unknown')


async def apply_policy(payload, revision):
    if not revision:
        return
    try:
        async with asyncio.timeout(2), get_session_factory()() as db:
            row = await db.get(EntitlementPolicyRow, revision)
            if not row or not row.approved or row.test_only:
                raise BusinessError(20001, '已批准的 Policy 版本不存在', 404)
            permissions = row.payload.get('permission_snapshot', {}).get('capabilities', [])
            allowed = {(e['capability_id'], e['capability_version']) for e in permissions}
    except (TimeoutError, SQLAlchemyError, RuntimeError, OSError, KeyError, TypeError, AttributeError):
        return
    for item in getattr(payload, 'items', [payload]):
        if hasattr(item, 'model_id'):
            key, version = 'model:' + item.model_id, item.capability_version
        elif hasattr(item, 'tool_id'):
            if item.registration == 'observed_only':
                continue
            key, version = item.tool_id, item.capability_version
        elif isinstance(item, Skill) and item.resource_digest and item.integrity == 'yes':
            key = 'skill:' + item.name
            identity = SkillIdentity(schema_version=1, kind='skill', capability_id=key,
                                     resource_content_digest=item.resource_digest, dependency_digests=[])
            version = digest(identity.model_dump(mode='json'))
        else:
            continue
        if version:
            item.states.authorized = Evidence(
                state='yes' if (key, version) in allowed else 'no',
                source='policy:' + revision, observed_at=now(),
            )
