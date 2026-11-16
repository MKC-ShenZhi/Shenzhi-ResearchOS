"""Paper likes and topic follows owned by the authenticated Better Auth user.

Public counters are readable by anonymous visitors; every personal field and
every write requires the trusted BFF identity, so a browser-supplied user id is
never accepted.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.core.errors import BusinessError
from app.core.identity import RequestIdentity, request_identity, require_user
from app.core.responses import ok
from app.schemas.interactions import (
    LikeStateResponse,
    PaperInteractionItem,
    PaperInteractionsRequest,
    PaperInteractionsResponse,
    TopicFollowListResponse,
    TopicFollowStateResponse,
    TopicInteractionItem,
    TopicInteractionsRequest,
    TopicInteractionsResponse,
)
from app.services.library.interactions import InteractionService
from app.services.library.paper_likes import PaperLikeService
from app.services.library.topic_follows import TopicFollowService


router = APIRouter(prefix='/api/v1', tags=['interactions'])
interactions = InteractionService()
likes = PaperLikeService()
follows = TopicFollowService()

MAX_IDENTIFIER_LENGTH = 300


def _identifier(value: str, label: str) -> str:
    trimmed = value.strip()
    if not trimmed or trimmed != value or len(trimmed) > MAX_IDENTIFIER_LENGTH:
        raise BusinessError(20001, f'{label} 不合法', 422)
    return trimmed


@router.post('/papers/interactions')
async def paper_interactions(
    body: PaperInteractionsRequest,
    identity: RequestIdentity = Depends(request_identity),
):
    user_id = identity.subject_id if identity.kind == 'user' else None
    states = await interactions.paper_states(user_id, body.paper_ids)
    return ok(PaperInteractionsResponse(
        authenticated=user_id is not None,
        user_id=user_id,
        items=[PaperInteractionItem(**asdict(state)) for state in states],
    ).model_dump(mode='json'))


@router.put('/papers/{paper_id}/like')
async def like_paper(paper_id: str, identity: RequestIdentity = Depends(require_user)):
    resolved = _identifier(paper_id, '论文 ID')
    count = await likes.like(identity.subject_id, resolved)
    return ok(LikeStateResponse(
        paper_id=resolved, liked=True, like_count=count,
    ).model_dump(mode='json'))


@router.delete('/papers/{paper_id}/like')
async def unlike_paper(paper_id: str, identity: RequestIdentity = Depends(require_user)):
    resolved = _identifier(paper_id, '论文 ID')
    count = await likes.unlike(identity.subject_id, resolved)
    return ok(LikeStateResponse(
        paper_id=resolved, liked=False, like_count=count,
    ).model_dump(mode='json'))


@router.get('/likes')
async def my_likes(
    identity: RequestIdentity = Depends(require_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=20),
):
    return ok((await likes.liked_papers(identity.subject_id, page, page_size)).model_dump(mode='json'))


@router.post('/topics/interactions')
async def topic_interactions(
    body: TopicInteractionsRequest,
    identity: RequestIdentity = Depends(request_identity),
):
    user_id = identity.subject_id if identity.kind == 'user' else None
    states = await interactions.topic_states(user_id, body.topic_ids)
    return ok(TopicInteractionsResponse(
        authenticated=user_id is not None,
        user_id=user_id,
        items=[TopicInteractionItem(**asdict(state)) for state in states],
    ).model_dump(mode='json'))


@router.put('/topic-follows/{topic_id}')
async def follow_topic(topic_id: str, identity: RequestIdentity = Depends(require_user)):
    resolved = _identifier(topic_id, '主题 ID')
    count = await follows.follow(identity.subject_id, resolved)
    return ok(TopicFollowStateResponse(
        topic_id=resolved, is_following=True, follower_count=count,
    ).model_dump(mode='json'))


@router.delete('/topic-follows/{topic_id}')
async def unfollow_topic(topic_id: str, identity: RequestIdentity = Depends(require_user)):
    resolved = _identifier(topic_id, '主题 ID')
    count = await follows.unfollow(identity.subject_id, resolved)
    return ok(TopicFollowStateResponse(
        topic_id=resolved, is_following=False, follower_count=count,
    ).model_dump(mode='json'))


@router.get('/topic-follows')
async def my_topic_follows(identity: RequestIdentity = Depends(require_user)):
    return ok((await follows.list_follows(identity.subject_id)).model_dump(mode='json'))
