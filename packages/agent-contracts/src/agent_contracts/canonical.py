"""canonical_json_v1: shared byte identity, never a serializer for secrets."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
import math
from datetime import datetime, timezone
from typing import Any

SAFE_INTEGER = 2**53 - 1


def canonical_json_v1(value: Any) -> bytes:
    def normalize(item):
        if item is None or isinstance(item, (str, bool)):
            return item
        if isinstance(item, int):
            if abs(item) > SAFE_INTEGER:
                raise ValueError('unsafe integer')
            return item
        if isinstance(item, datetime):
            if item.tzinfo is None or item.utcoffset() is None:
                raise ValueError('timezone required')
            return item.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        if isinstance(item, (list, tuple)):
            return [normalize(v) for v in item]
        if isinstance(item, dict) and all(isinstance(k, str) for k in item):
            return {k: normalize(v) for k, v in item.items()}
        raise ValueError('canonical_json_v1 requires JSON primitives; decimals must be strings')
    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def parse_canonical(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate key')
            result[k] = v
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    if canonical_json_v1(value) != raw:
        raise ValueError('noncanonical JSON')
    return value


def digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(canonical_json_v1(value)).hexdigest()


def request_digest_v1(value: Any) -> str:
    """Normalize finite business decimals to strings BEFORE canonical_json_v1.

    The transmitted provider/tool payload is unchanged. Task idempotency also
    compares the frozen parsed request, not only its normalized digest.
    """
    def normalize(item):
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError('non-finite request decimal')
            return format(Decimal(str(item)).normalize(), 'f')
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(v) for v in item]
        return item
    return digest(normalize(value))
