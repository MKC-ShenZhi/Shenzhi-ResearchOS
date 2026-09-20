"""Runtime evidence contract used by Chat without exposing Knowledge schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping


REFERENCE_CONTEXT_MAX_CHARS = 48_000
_REFERENCE_ABSTRACT_MAX_CHARS = 4_000
_REFERENCE_FIELD_MAX_CHARS = 512


@dataclass(frozen=True)
class KnowledgeContextItem:
    """One grounding-ready paper returned by the Knowledge Capability."""

    reference_id: str
    resource_type: str
    resource_id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: Any = None
    score: float | None = None

    def snapshot(self) -> dict[str, Any]:
        """Return the durable/reference payload for this exact evidence item."""
        authors = self.metadata.get("authors", [])
        author_names = [author for author in authors if isinstance(author, str)] \
            if isinstance(authors, list) else []
        return {
            "referenceId": self.reference_id,
            "resourceType": self.resource_type,
            "resourceId": self.resource_id,
            "title": self.title,
            "content": self.content,
            "metadata": dict(self.metadata),
            "provenance": self.provenance,
            "score": self.score,
            # These aliases keep the existing Chat source card contract readable
            # while the canonical snapshot fields above remain authoritative.
            "ordinal": int(self.reference_id),
            "source_type": self.resource_type,
            "source_id": self.resource_id,
            "venue": self.metadata.get("venue"),
            "org": None,
            "authors": " · ".join(author_names),
            "citation_count": None,
            "recommended": self.reference_id == "1",
            "url": None,
        }


@dataclass(frozen=True)
class EvidenceBundle:
    """The small Chat-facing Knowledge evidence envelope."""

    provider: Literal["knowledge"] = "knowledge"
    status: Literal["ready"] = "ready"
    items: list[KnowledgeContextItem] = field(default_factory=list)


@dataclass(frozen=True)
class FormattedReferenceData:
    """Runtime-only prompt text and whether deterministic bounds changed it."""

    text: str
    truncated: bool


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _provenance(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


class KnowledgeContextBuilder:
    """Filter and number SearchResponse results without changing their order."""

    def __init__(self, top_k: int = 10):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.top_k = top_k

    def build(self, response: Any) -> EvidenceBundle:
        results = _value(response, "results", [])
        if not isinstance(results, list):
            return EvidenceBundle(items=[])

        items: list[KnowledgeContextItem] = []
        for result in results:
            if len(items) >= self.top_k:
                break
            paper_id = _value(result, "id")
            title = _value(result, "title")
            abstract = _value(result, "abstract")
            # A missing abstract is not usable grounding and must not become
            # the string "None" or an empty synthetic document.
            if not isinstance(paper_id, str) or not paper_id:
                continue
            if not isinstance(title, str) or not title:
                continue
            if not isinstance(abstract, str) or not abstract.strip():
                continue
            authors = _value(result, "authors", [])
            if not isinstance(authors, list):
                authors = []
            metadata = {
                "authors": list(authors),
                "year": _value(result, "year"),
                "venue": _value(result, "venue"),
            }
            items.append(KnowledgeContextItem(
                reference_id=str(len(items) + 1),
                resource_type="paper",
                resource_id=paper_id,
                title=title,
                # Preserve the upstream abstract as supplied; strip is only
                # used above to decide whether the field is usable.
                content=abstract,
                metadata=metadata,
                provenance=_provenance(_value(result, "provenance")),
                score=_value(result, "score"),
            ))
        return EvidenceBundle(items=items)


def snapshots_for_bundle(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    return [item.snapshot() for item in bundle.items]


def _safe_text(value: Any, max_chars: int = _REFERENCE_FIELD_MAX_CHARS) -> tuple[str, bool]:
    """Keep untrusted values on one data line and neutralize delimiter syntax."""
    raw = str(value)
    truncated = len(raw) > max_chars
    raw = raw[:max_chars]
    escaped = (raw.replace("\\", "\\\\")
                   .replace("\r", "\\r")
                   .replace("\n", "\\n")
                   .replace("<", "\\u003c")
                   .replace(">", "\\u003e")
                   .replace("&", "\\u0026"))
    return escaped, truncated


def _reference_items(bundle: EvidenceBundle | Iterable[KnowledgeContextItem]) -> list[KnowledgeContextItem]:
    return bundle.items if isinstance(bundle, EvidenceBundle) else list(bundle)


def _render_reference_item(item: KnowledgeContextItem, abstract: str) -> tuple[str, bool]:
    lines = [
        f"[{_safe_text(item.reference_id)[0]}]",
        f"resource_type: {_safe_text(item.resource_type)[0]}",
        f"resource_id: {_safe_text(item.resource_id)[0]}",
        f"title: {_safe_text(item.title)[0]}",
    ]
    truncated = any(_safe_text(value)[1] for value in (
        item.reference_id, item.resource_type, item.resource_id, item.title,
    ))
    authors = item.metadata.get("authors")
    if isinstance(authors, list) and authors:
        author_text, author_truncated = _safe_text(
            ", ".join(str(author) for author in authors)
        )
        lines.append(f"authors: {author_text}")
        truncated = truncated or author_truncated
    if item.metadata.get("year") is not None:
        year, year_truncated = _safe_text(item.metadata["year"])
        lines.append(f"year: {year}")
        truncated = truncated or year_truncated
    if item.metadata.get("venue"):
        venue, venue_truncated = _safe_text(item.metadata["venue"])
        lines.append(f"venue: {venue}")
        truncated = truncated or venue_truncated
    safe_abstract, abstract_truncated = _safe_text(
        abstract, _REFERENCE_ABSTRACT_MAX_CHARS
    )
    lines.extend(["abstract:", safe_abstract, ""])
    return "\n".join(lines), truncated or abstract_truncated


def _wrapped_reference_data(blocks: list[str]) -> str:
    body = "\n".join(blocks)
    return "<reference_data>\n" + body + "\n</reference_data>"


def _max_prefix_that_fits(
    item: KnowledgeContextItem,
    blocks: list[str],
    index: int,
    max_chars: int,
) -> int:
    high = min(len(item.content), _REFERENCE_ABSTRACT_MAX_CHARS)
    low = 0
    best = 0
    while low <= high:
        candidate = (low + high) // 2
        rendered, _ = _render_reference_item(item, item.content[:candidate])
        trial = list(blocks)
        trial[index] = rendered
        if len(_wrapped_reference_data(trial)) <= max_chars:
            best = candidate
            low = candidate + 1
        else:
            high = candidate - 1
    return best


def format_reference_data_with_status(
    bundle: EvidenceBundle | Iterable[KnowledgeContextItem],
    *,
    max_chars: int = REFERENCE_CONTEXT_MAX_CHARS,
) -> FormattedReferenceData:
    """Format bounded, escaped runtime evidence without changing its snapshot."""
    if max_chars < len(_wrapped_reference_data([])):
        raise ValueError("max_chars is too small for reference_data delimiters")

    items = _reference_items(bundle)
    blocks = [_render_reference_item(item, "")[0] for item in items]
    if len(_wrapped_reference_data(blocks)) > max_chars:
        raise ValueError("max_chars is too small for reference metadata")

    truncated = False
    for index, item in enumerate(items):
        candidate = _max_prefix_that_fits(item, blocks, index, max_chars)
        blocks[index], item_truncated = _render_reference_item(
            item, item.content[:candidate]
        )
        truncated = truncated or item_truncated or candidate < len(item.content)

    return FormattedReferenceData(_wrapped_reference_data(blocks), truncated)


def format_reference_data(
    bundle: EvidenceBundle | Iterable[KnowledgeContextItem],
    *,
    max_chars: int = REFERENCE_CONTEXT_MAX_CHARS,
) -> str:
    """Format evidence for the model; snapshots retain the unmodified content."""
    return format_reference_data_with_status(bundle, max_chars=max_chars).text


def _citation_ids(answer: str) -> Iterable[str]:
    return (match.group(1) for match in re.finditer(r"\[(\d+)\]", answer))


def citation_reference_ids(
    answer: str,
    bundle: EvidenceBundle | Iterable[KnowledgeContextItem],
) -> list[str]:
    """Return valid citation IDs once, preserving their first appearance."""
    valid = {item.reference_id for item in _reference_items(bundle)}
    seen: set[str] = set()
    cited: list[str] = []
    for reference_id in _citation_ids(answer):
        if reference_id in valid and reference_id not in seen:
            seen.add(reference_id)
            cited.append(reference_id)
    return cited


def validate_citations(answer: str, bundle: EvidenceBundle | Iterable[KnowledgeContextItem]) -> list[str]:
    """Return citation numbers in the answer that are absent from the evidence."""
    valid = {item.reference_id for item in _reference_items(bundle)}
    invalid: list[str] = []
    for reference_id in _citation_ids(answer):
        if reference_id not in valid and reference_id not in invalid:
            invalid.append(reference_id)
    return invalid


__all__ = [
    "EvidenceBundle",
    "FormattedReferenceData",
    "KnowledgeContextBuilder",
    "KnowledgeContextItem",
    "REFERENCE_CONTEXT_MAX_CHARS",
    "citation_reference_ids",
    "format_reference_data",
    "format_reference_data_with_status",
    "snapshots_for_bundle",
    "validate_citations",
]
