"""Home-feed source quotas and bounds.

Quotas are cards per screen of SCREEN_SIZE; a source that runs out yields its
slots to the others. Limits cap what each source may contribute per list.
"""

import os

# Knowledge-base images exist almost only for this year, so the pool syncs it
# by default; HOME_FEED_POOL_YEAR overrides it without a release.
DEFAULT_POOL_YEAR = 2026


def pool_year() -> int:
    value = os.getenv('HOME_FEED_POOL_YEAR', '').strip()
    return int(value) if value.isdigit() else DEFAULT_POOL_YEAR


SCREEN_SIZE = 12
VENUE_PER_SCREEN = 4

ANONYMOUS_QUOTAS = {'daily': 10, 'trending': 2}
SIGNED_IN_QUOTAS = {'personal': 6, 'daily': 4, 'trending': 2}

DAILY_LIMIT = 300
TRENDING_LIMIT = 30
FEED_LIMIT = 400

# A stored daily list older than this is no longer served.
DAILY_MAX_AGE_DAYS = 7
# Below this many cards the packaged fallback list is appended, once, after the live sources.
FALLBACK_MIN_ITEMS = 36

# Sources read at request time are cached briefly; their inputs change at most daily.
SOURCE_CACHE_SECONDS = 60.0
