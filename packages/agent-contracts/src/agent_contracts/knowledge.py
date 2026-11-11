"""Shared wire schemas for Agent access to Backend-owned Knowledge services."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .wire import WireModel


class KnowledgeProvenanceWire(WireModel):
    provider: str = 'knowledge-base'
    external_id: str | None = Field(default=None, alias='externalId')
    retrieved_at: datetime | None = Field(default=None, alias='retrievedAt')
    source_version: str | None = Field(default=None, alias='sourceVersion')


class KnowledgeSearchRequestWire(WireModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, alias='topK', ge=1, le=100)
    offset: int | None = Field(default=None, ge=0)
    year_from: int | None = Field(default=None, alias='yearFrom')
    year_to: int | None = Field(default=None, alias='yearTo')
    venue: list[str] = Field(default_factory=list)
    author: list[str] = Field(default_factory=list)
    keyword: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)


class KnowledgePaperResultWire(WireModel):
    id: str
    image_id: str | None = Field(default=None, alias='imageId')
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    score: float | None = None
    rank: int | None = None
    provenance: KnowledgeProvenanceWire


class KnowledgeSearchResponseWire(WireModel):
    results: list[KnowledgePaperResultWire] = Field(default_factory=list)
    has_more: bool = Field(default=False, alias='hasMore')
    total: int | None = None


class KnowledgeGraphQueryWire(WireModel):
    depth: int = Field(default=1, ge=1, le=3)


class KnowledgePaperDetailWire(KnowledgePaperResultWire):
    doi: str | None = None
    pdf_url: str | None = Field(default=None, alias='pdfUrl')
    citation_count: int | None = Field(default=None, alias='citationCount')
    reference_count: int | None = Field(default=None, alias='referenceCount')


class KnowledgeGraphNodeWire(WireModel):
    id: str
    kind: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: KnowledgeProvenanceWire


class KnowledgeGraphEdgeWire(WireModel):
    source_id: str = Field(alias='sourceId')
    target_id: str = Field(alias='targetId')
    relation: str
    description: str | None = None
    weight: float | None = None
    provenance: KnowledgeProvenanceWire


class KnowledgePaperGraphWire(WireModel):
    root_id: str = Field(alias='rootId')
    nodes: list[KnowledgeGraphNodeWire] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdgeWire] = Field(default_factory=list)
    provenance: KnowledgeProvenanceWire
