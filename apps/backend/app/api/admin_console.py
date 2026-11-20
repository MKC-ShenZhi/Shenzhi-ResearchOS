from fastapi import APIRouter, Depends, Query, Request
from app.core import admin_auth
from app.core.database import session_scope
from app.core.responses import ok
from app.schemas.admin import AdminUsersResponse
from app.schemas.admin_console import AdminLogin
from app.services.admin_users import list_users
from app.integrations.admin_console.capabilities import get_capabilities

router = APIRouter(prefix=admin_auth.PATH, tags=['admin-console'])


@router.post('/auth/login')
def login(body: AdminLogin, request: Request):
    token, ttl = admin_auth.login(request, body.username, body.password)
    response = ok({'username': body.username})
    response.set_cookie(admin_auth.COOKIE, token, max_age=ttl, httponly=True,
                        samesite='strict', secure=request.url.scheme == 'https', path=admin_auth.PATH)
    return response


@router.post('/auth/logout')
def logout(_admin=Depends(admin_auth.require_admin)):
    response = ok({})
    response.delete_cookie(admin_auth.COOKIE, path=admin_auth.PATH, httponly=True, samesite='strict')
    return response


@router.get('/auth/me')
def me(username=Depends(admin_auth.require_admin)):
    return ok({'username': username})


@router.get('/users')
async def users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                search: str = Query('', max_length=255), plan_id: str | None = Query(None, max_length=255),
                _admin=Depends(admin_auth.require_admin)):
    async with session_scope() as db:
        result = await list_users(db, page=page, page_size=page_size, search=search.strip(), plan_id=plan_id)
    return ok(AdminUsersResponse.model_validate(result).model_dump(mode='json'))


@router.get('/capabilities')
async def capabilities(_admin=Depends(admin_auth.require_admin)):
    return ok(await get_capabilities())
