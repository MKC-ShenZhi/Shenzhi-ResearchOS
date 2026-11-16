from fastapi import APIRouter, Depends

from app.core.identity import MigrationIdentity, migration_identity, require_bff
from app.core.responses import ok
from app.schemas.identity import AnonymousClaimResult
from app.services.identity.anonymous_claim import claim_anonymous_sessions

router = APIRouter(prefix='/api/v1/identity', tags=['identity'])


@router.get('/bootstrap')
def bootstrap(_credential: None = Depends(require_bff)):
    """Lightweight first contact; the BFF issues the anonymous cookie on success."""
    return ok({})


@router.post('/anonymous-claim')
async def claim(identity: MigrationIdentity = Depends(migration_identity)):
    result = await claim_anonymous_sessions(identity.source_owner, identity.target_owner)
    return ok(AnonymousClaimResult(**result).model_dump())
