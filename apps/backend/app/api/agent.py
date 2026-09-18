"""Agent 基座的 HTTP 入口：无状态 run + SSE、运行配置、Web 工作区上传、会话产物文件。"""
import json
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import MAX_FILES, UPLOAD_ACCEPT, model_config
from app.core.errors import BusinessError
from app.core.identity import request_owner, require_bff
from app.core.responses import ok
from app.services.agent import service as agent_service
from app.services.agent import export as agent_export

router = APIRouter(prefix='/api/v1/agent', tags=['agent'])


class AgentRunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)
    history: list[dict] = Field(default_factory=list, max_length=200)
    model: str | None = None
    # 默认 fast。预算对齐 SZDR 的实测形态（900 秒 / 120 次工具调用，见 policies.py）：
    # deadline 是上限不是目标，快问题照样快回；mode 只影响温度等资源倾向。
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
    settings = model_config()
    store = agent_service.default_store()
    skills = [{'name': skill.name, 'description': skill.description}
              for name in store.names()
              for skill in [store.get(name)]
              if skill and not skill.disable_model_invocation]
    return ok({
        'models': [{'value': item, 'label': item, 'provider': settings.provider,
                    'enabled': bool(settings.key)}
                   for item in settings.models],
        'default_model': settings.model,
        'skills': skills,
        'upload': {'max_size_mb': 20, 'max_files': MAX_FILES, 'accept': UPLOAD_ACCEPT},
    })


@router.post('/run')
async def run(body: AgentRunBody, owner: str = Depends(request_owner)):
    runtime = agent_service.build_run_runtime(
        owner=owner, model=body.model, mode=body.mode,
        workspace_id=body.workspace_id,
        forced_skills=body.skills, session_id=body.session_id)
    history = agent_service.decode_history(body.history)
    attachments, warnings = agent_service.resolve_attachments(body.attachments, owner)
    meta = {'warnings': warnings} if warnings else None

    async def generate():
        async for name, data in agent_service.run_events(runtime, body.prompt + attachments,
                                                         history, meta=meta, owner=owner,
                                                         session_id=body.session_id):
            yield f'event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform',
                                      'X-Accel-Buffering': 'no'})


@router.post('/run/{run_id}/steer')
async def steer(run_id: str, body: SteerBody, owner: str = Depends(request_owner)):
    """运行中插话：下一模型请求前注入（不打断当前工具批）。"""
    if not body.text.strip():
        raise BusinessError(20001, '插话内容不能为空')
    if not agent_service.steer_run(run_id, body.text.strip()):
        raise BusinessError(20004, '该运行已结束或不存在', 404)
    return ok({'injected': True})


@router.get('/session/{session_id}/file')
def session_file(session_id: str, path: str, download: bool = False,
                 owner: str = Depends(request_owner)):
    """会话工作区文件（agent 产物）：inline 预览或 attachment 下载。"""
    content, media_type = agent_service.read_session_file(owner, session_id, path)
    filename = PurePosixPath(path).name or 'file'
    disposition = 'attachment' if download else 'inline'
    return Response(
        content, media_type=media_type,
        headers={'Content-Disposition': f"{disposition}; filename*=UTF-8''{quote(filename)}"})


@router.get('/assets/{session_id}/{path:path}')
def session_asset(session_id: str, path: str, owner: str = Depends(request_owner)):
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
    content, media_type = agent_service.read_session_file(owner, session_id, path)
    filename = PurePosixPath(path).name or 'asset'
    headers = {
        'Cache-Control': 'private, max-age=300',  # 会话私有产物：共享缓存不得留存
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
