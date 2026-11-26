"""Bounded SELECT-only projections of existing Agent runtime records."""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, exists, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from agent_contracts.canonical import digest
from agent_contracts.v2 import SkillIdentity

from agent_contracts.management import (
    Call, Counts, Event, Execution, ModelObservation, Run, Runtime, Snapshot, Task, Usage, Worker, Workspace,
)
from agent_contracts.runs import RunStatus
from agent_contracts.tasks import TaskStatus
from agent_app.control.metering import GateDenied, now_utc
from agent_app.extensions.workspace import WORKSPACE_ROOT
from agent_app.infrastructure.database import get_session
from agent_app.infrastructure.metering_models import CallRow, ExecutionRow, ObservationRow
from agent_app.infrastructure.models import RunEventRow, RunRow, TaskRow


@asynccontextmanager
async def reading():
    try:
        async with asyncio.timeout(2.5), asynccontextmanager(get_session)() as db:
            yield db
    except (TimeoutError, RuntimeError, OSError, SQLAlchemyError):
        raise GateDenied('AGENT_DATABASE_UNAVAILABLE', 503) from None


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def snapshot(source, status='ok', reason=None):
    return dict(source=source, status=status, observed_at=now_utc(), reason_code=reason)


def workspace_health():
    try:
        readable = WORKSPACE_ROOT.is_dir() and os.access(WORKSPACE_ROOT, os.R_OK | os.X_OK)
    except OSError:
        readable = False
    return Workspace(**snapshot('workspace_root_metadata', 'ok' if readable else 'unavailable',
                                None if readable else 'WORKSPACE_ROOT_UNAVAILABLE'),
                     readable='yes' if readable else 'no')


async def database_health():
    try:
        async with reading() as db:
            await db.execute(text('SELECT 1'))
    except GateDenied as exc:
        return Snapshot(**snapshot('agent_database_select_1', 'unavailable', exc.reason))
    return Snapshot(**snapshot('agent_database_select_1'))


def lease_status(row, now):
    if row.status != 'running':
        return 'not_applicable'
    if row.lease_expires_at is None:
        return 'unknown'
    return 'active' if utc(row.lease_expires_at) > now else 'expired'


ERROR_CODES = {'authorization_denied', 'execution_cancelled', 'execution_failed',
               'worker_error', 'worker_execution_error', 'worker_lost', 'timeout', 'tool_error', 'provider_error', 'cancelled'}


def run_item(row, execution=None):
    now = now_utc()
    started, completed = utc(row.started_at), utc(row.completed_at)
    error = (row.report_json or {}).get('error_code')
    safe_error = error if isinstance(error, str) and error in ERROR_CODES else (
        'RUN_FAILED' if row.status == 'failed' else None)
    end = completed or (now if row.status == 'running' else None)
    return Run(run_id=row.run_id, task_id=row.task_id, attempt=row.attempt,
               status=row.status if row.status in RunStatus._value2member_map_ else 'unknown',
               worker_id=row.worker_id, created_at=utc(row.created_at), started_at=started,
               completed_at=completed, lease_status=lease_status(row, now), error_code=safe_error,
               duration_ms=max(0, int((end - started).total_seconds() * 1000)) if started and end else None,
               execution=execution)


def task_item(row, run=None, usage=None):
    request = row.request_json
    requested = request.get('model')
    mode = request.get('mode')
    return Task(task_id=row.task_id, owner_id=row.owner_id, created_at=utc(row.created_at),
                status=row.status if row.status in TaskStatus._value2member_map_ else 'unknown',
                mode=mode if mode in ('fast', 'deep') else None,
                requested_model=requested[:255] if isinstance(requested, str) else None,
                latest_run=run, error_code=run.error_code if run else None, observed_usage=usage)


