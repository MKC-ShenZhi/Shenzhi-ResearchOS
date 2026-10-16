"""Read and paginate the packaged ShenZhi home-discovery snapshot."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.core.time import utc_now
from app.schemas.discovery import DiscoveryPaper, DiscoveryPaperPage


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


def _decode_cursor(cursor: str, snapshot: DiscoverySnapshot) -> tuple[date, int]:
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
    if snapshot_id != snapshot.snapshot_id:
        raise DiscoveryCursorError('论文发现列表已更新，请重新加载后继续浏览')
    if offset < 0 or offset > len(snapshot.items):
        raise DiscoveryCursorError('分页游标超出当前论文列表范围')
    try:
        ordering_date = date.fromisoformat(ordering_date_value)
    except ValueError as error:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表') from error
    if ordering_date.isoformat() != ordering_date_value:
        raise DiscoveryCursorError('分页游标无效，请重新加载论文发现列表')
    return ordering_date, offset


class HomeDiscoveryService:
    def __init__(
        self,
        snapshot_loader=load_discovery_snapshot,
        today_provider: Callable[[], date] = _shanghai_today,
    ):
        self._snapshot_loader = snapshot_loader
        self._today_provider = today_provider

    def page(self, *, limit: int, cursor: str | None = None) -> DiscoveryPaperPage:
        snapshot = self._snapshot_loader()
        ordering_date, offset = (
            (self._today_provider(), 0)
            if cursor is None
            else _decode_cursor(cursor, snapshot)
        )
        daily_items = _daily_items(snapshot, ordering_date)
        end = min(offset + limit, len(daily_items))
        has_more = end < len(daily_items)
        return DiscoveryPaperPage(
            items=list(daily_items[offset:end]),
            next_cursor=(
                _encode_cursor(snapshot.snapshot_id, ordering_date, end)
                if has_more
                else None
            ),
            has_more=has_more,
            snapshot_id=_daily_snapshot_id(snapshot.snapshot_id, ordering_date),
            total=len(daily_items),
        )
