"""Public contract for the database-backed home discovery feed."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.knowledge import KnowledgeModel, PaperSearchResult


DiscoveryFeedTab = Literal['recommend', 'frontier', 'follow', 'research']


class DailyRecommendationResponse(KnowledgeModel):
    date: date
    items: list[PaperSearchResult] = Field(default_factory=list)
