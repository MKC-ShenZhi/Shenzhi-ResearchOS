"""Agent-owned presentation assembly; independent of providers and HTTP/SSE.

Only trusted tool outputs can register references. The LLM writes Markdown and
citation markers; identity, lifecycle and validation belong to this assembler.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from agent_contracts.messages import (
    AIMessage, CITATION, MarkdownBlock, MESSAGE_EVENT_MODELS, MessageStatus, Reference,
)

from agent_app.execution.references import ReferenceRegistry

OUTPUT_INSTRUCTIONS = (
    '回复正文使用 Markdown，不要输出消息 JSON、系统字段或自行排版参考文献列表。'
    '工具结果的 references 是可引用来源；引用时使用 [[cite:ref_id]]，'
    'ref_id 必须原样取自该集合，禁止编造来源或引用 ID。没有来源时直接作答并如实说明。'
)


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
        self._invalid_citations: set[str] = set()

    def _emit(self, name: str, **data: Any) -> None:
        # Validate before crossing the observer/persistence boundary.
        payload = MESSAGE_EVENT_MODELS[name].model_validate(data)
        self.emit(name, payload.model_dump(mode='json', exclude_none=True))

    def snapshot(self, status: MessageStatus = 'running', **metadata: Any) -> AIMessage:
        details = {**(self.message.metadata or {}), **metadata}
        if self._invalid_citations:
            details['invalid_citations'] = sorted(self._invalid_citations)
        return AIMessage(**{
            **self.message.model_dump(), 'status': status, 'blocks': self.blocks,
            'references': list(self.sources.references.values()), 'metadata': details,
        })

    def start(self) -> None:
        self._emit('message_start', message=self.snapshot())

    def register(self, sources: Iterable[Reference]) -> list[Reference]:
        registered = {}
        for source in sources:
            reference, changed = self.sources.upsert(source)
            registered[reference.id] = reference
            if changed:
                self._emit('reference_upsert', message_id=self.message.id, reference=reference)
        return list(registered.values())

    def _safe_citation(self, match) -> str:
        identifier = match[1]
        if identifier in self.sources.references:
            return match[0]
        self._invalid_citations.add(identifier)
        return '[引用不可用]'

    def append(self, text: str, *, final: bool = False) -> None:
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
            return
        if self._block is None:
            self._block = MarkdownBlock(id=f'block_{uuid.uuid4().hex}')
            self._emit('block_start', message_id=self.message.id, block=self._block)
        self._parts.append(ready)
        self._emit('block_delta', message_id=self.message.id, block_id=self._block.id, delta=ready)

    def end_block(self) -> None:
        self.append('', final=True)
        if self._block is None:
            return
        self.blocks.append(MarkdownBlock(id=self._block.id, content=''.join(self._parts)))
        self._emit('block_end', message_id=self.message.id, block_id=self._block.id)
        self._block = None
        self._parts = []

    def finish(self, status: MessageStatus, *, duration_ms: int) -> AIMessage:
        self.end_block()
        message = self.snapshot(status, duration_ms=duration_ms)
        self._emit('message_end', message=message)
        return message
