"""Built-in paper resource providers."""

from app.integrations.paper_resource.base import PDFProvider
from app.integrations.paper_resource.http import HTTPProvider
from app.integrations.paper_resource.openreview import OpenReviewProvider

__all__ = ['PDFProvider', 'HTTPProvider', 'OpenReviewProvider']
