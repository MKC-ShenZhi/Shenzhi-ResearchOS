from fastapi import APIRouter, Depends, Query, Request
import os
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
def me(request: Request):
    if os.getenv('ADMIN_AUTH_MODE') == 'ssh_tunnel':
        username, token, ttl = admin_auth.tunnel_session(request)
        response = ok({'username': username, 'mode': 'ssh_tunnel'})
        response.set_cookie(admin_auth.COOKIE, token, max_age=ttl, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', path=admin_auth.PATH)
        response.headers['Cache-Control'] = 'no-store'
        return response
    return ok({'username': admin_auth.require_admin(request), 'mode': 'local_password'})


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


from app.schemas.admin_plans import PublishPlans, AssignPlans, MigrationPreview
from app.schemas.admin_plans import ReconcileGrant
from app.services.agent_entitlements.reconciliation import reconcile
from app.services.agent_entitlements import admin as plan_admin


@router.get('/plans')
async def plans(_admin=Depends(admin_auth.require_admin)):
    async with session_scope() as db:
        return ok(await plan_admin.plans_view(db))


@router.post('/plans/publish')
async def publish_plans(body: PublishPlans, principal=Depends(admin_auth.require_admin_write)):
    runtime = await get_capabilities()
    async with session_scope() as db:
        return ok(await plan_admin.publish(db, body, principal, runtime))


@router.post('/entitlements/assign')
async def assign_plans(body: AssignPlans, principal=Depends(admin_auth.require_admin_write)):
    async with session_scope() as db:
        return ok(await plan_admin.assign(db, body, principal))


@router.post('/migration/preview')
async def migration_preview(body: MigrationPreview, _admin=Depends(admin_auth.require_admin_write)):
    async with session_scope() as db:
        return ok(await plan_admin.migration_preview(db, body.before, body.limit))


@router.post('/grants/{grant_id}/reconcile-close')
async def reconcile_close(grant_id: str, body: ReconcileGrant,
                          principal=Depends(admin_auth.require_admin_write)):
    result = await reconcile(grant_id, body, principal)
    if not result['eligible']:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={'data': result})
    return ok(result)


@router.get('/audit')
async def audit(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                _admin=Depends(admin_auth.require_admin)):
    async with session_scope() as db:
        return ok(await plan_admin.list_audit(db, page=page, page_size=page_size))
