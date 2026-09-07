"""HTTP routes for the ShenZhi Knowledge Capability."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.core.identity import require_bff
from app.core.logging import log_exception
from app.core.request_context import get_request_id
from app.core.responses import ok
from app.schemas.knowledge import KnowledgeError, KnowledgeSearchRequest
from app.services.knowledge import KnowledgeService, KnowledgeServiceError


router = APIRouter(prefix='/api/v1/knowledge', tags=['knowledge'])
service = KnowledgeService()
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


def _paper_id_or_error(paper_id: str | None, request: Request) -> str | JSONResponse:
    if paper_id is None or not paper_id.strip():
        return invalid_argument(request, 'paperId 不能为空')
    return paper_id


def _pdf_error(
    request: Request,
    *,
    code: str,
    message: str,
    retryable: bool,
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=KnowledgeError(
            code=code,
            message=message,
            retryable=retryable,
            request_id=request_id(request),
        ).model_dump(mode='json', by_alias=True),
    )


def _pdf_headers(source_headers: dict[str, str]) -> dict[str, str]:
    headers = {'Content-Type': 'application/pdf'}
    for name in (
        'content-length',
        'content-disposition',
        'accept-ranges',
        'content-range',
        'cache-control',
    ):
        if value := source_headers.get(name):
            headers[name] = value
    headers.setdefault('content-disposition', 'inline')
    return headers


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


@router.get('/paper/pdf')
async def paper_pdf(
    request: Request,
    paper_id: str | None = Query(default=None, alias='paperId'),
    _credential: None = Depends(require_bff),
):
    if 'url' in request.query_params:
        return invalid_argument(request, '不支持 url 参数')
    resolved = _paper_id_or_error(paper_id, request)
    if isinstance(resolved, JSONResponse):
        return resolved
    try:
        source = await service.get_paper_pdf_source(
            resolved, range_header=request.headers.get('range')
        )
    except KnowledgeServiceError as error:
        return _error_payload(error, request)
    except Exception as error:
        return unknown_error(request, error)

    if source is None:
        return _pdf_error(
            request,
            code='NOT_FOUND',
            message='当前论文暂无可用 PDF',
            retryable=False,
            status_code=404,
        )
    if source.probe.status == 'external_only':
        await service.close_paper_pdf(source)
        return _pdf_error(
            request,
            code='UPSTREAM_UNAVAILABLE',
            message='该 PDF 来源需要在原站完成访问验证',
            retryable=False,
            status_code=403,
        )
    if source.probe.status != 'available':
        await service.close_paper_pdf(source)
        return _pdf_error(
            request,
            code='UPSTREAM_UNAVAILABLE',
            message='PDF 暂时无法获取',
            retryable=source.probe.retryable,
            status_code=503 if source.probe.retryable else 502,
        )

    return StreamingResponse(
        service.stream_paper_pdf(source),
        status_code=source.probe.status_code,
        media_type='application/pdf',
        headers=_pdf_headers(dict(source.probe.headers)),
    )


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
