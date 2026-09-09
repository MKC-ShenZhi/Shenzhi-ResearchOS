"""Schemas for authenticated paper reading history."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.knowledge import PaperDetail


class ReadingHistoryItem(PaperDetail):
    paper_id: str
    last_viewed_at: datetime


class ReadingHistoryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ReadingHistoryItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int