from datetime import datetime, timezone
import json
import logging
import os
from time import perf_counter
from typing import Mapping

from fastapi import Request

from app.core.request_context import get_request_id
from app.core.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    normalize_request_id,
    reset_request_id,
    set_request_id,
)


ALLOWED_LOG_FIELDS = frozenset({
    'request_id',
    'route',
    'method',
    'status_code',
    'duration_ms',
    'error_type',
    'error_code',
    'retryable',
    'upstream',
    'provider',
    'operation',
})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, '_shenzhi_fields', {})
        request_id = fields.get('request_id') or get_request_id() or '-'
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'level': record.levelname,
            'service': 'backend',
            'environment': os.getenv('ENVIRONMENT') or 'development',
            'event': getattr(record, '_shenzhi_event', None) or record.getMessage(),
            'request_id': request_id,
        }
        for name in ALLOWED_LOG_FIELDS:
            if name == 'request_id':
                continue
            value = fields.get(name)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload['traceback'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def _safe_fields(fields: Mapping[str, object] | None) -> dict[str, object]:
    return {
        name: value
        for name, value in (fields or {}).items()
        if name in ALLOWED_LOG_FIELDS
    }


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    fields: Mapping[str, object] | None = None,
) -> None:
    logger.log(
        level,
        event,
        extra={'_shenzhi_event': event, '_shenzhi_fields': _safe_fields(fields)},
    )


def log_exception(
    logger: logging.Logger,
    event: str,
    fields: Mapping[str, object] | None = None,
    error: BaseException | None = None,
) -> None:
    exc_info = None
    if error is not None:
        exc_info = (type(error), error, error.__traceback__)
    logger.exception(
        event,
        extra={'_shenzhi_event': event, '_shenzhi_fields': _safe_fields(fields)},
        exc_info=exc_info,
    )


def request_duration_ms(request: Request) -> int | None:
    started_at = getattr(request.state, 'request_started_at', None)
    if started_at is None:
        return None
    return round((perf_counter() - started_at) * 1000)


async def http_logging_middleware(request: Request, call_next):
    request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER)) or new_request_id()
    token = set_request_id(request_id)
    request.state.request_id = request_id
    request.state.request_started_at = perf_counter()
    try:
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        failed = response.status_code >= 500
        log_event(
            logging.getLogger(__name__),
            logging.ERROR if failed else logging.INFO,
            'http.request.failed' if failed else 'http.request.completed',
            {
                'request_id': request_id,
                'route': request.url.path,
                'method': request.method,
                'status_code': response.status_code,
                'duration_ms': request_duration_ms(request),
            },
        )
        return response
    finally:
        reset_request_id(token)


def configure_logging() -> None:
    app_logger = logging.getLogger('app')
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if any(getattr(handler, '_shenzhi_json', False) for handler in app_logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    setattr(handler, '_shenzhi_json', True)
    app_logger.addHandler(handler)
