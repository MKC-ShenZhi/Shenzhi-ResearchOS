from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from app.core.config import MAX_FILES, UPLOAD_ACCEPT, model_config
from app.core.errors import BusinessError
from app.core.identity import MigrationIdentity, migration_identity, request_owner, require_bff
from app.core.responses import ok
from app.schemas.chat import AnonymousClaimResult, CreateSessionBody, FollowupBody, UpdateSessionBody
from app.services.chat import prepare_message, stop_message, stream_events
from app.services.sessions import repository

router = APIRouter(prefix='/api/v1/chat', tags=['chat'])


@router.get('/config')
def chat_config(_credential: None = Depends(require_bff)):
    config = model_config()
    return ok({'models': [{'value': model, 'label': model, 'provider': config.provider,
                          'enabled': bool(config.key),
                          **({} if config.key else {'reason': 'provider_not_configured'})}
                         for model in config.models],
               'default_model': config.model,
               'modes': ['fast', 'deep', 'idea', 'doubt'],
               'quota': {'used': 0, 'limit': 0, 'deep_used': 0, 'deep_limit': 0},
               'quota_enforced': False,
               'upload': {'max_size_mb': 20, 'max_files': MAX_FILES, 'accept': UPLOAD_ACCEPT}})


@router.get('/sessions')
async def list_sessions(owner: str = Depends(request_owner)):
    return ok({'sessions': await repository.list(owner), 'ephemeral': not repository.is_durable})


@router.post('/anonymous-claim')
async def claim_anonymous_sessions(identity: MigrationIdentity = Depends(migration_identity)):
    result = await repository.claim_anonymous_sessions(
        identity.source_owner,
        identity.target_owner,
    )
    return ok(AnonymousClaimResult(**result).model_dump())


@router.post('/sessions')
async def create_session(body: CreateSessionBody, owner: str = Depends(request_owner)):
    message = await prepare_message(body, owner)
    return ok({'session_id': message.session_id, 'message_id': message.id})


@router.get('/sessions/{session_id}')
async def get_session(session_id: str, owner: str = Depends(request_owner)):
    return ok((await repository.get(session_id, owner)).public(detail=True))


@router.patch('/sessions/{session_id}')
async def update_session(session_id: str, body: UpdateSessionBody, owner: str = Depends(request_owner)):
    session = await repository.update(session_id, owner, title=body.title, favorite=body.favorite)
    return ok(session.public())


@router.delete('/sessions/{session_id}')
async def delete_session(session_id: str, owner: str = Depends(request_owner)):
    session = await repository.get(session_id, owner)
    for message in session.messages:
        await stop_message(message)
    await repository.delete(session_id, owner)
    return ok({'ok': True})


@router.post('/sessions/{session_id}/messages')
async def followup(session_id: str, body: FollowupBody, owner: str = Depends(request_owner)):
    message = await prepare_message(body, owner, await repository.get(session_id, owner))
    return ok({'session_id': session_id, 'message_id': message.id})


@router.get('/messages/{message_id}/stream')
async def stream(message_id: str, owner: str = Depends(request_owner),
                 last_event_id: str | None = Header(default=None)):
    message = await repository.message(message_id, owner)
    try:
        cursor = int(last_event_id or '0')
    except ValueError:
        raise BusinessError(20001, '无效的 SSE 游标') from None
    if cursor < 0 or cursor > len(message.events):
        raise BusinessError(20001, 'SSE 游标超出范围')
    return StreamingResponse(stream_events(message, cursor), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


@router.post('/messages/{message_id}/stop')
async def stop(message_id: str, owner: str = Depends(request_owner)):
    await stop_message(await repository.message(message_id, owner))
    return ok({'ok': True})


@router.post('/messages/{message_id}/resume')
async def resume(message_id: str, owner: str = Depends(request_owner)):
    message = await repository.message(message_id, owner)
    session = await repository.get(message.session_id, owner)
    if session.messages[-1].id != message.id or message.status not in ('stopped', 'failed'):
        raise BusinessError(20009, '仅支持继续最近一条已停止或失败的回答', 409)
    await stop_message(message)
    cursor = str(len(message.events))
    message.status, message.error, message.task = 'streaming', None, None
    message.stop_requested = False
    try:
        await repository.persist_message(message)
    except Exception as exc:
        # Do not leave the in-memory message looking runnable when the durable
        # reset was rejected by the database.  The global handler still
        # returns a safe 500, while a later resume can retry from the terminal
        # state.
        message.status = 'failed'
        message.error = '对话恢复失败，请稍后重试'
        raise BusinessError(20004, message.error, 503) from exc
    return ok({'session_id': session.id, 'message_id': message.id, 'last_event_id': cursor})
