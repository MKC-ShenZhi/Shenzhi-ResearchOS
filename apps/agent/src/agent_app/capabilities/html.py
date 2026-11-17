"""Shared HTML-to-text cleanup used by web and paper Agent capabilities."""
from __future__ import annotations

import re
import lxml.html

_STRIP_TAGS = ('script', 'style', 'noscript', 'nav', 'footer', 'header', 'form', 'svg')


def html_text(raw: bytes) -> str:
    try:
        document=lxml.html.fromstring(raw)
    except Exception:
        return ''
    for tag in document.iter(*_STRIP_TAGS):
        tag.drop_tree()
    text = document.text_content()
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    return text.strip()
