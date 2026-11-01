"""Read and paginate the shared home-discovery list.

Each Shanghai day serves the stored daily edition (built offline by
``python -m app.services.discovery_pool publish``). Without one, yesterday's
edition is reused, and without that the packaged curated snapshot is shuffled
for the day, so the home feed never depends on the knowledge base or the
publish job at request time.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.daily_recommendation import DailyRecommendationRow
from app.schemas.discovery import DiscoveryPaper, DiscoveryPaperPage

logger = logging.getLogger(__name__)


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'home_discovery_snapshot.json'
SHANGHAI_TIMEZONE = ZoneInfo('Asia/Shanghai')


class DiscoverySnapshotError(RuntimeError):
    """The packaged snapshot is missing, malformed, or internally inconsistent."""


class DiscoveryCursorError(ValueError):
    """The cursor cannot address the currently published snapshot."""


@dataclass(frozen=True)
class DiscoveryCandidate:
    paper: DiscoveryPaper
    priority: int


@dataclass(frozen=True)
class DiscoverySnapshot:
    snapshot_id: str
    items: tuple[DiscoveryCandidate, ...]


@dataclass(frozen=True)
class DailyList:
    """One fixed, ordered list for a Shanghai day; cursors are bound to its id."""
    list_id: str
    ordering_date: date
    papers: tuple[DiscoveryPaper, ...]


EDITION_CACHE_SECONDS = 60.0
_edition_cache: dict[date, tuple[float, DailyList | None]] = {}


def edition_id(ordering_date: date, papers: list[DiscoveryPaper] | tuple[DiscoveryPaper, ...]) -> str:
    digest = hashlib.sha256('\n'.join(paper.id for paper in papers).encode('utf-8')).hexdigest()[:16]
    return f'daily:{ordering_date.isoformat()}:{digest}'


def parse_edition(ordering_date: date, payload: Any) -> DailyList | None:
    """Validate a stored edition; legacy or damaged rows are treated as missing."""
    try:
        if not isinstance(payload, list) or not payload:
            return None
        papers = tuple(DiscoveryPaper.model_validate(item) for item in payload)
    except (ValidationError, TypeError):
        return None
    ids = [paper.id for paper in papers]
    if len(set(ids)) != len(ids) or any(not (paper.thumbnail_url or paper.image_id) for paper in papers):
        return None
    return DailyList(edition_id(ordering_date, papers), ordering_date, papers)


async def load_stored_edition(ordering_date: date) -> DailyList | None:
    cached = _edition_cache.get(ordering_date)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        async with session_scope() as session:
            row = await session.get(DailyRecommendationRow, ordering_date)
        edition = parse_edition(ordering_date, row.payload) if row is not None else None
    except Exception as error:  # noqa: BLE001 - the packaged snapshot keeps the feed available
        logger.warning('Daily discovery edition unavailable (%s)', type(error).__name__)
        edition = None
    # Editions are written once a day offline; a short cache keeps paging off the database.
    _edition_cache[ordering_date] = (time.monotonic() + EDITION_CACHE_SECONDS, edition)
    return edition


def _read_snapshot(path: Path) -> DiscoverySnapshot:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        snapshot_id = payload['snapshot_id']
        raw_items = payload['items']
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DiscoverySnapshotError(f'Unable to read discovery snapshot: {path}') from error

    if not isinstance(snapshot_id, str) or not snapshot_id or not isinstance(raw_items, list):
        raise DiscoverySnapshotError('Discovery snapshot has an invalid envelope')

    candidates: list[DiscoveryCandidate] = []
    try:
        for item in raw_items:
            if not isinstance(item, dict):
                raise TypeError('paper entry is not an object')
            priority = item.get('priority')
            if not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 4:
                raise ValueError('paper priority must be between 1 and 4')
            candidates.append(
                DiscoveryCandidate(
                    paper=DiscoveryPaper.model_validate({
                        key: value for key, value in item.items() if key != 'priority'
                    }),
                    priority=priority,
                ),
            )
        items = tuple(candidates)
    except Exception as error:
        raise DiscoverySnapshotError('Discovery snapshot contains invalid paper metadata') from error

    paper_ids = [item.paper.id for item in items]
    if len(set(paper_ids)) != len(paper_ids):
        raise DiscoverySnapshotError('Discovery snapshot contains duplicate paper ids')
    return DiscoverySnapshot(snapshot_id=snapshot_id, items=items)


@lru_cache(maxsize=1)
def load_discovery_snapshot() -> DiscoverySnapshot:
    return _read_snapshot(SNAPSHOT_PATH)


def _shanghai_today() -> date:
    return utc_now().astimezone(SHANGHAI_TIMEZONE).date()


def _daily_snapshot_id(source_snapshot_id: str, ordering_date: date) -> str:
    return f'{source_snapshot_id}:{ordering_date.isoformat()}'


def _daily_items(snapshot: DiscoverySnapshot, ordering_date: date) -> tuple[DiscoveryPaper, ...]:
    """Keep priority buckets while deterministically shuffling each bucket per Shanghai day."""
    seed = f'{snapshot.snapshot_id}:{ordering_date.isoformat()}'

    def sort_key(candidate: DiscoveryCandidate) -> tuple[int, bytes, str]:
        random_rank = hashlib.sha256(f'{seed}:{candidate.paper.id}'.encode('utf-8')).digest()
        return candidate.priority, random_rank, candidate.paper.id

    return tuple(candidate.paper for candidate in sorted(snapshot.items, key=sort_key))


def _encode_cursor(snapshot_id: str, ordering_date: date, offset: int) -> str:
    raw = json.dumps(
        {'s': snapshot_id, 'd': ordering_date.isoformat(), 'o': offset},
        separators=(',', ':'),
    ).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode_cursor(cursor: str) -> tuple[str, date, int]:
    try:
        padding = '=' * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b'-_', validate=True)
        value: Any = json.loads(raw)
        snapshot_id = value['s']
        ordering_date_value = value['d']
        offset = value['o']
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表') from error

    if (
        not isinstance(snapshot_id, str)
        or not isinstance(ordering_date_value, str)
        or not isinstance(offset, int)
        or isinstance(offset, bool)
    ):
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表')
    if offset < 0:
        raise DiscoveryCursorError('分页游标超出当前论文列表范围')
    try:
        ordering_date = date.fromisoformat(ordering_date_value)
    except ValueError as error:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表') from error
    if ordering_date.isoformat() != ordering_date_value:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表')
    return snapshot_id, ordering_date, offset


class HomeDiscoveryService:
    def __init__(
        self,
        snapshot_loader=load_discovery_snapshot,
        today_provider: Callable[[], date] = _shanghai_today,
        edition_loader: Callable[[date], Awaitable[DailyList | None]] = load_stored_edition,
    ):
        self._snapshot_loader = snapshot_loader
        self._today_provider = today_provider
        self._edition_loader = edition_loader

    def _curated_list(self, ordering_date: date) -> DailyList:
        snapshot = self._snapshot_loader()
        return DailyList(
            _daily_snapshot_id(snapshot.snapshot_id, ordering_date), ordering_date,
            _daily_items(snapshot, ordering_date),
        )

    async def daily_list(self) -> DailyList:
        """Today's edition, else yesterday's, else today's shuffle of the curated snapshot."""
        today = self._today_provider()
        for ordering_date in (today, today - timedelta(days=1)):
            edition = await self._edition_loader(ordering_date)
            if edition is not None:
                return edition
        return self._curated_list(today)

    async def daily_papers(self) -> list[DiscoveryPaper]:
        """Today's complete shared order, which every personal feed continues with."""
        return list((await self.daily_list()).papers)

    async def _list_for_cursor(self, list_id: str, ordering_date: date) -> DailyList:
        edition = await self._edition_loader(ordering_date)
        if edition is not None and edition.list_id == list_id:
            return edition
        snapshot = self._snapshot_loader()
        # Cursors issued before daily editions carried the bare snapshot id.
        if list_id in (snapshot.snapshot_id, _daily_snapshot_id(snapshot.snapshot_id, ordering_date)):
            return self._curated_list(ordering_date)
        raise DiscoveryCursorError('论文发现列表已更新，请重新加载后继续浏览')

    async def page(self, *, limit: int, cursor: str | None = None) -> DiscoveryPaperPage:
        if cursor is None:
            daily, offset = await self.daily_list(), 0
        else:
            list_id, ordering_date, offset = _decode_cursor(cursor)
            daily = await self._list_for_cursor(list_id, ordering_date)
            if offset > len(daily.papers):
                raise DiscoveryCursorError('分页游标超出当前论文列表范围')
        end = min(offset + limit, len(daily.papers))
        has_more = end < len(daily.papers)
        return DiscoveryPaperPage(
            items=list(daily.papers[offset:end]),
            next_cursor=_encode_cursor(daily.list_id, daily.ordering_date, end) if has_more else None,
            has_more=has_more,
            snapshot_id=daily.list_id,
            total=len(daily.papers),
        )
