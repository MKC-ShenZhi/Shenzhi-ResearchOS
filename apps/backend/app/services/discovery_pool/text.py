"""Display cleanup for upstream paper metadata shown on home cards.

Shared by the fallback-snapshot publisher and the knowledge pool sync, so
both produce the same card text. Dependency-free on purpose: the publisher
script imports it without the backend runtime.
"""

from __future__ import annotations

import re
from typing import Any


TITLE_SUFFIX = re.compile(
    r'\s+(?:Thanks?|Acknowledg(?:e)?ments?|Conference|Journal|CCS|ISBN|DOI|Volume):\s*',
    re.IGNORECASE,
)
AUTHOR_NOISE = re.compile(
    r'(?:[{}\\]|https?://|@|\b(?:university|institute|laboratory|department|section|'
    r'equal contribution|corresponding author|work was done|code and data|project leader)\b)',
    re.IGNORECASE,
)
REPEATED_FOOTNOTE_NUMBER = re.compile(r'\s+([1-9])(?:\s+\1){2}(?=\s)')
TRAILING_AUTHOR_FOOTNOTE = re.compile(
    r'\s+[†‡](?:\s*[†‡])*\s+(?:footnotetext:\s*)?[†‡]?\s*'
    r'(?:corresponding author(?:s)?|project leader).*$',
    re.IGNORECASE,
)


def compact_text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.replace('\x00', ' ').split()).strip()


def display_title(value: Any) -> str:
    title = compact_text(value)
    marker = TITLE_SUFFIX.search(title)
    if marker and marker.start() >= 12:
        title = title[:marker.start()].rstrip(' -;,.:')
    return re.sub(r'\s+([,:;])', r'\1', title)


def display_abstract(value: Any) -> str:
    abstract = compact_text(value)
    abstract = REPEATED_FOOTNOTE_NUMBER.sub('', abstract)
    abstract = TRAILING_AUTHOR_FOOTNOTE.sub('', abstract)
    return re.sub(r'\s+([,.;:!?])', r'\1', abstract).strip()


def display_authors(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for candidate in value:
        author = compact_text(candidate).strip(' ,;.')
        if not (2 <= len(author) <= 85) or AUTHOR_NOISE.search(author):
            continue
        if re.fullmatch(r'[a-z][a-z0-9_.-]{3,}', author):
            continue
        if not any(character.isalpha() for character in author):
            continue
        if author not in authors:
            authors.append(author)
    return authors
