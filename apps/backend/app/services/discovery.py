"""Read and paginate the shared home-discovery list.

The anonymous home list is composed per Shanghai day from bounded sources:
``daily`` (the newest stored daily edition at most DAILY_MAX_AGE_DAYS old,
built offline by ``python -m app.services.discovery_pool publish``) and
``trending`` (platform activity). Only when they yield fewer than
FALLBACK_MIN_ITEMS papers is the packaged snapshot appended, once, as the
``fallback`` source; requests never call the knowledge base.
"""

from __future__ import annotations

import asyncio
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
from sqlalchemy import select

from app.core.database import session_scope
from app.core.time import utc_now
from app.models.home_daily_edition import HomeDailyEditionRow
from app.schemas.discovery import DiscoveryPaper, DiscoveryPaperPage
from app.services.home_feed import config
from app.services.home_feed.composer import compose
from app.services.home_feed.rules import admit
from app.services.home_feed.trending import load_trending

logger = logging.getLogger(__name__)


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'home_discovery_snapshot.json'
SHANGHAI_TIMEZONE = ZoneInfo('Asia/Shanghai')


class DiscoverySnapshotError(RuntimeError):
    """The packaged snapshot is missing, malformed, or internally inconsistent."""


class DiscoveryCursorError(ValueError):
    """The cursor is malformed or points past the end of its list."""


class DiscoveryListChangedError(DiscoveryCursorError):
    """The cursor is well-formed but its list was replaced; only page one can recover."""


@dataclass(frozen=True)
class DiscoveryCandidate:
    paper: DiscoveryPaper
    priority: int


@dataclass(frozen=True)
class DiscoverySnapshot:
    snapshot_id: str
    items: tuple[DiscoveryCandidate, ...]


@dataclass(frozen=True)
class HomeList:
    """One fixed, ordered anonymous home list for a Shanghai day; cursors are bound to its id."""
    list_id: str
    ordering_date: date
    papers: tuple[DiscoveryPaper, ...]


_edition_cache: dict[date, tuple[float, tuple[DiscoveryPaper, ...]]] = {}


def edition_id(ordering_date: date, papers: list[DiscoveryPaper] | tuple[DiscoveryPaper, ...]) -> str:
    digest = hashlib.sha256('\n'.join(paper.id for paper in papers).encode('utf-8')).hexdigest()[:16]
    return f'daily:{ordering_date.isoformat()}:{digest}'


def home_list_id(ordering_date: date, papers: list[DiscoveryPaper] | tuple[DiscoveryPaper, ...]) -> str:
    """Bind cursors to the exact composed order, sources included."""
    digest = hashlib.sha256(
        '\n'.join(f'{paper.source}:{paper.id}' for paper in papers).encode('utf-8'),
    ).hexdigest()[:16]
    return f'home:{ordering_date.isoformat()}:{digest}'


def parse_edition(payload: Any) -> tuple[DiscoveryPaper, ...] | None:
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
    return papers


async def load_latest_edition(ordering_date: date) -> tuple[DiscoveryPaper, ...]:
    """The newest valid edition on or before the date, within DAILY_MAX_AGE_DAYS; one query."""
    cached = _edition_cache.get(ordering_date)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    papers: tuple[DiscoveryPaper, ...] = ()
    try:
        async with session_scope() as session:
            payloads = await session.scalars(
                select(HomeDailyEditionRow.payload)
                .where(HomeDailyEditionRow.edition_date.between(
                    ordering_date - timedelta(days=config.DAILY_MAX_AGE_DAYS), ordering_date,
                ))
                .order_by(HomeDailyEditionRow.edition_date.desc()),
            )
            for payload in payloads:
                if (parsed := parse_edition(payload)) is not None:
                    papers = parsed
                    break
    except Exception as error:  # noqa: BLE001 - the other sources and the fallback keep the feed available
        logger.warning('Daily discovery edition unavailable (%s)', type(error).__name__)
    # Editions are written once a day offline; a short cache keeps paging off the database.
    _edition_cache[ordering_date] = (time.monotonic() + config.SOURCE_CACHE_SECONDS, papers)
    return papers


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
            DiscoveryPaper.model_validate({key: value for key, value in item.items() if key != 'priority'})
            paper, _reason = admit(item)
            if paper is not None:
                candidates.append(DiscoveryCandidate(paper=paper, priority=priority))
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


def _fallback_list_id(source_snapshot_id: str, ordering_date: date) -> str:
    return f'{source_snapshot_id}:{ordering_date.isoformat()}'


def _fallback_order(snapshot: DiscoverySnapshot, ordering_date: date) -> tuple[DiscoveryPaper, ...]:
    """Order the packaged papers: priority buckets kept, each shuffled deterministically per Shanghai day."""
    seed = f'{snapshot.snapshot_id}:{ordering_date.isoformat()}'

    def sort_key(candidate: DiscoveryCandidate) -> tuple[int, bytes, str]:
        random_rank = hashlib.sha256(f'{seed}:{candidate.paper.id}'.encode('utf-8')).digest()
        return candidate.priority, random_rank, candidate.paper.id

    return tuple(candidate.paper for candidate in sorted(snapshot.items, key=sort_key))


