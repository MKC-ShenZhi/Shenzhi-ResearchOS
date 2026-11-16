"""Short-lived in-process caches for home-feed sources, keyed by list date.

Each entry lives SOURCE_CACHE_SECONDS. Expired entries are dropped on every
write, so a cache only holds the dates requested within that window instead of
one entry per date ever seen.
"""

from __future__ import annotations

import time
from typing import Hashable, TypeVar

from app.services.home_feed import config

T = TypeVar('T')


def cached(cache: dict[Hashable, tuple[float, T]], key: Hashable) -> T | None:
    entry = cache.get(key)
    return entry[1] if entry is not None and entry[0] > time.monotonic() else None


def remember(cache: dict[Hashable, tuple[float, T]], key: Hashable, value: T) -> T:
    now = time.monotonic()
    for stale in [stale for stale, (expires, _value) in cache.items() if expires <= now]:
        del cache[stale]
    cache[key] = (now + config.SOURCE_CACHE_SECONDS, value)
    return value
