"""Agent HTTP 入口：产品会话、SSE run、运行配置、Web 工作区与产物文件。"""
import json
import logging
import asyncio
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from agent_contracts import (
    KnowledgeGraphQueryWire, KnowledgePaperDetailWire, KnowledgePaperGraphWire,
    KnowledgeSearchRequestWire, KnowledgeSearchResponseWire, validate_history,
)

from app.api._support.upload_reader import read_upload
from app.core.config import MAX_FILES, UPLOAD_ACCEPT
from app.core.errors import BusinessError
from app.core.idempotency import request_fingerprint, validate_idempotency_key
from app.core.identity import request_owner, require_agent_service, require_bff
from app.core.responses import ok
from app.schemas.agent import (
    AgentRunBody, AgentSessionCreate, AgentSessionRun, AgentSessionUpdate,
    LegacyAgentSessionImport, SteerBody,
)
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_sessions.live import LiveRun, get_live, subscribe
from app.services.agent_sessions.service import (
    get_session_detail, resume_session_run, start_session_run,
)
from app.services.agent_sessions import export as agent_export
from app.services.agent_gateway.client import agent_gateway
from app.services.agent_attachments import resolve_agent_attachments
from app.services.agent_uploads import agent_upload_store
from app.services.uploads.parser import parse_document
from app.schemas.knowledge import KnowledgeSearchRequest

router = APIRouter(prefix='/api/v1/agent', tags=['agent'])
logger = logging.getLogger(__name__)


@router.post('/internal/knowledge/search', dependencies=[Depends(require_agent_service)])
async def agent_knowledge_search(body: KnowledgeSearchRequestWire):
    """Agent-only adapter; Knowledge models and upstream credentials stay in Backend."""
    from app.api.knowledge import service as knowledge_service

    request = KnowledgeSearchRequest.model_validate(body.model_dump(mode='json', by_alias=True))
    result = await knowledge_service.search(request)
    return KnowledgeSearchResponseWire.model_validate(
        result.model_dump(mode='json', by_alias=True),
    ).model_dump(mode='json', by_alias=True)


@router.get('/internal/knowledge/papers/{paper_id:path}',
            dependencies=[Depends(require_agent_service)])
async def agent_knowledge_paper(paper_id: str):
    from app.api.knowledge import service as knowledge_service

    result = await knowledge_service.get_paper(paper_id)
    return KnowledgePaperDetailWire.model_validate(
        result.model_dump(mode='json', by_alias=True),
    ).model_dump(mode='json', by_alias=True)


@router.get('/internal/knowledge/graph/{paper_id:path}',
            dependencies=[Depends(require_agent_service)])
async def agent_knowledge_graph(paper_id: str, depth: int = Query(default=1, ge=1, le=3)):
    from app.api.knowledge import service as knowledge_service

    query = KnowledgeGraphQueryWire(depth=depth)
    result = await knowledge_service.get_graph(paper_id, depth=query.depth)
    return KnowledgePaperGraphWire.model_validate(
        result.model_dump(mode='json', by_alias=True),
    ).model_dump(mode='json', by_alias=True)


@router.get('/config')
async def config(_credential: None = Depends(require_bff)):
    """运行配置：可选模型、技能清单、附件限制。"""
    config = await agent_gateway.config()
    return ok({
        'models': config.get('models', []),
        'default_model': config.get('default_model'),
        'skills': config.get('skills', []),
        'upload': {'max_size_mb': 20, 'max_files': MAX_FILES, 'accept': UPLOAD_ACCEPT},
    })


