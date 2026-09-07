"""Stable ShenZhi-owned contract for the knowledge-base paper journey.

The models in this module deliberately do not mirror the upstream graph
payload.  Upstream presentation fields (for example ``color``) stay behind
the adapter boundary, while IDs and relation names remain opaque strings so
new knowledge-base entity types can be introduced without a backend release.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeModel(BaseModel):
    """Common model configuration for the public knowledge contract."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class Provenance(KnowledgeModel):
    provider: str = 'knowledge-base'
    external_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices('externalId', 'external_id'),
        serialization_alias='externalId',
    )
    retrieved_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices('retrievedAt', 'retrieved_at'),
        serialization_alias='retrievedAt',
    )
    source_version: str | None = Field(
        default=None,
        validation_alias=AliasChoices('sourceVersion', 'source_version'),
        serialization_alias='sourceVersion',
    )


class KnowledgeSearchRequest(KnowledgeModel):
    # The public Capability request has one canonical spelling.  The adapter
    # still maps these fields to the upstream snake_case payload, but the
    # upstream spellings are not accepted by ShenZhi's API boundary.
    model_config = ConfigDict(
        extra='forbid',
        populate_by_name=False,
        validate_by_alias=True,
        validate_by_name=False,
    )

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias='topK',
        serialization_alias='topK',
    )
    # None keeps non-paginated callers (notably Knowledge2Chat) on the
    # existing upstream request. Paper Search sends an explicit offset,
    # including 0 for its first page.
    offset: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(
        default=None,
        validation_alias='yearFrom',
        serialization_alias='yearFrom',
    )
    year_to: int | None = Field(
        default=None,
        validation_alias='yearTo',
        serialization_alias='yearTo',
    )
    venue: list[str] = Field(
        default_factory=list,
        validation_alias='venue',
    )
    author: list[str] = Field(default_factory=list)
    keyword: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)

    @field_validator('query')
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('query must not be blank')
        return value

    @field_validator('venue', 'author', 'keyword', 'subject', mode='before')
    @classmethod
    def normalize_filter_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError('filter values must be a string or list of strings')
        normalized = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError('filter values must be strings')
            item = item.strip()
            if item:
                normalized.append(item)
        return normalized

    @model_validator(mode='after')
    def validate_year_range(self) -> 'KnowledgeSearchRequest':
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError('yearFrom must not be greater than yearTo')
        return self


class PaperSearchResult(KnowledgeModel):
    id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    score: float | None = None
    rank: int | None = None
    provenance: Provenance


class KnowledgeSearchResponse(KnowledgeModel):
    results: list[PaperSearchResult] = Field(default_factory=list)
    has_more: bool = Field(default=False, serialization_alias='hasMore')


class PaperDetail(KnowledgeModel):
    id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    pdf_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices('pdfUrl', 'pdf_url'),
        serialization_alias='pdfUrl',
    )
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    citation_count: int | None = Field(
        default=None,
        validation_alias=AliasChoices('citationCount', 'citation_count'),
        serialization_alias='citationCount',
    )
    reference_count: int | None = Field(
        default=None,
        validation_alias=AliasChoices('referenceCount', 'reference_count'),
        serialization_alias='referenceCount',
    )
    provenance: Provenance


class GraphNode(KnowledgeModel):
    id: str
    kind: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance


class GraphEdge(KnowledgeModel):
    source_id: str = Field(
        validation_alias=AliasChoices('sourceId', 'source_id'),
        serialization_alias='sourceId',
    )
    target_id: str = Field(
        validation_alias=AliasChoices('targetId', 'target_id'),
        serialization_alias='targetId',
    )
    relation: str
    description: str | None = None
    weight: float | None = None
    provenance: Provenance


class PaperGraph(KnowledgeModel):
    root_id: str = Field(
        validation_alias=AliasChoices('rootId', 'root_id'),
        serialization_alias='rootId',
    )
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    provenance: Provenance


class KnowledgeError(KnowledgeModel):
    """Safe error payload exposed by the Knowledge API.

    ``code`` is a stable string classification, not a legacy numeric code.
    """

    code: Literal[
        'NOT_FOUND',
        'INVALID_ARGUMENT',
        'RATE_LIMITED',
        'UPSTREAM_UNAVAILABLE',
        'TIMEOUT',
        'CONTRACT_VIOLATION',
        'UNKNOWN',
    ]
    message: str
    retryable: bool
    request_id: str | None = Field(
        validation_alias=AliasChoices('requestId', 'request_id'),
        serialization_alias='requestId',
    )
