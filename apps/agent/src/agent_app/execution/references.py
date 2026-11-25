"""Reference identity and deduplication shared by tool adapters and message assembly."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agent_contracts.messages import Reference


def _url_key(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip('/'), parts.query, ''))


def reference_keys(reference: Reference) -> set[tuple[str, str, str]]:
    keys = set()
    for kind, value in (('entity', reference.entity_id), ('doi', reference.doi), ('url', reference.url)):
        if value:
            normalized = value.strip()
            if kind == 'url':
                normalized = _url_key(normalized)
            elif kind == 'doi':
                normalized = normalized.lower().removeprefix('https://doi.org/').removeprefix('doi:')
            keys.add((reference.type, kind, normalized))
    return keys or {(reference.type, 'title', reference.title.strip().casefold())}


def source_reference(**fields: Any) -> Reference:
    """Tool adapter helper: program-generated identity, never supplied by the LLM."""
    reference = Reference(id='source', **fields)
    priority = {'entity': 0, 'doi': 1, 'url': 2, 'title': 3}
    key = min(reference_keys(reference), key=lambda key: (priority[key[1]], key))
    identifier = hashlib.sha256(repr(key).encode()).hexdigest()[:24]
    return Reference(**{**reference.model_dump(), 'id': f'ref_{identifier}'})


class ReferenceRegistry:
    """Deduplicate trusted sources and preserve stable IDs when details arrive."""

    def __init__(self, sources: Iterable[Reference] = ()) -> None:
        self.references = {ref.id: ref for ref in sources}
        self._aliases = {key: ref.id for ref in self.references.values() for key in reference_keys(ref)}

    def upsert(self, source: Reference) -> tuple[Reference, bool]:
        source = Reference.model_validate(source)
        keys = reference_keys(source)
        identifier = next((self._aliases[key] for key in sorted(keys) if key in self._aliases), source.id)
        previous = self.references.get(identifier)
        if previous is not None:
            values = {key: value for key, value in source.model_dump().items()
                      if value is not None and value != []}
            reference = Reference(**{**previous.model_dump(), **values, 'id': identifier})
        else:
            reference = source
        self.references[identifier] = reference
        for key in keys:
            self._aliases[key] = identifier
        return reference, previous != reference
