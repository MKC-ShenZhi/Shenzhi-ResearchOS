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


class ScholarSearchRequest(KnowledgeModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator('query')
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('query must not be blank')
        return value


class RelatedPaperSearchRequest(KnowledgeModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(
        default=10,
        ge=1,
        le=20,
        validation_alias=AliasChoices('topK', 'top_k'),
        serialization_alias='topK',
    )

    @field_validator('query')
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('query must not be blank')
        return value


class ScholarSummary(KnowledgeModel):
    id: str
    name: str
    paper_count: int = Field(
        ge=0,
        validation_alias=AliasChoices('paperCount', 'paper_count'),
        serialization_alias='paperCount',
    )
    provenance: Provenance


class ScholarSearchResponse(KnowledgeModel):
    results: list[ScholarSummary] = Field(default_factory=list)


class ScholarReference(KnowledgeModel):
    id: str
    name: str


class ScholarPaper(KnowledgeModel):
    id: str
    title: str
    year: int | None = None


class ScholarDetail(KnowledgeModel):
    id: str
    name: str
    paper_count: int = Field(
        ge=0,
        validation_alias=AliasChoices('paperCount', 'paper_count'),
        serialization_alias='paperCount',
    )
    years: list[int] = Field(default_factory=list)
    conferences: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    funding: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    coauthors: list[ScholarReference] = Field(default_factory=list)
    papers: list[ScholarPaper] = Field(default_factory=list)
    provenance: Provenance


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


class PaperSummary(KnowledgeModel):
    """Small paper representation for list views."""

    id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    provenance: Provenance


class PaperBatchRequest(KnowledgeModel):
    paper_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator('paper_ids')
    @classmethod
    def normalize_paper_ids(cls, value: list[str]) -> list[str]:
        normalized = []
        for paper_id in value:
            if not isinstance(paper_id, str) or not paper_id.strip():
                raise ValueError('paper_ids must contain non-empty strings')
            paper_id = paper_id.strip()
            if paper_id not in normalized:
                normalized.append(paper_id)
        return normalized


class PaperBatchResponse(KnowledgeModel):
    papers: list[PaperSummary] = Field(default_factory=list)


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


OverviewStatus = Literal['available', 'empty', 'unsupported', 'pending', 'error']
MixedSearchType = Literal['paper', 'scholar', 'topic', 'project', 'patent', 'funding', 'graph']


class OverviewTag(KnowledgeModel):
    name: str
    count: int | None = None


class OverviewPaperLibrary(KnowledgeModel):
    paper_count: int | None = Field(
        default=None,
        validation_alias=AliasChoices('paperCount', 'paper_count'),
        serialization_alias='paperCount',
    )
    status: OverviewStatus = 'pending'
    popular_tags: list[OverviewTag] = Field(
        default_factory=list,
        validation_alias=AliasChoices('popularTags', 'popular_tags'),
        serialization_alias='popularTags',
    )
    recent_papers: list[PaperSummary] = Field(
        default_factory=list,
        validation_alias=AliasChoices('recentPapers', 'recent_papers'),
        serialization_alias='recentPapers',
    )


class OverviewHighlight(KnowledgeModel):
    id: str
    name: str
    count: int | None = None
    status: OverviewStatus = 'available'
    metadata: dict[str, Any] = Field(default_factory=dict)


class OverviewResearchAsset(KnowledgeModel):
    count: int | None = None
    supported: bool = False
    status: OverviewStatus = 'pending'


class OverviewResearchAssets(KnowledgeModel):
    total: int | None = None
    status: OverviewStatus = 'pending'
    highlights: list[OverviewHighlight] = Field(default_factory=list)
    by_type: dict[str, OverviewResearchAsset] = Field(
        default_factory=dict,
        validation_alias=AliasChoices('byType', 'by_type'),
        serialization_alias='byType',
    )
    coverage: dict[str, bool] = Field(default_factory=dict)


class OverviewGraphPreview(KnowledgeModel):
    supported: bool = False
    status: OverviewStatus = 'pending'
    root_paper_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices('rootPaperId', 'root_paper_id'),
        serialization_alias='rootPaperId',
    )
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class KnowledgeOverviewResponse(KnowledgeModel):
    as_of: datetime = Field(validation_alias=AliasChoices('asOf', 'as_of'), serialization_alias='asOf')
    scope: str
    paper_library: OverviewPaperLibrary = Field(
        validation_alias=AliasChoices('paperLibrary', 'paper_library'),
        serialization_alias='paperLibrary',
    )
    scholar_highlights: list[OverviewHighlight] = Field(
        default_factory=list,
        validation_alias=AliasChoices('scholarHighlights', 'scholar_highlights'),
        serialization_alias='scholarHighlights',
    )
    topic_highlights: list[OverviewHighlight] = Field(
        default_factory=list,
        validation_alias=AliasChoices('topicHighlights', 'topic_highlights'),
        serialization_alias='topicHighlights',
    )
    research_assets: OverviewResearchAssets = Field(
        validation_alias=AliasChoices('researchAssets', 'research_assets'),
        serialization_alias='researchAssets',
    )
    graph_preview: OverviewGraphPreview = Field(
        validation_alias=AliasChoices('graphPreview', 'graph_preview'),
        serialization_alias='graphPreview',
    )


class PersonalFolderCount(KnowledgeModel):
    id: int
    name: str
    is_default: bool = Field(
        validation_alias=AliasChoices('isDefault', 'is_default'),
        serialization_alias='isDefault',
    )
    paper_count: int = Field(
        validation_alias=AliasChoices('paperCount', 'paper_count'),
        serialization_alias='paperCount',
    )


class PersonalRecentPaper(PaperDetail):
    paper_id: str
    last_viewed_at: datetime


class KnowledgePersonalOverviewResponse(KnowledgeModel):
    auth_required: bool = Field(
        default=False,
        validation_alias=AliasChoices('authRequired', 'auth_required'),
        serialization_alias='authRequired',
    )
    folders: list[PersonalFolderCount] = Field(default_factory=list)
    recent_papers: list[PersonalRecentPaper] = Field(
        default_factory=list,
        validation_alias=AliasChoices('recentPapers', 'recent_papers'),
        serialization_alias='recentPapers',
    )


class KnowledgeMixedSearchRequest(KnowledgeModel):
    query: str = Field(min_length=1, max_length=200)
    types: list[MixedSearchType] = Field(min_length=1, max_length=7)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = None

    @field_validator('query')
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('query must not be blank')
        return value

    @field_validator('types')
    @classmethod
    def normalize_types(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        for item in value:
            if item not in ('paper', 'scholar', 'topic', 'project', 'patent', 'funding', 'graph'):
                raise ValueError('unsupported search type')
            if item not in result:
                result.append(item)
        if not result:
            raise ValueError('types must not be empty')
        return result


class KnowledgeMixedSearchResult(KnowledgeModel):
    type: MixedSearchType
    id: str
    title: str
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    action: str | None = None


class KnowledgeMixedSearchResponse(KnowledgeModel):
    results: list[KnowledgeMixedSearchResult] = Field(default_factory=list)
    supported_types: list[MixedSearchType] = Field(
        default_factory=list,
        validation_alias=AliasChoices('supportedTypes', 'supported_types'),
        serialization_alias='supportedTypes',
    )
    unsupported_types: list[MixedSearchType] = Field(
        default_factory=list,
        validation_alias=AliasChoices('unsupportedTypes', 'unsupported_types'),
        serialization_alias='unsupportedTypes',
    )
    failed_types: list[MixedSearchType] = Field(
        default_factory=list,
        validation_alias=AliasChoices('failedTypes', 'failed_types'),
        serialization_alias='failedTypes',
    )
    next_cursor: str | None = Field(
        default=None,
        validation_alias=AliasChoices('nextCursor', 'next_cursor'),
        serialization_alias='nextCursor',
    )


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
