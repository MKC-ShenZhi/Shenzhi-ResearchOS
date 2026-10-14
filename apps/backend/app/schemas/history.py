"""Schemas for authenticated paper reading history."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class PaperReadStatusRequest(BaseModel):
    paper_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator('paper_ids')
    @classmethod
    def validate_paper_ids(cls, paper_ids: list[str]) -> list[str]:
        if any(not paper_id.strip() for paper_id in paper_ids):
            raise ValueError('paper_ids must contain non-empty IDs')
        return list(dict.fromkeys(paper_ids))


class PaperReadStatusResponse(BaseModel):
    user_id: str
    read_paper_ids: list[str]
    reading_paper_ids: list[str]


class PaperViewRequest(BaseModel):
    paper_id: str = Field(min_length=1)

    @field_validator('paper_id')
    @classmethod
    def validate_paper_id(cls, paper_id: str) -> str:
        if not paper_id.strip():
            raise ValueError('paper_id must not be blank')
        return paper_id
