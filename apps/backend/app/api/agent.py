"""Agent HTTP 入口：产品会话、SSE run、运行配置、Web 工作区与产物文件。"""
import json
import logging
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api._support.upload_reader import read_upload
from app.core.config import MAX_FILES, UPLOAD_ACCEPT
from app.core.errors import BusinessError
from app.core.idempotency import request_fingerprint, validate_idempotency_key
from app.integrations.llm.resolver import load_registry
from app.core.identity import request_owner, require_bff
from app.core.responses import ok
from app.services.agent import service as agent_service
from app.services.agent import export as agent_export
from app.schemas.agent import (
    AgentSessionCreate, AgentSessionRun, AgentSessionUpdate, LegacyAgentSessionImport,
)
from app.services.agent_sessions.repository import agent_session_repository
from app.services.agent_sessions.live import LiveRun, get_live, subscribe
from app.services.agent_sessions.service import get_session_detail, start_session_run
from app.services.agent_uploads import agent_upload_store
from app.services.uploads.parser import parse_document

router = APIRouter(prefix='/api/v1/agent', tags=['agent'])
logger = logging.getLogger(__name__)


class AgentRunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    history: list[dict] = Field(default_factory=list, max_length=200)
    model: str | None = None
    # 默认 fast：180 秒 / 12 次工具调用，其余模式保持 900 秒 / 120 次（见 policies.py）。
    # mode 决定温度、运行预算，以及未显式选择技能时的快速回答技能与工具集。
    mode: Literal['fast', 'deep', 'idea', 'doubt'] = 'fast'
    attachments: list[dict] = Field(default_factory=list, max_length=MAX_FILES)
    workspace_id: str | None = None
    skills: list[str] = Field(default_factory=list, max_length=10)  # 用户显式选中：本轮强制启用
    session_id: str | None = None  # 会话即工作区：选中深度研究技能时自动挂载


class SteerBody(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


@router.get('/config')
def config(_credential: None = Depends(require_bff)):
    """运行配置：可选模型、技能清单、附件限制（结构与 chat/config 对齐）。"""
    registry = load_registry()
    store = agent_service.default_store()
    skills = [{'name': skill.name, 'description': skill.description}
              for name in store.names()
              for skill in [store.get(name)]
              if skill and not skill.disable_model_invocation]
    return ok({
        'models': registry.public_models('agent'),
        'default_model': registry.public_default('agent'),
        'skills': skills,
        'upload': {'max_size_mb': 20, 'max_files': MAX_FILES, 'accept': UPLOAD_ACCEPT},
    })


@router.post('/run')
async def run(body: AgentRunBody, owner: str = Depends(request_owner)):
    runtime = agent_service.build_run_runtime(
        owner=owner, model=body.model, mode=body.mode,
        workspace_id=body.workspace_id,
        forced_skills=body.skills, session_id=body.session_id, allow_shell=False)
    history = agent_service.decode_history(body.history)
    attachments, warnings, files = await agent_service.resolve_attachments(body.attachments, owner)
    meta = {'warnings': warnings} if warnings else None

    async def cleanup(_result):
        try:
            await agent_upload_store.consume(owner, list(files))
        except Exception:
            logger.exception('Failed to delete consumed Agent attachment text')

    async def generate():
        async for name, data in agent_service.run_events(runtime, body.prompt + attachments,
                                                         history, meta=meta, owner=owner,
                                                         session_id=body.session_id,
                                                         on_complete=cleanup):
            yield f'event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform',
                                      'X-Accel-Buffering': 'no'})


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
    if not agent_service.steer_run(run_id, body.text.strip(), owner):
        raise BusinessError(20004, '该运行已结束或不存在', 404)
    return ok({'injected': True})


@router.post('/run/{run_id}/stop')
async def stop(run_id: str, owner: str = Depends(request_owner)):
    """Cleanly stop the active run so its partial result remains recoverable."""
    if not agent_service.stop_run(run_id, owner):
        raise BusinessError(20004, '该运行已结束或不存在', 404)
    return ok({'stopping': True})


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
        raise BusinessError(20004, '当前没有运行中的任务', 404)
    return session_run_stream(live, after)


@router.get('/session/{session_id}/file')
async def session_file(session_id: str, path: str, download: bool = False,
                       owner: str = Depends(request_owner)):
    """会话工作区文件（agent 产物）：inline 预览或 attachment 下载。"""
    # Do not let a retained workspace directory recreate access after its DB
    # session has been deleted.  The existence/owner check is deliberately at
    # the HTTP boundary, before resolving the physical path.
    await agent_session_repository.get(session_id, owner)
    content, media_type = agent_service.read_session_file(owner, session_id, path)
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
    content, media_type = agent_service.read_session_file(owner, session_id, path)
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
    return ok(agent_service.create_workspace(owner))


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
    return ok(agent_service.write_workspace_file(workspace_id, owner, relative_path, data))
