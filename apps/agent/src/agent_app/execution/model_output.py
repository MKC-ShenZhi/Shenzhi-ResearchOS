"""Split streamed Markdown from a model-authored references JSON sidecar."""
from __future__ import annotations

import json
import re

from agent_contracts.messages import Reference
from pydantic import ValidationError

REFERENCES_OPEN = '<references_json>'
REFERENCES_CLOSE = '</references_json>'
MAX_REFERENCE_CHARS = 256_000
MAX_REFERENCES = 200
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


class ModelOutput:
    def __init__(self) -> None:
        self._line = ''
        self._held = ''
        self._fence: str | None = None
        self._reference_parts: list[str] = []
        self._reference_chars = 0
        self.has_references = False
        self.received = False

    def append(self, text: str) -> str:
        self.received = self.received or bool(text)
        visible = []
        for character in text:
            if self.has_references:
                self._reference_chars += 1
                if self._reference_chars <= MAX_REFERENCE_CHARS:
                    self._reference_parts.append(character)
                continue
            self._line += character
            if self._fence is None and REFERENCES_OPEN.startswith(self._line):
                self._held += character
                if self._line == REFERENCES_OPEN:
                    self.has_references = True
                    self._held = ''
                continue
            visible.append(self._held + character)
            self._held = ''
            if character == '\n':
                match = _FENCE.match(self._line.rstrip('\r\n'))
                if match:
                    fence, suffix = match.groups()
                    if self._fence is None:
                        self._fence = fence
                    elif fence[0] == self._fence[0] and len(fence) >= len(self._fence) and not suffix.strip():
                        self._fence = None
                self._line = ''
        return ''.join(visible)

    def finish(self) -> tuple[str, dict[str, Reference], list[str]]:
        if not self.has_references:
            tail = '' if len(self._held) > 1 else self._held
            return tail, {}, ['incomplete_references_tag'] if len(self._held) > 1 else []
        if self._reference_chars > MAX_REFERENCE_CHARS:
            return '', {}, ['references_too_large']
        payload = ''.join(self._reference_parts).strip()
        if not payload.endswith(REFERENCES_CLOSE):
            return '', {}, ['incomplete_references_json']
        try:
            records = json.loads(payload[:-len(REFERENCES_CLOSE)], object_pairs_hook=_unique_object)
            if not isinstance(records, list) or len(records) > MAX_REFERENCES:
                raise ValueError('expected a bounded reference array')
        except (ValueError, RecursionError):
            return '', {}, ['invalid_references_json']
        references: dict[str, Reference] = {}
        ambiguous = set()
        errors = []
        for record in records:
            try:
                reference = Reference.model_validate(record)
            except (ValidationError, ValueError):
                errors.append('invalid_reference')
                continue
            previous = references.get(reference.id)
            if previous is not None and previous != reference:
                ambiguous.add(reference.id)
                errors.append('conflicting_reference_key')
            references[reference.id] = reference
        return '', {key: ref for key, ref in references.items() if key not in ambiguous}, errors
