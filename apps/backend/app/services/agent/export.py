"""会话导出：RunResult.messages → HTML 报告 / JSONL 轨迹（pi session-export 移植）。

数据归属：会话历史在调用方（前端 localStorage / CLI 本地）；本模块只做渲染，
POST 进来什么就导出什么，不落库不持久化。
"""
from __future__ import annotations

import html
import json
from collections.abc import Sequence

from app.services.agent.types import (
    AgentMessage, ToolResultMessage, UserMessage, message_from_dict,
)

_MAX_HTML_CHARS = 300_000  # 防御性上限：超大会话截断导出而非 500

_HTML_HEAD = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShenzhiAi 会话导出</title>
<style>
:root { --ink:#17212b; --muted:#6b7280; --line:#e5e7eb; --panel:#e8f1f8; --primary:#174a7e; --agent:#0f766e; }
body { font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif; max-width:52rem;
       margin:0 auto; padding:2.5rem 1.25rem; color:var(--ink); line-height:1.75; background:#fff; }
header { border-bottom:2px solid var(--primary); padding-bottom:.8rem; margin-bottom:2rem; }
header h1 { font-size:1.35rem; margin:0 0 .25rem; }
header p { color:var(--muted); font-size:.8rem; margin:0; }
.user { background:var(--panel); border-radius:1.25rem; padding:.8rem 1.1rem; margin:1.2rem 0 1.2rem auto;
        max-width:78%; width:fit-content; }
.assistant { margin:1.2rem 0; }
.assistant .who { color:var(--agent); font-size:.75rem; font-weight:600; margin-bottom:.2rem; }
.tool { border-left:3px solid var(--line); color:var(--muted); font-family:ui-monospace,Consolas,monospace;
        font-size:.75rem; padding:.15rem 0 .15rem .7rem; margin:.25rem 0; }
.tool.err { color:#ef4444; }
pre { background:#f6f9fc; border:1px solid var(--line); border-radius:.5rem; padding:.8rem;
      overflow-x:auto; font-size:.82rem; }
code { background:#f3f4f6; border-radius:.2rem; padding:.05rem .3rem; font-size:.85em; }
blockquote { border-left:3px solid var(--primary); margin:.6rem 0; padding-left:.8rem; color:var(--muted); }
</style></head><body>
'''

_HTML_TAIL = '\n</body></html>\n'


def export_jsonl(messages: Sequence[dict]) -> str:
    """JSONL：一行一条消息（pi exportSessionToJsonl 同构，message_to_dict 编码）。"""
    return '\n'.join(json.dumps(item, ensure_ascii=False)
                     for item in messages if isinstance(item, dict)) + '\n'


def export_html(title: str, messages: Sequence[dict]) -> str:
    """HTML 报告：用户气泡 / 助手通栏 / 工具往返折叠行（pi export-html 的极简版）。"""
    decoded: list[AgentMessage] = [message_from_dict(item) for item in messages
                                   if isinstance(item, dict) and item.get('kind') != 'tool']
    parts = [_HTML_HEAD,
             f'<header><h1>{html.escape(title or "ShenzhiAi 会话")}</h1>'
             f'<p>深知科研智能体导出 · {len(decoded)} 条消息 · {html.escape(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"))}</p></header>']
    budget = _MAX_HTML_CHARS
    for message in decoded:
        if budget <= 0:
            parts.append('<p>…（会话过长，导出已截断）</p>')
            break
        block = _render_message(message)
        budget -= len(block)
        parts.append(block)
    parts.append(_HTML_TAIL)
    return ''.join(parts)


def _render_message(message: AgentMessage) -> str:
    if isinstance(message, UserMessage):
        return f'<div class="user">{html.escape(message.text)}</div>'
    if isinstance(message, ToolResultMessage):
        mark = ' err' if message.is_error else ''
        summary = html.escape(message.content[:120])
        return f'<div class="tool{mark}">{"✗" if message.is_error else "✓"} {html.escape(message.name)} {summary}</div>'
    assistant = message
    parts = ['<div class="assistant"><div class="who">ShenzhiAi</div>']
    for call in assistant.tool_calls:
        parts.append(f'<div class="tool">→ {html.escape(call.name)}</div>')
    text = (assistant.content or '').strip()
    if text:
        parts.append(f'<p>{html.escape(text)}</p>')
    parts.append('</div>')
    return ''.join(parts)