async def run_items(db, rows):
    if not rows:
        return []
    executions = (await db.scalars(select(ExecutionRow).where(
        ExecutionRow.run_id.in_([row.run_id for row in rows]),
        exists(select(RunRow.run_id).where(RunRow.run_id == ExecutionRow.run_id,
                                           RunRow.lease_token == ExecutionRow.lease_token)),
    ))).all()
    by_run = {item.run_id: Execution(execution_id=item.execution_id, worker_id=item.worker_id, sealed=item.sealed)
              for item in executions}
    return [run_item(row, by_run.get(row.run_id)) for row in rows]


def window(from_at, to_at):
    if any(value is not None and value.utcoffset() is None for value in (from_at, to_at)):
        raise GateDenied('TIMEZONE_REQUIRED', 422)
    end = to_at or now_utc()
    start = from_at or end - timedelta(days=1)
    if start >= end or end - start > timedelta(days=31):
        raise GateDenied('TIME_WINDOW_INVALID', 422)
    return start, end


async def tasks(query, offset, size):
    start, end = window(query.from_at, query.to_at)
    predicates = [TaskRow.created_at >= start, TaskRow.created_at < end]
    for value, column in ((query.task_id, TaskRow.task_id), (query.status, TaskRow.status)):
        if value:
            predicates.append(column == value)
    if query.user_id:
        predicates.append(TaskRow.owner_id == 'user:' + query.user_id.removeprefix('user:'))
    if query.run_id:
        predicates.append(exists(select(RunRow.run_id).where(RunRow.task_id == TaskRow.task_id,
                                                             RunRow.run_id == query.run_id)))
    if query.worker_id:
        predicates.append(or_(
            exists(select(ExecutionRow.execution_id).where(ExecutionRow.task_id == TaskRow.task_id,
                                                           ExecutionRow.worker_id == query.worker_id)),
            exists(select(RunRow.run_id).where(RunRow.task_id == TaskRow.task_id,
                                              RunRow.worker_id == query.worker_id)),
        ))
    for prefix, requested in [('model:', query.model_id), ('tool:', query.tool_id)]:
        if requested:
            capability = prefix + requested.removeprefix(prefix)
            predicates.append(exists(select(CallRow.call_id).where(
                CallRow.task_id == TaskRow.task_id, CallRow.start_fact['capability_id'].as_string() == capability,
            )))
    async with reading() as db:
        order = (TaskRow.created_at.desc(), TaskRow.task_id.desc()) if query.order == 'desc' else (
            TaskRow.created_at.asc(), TaskRow.task_id.asc())
        pairs = (await db.execute(select(TaskRow, RunRow).outerjoin(RunRow, RunRow.run_id == TaskRow.current_run_id)
                                  .where(*predicates).order_by(*order).offset(offset).limit(size))).all()
        runs = {r.run_id: r for r in await run_items(db, [run for _, run in pairs if run])}
        return [task_item(task, runs.get(task.current_run_id)) for task, _ in pairs]


def tokens(payload):
    known = [v for v in (payload.get('prompt_tokens'), payload.get('completion_tokens')) if type(v) is int and v >= 0]
    return sum(known) if known else None


def observation_usage(payload):
    status = payload.get('usage_status')
    if payload.get('phase') == 'started':
        return 'unsettled'
    return status if status in ('measured', 'partial', 'unknown', 'estimated') else 'unknown'


def latest_observations():
    return select(ObservationRow.call_id, ObservationRow.payload, ObservationRow.task_id,
                  func.row_number().over(partition_by=ObservationRow.call_id,
                                         order_by=ObservationRow.revision.desc()).label('rank')).subquery()


