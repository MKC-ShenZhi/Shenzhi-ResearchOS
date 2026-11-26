"""Standalone v2 management API. The execution routers never depend on it."""
import asyncio
import base64
import binascii
import hashlib
import json
import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from agent_contracts.canonical import digest
from agent_contracts.management import CallQuery, CatalogQuery, EventQuery, Key, Pagination, TaskQuery
from agent_contracts.management_phase2 import DiagnosticRequest, Identifier, ProbeRequest, Target, WorkerReport
from agent_app import management_catalog as catalog, management_observations as observations
from agent_app import management_checks, management_diagnostics, management_workers
from agent_app.control.metering import GateDenied, now_utc
from agent_contracts.management_operations import CheckSummaryRequest
from agent_contracts.management_operations import ModelReferences
from .v2 import V2Route, role

MANAGEMENT_TOKEN = 'AGENT_MANAGEMENT_TOKEN'


class NoStoreRoute(V2Route):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                if request.method in ('PUT', 'POST'):
                    length = request.headers.get('content-length', '')
                    if not length.isdigit() or len(length) > 7 or int(length) > 524_288:
                        return JSONResponse(status_code=413, headers={'Cache-Control': 'no-store'},
                                            content={'error': {'schema_version': 1, 'reason_code': 'BODY_LIMIT'}})
                async with asyncio.timeout(8 if request.method == 'POST' else 4):
                    response = await handler(request)
                if len(response.body) <= 2 * 1024 * 1024:
                    response.headers['Cache-Control'] = 'no-store'
                    return response
                reason, status = 'RESPONSE_TOO_LARGE', 503
            except (TimeoutError, OSError, SQLAlchemyError):
                reason, status = 'MANAGEMENT_DEPENDENCY_UNAVAILABLE', 503
            return JSONResponse(status_code=status, headers={'Cache-Control': 'no-store'},
                                content={'error': {'schema_version': 1, 'reason_code': reason}})

        return handle


def reject_report_role_reuse(role_name=MANAGEMENT_TOKEN):
    token = os.getenv(role_name, '').strip()
    try:
        identities = json.loads(os.getenv('AGENT_WORKER_REPORT_IDENTITIES') or '{}')
        collision = hashlib.sha256(token.encode()).hexdigest() in identities.values()
    except (ValueError, AttributeError):
        raise GateDenied('ROLE_CREDENTIALS_NOT_ISOLATED', 503) from None
    if collision:
        raise GateDenied('ROLE_CREDENTIALS_NOT_ISOLATED', 503)


require_management = role(MANAGEMENT_TOKEN)


def reject_management_report_reuse():
    reject_report_role_reuse()


router = APIRouter(prefix='/internal/v2/management', dependencies=[Depends(require_management), Depends(reject_management_report_reuse)],
                   route_class=NoStoreRoute)


@router.post('/identities')
async def identities(body: CheckSummaryRequest):
    def load():
        providers, models = catalog.llm_catalog()
        tools, skills = catalog.tool_catalog(), catalog.skill_catalog()
        values = {}
        for target in body.targets:
            key, version = target.target_id, None
            if target.kind == 'provider' and key in providers:
                registry = management_checks.load_registry()
                version = digest(registry.providers[key].spec.model_dump(mode='json'))
            elif target.kind == 'model' and key in models:
                version = models[key].capability_version
            elif target.kind == 'tool' and key in tools:
                version = tools[key].capability_version
            elif target.kind == 'skill' and key in skills:
                version = skills[key].resource_digest
            values[target.kind + '/' + key] = version
        return values
    return result(await asyncio.to_thread(load))


@router.get('/alerts')
async def alerts(offset: Annotated[int, Query(ge=0, le=10000)] = 0,
                 limit: Annotated[int, Query(ge=1, le=100)] = 20):
    from agent_app.management_operations import alerts as read_alerts
    return result(await read_alerts(offset, limit))


@router.post('/model-references')
async def model_references(body: ModelReferences):
    from sqlalchemy import select, func
    from agent_app.infrastructure.models import TaskRow
    async with observations.reading() as db:
        model = TaskRow.request_json['model'].as_string()
        rows = (await db.execute(select(model, TaskRow.status, func.count()).where(
            model.in_(body.model_ids)).group_by(model, TaskRow.status))).all()
    return result(dict(persisted_task_references=[dict(model_id=key, status=status, count=count)
        for key, status, count in rows], external_clients='unknown'))


@router.get('/worker-control/{worker_id}')
async def worker_control(worker_id: Identifier):
    from agent_app.management_operations import drain_state
    return result(await drain_state(worker_id))


