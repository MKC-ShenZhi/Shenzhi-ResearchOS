"""Internal-only business-data cleanup for the Web account-deletion orchestrator."""

from fastapi import APIRouter, Request

from app.core.errors import BusinessError
from app.core.identity import request_identity
from app.core.responses import ok
from app.services.account_deletion import AccountDeletionService

router = APIRouter(prefix='/api/v1/account-deletion', tags=['account-deletion'])
service = AccountDeletionService()


def deletion_user_id(request: Request) -> str:
    identity = request_identity(request)
    if identity.kind != 'user':
        raise BusinessError(10001, '请登录后注销账号', 401)
    # The generic BFF forwards an allowlist of browser headers and never
    # forwards this internal orchestration marker.
    if request.headers.get('x-shenzhi-account-deletion') != '1':
        raise BusinessError(10001, '请通过账号注销流程执行', 403)
    return identity.subject_id


@router.post('/cleanup')
async def cleanup_business_data(request: Request):
    result = await service.delete_all_for_user(deletion_user_id(request))
    return ok({
        'profiles_deleted': result.profiles_deleted,
        'settings_deleted': result.settings_deleted,
        'chat_sessions_deleted': result.chat_sessions_deleted,
    })