@router.post('/run')
async def run(body: AgentRunBody, owner: str = Depends(request_owner)):
    try:
        validate_history(body.history)
    except ValueError as exc:
        raise BusinessError(20001, '历史消息格式无效', 400) from exc
    attachment_text, warnings, files = await resolve_agent_attachments(body.attachments, owner)
    task = await agent_gateway.submit({
        'owner_id': owner, 'prompt': body.prompt + attachment_text,
        'session_id': body.session_id, 'mode': body.mode, 'model': body.model,
        'workspace_id': body.workspace_id,
        'skills': body.skills, 'history': body.history,
    })
    if files:
        try:
            await agent_upload_store.consume(owner, list(files))
        except Exception:
            logger.exception('Failed to consume Agent attachments after submit')
    return StreamingResponse(_agent_task_stream(owner, task, warnings), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform',
                                      'X-Accel-Buffering': 'no'})


async def _agent_task_stream(owner: str, task: dict, warnings: list[str]):
    task_id = task['task_id']
    run_id = task['current_run_id']
    after_seq = 0
    if warnings:
        yield f"event: meta\ndata: {json.dumps({'warnings': warnings}, ensure_ascii=False)}\n\n"
    yield f"event: run_start\ndata: {json.dumps({'run_id': run_id}, ensure_ascii=False)}\n\n"
    heartbeat_at = asyncio.get_running_loop().time()
    while True:
        events = await agent_gateway.events(run_id, owner, after_seq)
        for event in events:
            after_seq = max(after_seq, int(event['seq']))
            event_id = f"id: {after_seq}\n"
            yield (f"{event_id}event: {event['name']}\n"
                   f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n")
        run = await agent_gateway.run(run_id, owner)
        task_state = await agent_gateway.task(task_id, owner)
        current_run_id = task_state.get('current_run_id')
        report = run.get('report')
        if report and current_run_id and current_run_id != run_id:
            run_id, after_seq = current_run_id, 0
            yield f"event: run_start\ndata: {json.dumps({'run_id': run_id}, ensure_ascii=False)}\n\n"
            continue
        if report:
            result_data = report.get('result') or {}
            status = {'completed': 'done', 'failed': 'failed', 'cancelled': 'stopped',
                      'timed_out': 'timeout', 'awaiting_input': 'awaiting_input'}.get(
                          report.get('status'), 'failed')
            result = {
                'status': status, 'stop_reason': result_data.get('stop_reason') or 'error',
                'final_text': result_data.get('final_text', ''),
                'output': result_data.get('output'), 'question': result_data.get('question'),
                'turns': result_data.get('turns', 0),
                'duration_ms': result_data.get('duration_ms', 0),
                'prompt_tokens': result_data.get('prompt_tokens', 0),
                'completion_tokens': result_data.get('completion_tokens', 0),
                'truncated': result_data.get('truncated', False),
                'error': ({'code': report.get('error_code'),
                           'message': report.get('error_message')}
                          if report.get('error_code') else None),
            }
            yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
            return
        now = asyncio.get_running_loop().time()
        if now - heartbeat_at >= 15:
            yield ': ping\n\n'
            heartbeat_at = now
        await asyncio.sleep(0.5)


@router.post('/uploads')
async def upload_agent_attachment(request: Request, owner: str = Depends(request_owner)):
    filename, data = await read_upload(request)
    parsed = await run_in_threadpool(parse_document, data, filename)
    return ok(await agent_upload_store.save(owner, filename, parsed))


@router.get('/uploads/{file_id}')
async def get_agent_attachment(file_id: str, owner: str = Depends(request_owner)):
    item = await agent_upload_store.get(owner, file_id)
    return ok({key: value for key, value in item.items() if key not in ('text', 'owner', 'expires_at')})


@router.post('/run/{run_id}/steer')
async def steer(run_id: str, body: SteerBody, owner: str = Depends(request_owner)):
    """运行中插话：下一模型请求前注入（不打断当前工具批）。"""
    if not body.text.strip():
        raise BusinessError(20001, '插话内容不能为空')
    await agent_gateway.steer(run_id, owner, body.text.strip())
    return ok({'injected': True})


@router.post('/run/{run_id}/stop')
async def stop(run_id: str, owner: str = Depends(request_owner)):
    """Cleanly stop the active run so its partial result remains recoverable."""
    run = await agent_gateway.run(run_id, owner)
    task = await agent_gateway.cancel(run['task_id'], owner)
    return ok({'stopping': task.get('cancel_requested', False)})


@router.post('/sessions')
async def create_agent_session(body: AgentSessionCreate, owner: str = Depends(request_owner)):
    settings = {
        'model': body.model, 'mode': body.mode,
        'skills': body.skills, 'workspace_id': body.workspace_id,
    }
    session = await agent_session_repository.create(
        owner, body.prompt, settings, branched_from=body.branched_from,
    )
    return ok(session.summary())


@router.get('/sessions')
async def list_agent_sessions(
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=500),
    owner: str = Depends(request_owner),
):
    page = await agent_session_repository.list_page(owner, limit, cursor)
    return ok({**page, 'ephemeral': not agent_session_repository.is_durable})


