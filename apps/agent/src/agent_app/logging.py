"""Structured log helper used by Agent upstream adapters."""
from __future__ import annotations

import logging
from typing import Any


def log_event(logger: logging.Logger, level: int, event: str, fields: dict[str, Any]) -> None:
    logger.log(level, event, extra={'event': event, **fields})
