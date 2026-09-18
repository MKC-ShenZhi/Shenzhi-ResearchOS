"""Public schemas for paper collection folders and items."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.knowledge import PaperDetail


class FolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CollectionFolder(BaseModel):
    id: int
    name: str
    is_default: bool
    paper_count: int


class FolderListResponse(BaseModel):
    folders: list[CollectionFolder]


class CollectionPaperItem(PaperDetail):
    paper_id: str
    added_at: datetime


class CollectionPaperListResponse(BaseModel):
    items: list[CollectionPaperItem]
    total: int
    page: int
    page_size: int


class PaperCollectionResponse(BaseModel):
    folder_ids: list[int]


class PaperCollectionUpdateRequest(BaseModel):
    folder_ids: list[int]


class MoveCollectionItemRequest(BaseModel):
    target_folder_id: int