@router.post('/sessions/import')
async def import_agent_session(
    body: LegacyAgentSessionImport, owner: str = Depends(request_owner),
):
    session = await agent_session_repository.import_legacy(owner, body.model_dump())
    return ok(session.summary())


@router.get('/sessions/{session_id}')
async def get_agent_session(session_id: str, owner: str = Depends(request_owner)):
    return ok((await get_session_detail(session_id, owner)).public())


@router.patch('/sessions/{session_id}')
async def update_agent_session(
    session_id: str, body: AgentSessionUpdate, owner: str = Depends(request_owner),
):
    session = await agent_session_repository.update_title(session_id, owner, body.title)
    return ok(session.summary())


@router.delete('/sessions/{session_id}')
async def delete_agent_session(session_id: str, owner: str = Depends(request_owner)):
    # Workspace removal is intentionally not recursive here. Database rows cascade; the bounded
    # workspace lifecycle needs a separate retention job rather than deleting model-provided paths.
    await agent_session_repository.delete(session_id, owner)
    return ok({'ok': True})


@router.post('/sessions/{session_id}/run')
async def run_agent_session(
    session_id: str, body: AgentSessionRun,
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
    owner: str = Depends(request_owner),
):
    key = validate_idempotency_key(idempotency_key)
    live = await start_session_run(
        owner=owner, session_id=session_id, prompt=body.prompt, model=body.model,
        mode=body.mode, attachments=body.attachments, workspace_id=body.workspace_id,
        skills=body.skills, allow_shell=False, idempotency_key=key,
        idempotency_fingerprint=(request_fingerprint(body.model_dump(mode='json'))
                                 if key is not None else None),
    )

    return session_run_stream(live)


def session_run_stream(live: LiveRun, after: int = 0) -> StreamingResponse:
    async def generate():
        async for event in subscribe(live, after):
            if event is None:
                yield ': ping\n\n'
            else:
                index, name, data = event
                yield f'id: {index}\nevent: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform',
                                      'X-Accel-Buffering': 'no'})


@router.get('/sessions/{session_id}/run/stream')
async def attach_agent_session_run(
    session_id: str, after: int = Query(default=0, ge=0),
    owner: str = Depends(request_owner),
):
    live = get_live(session_id, owner)
    if live is None:
        live = await resume_session_run(session_id, owner)
    return session_run_stream(live, after)


@router.get('/session/{session_id}/file')
async def session_file(session_id: str, path: str, download: bool = False,
                       owner: str = Depends(request_owner)):
    """会话工作区文件（agent 产物）：inline 预览或 attachment 下载。"""
    # Do not let a retained workspace directory recreate access after its DB
    # session has been deleted.  The existence/owner check is deliberately at
    # the HTTP boundary, before resolving the physical path.
    await agent_session_repository.get(session_id, owner)
    content, media_type = await agent_gateway.read_session_file(owner, session_id, path)
    filename = PurePosixPath(path).name or 'file'
    disposition = 'attachment' if download else 'inline'
    return Response(
        content, media_type=media_type,
        headers={
            'Content-Disposition': f"{disposition}; filename*=UTF-8''{quote(filename)}",
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        })