def _encode_cursor(list_id: str, ordering_date: date, offset: int) -> str:
    raw = json.dumps(
        {'s': list_id, 'd': ordering_date.isoformat(), 'o': offset},
        separators=(',', ':'),
    ).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode_cursor(cursor: str) -> tuple[str, date, int]:
    try:
        padding = '=' * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b'-_', validate=True)
        value: Any = json.loads(raw)
        list_id = value['s']
        ordering_date_value = value['d']
        offset = value['o']
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表') from error

    if (
        not isinstance(list_id, str)
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
    return list_id, ordering_date, offset


class HomeDiscoveryService:
    def __init__(
        self,
        snapshot_loader=load_discovery_snapshot,
        today_provider: Callable[[], date] = _shanghai_today,
        edition_loader: Callable[[date], Awaitable[tuple[DiscoveryPaper, ...]]] = load_latest_edition,
        trending_loader: Callable[[date], Awaitable[list[DiscoveryPaper]]] = load_trending,
    ):
        self._snapshot_loader = snapshot_loader
        self._today_provider = today_provider
        self._edition_loader = edition_loader
        self._trending_loader = trending_loader
        self._lists: dict[date, tuple[float, HomeList]] = {}

    def today(self) -> date:
        return self._today_provider()

    def _fallback_list(self, ordering_date: date) -> HomeList:
        snapshot = self._snapshot_loader()
        return HomeList(
            _fallback_list_id(snapshot.snapshot_id, ordering_date), ordering_date,
            _fallback_order(snapshot, ordering_date),
        )

    async def shared_sources(self, ordering_date: date) -> dict[str, list[DiscoveryPaper]]:
        """The live sources every visitor shares for the day; a failed source is empty."""
        daily, trending = await asyncio.gather(
            self._edition_loader(ordering_date), self._trending_loader(ordering_date),
        )
        return {'daily': list(daily)[:config.DAILY_LIMIT], 'trending': list(trending)[:config.TRENDING_LIMIT]}

    def with_fallback(self, papers: list[DiscoveryPaper], ordering_date: date) -> list[DiscoveryPaper]:
        """Append the packaged list once when the live sources fall short; never retried."""
        if len(papers) >= config.FALLBACK_MIN_ITEMS:
            return papers
        try:
            fallback = self._fallback_list(ordering_date).papers
        except DiscoverySnapshotError:
            if papers:
                return papers
            raise
        seen = {paper.id for paper in papers}
        extra = [paper.model_copy(update={'source': 'fallback'}) for paper in fallback if paper.id not in seen]
        return (papers + extra)[:config.FEED_LIMIT]

    async def list_for(self, ordering_date: date) -> HomeList:
        """The composed anonymous list for a day, cached briefly per instance."""
        cached = self._lists.get(ordering_date)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        composed = compose(await self.shared_sources(ordering_date), config.ANONYMOUS_QUOTAS)
        papers = tuple(self.with_fallback(composed, ordering_date))
        home = HomeList(home_list_id(ordering_date, papers), ordering_date, papers)
        self._lists[ordering_date] = (time.monotonic() + config.SOURCE_CACHE_SECONDS, home)
        return home

    async def today_list(self) -> HomeList:
        return await self.list_for(self.today())

    async def _list_for_cursor(self, list_id: str, ordering_date: date) -> HomeList:
        home = await self.list_for(ordering_date)
        if home.list_id == list_id:
            return home
        snapshot = self._snapshot_loader()
        # Cursors issued before composed lists carried the bare snapshot id.
        if list_id in (snapshot.snapshot_id, _fallback_list_id(snapshot.snapshot_id, ordering_date)):
            return self._fallback_list(ordering_date)
        raise DiscoveryListChangedError('论文发现列表已更新，请重新加载后继续浏览')

    async def page(self, *, limit: int, cursor: str | None = None) -> DiscoveryPaperPage:
        if cursor is None:
            home, offset = await self.today_list(), 0
        else:
            list_id, ordering_date, offset = _decode_cursor(cursor)
            home = await self._list_for_cursor(list_id, ordering_date)
            if offset > len(home.papers):
                raise DiscoveryCursorError('分页游标超出当前论文列表范围')
        end = min(offset + limit, len(home.papers))
        has_more = end < len(home.papers)
        return DiscoveryPaperPage(
            items=list(home.papers[offset:end]),
            next_cursor=_encode_cursor(home.list_id, home.ordering_date, end) if has_more else None,
            has_more=has_more,
            list_id=home.list_id,
            total=len(home.papers),
        )
