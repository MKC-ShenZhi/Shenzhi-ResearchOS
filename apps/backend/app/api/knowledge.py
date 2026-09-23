"""HTTP routes for the ShenZhi Knowledge Capability."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.identity import request_identity, require_bff
from app.core.logging import log_exception
from app.core.request_context import get_request_id
from app.core.responses import ok
from app.schemas.knowledge import (
    FundingSearchRequest,
    KnowledgeError,
    KnowledgeMixedSearchRequest,
    KnowledgePersonalOverviewResponse,
    KnowledgeSearchRequest,
    PersonalRecentPaper,
    RelatedPaperSearchRequest,
    ScholarSearchRequest,
)
from app.services.knowledge.service import KnowledgeService, KnowledgeServiceError
from app.services.library.collections import CollectionService
from app.services.library.reading_history import ReadingHistoryService
from app.schemas.knowledge import PaperBatchRequest


router = APIRouter(prefix='/api/v1/knowledge', tags=['knowledge'])
papers_router = APIRouter(prefix='/api/v1', tags=['papers'])
service = KnowledgeService()
collection_service = CollectionService()
reading_history_service = ReadingHistoryService()
logger = logging.getLogger(__name__)


def request_id(request: Request) -> str:
    if contextual := get_request_id():
        return contextual
    candidate = request.headers.get('x-request-id', '').strip()
    if candidate and len(candidate) <= 128:
        return candidate
    return uuid4().hex


def _error_payload(error: KnowledgeServiceError, request: Request) -> JSONResponse:
    safe = error.error.model_copy(update={'request_id': request_id(request)})
    return JSONResponse(
        status_code=error.status_code,
        content=safe.model_dump(mode='json', by_alias=True),
    )


def invalid_argument(request: Request, message: str = '请求参数不合法') -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=KnowledgeError(
            code='INVALID_ARGUMENT',
            message=message,
            retryable=False,
            request_id=request_id(request),
        ).model_dump(mode='json', by_alias=True),
    )


def unknown_error(request: Request, error: Exception) -> JSONResponse:
    log_exception(
        logger,
        'exception.unexpected',
        {
            'route': request.url.path,
            'method': request.method,
            'status_code': 500,
            'error_type': type(error).__name__,
            'error_code': 'UNKNOWN',
        },
        error,
    )
    return JSONResponse(
        status_code=500,
        content=KnowledgeError(
            code='UNKNOWN',
            message='知识服务请求失败',
            retryable=False,
            request_id=request_id(request),
        ).model_dump(mode='json', by_alias=True),
    )


@router.post('/search')
async def search(
    request: Request,
    _credential: None = Depends(require_bff),
):
    try:
        body = await request.json()
        search_request = KnowledgeSearchRequest.model_validate(body)
    except (ValidationError, ValueError, UnicodeDecodeError):
        return invalid_argument(request, '检索参数不合法')

    try:
        response = await service.search(search_request)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/overview')
async def overview(
    request: Request,
    _credential: None = Depends(require_bff),
):
    try:
        response = await service.overview()
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/personal-overview')
async def personal_overview(
    request: Request,
    _credential: None = Depends(require_bff),
):
    try:
        identity = request_identity(request)
        if identity.kind != 'user':
            return ok(KnowledgePersonalOverviewResponse(auth_required=True).model_dump(
                mode='json', by_alias=True
            ))
        folders = await collection_service.folders(identity.subject_id)
        history = await reading_history_service.list(identity.subject_id, 1, 5, '')
        response = KnowledgePersonalOverviewResponse(
            folders=[folder.model_dump() for folder in folders.folders],
            recent_papers=[
                PersonalRecentPaper.model_validate(item.model_dump())
                for item in history.items
            ],
        )
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.post('/overview/search')
async def overview_search(
    request: Request,
    _credential: None = Depends(require_bff),
):
    try:
        body = await request.json()
        search_request = KnowledgeMixedSearchRequest.model_validate(body)
    except (ValidationError, ValueError, UnicodeDecodeError):
        return invalid_argument(request, '混合检索参数不合法')

    try:
        response = await service.mixed_search(search_request)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/scholars/search')
async def search_scholars(
    request: Request,
    q: str | None = Query(default=None),
    limit: str = Query(default='20'),
    offset: str = Query(default='0'),
    _credential: None = Depends(require_bff),
):
    try:
        search_request = ScholarSearchRequest.model_validate({
            'query': q,
            'limit': int(limit),
            'offset': int(offset),
        })
    except (ValidationError, TypeError, ValueError):
        return invalid_argument(request, '学者检索参数不合法')

    try:
        response = await service.search_scholars(search_request)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/scholars/{scholar_id:path}')
async def scholar(
    scholar_id: str,
    request: Request,
    _credential: None = Depends(require_bff),
):
    if not scholar_id.strip():
        return invalid_argument(request, 'scholarId 不能为空')
    try:
        response = await service.get_scholar(scholar_id)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


def _related_search_request(
    value: str | None, top_k: str
) -> RelatedPaperSearchRequest | None:
    try:
        return RelatedPaperSearchRequest.model_validate({
            'query': value,
            'topK': int(top_k),
        })
    except (ValidationError, TypeError, ValueError):
        return None


def _subject_page_request(
    value: str | None, offset: str, limit: str
) -> tuple[str, int, int] | None:
    try:
        request = RelatedPaperSearchRequest.model_validate({'query': value, 'topK': 1})
        offset_value = int(offset)
        limit_value = int(limit)
        if offset_value < 0 or offset_value >= 1000 or limit_value < 1 or limit_value > 100:
            return None
        return request.query, offset_value, limit_value
    except (ValidationError, TypeError, ValueError):
        return None


@router.get('/subjects/search')
async def search_by_subject(
    request: Request,
    subject: str | None = Query(default=None),
    offset: str = Query(default='0'),
    limit: str = Query(default='10'),
    _credential: None = Depends(require_bff),
):
    search_request = _subject_page_request(subject, offset, limit)
    if search_request is None:
        return invalid_argument(request, '主题检索参数不合法')
    try:
        response = await service.search_by_subject(
            search_request[0], offset=search_request[1], limit=search_request[2]
        )
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/funding/search')
async def search_by_funding(
    request: Request,
    funding: str | None = Query(default=None),
    top_k: str = Query(default='10', alias='topK'),
    _credential: None = Depends(require_bff),
):
    search_request = _related_search_request(funding, top_k)
    if search_request is None:
        return invalid_argument(request, '基金关联论文检索参数不合法')
    try:
        response = await service.search_by_funding(
            search_request.query, top_k=search_request.top_k
        )
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/fundings/search')
async def search_fundings(
    request: Request,
    q: str | None = Query(default=None),
    limit: str = Query(default='20'),
    offset: str = Query(default='0'),
    _credential: None = Depends(require_bff),
):
    try:
        search_request = FundingSearchRequest.model_validate({
            'query': q,
            'limit': int(limit),
            'offset': int(offset),
        })
    except (ValidationError, TypeError, ValueError):
        return invalid_argument(request, '基金候选检索参数不合法')

    try:
        response = await service.search_fundings(search_request)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


def _paper_id_or_error(paper_id: str | None, request: Request) -> str | JSONResponse:
    if paper_id is None or not paper_id.strip():
        return invalid_argument(request, 'paperId 不能为空')
    return paper_id


@router.get('/paper')
async def paper(
    request: Request,
    paper_id: str | None = Query(default=None, alias='paperId'),
    _credential: None = Depends(require_bff),
):
    resolved = _paper_id_or_error(paper_id, request)
    if isinstance(resolved, JSONResponse):
        return resolved
    try:
        response = await service.get_paper(resolved)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))


@router.get('/graph')
async def graph(
    request: Request,
    paper_id: str | None = Query(default=None, alias='paperId'),
    depth: str = Query(default='1'),
    _credential: None = Depends(require_bff),
):
    resolved = _paper_id_or_error(paper_id, request)
    if isinstance(resolved, JSONResponse):
        return resolved
    try:
        depth_value = int(depth)
    except (TypeError, ValueError):
        return invalid_argument(request, 'depth 必须是 1 或 2')
    if depth_value not in (1, 2):
        return invalid_argument(request, 'depth 必须是 1 或 2')

    try:
        response = await service.get_graph(resolved, depth=depth_value)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok(response.model_dump(mode='json', by_alias=True))

@papers_router.post('/papers/batch')
async def batch_papers(
    request: Request,
    _credential: None = Depends(require_bff),
):
    try:
        body = PaperBatchRequest.model_validate(await request.json())
    except (ValidationError, ValueError, UnicodeDecodeError):
        return invalid_argument(request, '论文 ID 列表不合法')

    try:
        papers = await service.batch_get_papers(body.paper_ids)
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)
    return ok({'papers': [paper.model_dump(mode='json', by_alias=True) for paper in papers]})