async def task_detail(task_id):
    async with reading() as db:
        row = await db.get(TaskRow, task_id)
        if row is None:
            raise GateDenied('TASK_NOT_FOUND', 404)
        records = latest_observations()
        # Aggregate current call observations in SQL; never load usage payloads into the response.
        kind = records.c.payload['capability_identity']['kind'].as_string()
        status = records.c.payload['usage_status'].as_string()
        phase = records.c.payload['phase'].as_string()
        prompt = records.c.payload['prompt_tokens'].as_integer()
        completion = records.c.payload['completion_tokens'].as_integer()
        known = func.coalesce(prompt, 0) + func.coalesce(completion, 0)
        count, partial, pending, unknown, estimated, measured_count, measured, total = (await db.execute(select(
            func.count(), func.count().filter(status == 'partial'), func.count().filter(phase == 'started'),
            func.count().filter(status == 'unknown'), func.count().filter(status == 'estimated'),
            func.count().filter(status == 'measured'),
            func.sum(known).filter(status == 'measured'),
            func.sum(case((or_(prompt.is_not(None), completion.is_not(None)), known))).filter(status != 'estimated'),
        ).where(records.c.task_id == task_id, records.c.rank == 1, kind == 'model'))).one()
        missing = await db.scalar(select(func.count()).select_from(CallRow).where(
            CallRow.task_id == task_id, CallRow.start_fact['capability_identity']['kind'].as_string() == 'model',
            ~exists(select(ObservationRow.call_id).where(ObservationRow.call_id == CallRow.call_id)),
        ))
        status = ('unsettled' if pending or missing else 'partial' if partial or (unknown and measured_count)
                  else 'unknown' if unknown or not count else 'estimated' if estimated else 'measured')
        run = await db.get(RunRow, row.current_run_id) if row.current_run_id else None
        detail = task_item(row, (await run_items(db, [run]))[0] if run else None,
                           Usage(status=status, measured_tokens=measured, known_tokens=total))
        from agent_app.config_scheduling import describe_wait
        detail.execution_config_revision, detail.execution_wait_reason = await describe_wait(db, row, run)
        return detail


async def task_runs(task_id, offset, size):
    async with reading() as db:
        if await db.get(TaskRow, task_id) is None:
            raise GateDenied('TASK_NOT_FOUND', 404)
        rows = (await db.scalars(select(RunRow).where(RunRow.task_id == task_id)
                                 .order_by(RunRow.attempt.desc()).offset(offset).limit(size))).all()
        return await run_items(db, rows)


async def run_detail(run_id):
    async with reading() as db:
        row = await db.get(RunRow, run_id)
        if row is None:
            raise GateDenied('RUN_NOT_FOUND', 404)
        run = (await run_items(db, [row]))[0]
        history = (await db.scalars(select(ExecutionRow).where(ExecutionRow.run_id == run_id)
                                    .order_by(ExecutionRow.lease_token.desc()).limit(101))).all()
        run.executions = [Execution(execution_id=item.execution_id, worker_id=item.worker_id, sealed=item.sealed)
                          for item in history[:100]]
        run.executions_truncated = len(history) > 100
        return run


async def run_events(run_id, query, offset, size):
    async with reading() as db:
        if await db.get(RunRow, run_id) is None:
            raise GateDenied('RUN_NOT_FOUND', 404)
        result = (await db.execute(select(RunEventRow.seq, RunEventRow.turn, RunEventRow.name, RunEventRow.occurred_at)
                                   .where(RunEventRow.run_id == run_id, RunEventRow.seq > (query.after_seq or 0))
                                   .order_by(RunEventRow.seq).offset(offset).limit(size))).all()
        return [Event(seq=seq, turn=turn, name=name, occurred_at=utc(occurred)) for seq, turn, name, occurred in result]


