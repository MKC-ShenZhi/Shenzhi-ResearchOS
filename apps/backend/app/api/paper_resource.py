"""Same-origin streaming route for resolved paper resources."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.identity import require_bff
from app.core.request_context import get_request_id, new_request_id
from app.schemas.knowledge import KnowledgeError
from app.services.knowledge import KnowledgeService, KnowledgeServiceError
from app.services.paper_resource import PaperResourceService
from app.services.paper_resource.service import PaperResourceFetch


router = APIRouter(prefix='/api/v1/paper-resource', tags=['paper-resource'])
knowledge_service = KnowledgeService()
paper_resource_service = PaperResourceService()


def _request_id() -> str:
    return get_request_id() or new_request_id()


def _error(
    *,
    code: str,
    message: str,
    retryable: bool,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content=KnowledgeError(
            code=code,
            message=message,
            retryable=retryable,
            request_id=_request_id(),
        ).model_dump(mode='json', by_alias=True),
    )


def _response_headers(source_headers: Mapping[str, str]) -> dict[str, str]:
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


async def _stream(fetch: PaperResourceFetch) -> AsyncIterator[bytes]:
    try:
        async for chunk in fetch.iter_bytes():
            yield chunk
    finally:
        await fetch.close()


@router.get('/pdf')
async def paper_pdf(
    request: Request,
    paper_id: str | None = Query(default=None, alias='paperId'),
    _credential: None = Depends(require_bff),
):
    """Stream a trusted paper's PDF without accepting an arbitrary source URL."""
    if 'url' in request.query_params:
        return _error(
            code='INVALID_ARGUMENT',
            message='不支持 url 参数',
            retryable=False,
            status_code=422,
        )
    if paper_id is None or not paper_id.strip():
        return _error(
            code='INVALID_ARGUMENT',
            message='paperId 不能为空',
            retryable=False,
            status_code=422,
        )

    try:
        detail = await knowledge_service.get_paper(paper_id)
    except KnowledgeServiceError as error:
        safe = error.error.model_copy(update={'request_id': _request_id()})
        return JSONResponse(
            status_code=error.status_code,
            content=safe.model_dump(mode='json', by_alias=True),
        )

    fetch = await paper_resource_service.open_paper_resource(
        detail.pdf_url,
        range_header=request.headers.get('range'),
    )
    if fetch.resource.status != 'available':
        await fetch.close()
        if fetch.status_code == 416:
            content_range = fetch.headers.get('content-range')
            return _error(
                code='INVALID_ARGUMENT',
                message='PDF Range 无法满足',
                retryable=False,
                status_code=416,
                headers={'Content-Range': content_range} if content_range else None,
            )
        if fetch.status_code in (401, 403):
            return _error(
                code='UPSTREAM_UNAVAILABLE',
                message='该 PDF 来源需要在原站完成访问验证',
                retryable=False,
                status_code=403,
            )
        if fetch.status_code == 404 or fetch.resource.reason == 'invalid_pdf_url':
            return _error(
                code='NOT_FOUND',
                message='当前论文暂无可用 PDF',
                retryable=False,
                status_code=404,
            )
        if fetch.resource.reason == 'pdf_too_large':
            return _error(
                code='INVALID_ARGUMENT',
                message='PDF 超过允许的大小',
                retryable=False,
                status_code=413,
            )
        if fetch.resource.reason == 'request_timeout':
            return _error(
                code='TIMEOUT',
                message='PDF 资源请求超时',
                retryable=True,
                status_code=504,
            )
        return _error(
            code='UPSTREAM_UNAVAILABLE',
            message='PDF 暂时无法获取',
            retryable=bool(fetch.status_code and fetch.status_code >= 500),
            status_code=503 if fetch.status_code and fetch.status_code >= 500 else 502,
        )

    return StreamingResponse(
        _stream(fetch),
        status_code=fetch.status_code or 200,
        media_type='application/pdf',
        headers=_response_headers(fetch.headers),
    )
