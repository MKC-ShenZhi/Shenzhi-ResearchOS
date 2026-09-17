"""Personal profile API, scoped to the trusted authenticated identity."""

from fastapi import APIRouter, Request

from app.core.errors import BusinessError
from app.core.identity import request_identity
from app.core.responses import ok
from app.schemas.profile import UserProfilePatch
from app.services.user.profile import ProfileService

router = APIRouter(prefix='/api/v1/profile', tags=['profile'])
service = ProfileService()


def authenticated_user_id(request: Request) -> str:
    identity = request_identity(request)
    if identity.kind != 'user':
        raise BusinessError(10001, '请登录后管理个人资料', 401)
    return identity.subject_id


@router.get('')
async def get_profile(request: Request):
    profile = await service.get(authenticated_user_id(request))
    return ok(profile.model_dump(mode='json'))


@router.patch('')
async def patch_profile(request: Request, patch: UserProfilePatch):
    profile = await service.patch(authenticated_user_id(request), patch)
    return ok(profile.model_dump(mode='json'))
