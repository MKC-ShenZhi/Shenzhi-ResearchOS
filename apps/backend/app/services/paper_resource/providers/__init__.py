"""Built-in paper resource providers."""

from app.services.paper_resource.providers.base import PDFProvider
from app.services.paper_resource.providers.http import HTTPProvider
from app.services.paper_resource.providers.openreview import OpenReviewProvider

__all__ = ['PDFProvider', 'HTTPProvider', 'OpenReviewProvider']
