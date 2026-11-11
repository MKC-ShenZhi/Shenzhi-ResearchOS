"""Bounded public HTTP fetching for capability adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import httpx

from agent_app.integrations.public_web.security import read_bytes_capped, safe_get


@dataclass(frozen=True)
class PublicResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes

    def json(self):
        import json
        return json.loads(self.content)


def fetch_public(
    url: str, *, timeout: float, max_bytes: int, headers: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> PublicResponse:
    """GET a public HTTP(S) resource with per-hop SSRF checks and a hard body cap."""
    with httpx.Client(timeout=timeout, headers=dict(headers or {}), follow_redirects=False,
                      transport=transport) as client:
        response = safe_get(client, url)
        body = read_bytes_capped(response, max_bytes)
        return PublicResponse(str(response.url), response.status_code,
                              dict(response.headers), body)
