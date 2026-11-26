"""Agent-owned presentation assembly; independent of providers and HTTP/SSE.

The LLM writes Markdown and a references JSON sidecar. Identity, lifecycle,
deduplication and validation belong to this assembler.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from agent_contracts.messages import (
    AIMessage, CITATION, MarkdownBlock, MESSAGE_EVENT_MODELS, MessageStatus, Reference,
)

from agent_app.execution.references import ReferenceRegistry
from agent_app.execution.model_output import ModelOutput

OUTPUT_INSTRUCTIONS = '''消息输出格式（适用于直接回复，不改变工作区文件的格式）：
先输出 Markdown 正文，正文结束后另起一行顶格输出 <references_json>，随后输出 JSON 数组，
最后另起一行顶格输出 </references_json>。不要把这段 JSON 包在代码围栏内，不要在它后面继续写正文。
正文与 JSON 会由服务端拆分，JSON 不作为正文展示。无引用时输出空数组 []。
由你选择实际用于本次回答的来源，可以使用当前工具结果、用户提供的资料或会话历史中已获取的真实资料；
不要把所有检索结果都当作引用，不凭记忆编造来源、作者、年份或链接。未知的可选字段省略。
正文用 [[cite:r1]]、[[cite:r2]] 等局部引用键标记位置；同一来源重复引用使用同一键。
正文禁止把 paper_id、entity_id、内部数据库 ID 当作引用展示，禁止自行输出数字角标或参考文献列表。
JSON 中每条记录的 id 必须与正文引用键一致，必须包含 type、title；
type 仅为 paper、author、institution、webpage、dataset、funding。
可选字段为 url、entity_id、authors（字符串数组）、year（整数）、venue、doi。
这些 id 只是本次输出的关联键，正式来源 ID 及消息 ID、状态、时间、版本由程序生成。
每次模型回复单独提交自己的引用键与来源记录，不依赖上一次回复的局部键。
不要输出整个消息 JSON，不要输出 metadata、blocks 等系统结构。
示例：
结论来自该论文。[[cite:r1]]
<references_json>
[{"id":"r1","type":"paper","title":"工具返回的真实论文标题","authors":["真实作者"],"year":2025}]
</references_json>'''


class MessageStream:
    def __init__(self, emit: Callable[[str, dict], None], *, model: str,
                 snapshot: AIMessage | None = None) -> None:
        self.emit = emit
        self.message = snapshot or AIMessage(
            id=f'msg_{uuid.uuid4().hex}', created_at=time.time(), metadata={'model': model},
        )
        self.blocks = list(self.message.blocks)
        self.sources = ReferenceRegistry(self.message.references)
        self._block: MarkdownBlock | None = None
        self._parts: list[str] = []
        self._pending = ''
        self._output = ModelOutput()
        self._keys: dict[str, str] = {}
        self._invalid_citations: set[str] = set()
        self._reference_errors: set[str] = set()
        self.last_text = ''

    def _emit(self, name: str, **data: Any) -> None:
        # Validate before crossing the observer/persistence boundary.
        payload = MESSAGE_EVENT_MODELS[name].model_validate(data)
        self.emit(name, payload.model_dump(mode='json', exclude_none=True))

    def snapshot(self, status: MessageStatus = 'running', **metadata: Any) -> AIMessage:
        details = {**(self.message.metadata or {}), **metadata}
        if self._invalid_citations:
            details['invalid_citations'] = sorted(self._invalid_citations)
        if self._reference_errors:
            details['reference_errors'] = sorted(self._reference_errors)
        ordered = dict.fromkeys(key for block in self.blocks for key in CITATION.findall(block.content))
        return AIMessage(**{
            **self.message.model_dump(), 'status': status, 'blocks': self.blocks,
            'references': [self.sources.references[key] for key in ordered if key in self.sources.references],
            'metadata': details,
        })

    def start(self) -> None:
        self._emit('message_start', message=self.snapshot())

    def begin_response(self) -> None:
        self.end_block()
        self.last_text = ''

    def _safe_citation(self, match) -> str:
        key = match[1]
        if not key:
            self._invalid_citations.add(key)
            return '[引用不可用]'
        if key not in self._keys:
            self._keys[key] = f'ref_{uuid.uuid4().hex}'
        return f'[[cite:{self._keys[key]}]]'

    def _append_markdown(self, text: str, *, final: bool = False) -> str:
        self._pending += text
        ready, self._pending = self._pending, ''
        # Withhold an incomplete citation even when split at any character boundary.
        start = ready.rfind('[[')
        if not final:
            if start >= 0 and ']]' not in ready[start:]:
                suffix = ready[start:]
                if '[[cite:'.startswith(suffix) or suffix.startswith('[[cite:'):
                    ready, self._pending = ready[:start], suffix
            elif ready.endswith('['):
                ready, self._pending = ready[:-1], '['
        else:
            if start >= 0 and ready[start:].startswith('[[cite:') and ']]' not in ready[start:]:
                self._invalid_citations.add(ready[start:])
                ready = ready[:start] + '[引用不完整]'
        ready = CITATION.sub(self._safe_citation, ready)
        if not ready:
            return ''
        if self._block is None:
            self._block = MarkdownBlock(id=f'block_{uuid.uuid4().hex}')
            self._emit('block_start', message_id=self.message.id, block=self._block)
        self._parts.append(ready)
        self._emit('block_delta', message_id=self.message.id, block_id=self._block.id, delta=ready)
        return ready

    def append(self, text: str) -> str:
        return self._append_markdown(self._output.append(text))

    def end_block(self) -> str:
        if not self._output.received:
            return ''
        tail, records, errors = self._output.finish()
        self._reference_errors.update(errors)
        flushed = self._append_markdown(tail, final=True)
        resolved: dict[str, str] = {}
        # Only model-selected, actually cited records enter the message.
        for key, identifier in self._keys.items():
            record = records.get(key)
            if record is None:
                self._invalid_citations.add(key)
                continue
            source = Reference(**{**record.model_dump(), 'id': identifier})
            reference, changed = self.sources.upsert(source)
            resolved[identifier] = reference.id
            if changed:
                self._emit('reference_upsert', message_id=self.message.id, reference=reference)
        self.last_text = CITATION.sub(
            lambda match: f'[[cite:{resolved[match[1]]}]]' if match[1] in resolved else '[引用不可用]',
            ''.join(self._parts),
        )
        if self._block is not None:
            self.blocks.append(MarkdownBlock(id=self._block.id, content=self.last_text))
            self._emit('block_end', message_id=self.message.id, block_id=self._block.id)
        self._block = None
        self._parts = []
        self._pending = ''
        self._keys = {}
        self._output = ModelOutput()
        return flushed

    def finish(self, status: MessageStatus, *, duration_ms: int) -> AIMessage:
        self.end_block()
        message = self.snapshot(status, duration_ms=duration_ms)
        self._emit('message_end', message=message)
        return message
