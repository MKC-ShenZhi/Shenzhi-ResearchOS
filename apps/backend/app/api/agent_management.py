"""Same-origin read-only Agent Registry catalog, protected by existing Admin auth."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from agent_contracts.management import CatalogQuery, Document, Key, Model, Page, Provider, Skill, Tool
from app.core.admin_auth import PATH, require_admin
from app.core.errors import BusinessError
from app.core.responses import ok
from app.integrations import agent_management as agent
from app.services.model_metadata import get_model_metadata

router = APIRouter(prefix=PATH + '/agent', tags=['agent-catalog'], dependencies=[Depends(require_admin)])


def response(data):
    result = ok(data.model_dump(mode='json'))
    result.headers['Cache-Control'] = 'no-store'
    return result


@router.get('/model-metadata/{model_id:path}')
async def model_metadata(model_id: Key):
    return response(get_model_metadata(model_id))


class SkillDocument(BaseModel):
    resource_digest: Key


def read_endpoint(path, response_type, query_type):
    async def endpoint(request: Request):
        try:
            query = query_type.model_validate(dict(request.query_params)) if query_type else None
        except ValidationError:
            raise BusinessError(20001, '请求参数不合法', 422) from None
        values = query.model_dump(mode='json', exclude_none=True) if query else {}
        return response(await agent.read(agent.management_path(path, request.path_params), response_type, values))
    return endpoint


for path, response_type, query_type in (
    ('/providers', Page[Provider], CatalogQuery), ('/providers/{provider_id}', Provider, None),
    ('/models', Page[Model], CatalogQuery), ('/models/{model_id:path}', Model, None),
    ('/tools', Page[Tool], CatalogQuery), ('/tools/{tool_id}', Tool, None),
    ('/skills', Page[Skill], CatalogQuery), ('/skills/{skill_name}/document', Document, SkillDocument),
    ('/skills/{skill_name}', Skill, None),
):
    router.add_api_route(path, read_endpoint(path, response_type, query_type), methods=['GET'], name='agent_catalog' + path)
