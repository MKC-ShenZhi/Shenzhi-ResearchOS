"""ShenZhi Knowledge Capability business service."""

from __future__ import annotations

from app.integrations.knowledge.adapter import KnowledgeAdapter
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.schemas.knowledge import (
    KnowledgeError,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    PaperDetail,
    PaperGraph,
)


class KnowledgeServiceError(Exception):
    """Safe domain error returned by the Knowledge service boundary."""

    def __init__(self, error: KnowledgeError | str, status_code: int = 502):
        if isinstance(error, str):
            error = KnowledgeError(
                code='CONTRACT_VIOLATION',
                message='知识底座返回格式无效',
                retryable=False,
                request_id='',
            )
        super().__init__(error.message)
        self.error = error
        self.status_code = status_code

    @classmethod
    def from_integration_error(
        cls, error: KnowledgeIntegrationError
    ) -> 'KnowledgeServiceError':
        return cls(
            KnowledgeError(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                request_id='',
            ),
            status_code=error.status_code,
        )


class KnowledgeService:
    """Thin business boundary shared by the API and future backend callers."""

    def __init__(self, adapter: KnowledgeAdapter | None = None):
        self.adapter = adapter or KnowledgeAdapter()

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        try:
            return await self.adapter.search(request)
        except KnowledgeIntegrationError as error:
            raise KnowledgeServiceError.from_integration_error(error) from error

    async def get_paper(self, paper_id: str) -> PaperDetail:
        try:
            return await self.adapter.paper(paper_id)
        except KnowledgeIntegrationError as error:
            raise KnowledgeServiceError.from_integration_error(error) from error

    async def get_graph(self, paper_id: str, *, depth: int = 1) -> PaperGraph:
        try:
            return await self.adapter.graph(paper_id, depth=depth)
        except KnowledgeIntegrationError as error:
            raise KnowledgeServiceError.from_integration_error(error) from error
