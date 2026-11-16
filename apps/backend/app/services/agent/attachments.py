"""Build the Agent turn context from parsed uploads and referenced entries."""
from app.core.config import MAX_ATTACHMENT_CHARS
from app.core.errors import BusinessError


def attachment_context(attachments, file_contexts: dict[str, dict]) -> tuple[str, list[str]]:
    parts, warnings = [], []
    remaining = MAX_ATTACHMENT_CHARS
    for attachment in attachments:
        if attachment.kind == 'file':
            item = file_contexts.get(attachment.file_id or '')
            if item is None:
                raise BusinessError(20004, '附件不存在或已过期，请重新上传', 404)
            text = item['text']
            if item['warning']:
                warnings.append(item['warning'])
            label = item['filename']
        elif attachment.kind == 'paper':
            # Agent reads papers through its read_paper tool, not inline attachments.
            raise BusinessError(20007, '当前论文上下文不可用，请重新加载论文后重试', 503)
        else:
            # A's references remain selectable, but are NOT passed off as retrieved full texts.
            text = f'用户引用的条目：{attachment.title or attachment.ref_id or attachment.kind}（未接入全文解析）'
            label = attachment.kind
            warnings.append('知识库 / 项目引用目前仅提供条目名称，未读取全文')
        prefix = f'\n<attachment name={label!r}>\n'
        suffix = '\n</attachment>\n'
        block = prefix + text + suffix
        if len(block) > remaining:
            warnings.append('多附件上下文已截断至合计 60,000 字')
        parts.append(block[:remaining])
        remaining = max(0, remaining - len(block))
    return ''.join(parts), list(dict.fromkeys(warnings))