def as_time(value):
    try:
        return utc(datetime.fromisoformat(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def call_item(row, run_id, payload):
    fact = row.start_fact or {}
    identity = fact.get('capability_identity') or row.intent.get('capability_identity') or {}
    kind = identity.get('kind')
    started = as_time(fact.get('started_at'))
    ended = as_time(payload.get('ended_at')) if payload else None
    usage = 'not_applicable' if kind in ('tool', 'skill') else observation_usage(payload) if payload else (
        'unsettled' if started else 'unknown')
    return Call(call_id=row.call_id, run_id=run_id, execution_id=row.execution_id,
                kind=kind if kind in ('model', 'tool', 'skill') else 'unknown',
                capability_id=identity.get('capability_id'), capability_version=fact.get('capability_version'),
                status=row.state, started_at=started, duration_ms=max(0, int((ended-started).total_seconds()*1000))
                if started and ended else None, usage_status=usage,
                known_tokens=tokens(payload) if payload and kind == 'model' else None)


def call_query():
    records = latest_observations()
    return (select(CallRow, ExecutionRow.run_id, records.c.payload)
            .join(ExecutionRow, ExecutionRow.execution_id == CallRow.execution_id)
            .outerjoin(records, and_(records.c.call_id == CallRow.call_id, records.c.rank == 1)))


async def run_calls(run_id, kind, offset, size):
    async with reading() as db:
        if await db.get(RunRow, run_id) is None:
            raise GateDenied('RUN_NOT_FOUND', 404)
        query = call_query().where(ExecutionRow.run_id == run_id)
        if kind:
            query = query.where(CallRow.intent['capability_identity']['kind'].as_string() == kind)
        rows = (await db.execute(query.order_by(CallRow.start_fact['started_at'].as_string().desc().nulls_last(),
                                               CallRow.call_id.desc()).offset(offset).limit(size))).all()
        return [call_item(*row) for row in rows]


async def skill_activated(name, resource_digest):
    if not resource_digest:
        return False
    capability_id = 'skill:' + name
    identity = SkillIdentity(schema_version=1, kind='skill', capability_id=capability_id,
                             resource_content_digest=resource_digest, dependency_digests=[])
    version = digest(identity.model_dump(mode='json'))
    async with reading() as db:
        return bool(await db.scalar(select(CallRow.call_id).where(
            CallRow.start_fact['capability_id'].as_string() == capability_id,
            CallRow.start_fact['capability_version'].as_string() == version,
            CallRow.state == 'completed',
        ).limit(1)))


async def latest_model_observation(*, provider_id=None, model_id=None):
    payload = ObservationRow.payload
    identity = payload['capability_identity']
    selector = identity['provider_id'].as_string() == provider_id if provider_id is not None else (
        identity['registry_model_id'].as_string() == model_id)
    async with reading() as db:
        latest = await db.scalar(select(payload).where(
            identity['kind'].as_string() == 'model', payload['phase'].as_string() == 'completed', selector,
        ).order_by(payload['observed_at'].as_string().desc().nulls_last(), ObservationRow.measurement_id.desc()).limit(1))
    if latest:
        observed_at = as_time(latest.get('observed_at'))
        identity = latest.get('capability_identity', {})
        observed_model = identity.get('registry_model_id')
        version = latest.get('capability_version')
        if observed_at and observed_model and version:
            outcome = latest.get('outcome')
            return ModelObservation(model_id=observed_model, capability_version=version, observed_at=observed_at,
                                    outcome=outcome if outcome in ('succeeded', 'failed', 'timed_out', 'cancelled')
                                    else 'unknown')
    return None


async def observed_tool_ids():
    capability = CallRow.start_fact['capability_id'].as_string()
    async with reading() as db:
        return (await db.scalars(select(capability).where(capability.like('tool:%'))
                                 .distinct().order_by(capability).limit(200))).all()


async def latest_tool_call(tool_id):
    async with reading() as db:
        row = (await db.execute(call_query().where(CallRow.start_fact['capability_id'].as_string() == tool_id)
                                .order_by(CallRow.start_fact['started_at'].as_string().desc(), CallRow.call_id.desc())
                                .limit(1))).first()
        return call_item(*row) if row else None


async def workers(offset, size, worker_id=None):
    now = now_utc()
    assignments = select(RunRow.run_id, RunRow.worker_id).where(RunRow.worker_id.is_not(None)).union(
        select(ExecutionRow.run_id, ExecutionRow.worker_id),
    ).subquery()
    rank = (select(RunRow.run_id, assignments.c.worker_id, func.row_number().over(partition_by=assignments.c.worker_id,
                    order_by=(RunRow.started_at.desc().nulls_last(), RunRow.created_at.desc(), RunRow.run_id.desc())).label('rank'))
            .join(assignments, RunRow.run_id == assignments.c.run_id))
    if worker_id:
        rank = rank.where(assignments.c.worker_id == worker_id)
    ranked = rank.subquery()
    async with reading() as db:
        assignments_page = (await db.execute(select(RunRow, ranked.c.worker_id)
                            .join(ranked, RunRow.run_id == ranked.c.run_id)
                            .where(ranked.c.rank == 1).order_by(ranked.c.worker_id)
                            .offset(offset).limit(size))).all()
        runs = [row for row, _ in assignments_page]
        ids = [worker for _, worker in assignments_page]
        by_worker = {}
        if ids:
            active_execution = exists(select(ExecutionRow.execution_id).where(
                ExecutionRow.run_id == RunRow.run_id, ExecutionRow.lease_token == RunRow.lease_token,
                ExecutionRow.sealed.is_(False)))
            counts = (await db.execute(select(RunRow.worker_id, func.count().filter(
                RunRow.lease_expires_at > now, active_execution), func.count().filter(RunRow.lease_expires_at <= now),
                func.count().filter(RunRow.lease_expires_at > now))
                .where(RunRow.status == 'running', RunRow.worker_id.in_(ids)).group_by(RunRow.worker_id))).all()
            by_worker = {key: (active, expired, valid) for key, active, expired, valid in counts}
        projected = await run_items(db, runs)
        result = []
        for (row, observed_worker), run in zip(assignments_page, projected, strict=True):
            active, expired, valid = by_worker.get(observed_worker, (0, 0, 0))
            # Superseded executions have no per-lease timestamps. Use the Run start as association evidence.
            last_activity = (row.completed_at if observed_worker == row.worker_id else None) or row.started_at or row.created_at
            result.append(Worker(worker_id=observed_worker, latest_run=run,
                                 last_activity=utc(last_activity),
                                 active_executions=active, expired_leases=expired,
                                 state='lease_observed' if valid else 'unknown'))
        return result


async def runtime():
    try:
        async with reading() as db:
            rows = (await db.scalars(select(RunRow).order_by(RunRow.created_at.desc(), RunRow.run_id.desc())
                                     .limit(20))).all()
            return Runtime(**snapshot('persisted_runs_and_executions'), runs=await run_items(db, rows))
    except GateDenied as exc:
        return Runtime(**snapshot('persisted_runs_and_executions', 'unavailable', exc.reason))


async def counts(from_at, to_at):
    start, end = window(from_at, to_at)
    values = dict(window_start=start, window_end=end)
    try:
        async with reading() as db:
            queued = await db.scalar(select(func.count()).select_from(TaskRow).where(TaskRow.status == 'queued'))
            running, expired = (await db.execute(select(func.count(), func.count().filter(RunRow.lease_expires_at <= now_utc()))
                                .select_from(RunRow).where(RunRow.status == 'running'))).one()
            failed = await db.scalar(select(func.count()).select_from(TaskRow).join(RunRow, RunRow.run_id == TaskRow.current_run_id)
                                     .where(TaskRow.status == 'failed', RunRow.completed_at >= start, RunRow.completed_at < end))
            rows = (await db.scalars(select(RunRow).where(RunRow.status.in_(['failed', 'timed_out']),
                                                          RunRow.completed_at >= start, RunRow.completed_at < end)
                                     .order_by(RunRow.completed_at.desc(), RunRow.run_id.desc()).limit(10))).all()
            return Counts(**snapshot('task_and_run_records'), **values, queued_tasks=queued, running_runs=running,
                          failed_tasks=failed, expired_leases=expired, recent_failures=await run_items(db, rows))
    except GateDenied as exc:
        return Counts(**snapshot('task_and_run_records', 'unavailable', exc.reason), **values)
