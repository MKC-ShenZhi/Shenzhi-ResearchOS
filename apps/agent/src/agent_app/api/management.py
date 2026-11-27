"""Read-only registry catalog. No execution or management database dependencies."""
import asyncio
import base64
import binascii
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from agent_contracts.canonical import digest
from agent_contracts.management import CatalogQuery, Key
from agent_app import management_catalog as catalog
from agent_app.control.metering import GateDenied, now_utc
from .routes import V2Route, role


class NoStoreRoute(V2Route):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            response = await handler(request)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return handle


router = APIRouter(prefix='/internal/v2/management',
    dependencies=[Depends(role('AGENT_MANAGEMENT_TOKEN'))], route_class=NoStoreRoute)
MAX_OFFSET = 10_000


def result(value):
    return {'schema_version': 1, 'data': value}


def page_offset(scope, query):
    identity = digest([scope, query.model_dump(mode='json', exclude={'cursor'})])
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



@router.get('/providers')
async def providers(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('providers', query, lambda: catalog.llm_catalog()[0])


@router.get('/providers/{provider_id}')
async def provider(provider_id: Key):
    return result(await catalog_entry(lambda: catalog.llm_catalog()[0], provider_id))


@router.get('/models')
async def models(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('models', query, lambda: catalog.llm_catalog()[1])


@router.get('/models/{model_id:path}')
async def model(model_id: Key):
    return result(await catalog_entry(lambda: catalog.llm_catalog()[1], model_id))


@router.get('/tools')
async def tools(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('tools', query, catalog.tool_catalog)


@router.get('/tools/{tool_id}')
async def tool(tool_id: Key):
    return result(await catalog_entry(catalog.tool_catalog, tool_id))


@router.get('/skills')
async def skills(query: Annotated[CatalogQuery, Query()]):
    return await catalog_page('skills', query, catalog.skill_catalog)


@router.get('/skills/{skill_name}/document')
async def skill_document(skill_name: Key, resource_digest: Key):
    return result(await asyncio.to_thread(catalog.skill_document, skill_name, resource_digest))


@router.get('/skills/{skill_name}')
async def skill(skill_name: Key):
    return result(await catalog_entry(catalog.skill_catalog, skill_name))
