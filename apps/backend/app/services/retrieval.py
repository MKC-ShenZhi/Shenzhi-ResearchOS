from __future__ import annotations

import os
from typing import Any

import httpx

RETRIEVAL_BASE_URL = os.getenv("RETRIEVAL_API_URL", "").rstrip("/")
RETRIEVAL_TIMEOUT = float(os.getenv("RETRIEVAL_TIMEOUT_SEC", "30"))

VENUE_TONES = ("violet", "amber", "green")


def _authors_text(raw: Any) -> str:
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
        return " · ".join(parts) if parts else "未知作者"
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "未知作者"


def _tags(item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("keywords", "subjects"):
        val = item.get(key)
        if isinstance(val, list):
            tags.extend(str(x).strip() for x in val if str(x).strip())
    return tags[:6]


def map_hit_to_feed_paper(item: dict[str, Any], index: int) -> dict[str, Any]:
    paper_id = str(item.get("paper_id") or item.get("id") or f"paper-{index}")
    year = item.get("year")
    venue = str(item.get("conference") or item.get("venue") or "论文")
    return {
        "id": paper_id,
        "date": str(year) if year else "",
        "venue": venue,
        "venueTone": VENUE_TONES[index % len(VENUE_TONES)],
        "authors": _authors_text(item.get("authors")),
        "title": str(item.get("title") or "未命名论文"),
        "abstract": str(item.get("abstract") or ""),
        "aiLink": "AI 深度解读",
        "tags": _tags(item),
        "likes": 0,
        "citations": int(item.get("citation_count") or 0),
        "thumb": "论文摘要图",
        "rank": item.get("rank", index + 1),
        "score": item.get("score"),
    }


def map_hit_to_reference(item: dict[str, Any], ordinal: int) -> dict[str, Any]:
    paper_id = str(item.get("paper_id") or item.get("id") or f"paper-{ordinal}")
    venue = item.get("conference") or item.get("venue")
    return {
        "ordinal": ordinal,
        "source_type": "paper",
        "source_id": paper_id,
        "title": str(item.get("title") or "未命名论文"),
        "venue": str(venue) if venue else None,
        "org": None,
        "authors": _authors_text(item.get("authors")),
        "citation_count": int(item.get("citation_count") or 0),
        "recommended": ordinal == 1,
        "url": None,
    }


async def retrieval_search(
    query: str,
    *,
    top_k: int = 10,
    mode: str = "fast",
) -> list[dict[str, Any]]:
    """调用外部论文检索 API，失败时返回空列表。"""
    if not RETRIEVAL_BASE_URL:
        return []
    limit = min(max(top_k, 1), 20)
    if mode == "fast":
        limit = min(limit, 5)

    payload = {"query": query.strip(), "top_k": limit}
    url = f"{RETRIEVAL_BASE_URL}/api/retrieval/search"

    try:
        async with httpx.AsyncClient(timeout=RETRIEVAL_TIMEOUT) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            body = res.json()
    except (httpx.HTTPError, ValueError):
        return []

    results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


async def retrieval_health_ok() -> bool:
    url = f"{RETRIEVAL_BASE_URL}/api/retrieval/ready"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url)
            return res.status_code == 200
    except httpx.HTTPError:
        return False
