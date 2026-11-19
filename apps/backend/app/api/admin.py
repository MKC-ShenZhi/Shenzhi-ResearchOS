import os

from fastapi import APIRouter, Depends, Query, Request

from app.core.database import session_scope
from app.core.errors import BusinessError
from app.core.identity import require_user
from app.core.responses import ok
from app.services.admin_users import list_users
from app.schemas.admin import AdminUsersResponse

router = APIRouter(prefix='/api/v1/admin', tags=['admin'])


def require_admin(request: Request):
    identity = require_user(request)
    allowed = {value.strip() for value in os.getenv('SHENZHI_ADMIN_USER_IDS', '').split(',') if value.strip()}
    if identity.subject_id not in allowed:
        raise BusinessError(10001, '需要管理员权限', 403)
    return identity


@router.get('/access')
def access(_admin=Depends(require_admin)):
    response = ok({'read_only': True})
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/users')
async def users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                search: str = Query('', max_length=255), plan_id: str | None = Query(None, max_length=255),
                _admin=Depends(require_admin)):
    async with session_scope() as db:
        result = await list_users(db, page=page, page_size=page_size, search=search.strip(), plan_id=plan_id)
    response = ok(AdminUsersResponse.model_validate(result).model_dump(mode='json'))
    response.headers['Cache-Control'] = 'no-store'
    return response
