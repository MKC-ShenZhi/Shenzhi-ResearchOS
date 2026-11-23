"""URL discovery for full-text sources consumed by the Agent read-paper capability."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote


def pdf_candidates(url: str) -> list[str]:
    """Expand known arXiv, OpenReview and DOI URLs into public PDF candidates."""
    url=url.strip(); out=[url]
    arxiv=re.search(r'arxiv\.org/(abs|pdf)/([0-9]+\.[0-9]+)',url)
    if arxiv:
        ident=arxiv.group(2); out += [f'https://arxiv.org/pdf/{ident}',f'https://arxiv.org/abs/{ident}']
    review=re.search(r'openreview\.net/forum\?id=([\w-]+)',url)
    if review: out.append(f'https://openreview.net/pdf?id={review.group(1)}')
    doi=re.search(r'doi\.org/(10\.[^\s?#]+)',url)
    if doi: out.append(f'https://api.unpaywall.org/v2/{quote(doi.group(1),safe="")}?email=research@example.org')
    seen=set(); return [item for item in out if not (item in seen or seen.add(item))]


def unpaywall_pdf(body: Any) -> str | None:
    """Choose the best available open-access PDF URL from an Unpaywall response."""
    if not isinstance(body,dict): return None
    best=body.get('best_oa_location')
    if isinstance(best,dict) and isinstance(best.get('url_for_pdf'),str): return best['url_for_pdf']
    for location in body.get('oa_locations') or []:
        if isinstance(location,dict) and isinstance(location.get('url_for_pdf'),str):
            return location['url_for_pdf']
    return None
