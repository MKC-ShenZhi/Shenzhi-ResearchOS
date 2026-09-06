import re
from contextvars import ContextVar, Token
from uuid import uuid4


REQUEST_ID_HEADER = 'X-Request-ID'
_REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')

request_id_context: ContextVar[str | None] = ContextVar(
    'request_id', default=None,
)


def normalize_request_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if _REQUEST_ID_PATTERN.fullmatch(normalized) else None


def new_request_id() -> str:
    return str(uuid4())


def set_request_id(value: str) -> Token[str | None]:
    return request_id_context.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_context.reset(token)


def get_request_id() -> str | None:
    return request_id_context.get()
