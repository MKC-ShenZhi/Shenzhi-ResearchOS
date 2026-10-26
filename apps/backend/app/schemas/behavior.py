"""Bounded browser behavior ingestion; explicit state changes are server owned."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ImplicitEventType = Literal[
    'paper_impression', 'paper_click', 'paper_detail_view', 'abstract_expand',
    'active_read', 'search_result_click', 'recommendation_impression', 'recommendation_click',
    'search_submit',
]
EventSource = Literal['discovery', 'recommendation', 'search', 'paper_detail']


class BehaviorEventInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: UUID
    event_type: ImplicitEventType
    paper_id: str | None = Field(default=None, min_length=1, max_length=255)
    query: str | None = Field(default=None, min_length=1, max_length=200)
    source: EventSource
    request_id: str | None = Field(default=None, max_length=128)
    query_id: UUID | None = None
    rank: int | None = Field(default=None, ge=1, le=1000)
    duration_seconds: int | None = Field(default=None, ge=30, le=1800)

    @model_validator(mode='after')
    def validate_context(self):
        if self.event_type == 'search_submit':
            if self.source != 'search' or not self.query or self.paper_id is not None:
                raise ValueError('search_submit requires a search query and no paper_id')
        elif self.paper_id is None or self.query is not None:
            raise ValueError('paper events require paper_id and no query')
        if self.query_id is not None and (self.source != 'search' or self.event_type not in ('search_submit', 'search_result_click')):
            raise ValueError('query_id only applies to search events')
        if self.event_type.startswith('recommendation_') and (self.source != 'recommendation' or not self.request_id or self.rank is None):
            raise ValueError('recommendation events require source, request_id and rank')
        if self.event_type.startswith('recommendation_'):
            try:
                UUID(self.request_id or '')
            except ValueError as error:
                raise ValueError('recommendation request_id must be a UUID') from error
        if self.event_type == 'active_read' and self.duration_seconds is None:
            raise ValueError('active_read requires duration_seconds')
        if self.event_type != 'active_read' and self.duration_seconds is not None:
            raise ValueError('duration_seconds only applies to active_read')
        return self


class BehaviorBatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[BehaviorEventInput] = Field(min_length=1, max_length=20)
