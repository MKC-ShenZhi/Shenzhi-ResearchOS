"""The upstream Knowledge Base API contract.

These types intentionally retain the Research Capability's field names. They
are transport-bound descriptions, not ShenZhi's public Knowledge contract.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class UpstreamSearchPayload(TypedDict):
    query: str
    top_k: int
    year_gte: NotRequired[int]
    year_lte: NotRequired[int]
    conference: NotRequired[list[str]]
    author: NotRequired[list[str]]
    keyword: NotRequired[list[str]]
    subject: NotRequired[list[str]]


class UpstreamSearchResult(TypedDict):
    paper_id: str
    title: str
    abstract: NotRequired[str | None]
    conference: NotRequired[str | None]
    venue: NotRequired[str | None]
    authors: NotRequired[list[str] | str | None]
    year: NotRequired[int | str | None]
    keywords: NotRequired[list[str] | str | None]
    subjects: NotRequired[list[str] | str | None]
    score: NotRequired[int | float | str | None]
    rank: NotRequired[int | str | None]


class UpstreamSearchResponse(TypedDict):
    results: list[UpstreamSearchResult]
    total: NotRequired[int]
    state: NotRequired[dict[str, Any]]
    query_parse: NotRequired[dict[str, Any]]
    query_rewrite: NotRequired[dict[str, Any]]


class UpstreamScholarSearchResult(TypedDict):
    scholar_id: str
    name: str
    paper_count: int | str


class UpstreamScholarSearchResponse(TypedDict):
    results: list[UpstreamScholarSearchResult]
    query: NotRequired[str]


class UpstreamFundingSearchResult(TypedDict):
    funding_id: str
    name: str
    paper_count: int | str


class UpstreamFundingSearchResponse(TypedDict):
    results: list[UpstreamFundingSearchResult]
    query: NotRequired[str]


class UpstreamPaperSummaryResponse(TypedDict):
    paper_count: int | str


class UpstreamResearchAssetsSummaryResponse(TypedDict):
    research_asset_count: int | str


class UpstreamScholarReference(TypedDict):
    scholar_id: str
    name: str


class UpstreamScholarPaper(TypedDict):
    paper_id: str
    title: str
    year: NotRequired[int | str | None]


class UpstreamScholarResponse(TypedDict):
    scholar_id: str
    name: str
    paper_count: int | str
    years: NotRequired[list[int | str] | None]
    conferences: NotRequired[list[str] | None]
    topics: NotRequired[list[str] | None]
    funding: NotRequired[list[str] | None]
    institutions: NotRequired[list[str] | None]
    coauthors: NotRequired[list[UpstreamScholarReference] | None]
    papers: NotRequired[list[UpstreamScholarPaper] | None]


class UpstreamFundingSearchResult(TypedDict):
    funding_id: str
    name: str
    paper_count: int | str


class UpstreamFundingSearchResponse(TypedDict):
    results: list[UpstreamFundingSearchResult]
    query: NotRequired[str]


class UpstreamPaperResponse(TypedDict):
    paper_id: str
    title: str
    abstract: NotRequired[str | None]
    authors: NotRequired[list[str] | str | None]
    year: NotRequired[int | str | None]
    venue: NotRequired[str | None]
    conference: NotRequired[str | None]
    doi: NotRequired[str | None]
    pdf_url: NotRequired[str | None]
    pdfUrl: NotRequired[str | None]
    keywords: NotRequired[list[str] | str | None]
    subjects: NotRequired[list[str] | str | None]
    citationCount: NotRequired[int | str | None]
    citation_count: NotRequired[int | str | None]
    citeCount: NotRequired[int | str | None]
    cite_count: NotRequired[int | str | None]
    referenceCount: NotRequired[int | str | None]
    reference_count: NotRequired[int | str | None]


class UpstreamGraphNode(TypedDict, total=False):
    id: str
    text: str
    title: str
    color: str
    borderColor: str
    data: dict[str, Any]


UpstreamGraphEdge = TypedDict(
    'UpstreamGraphEdge',
    {
        'from': str,
        'to': str,
        'text': NotRequired[str],
        'description': NotRequired[str],
        'data': NotRequired[dict[str, Any]],
    },
    total=False,
)


class UpstreamGraphResponse(TypedDict):
    rootId: str
    nodes: list[UpstreamGraphNode]
    lines: list[UpstreamGraphEdge]