@router.get('/assets/{session_id}/{path:path}')
async def session_asset(session_id: str, path: str, owner: str = Depends(request_owner)):
    """会话工作区图片产物（报告内嵌图）：稳定 URL，供报告 markdown 直接 <img src> 引用。

    与 /session/{id}/file 的差别只在 URL 形态：产物路径进 path 段而非 query，同一张图恒定
    一个 URL，浏览器（及将来的 CDN 回源）可以按 URL 命中缓存。owner 隔离与路径禁闭不在此
    重做，仍由 read_session_file 收口（session_id 正则 + Workspace.resolve 双 resolve 后
    必须仍在工作区内），本层只定响应头。

    inline SVG 的风险判断：SVG 是活动内容（可含 <script>、外链、<foreignObject>），而它的
    字节来自模型 / 被上传文档左右的工作区，且浏览器只打同源 /api/v1（Next 微后端转发到
    FastAPI），因此"把 /assets/.../x.svg 直接当页面打开"就是一个同源存储型 XSS 面；<img>
    内嵌不会执行脚本，但不能只指望前端永远用 <img>。故 SVG 保留 inline（attachment 会让
    报告缩略图/预览链路失效），同时附 CSP `default-src 'none'` 关掉脚本与外部请求，
    只放行内联样式（图形本身的 fill/stroke/<style> 需要）；其余图片类型无活动内容，不加 CSP。
    """
    await agent_session_repository.get(session_id, owner)
    content, media_type = await agent_gateway.read_session_file(owner, session_id, path)
    filename = PurePosixPath(path).name or 'asset'
    headers = {
        # Deletion must take effect for a previously copied URL as well; a
        # browser cache must not keep serving a retained session artifact.
        'Cache-Control': 'private, no-store',
        'Content-Disposition': f"inline; filename*=UTF-8''{quote(filename)}",
        # media_type 只看后缀（read_session_file 不做字节嗅探），禁掉嗅探避免伪装后缀被当活动内容执行
        'X-Content-Type-Options': 'nosniff',
    }
    if media_type == 'image/svg+xml':
        headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'"
    return Response(content, media_type=media_type, headers=headers)


class ExportBody(BaseModel):
    title: str = Field(default='ShenzhiAi 会话', max_length=200)
    messages: list[dict] = Field(max_length=2_000)
    format: Literal['html', 'jsonl'] = 'html'


@router.post('/session/export')
def export_session(body: ExportBody, _credential: None = Depends(require_bff)):
    """会话导出（pi session-export）：前端 POST 本地会话数据，返回 HTML 报告或 JSONL。"""
    if body.format == 'jsonl':
        return Response(agent_export.export_jsonl(body.messages), media_type='application/jsonl',
                        headers={'Content-Disposition': "attachment; filename*=UTF-8''session.jsonl"})
    return Response(agent_export.export_html(body.title, body.messages), media_type='text/html',
                    headers={'Content-Disposition': "attachment; filename*=UTF-8''session.html"})


@router.post('/workspace')
async def create_workspace(owner: str = Depends(request_owner)):
    return ok(await agent_gateway.create_workspace(owner))


@router.post('/workspace/{workspace_id}/files')
async def upload_workspace_file(workspace_id: str, request: Request,
                                owner: str = Depends(request_owner)):
    """multipart 单文件上传；path 字段携带浏览器侧相对路径（webkitRelativePath）。"""
    form = await request.form()
    upload = form.get('file')
    relative_path = str(form.get('path') or '')
    if not isinstance(upload, UploadFile) or not relative_path:
        raise BusinessError(20001, '需要 file 与 path 字段')
    data = await upload.read()
    return ok(await agent_gateway.write_workspace_file(workspace_id, owner, relative_path, data))
