"""ShenZhi-owned contract for browser-consumable paper resources."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


PaperResourceProvider = Literal['openreview', 'http']
PaperResourceStatus = Literal['available', 'unavailable']
PaperResourceReason = Literal[
    'invalid_pdf_url',
    'request_timeout',
    'resource_unavailable',
    'invalid_content_type',
    'pdf_too_large',
]


class PaperResource(BaseModel):
    """A resolved source URL and its browser-consumption availability."""

    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    url: str | None
    provider: PaperResourceProvider
    status: PaperResourceStatus
    reason: PaperResourceReason | None = None
