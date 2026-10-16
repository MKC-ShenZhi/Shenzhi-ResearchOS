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


class DiscoveryPaperPage(KnowledgeModel):
    items: list[DiscoveryPaper] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    snapshot_id: str
    total: int = Field(ge=0)
