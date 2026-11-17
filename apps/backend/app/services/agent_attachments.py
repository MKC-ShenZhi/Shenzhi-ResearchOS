"""Backend-owned parsing and context mapping for product Agent attachments."""
from __future__ import annotations

from app.core.config import MAX_ATTACHMENT_CHARS
from app.core.errors import BusinessError
from app.schemas.agent import AgentAttachment
from app.services.agent_uploads import agent_upload_store


def attachment_context(attachments, file_contexts: dict[str, dict]) -> tuple[str, list[str]]:
    """Render only Backend-authorized attachment context for an Agent task."""
    parts: list[str] = []
    warnings: list[str] = []
    remaining = MAX_ATTACHMENT_CHARS
    for attachment in attachments:
        if attachment.kind == 'file':
            item = file_contexts.get(attachment.file_id or '')
            if item is None:
                raise BusinessError(20004, '附件不存在或已过期，请重新上传', 404)
            text, label = item['text'], item['filename']
            if item.get('warning'):
                warnings.append(item['warning'])
        elif attachment.kind == 'paper':
            raise BusinessError(20007, '当前论文上下文不可用，请重新加载论文后重试', 503)
        else:
            label = attachment.kind
            text = (f'用户引用的条目：{attachment.title or attachment.ref_id or attachment.kind}'
                    '（未接入全文解析）')
            warnings.append('知识库 / 项目引用目前仅提供条目名称，未读取全文')
        block = f'\n<attachment name={label!r}>\n{text}\n</attachment>\n'
        if len(block) > remaining:
            warnings.append('多附件上下文已截断至合计 60,000 字')
        parts.append(block[:remaining])
        remaining = max(0, remaining - len(block))
    return ''.join(parts), list(dict.fromkeys(warnings))


async def resolve_agent_attachments(raw: list[dict], owner: str) -> tuple[str, list[str], dict[str, dict]]:
    try:
        attachments = [AgentAttachment.model_validate(item) for item in raw]
    except Exception as exc:
        raise BusinessError(20001, 'attachments 格式无效') from exc
    files = await agent_upload_store.get_many(
        owner, [item.file_id or '' for item in attachments if item.kind == 'file'],
    )
    context, warnings = attachment_context(attachments, files)
    return context, warnings, files
