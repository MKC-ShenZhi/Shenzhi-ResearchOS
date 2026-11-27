"""Message schema v1: only Markdown and independently registered references.

Presentation messages are separate from the provider's tool-call transcript.
Add future block models to ContentBlock; transport envelopes stay unchanged.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CITATION = re.compile(r'\[\[cite:([^\[\]\r\n]*)\]\]')
MessageStatus = Literal['running', 'done', 'failed', 'stopped', 'timeout', 'awaiting_input']
ReferenceType = Literal['paper', 'author', 'institution', 'webpage', 'dataset', 'funding']


class MessageModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, revalidate_instances='always')


class MarkdownBlock(MessageModel):
    id: str = Field(min_length=1)
    type: Literal['markdown'] = 'markdown'
    content: str = ''


ContentBlock = Annotated[MarkdownBlock, Field(discriminator='type')]


class Reference(MessageModel):
    id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_.:-]+$')
    type: ReferenceType
    title: str = Field(min_length=1)
    url: str | None = None
    entity_id: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None


class MessageMetadata(MessageModel):
    id: str = Field(min_length=1)
    role: Literal['assistant'] = 'assistant'
    status: MessageStatus = 'running'
    created_at: float = Field(ge=0, allow_inf_nan=False)
    schema_version: Literal[1] = 1
    metadata: dict[str, Any] | None = None


class AIMessage(MessageMetadata):
    blocks: list[ContentBlock] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid_links(self) -> AIMessage:
        for name, items in (('block', self.blocks), ('reference', self.references)):
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f'duplicate {name} id')
        references = {ref.id for ref in self.references}
        for block in self.blocks:
            if isinstance(block, MarkdownBlock):
                missing = set(CITATION.findall(block.content)) - references
                if missing:
                    raise ValueError(f'unresolved citations: {sorted(missing)}')
        return self


class MessageStart(MessageModel):
    message: AIMessage

    @model_validator(mode='after')
    def running_message(self):
        if self.message.status != 'running':
            raise ValueError('message_start requires a running message')
        return self


class BlockStart(MessageModel):
    message_id: str = Field(min_length=1)
    block: ContentBlock


class BlockDelta(MessageModel):
    message_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    delta: str


class BlockEnd(MessageModel):
    message_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)


class ReferenceUpsert(MessageModel):
    message_id: str = Field(min_length=1)
    reference: Reference


class MessageEnd(MessageModel):
    message: AIMessage

    @model_validator(mode='after')
    def terminal_message(self):
        if self.message.status == 'running':
            raise ValueError('message_end requires a terminal message')
        return self


MESSAGE_EVENT_MODELS = {
    'message_start': MessageStart,
    'block_start': BlockStart,
    'block_delta': BlockDelta,
    'block_end': BlockEnd,
    'reference_upsert': ReferenceUpsert,
    'message_end': MessageEnd,
}
