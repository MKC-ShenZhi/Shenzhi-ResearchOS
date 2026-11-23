"""Rule B: the one admission check every home-feed source passes through.

A source may produce candidates however it likes (offline pool, live recall,
packaged snapshot); before a paper can reach a home card it is cleaned with the
shared display rules and rejected when a card could not show it properly.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.schemas.discovery import DiscoveryPaper
from app.services.discovery_pool.text import display_abstract, display_authors, display_title

MIN_TITLE_LENGTH = 8
MIN_ABSTRACT_LENGTH = 200
MAX_TOPICS = 8

# Mirrors apps/web/lib/paper-thumbnail.ts: anything the web image proxy would
# reject (SVG included, which must not be served same-origin) is not displayable.
_IMAGE_PART = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
_IMAGE_SUFFIX = re.compile(r'\.(png|jpe?g|webp)$', re.IGNORECASE)
# Packaged fallback papers ship their own optimized WebP under the web app.
_STATIC_THUMBNAIL = re.compile(r'^/paper-thumbnails/[A-Za-z0-9][A-Za-z0-9._-]*\.webp$')
# PDF extraction sometimes stores a section heading as the title ("1 Introduction").
_SECTION_TITLE = re.compile(
    r'^(?:\d+(?:\.\d+)*\.?\s+)?(?:abstract|introduction|related works?|background|'
    r'conclusions?|references|acknowledg(?:e)?ments?|appendix)$',
    re.IGNORECASE,
)
# Upstream subjects occasionally carry the venue label, e.g. "CVPR.2024 - Accept".
_VENUE_LABEL = re.compile(r'^[A-Za-z][\w&-]*\.\d{4}\b')


def displayable_image_id(value: str | None) -> bool:
    if not value or not value.startswith('/images/'):
        return False
    parts = value[len('/images/'):].split('/')
    return (0 < len(parts) <= 16
            and all(len(part) <= 255 and _IMAGE_PART.match(part) for part in parts)
            and bool(_IMAGE_SUFFIX.search(parts[-1])))


def display_topics(values: Any) -> list[str]:
    topics: list[str] = []
    for value in values if isinstance(values, list) else []:
        topic = ' '.join(value.split()) if isinstance(value, str) else ''
        if topic and not _VENUE_LABEL.match(topic) and topic not in topics:
            topics.append(topic)
    return topics[:MAX_TOPICS]


def admit(raw: Mapping[str, Any], *, year: int | None = None) -> tuple[DiscoveryPaper | None, str | None]:
    """Return the cleaned card paper, or the reason a home card could not show it.

    `raw` uses the DiscoveryPaper field names; `year`, when given, is required.
    """
    image_id = raw.get('image_id') or None
    thumbnail_url = raw.get('thumbnail_url') or None
    if thumbnail_url and not _STATIC_THUMBNAIL.match(thumbnail_url):
        thumbnail_url = None
    if not thumbnail_url:
        if not image_id:
            return None, 'image_missing'
        if not displayable_image_id(image_id):
            return None, 'image_format'
    if image_id and not displayable_image_id(image_id):
        image_id = None
    if year is not None and raw.get('year') != year:
        return None, 'year'
    if not isinstance(raw.get('year'), int):
        return None, 'year'
    title = display_title(raw.get('title'))
    if len(title) < MIN_TITLE_LENGTH or _SECTION_TITLE.match(title):
        return None, 'title'
    abstract = display_abstract(raw.get('abstract'))
    if len(abstract) < MIN_ABSTRACT_LENGTH:
        return None, 'abstract'
    authors = display_authors(raw.get('authors'))
    if not authors:
        return None, 'authors'
    venue = raw.get('venue')
    return DiscoveryPaper(
        id=raw['id'], title=title, abstract=abstract, authors=authors, year=raw['year'],
        venue=venue.strip() if isinstance(venue, str) and venue.strip() else None,
        pdf_url=raw.get('pdf_url') or None, thumbnail_url=thumbnail_url, image_id=image_id,
        keywords=display_topics(raw.get('keywords')), subjects=display_topics(raw.get('subjects')),
        topics=raw.get('topics'),
    ), None