report_router = APIRouter(prefix='/internal/v2/worker-reports', dependencies=[Depends(management_workers.require_reporter)],
                          route_class=NoStoreRoute)
MAX_OFFSET = 10_000


@report_router.put('/{worker_id}')
async def worker_report(worker_id: Identifier, report: WorkerReport):
    return result(await management_workers.save(worker_id, report))


@router.get('/worker-evidence')
async def worker_evidence(query: Annotated[Pagination, Query()]):
    return await page('worker-evidence', query, management_workers.list_workers)


@router.get('/worker-evidence/{worker_id}')
async def worker_evidence_detail(worker_id: Identifier):
    workers = await management_workers.list_workers(0, 1, worker_id, include_manifest=True)
    if not workers:
        raise GateDenied('WORKER_NOT_OBSERVED', 404)
    return result(workers[0])


@router.get('/worker-evidence/{worker_id}/manifests')
async def worker_manifest_history(worker_id: Identifier, query: Annotated[Pagination, Query()]):
    return await page('manifest-history/' + worker_id, query,
                      lambda offset, limit: management_workers.manifest_history(worker_id, offset, limit))


@router.get('/capability-evidence')
async def capability_evidence(kind: Target, target_id: Identifier, query: Annotated[Pagination, Query()]):
    return await page('capability/' + kind + '/' + target_id, query,
                      lambda offset, limit: management_workers.capability_evidence(kind, target_id, offset, limit))


@router.post('/checks')
async def active_check(request: ProbeRequest):
    return result(await management_checks.check(request))


@router.post('/diagnostics')
async def diagnostics(request: DiagnosticRequest):
    return result(await management_diagnostics.diagnose(request.kind, request.target_id))


def result(value):
    return {'schema_version': 1, 'data': value}


def page_offset(scope, query):
    identity = digest([scope, query.model_dump(mode='json', exclude={'cursor', 'policy_revision'})])
    if not query.cursor:
        return identity, 0
    try:
        raw = base64.urlsafe_b64decode(query.cursor.encode('ascii'))
        key, offset = json.loads(raw)
        if key == identity and type(offset) is int and 0 <= offset <= MAX_OFFSET:
            return identity, offset
    except (ValueError, TypeError, binascii.Error):
        pass
    raise GateDenied('CURSOR_INVALID', 422)


async def page(scope, query, load):
    identity, offset = page_offset(scope, query)
    values = await load(offset, query.limit + 1)
    next_offset = offset + query.limit
    cursor = None
    if len(values) > query.limit and next_offset <= MAX_OFFSET:
        cursor = base64.urlsafe_b64encode(json.dumps([identity, next_offset]).encode()).decode()
    return result(dict(items=values[:query.limit], observed_at=now_utc(), next_cursor=cursor))


async def catalog_page(scope, query, factory):
    async def items(offset, size):
        entries = await asyncio.to_thread(factory)
        search = query.search.strip().casefold()
        ids = [item for item in sorted(entries, reverse=query.order == 'desc') if search in item.casefold()]
        return [entries[item] for item in ids[offset:offset + size]]

    return await page(scope, query, items)


async def catalog_entry(factory, key):
    entry = (await asyncio.to_thread(factory)).get(key)
    if entry is None:
        raise GateDenied('RESOURCE_NOT_FOUND', 404)
    return entry


async def worker_health():
    try:
        if await management_workers.list_workers(0, 1):
            return observations.snapshot('worker_heartbeat_reports')
    except GateDenied:
        pass
    return observations.snapshot('persisted_run_leases', 'unknown', 'WORKER_HEARTBEAT_NOT_AVAILABLE')


@router.get('/overview')
async def overview(from_at: datetime | None = None, to_at: datetime | None = None):
    db, runtime, counts, workspace, worker_summary = await asyncio.gather(
        observations.database_health(), observations.runtime(), observations.counts(from_at, to_at),
        asyncio.to_thread(observations.workspace_health), worker_health(),
    )
    return result(dict(
        api=dict(**observations.snapshot('agent_api_response'),
                 build_revision=os.getenv('AGENT_BUILD_REVISION', '').strip()[:255] or None),
        agent_db=db, workspace=workspace, runtime=runtime, counts=counts,
        workers=worker_summary,
    ))


@router.get('/workers')
async def workers(query: Annotated[Pagination, Query()]):
    return await page('workers', query, observations.workers)


@router.get('/workers/{worker_id}')
async def worker(worker_id: Key):
    values = await observations.workers(0, 1, worker_id)
    if not values:
        raise GateDenied('WORKER_NOT_OBSERVED', 404)
    return result(values[0])


