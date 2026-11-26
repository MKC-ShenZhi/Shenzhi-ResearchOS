"""Same-origin, read-only Agent management API."""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError

from agent_contracts.management import (
    Call, CallQuery, CatalogQuery, Document, Event, EventQuery, Key, Model, Page,
    Pagination, Provider, Run, Skill, Task, TaskQuery, Tool, Worker,
)
from app.core.admin_auth import PATH, require_admin
from app.core.errors import BusinessError
from app.core.responses import ok
from app.integrations import agent_management as agent
from app.services import agent_management as management

router = APIRouter(prefix=PATH + '/agent', tags=['agent-management'], dependencies=[Depends(require_admin)])


@router.get('/overview')
async def overview(from_at: datetime | None = None, to_at: datetime | None = None):
    query = {k: v.isoformat() for k, v in {'from_at': from_at, 'to_at': to_at}.items() if v is not None}
    data = await management.overview(query, from_at, to_at)
    return response(data)


def response(data):
    result = ok(data.model_dump(mode='json'))
    result.headers['Cache-Control'] = 'no-store'
    return result


class Context(BaseModel):
    policy_revision: Key | None = None
    run_id: Key | None = None


class SkillDocument(BaseModel):
    resource_digest: Key


def read_endpoint(path, response_type, query_type):
    async def endpoint(request: Request):
        try:
            query = query_type.model_validate(dict(request.query_params)) if query_type else None
        except ValidationError:
            raise BusinessError(20001, '请求参数不合法', 422) from None
        values = query.model_dump(mode='json', exclude_none=True) if query else {}
        revision = values.pop('policy_revision', None)
        url = agent.management_path(path, request.path_params)
        if isinstance(query, TaskQuery):
            management.time_window(query.from_at, query.to_at)
        data = await agent.read(url, response_type, values)
        if response_type is Task:
            data.backend_usage = await management.task_usage(data)
        await management.apply_policy(data, revision)
        return response(data)

    return endpoint


for path, response_type, query_type in (
    ('/workers', Page[Worker], Pagination), ('/workers/{worker_id}', Worker, None),
    ('/providers', Page[Provider], CatalogQuery), ('/providers/{provider_id}', Provider, Context),
    ('/models', Page[Model], CatalogQuery), ('/models/{model_id:path}', Model, Context),
    ('/tools', Page[Tool], CatalogQuery), ('/tools/{tool_id}', Tool, Context),
    ('/skills', Page[Skill], CatalogQuery), ('/skills/{skill_name}/document', Document, SkillDocument),
    ('/skills/{skill_name}', Skill, Context),
    ('/tasks', Page[Task], TaskQuery), ('/tasks/{task_id}', Task, None),
    ('/tasks/{task_id}/runs', Page[Run], Pagination), ('/runs/{run_id}', Run, None),
    ('/runs/{run_id}/events', Page[Event], EventQuery), ('/runs/{run_id}/calls', Page[Call], CallQuery),
):
    router.add_api_route(path, read_endpoint(path, response_type, query_type), methods=['GET'], name='agent_management' + path)
