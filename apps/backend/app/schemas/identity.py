from pydantic import BaseModel, Field


class AnonymousClaimResult(BaseModel):
    moved_count: int = Field(ge=0)
    skipped_streaming_count: int = Field(ge=0)
    durable: bool
