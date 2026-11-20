from fastapi import APIRouter, Depends

from app.core.identity import MigrationIdentity, migration_identity, require_bff
from app.core.responses import ok
from app.schemas.identity import AnonymousClaimResult
from app.services.identity.anonymous_claim import claim_anonymous_sessions
from app.core.identity import require_user, RequestIdentity

router = APIRouter(prefix='/api/v1/identity', tags=['identity'])


@router.post('/entitlements/initialize')
async def initialize_entitlements(identity: RequestIdentity = Depends(require_user)):
    from app.core.database import session_scope
    from app.services.agent_entitlements.defaults import initialize_free
    from app.services.agent_entitlements.service import EntitlementError
    from app.core.errors import BusinessError
    try:
        async with session_scope() as db:
            count = await initialize_free(db, identity.subject_id)
    except EntitlementError as exc:
        raise BusinessError(20004, exc.reason, exc.status) from exc
    return ok({'initialized': count})


@router.get('/bootstrap')
def bootstrap(_credential: None = Depends(require_bff)):
    """Lightweight first contact; the BFF issues the anonymous cookie on success."""
    return ok({})


@router.post('/anonymous-claim')
async def claim(identity: MigrationIdentity = Depends(migration_identity)):
    result = await claim_anonymous_sessions(identity.source_owner, identity.target_owner)
    return ok(AnonymousClaimResult(**result).model_dump())