@router.get('/providers')
async def providers(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('providers', query, lambda: catalog.llm_catalog()[0])


async def attach_model_observation(entry, **identity):
    try:
        entry.latest_observation = await observations.latest_model_observation(**identity)
    except GateDenied as exc:
        if exc.status != 503:
            raise
    return result(entry)


@router.get('/providers/{provider_id}')
async def provider(provider_id: Key):
    entry = await catalog_entry(lambda: catalog.llm_catalog()[0], provider_id)
    return await attach_model_observation(entry, provider_id=provider_id)


@router.get('/models')
async def models(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('models', query, lambda: catalog.llm_catalog()[1])


@router.get('/models/{model_id:path}')
async def model(model_id: Key):
    entry = await catalog_entry(lambda: catalog.llm_catalog()[1], model_id)
    return await attach_model_observation(entry, model_id=model_id)


def observed_tool(tool_id, recent=None):
    return dict(tool_id=tool_id, name=tool_id.removeprefix('tool:'), description='',
                source='persisted_call', registration='observed_only', states={}, conditions=[],
                parameters_schema=None, schema_digest=None,
                capability_version=recent.capability_version if recent else None)


@router.get('/tools')
async def tools(query: Annotated[CatalogQuery, Query()]):
    async def items(offset, size):
        entries = await asyncio.to_thread(catalog.tool_catalog)
        try:
            for tool_id in await observations.observed_tool_ids():
                entries.setdefault(tool_id, observed_tool(tool_id))
        except GateDenied as exc:
            if exc.status != 503:
                raise
        search = query.search.strip().casefold()
        keys = [key for key in sorted(entries, reverse=query.order == 'desc') if search in key.casefold()]
        return [entries[key] for key in keys[offset:offset + size]]

    return await page('tools', query, items)


@router.get('/tools/{tool_id}')
async def tool(tool_id: Key, run_id: Key | None = None):
    try:
        recent = await observations.latest_tool_call(tool_id)
    except GateDenied as exc:
        if exc.status != 503:
            raise
        recent = None
    entry = (await asyncio.to_thread(catalog.tool_catalog)).get(tool_id)
    if entry is None and recent is None:
        raise GateDenied('RESOURCE_NOT_FOUND', 404)
    if entry is None:
        entry = observed_tool(tool_id, recent)
    else:
        entry = entry.model_dump()
    runtime = await observations.tool_runtime(tool_id, run_id) if run_id else None
    if runtime:
        entry.update(latent=runtime['latent'], run_callable=runtime['run_callable'])
        if runtime.get('observed_at'):
            entry['states']['loaded'] = dict(state=runtime['loaded'], source='authenticated_worker_runtime',
                observed_at=runtime['observed_at'], worker_id=runtime['worker_id'])
    return result(dict(entry, latest_call=recent, runtime_evidence=runtime))


@router.get('/skills')
async def skills(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('skills', query, catalog.skill_catalog)


@router.get('/skills/{skill_name}/document')
async def skill_document(skill_name: Key, resource_digest: Key):
    return result(await asyncio.to_thread(catalog.skill_document, skill_name, resource_digest))


@router.get('/skills/{skill_name}')
async def skill(skill_name: Key):
    entry = await catalog_entry(catalog.skill_catalog, skill_name)
    try:
        if await observations.skill_activated(skill_name, entry.resource_digest):
            entry.activated = 'yes'
        entry.activation_contexts = await observations.skill_contexts(skill_name, entry.resource_digest)
    except GateDenied as exc:
        if exc.status != 503:
            raise
    return result(entry)


@router.get('/tasks')
async def tasks(query: Annotated[TaskQuery, Query()]):
    return await page('tasks', query, lambda offset, size: observations.tasks(query, offset, size))


@router.get('/tasks/{task_id}')
async def task(task_id: Key):
    return result(await observations.task_detail(task_id))


@router.get('/tasks/{task_id}/runs')
async def task_runs(task_id: Key, query: Annotated[Pagination, Query()]):
    return await page(task_id + '/runs', query, lambda offset, size: observations.task_runs(task_id, offset, size))


@router.get('/runs/{run_id}')
async def run(run_id: Key):
    return result(await observations.run_detail(run_id))


@router.get('/runs/{run_id}/events')
async def events(run_id: Key, query: Annotated[EventQuery, Query()]):
    return await page(run_id + '/events', query, lambda offset, size: observations.run_events(run_id, query, offset, size))


@router.get('/runs/{run_id}/calls')
async def calls(run_id: Key, query: Annotated[CallQuery, Query()]):
    return await page(run_id + '/calls', query, lambda offset, size: observations.run_calls(run_id, query.kind, offset, size))
