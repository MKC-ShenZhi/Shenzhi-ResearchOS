"""Personal settings API, available only to trusted authenticated identities."""

from fastapi import APIRouter, Request

from app.core.errors import BusinessError
from app.core.identity import request_identity
from app.core.responses import ok
from app.schemas.settings import UserSettingsPatch
from app.services.settings import SettingsService

router = APIRouter(prefix='/api/v1/settings', tags=['settings'])
service = SettingsService()


def authenticated_user_id(request: Request) -> str:
    identity = request_identity(request)
    if identity.kind != 'user':
        raise BusinessError(10001, '请登录后管理个人设置', 401)
    return identity.subject_id


@router.get('')
async def get_settings(request: Request):
    settings = await service.get(authenticated_user_id(request))
    return ok(settings.model_dump(mode='json'))


@router.patch('')
async def patch_settings(request: Request, patch: UserSettingsPatch):
    settings = await service.patch(authenticated_user_id(request), patch)
    return ok(settings.model_dump(mode='json'))
