"""Public contract for the versioned home paper-discovery snapshot."""

from pydantic import Field

from app.schemas.knowledge import KnowledgeModel


class DiscoveryPaper(KnowledgeModel):
    id: str
    title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    year: int
    venue: str | None = None
    pdf_url: str | None = None
    thumbnail_url: str | None = None
    # Knowledge image path for pool papers; the web layer resolves it to its image proxy.
    image_id: str | None = None
    # Card topics, shown like knowledge search cards: keywords first, else subjects.
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    # Which home-feed source placed the paper (daily / trending / personal / fallback).
    source: str | None = None


class DiscoveryPaperPage(KnowledgeModel):
    items: list[DiscoveryPaper] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    snapshot_id: str
    total: int = Field(ge=0)
