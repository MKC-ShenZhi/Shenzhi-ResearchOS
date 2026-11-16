"""Shared rules for client supplied idempotency keys."""
import hashlib
import json
from typing import Any

from app.core.errors import BusinessError

MAX_IDEMPOTENCY_KEY_LENGTH = 255


def validate_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    if (not value or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH
            or any(ord(char) < 33 or ord(char) > 126 for char in value)):
        raise BusinessError(20001, 'Idempotency-Key 格式无效', 422)
    return value


def request_fingerprint(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def ensure_same_request(stored: str | None, incoming: str) -> None:
    if stored != incoming:
        raise BusinessError(20009, 'Idempotency-Key 已用于不同请求', 409)
