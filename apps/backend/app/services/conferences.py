"""Conference submission deadlines served from the packaged ccf-deadlines snapshot.

Upstream deadlines are wall-clock strings in each edition's own timezone
(`AoE`, `UTC±N`, `PT`, ...). They are converted to absolute UTC instants once at
load time; everything that depends on "now" (which edition is current, the next
milestone, open/closed) is evaluated per request.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.core.time import utc_now
from app.schemas.conferences import (
    ConferenceCategory,
    ConferenceCategoryList,
    ConferenceDeadline,
    ConferenceDeadlineList,
    ConferenceEdition,
    ConferenceMilestone,
    ConferenceSnapshotFile,
    DeadlineStatus,
    SnapshotConference,
    SnapshotEdition,
)


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'conference_deadlines_snapshot.json'
UNRANKED = 'N'
_UTC_OFFSET = re.compile(r'^UTC([+-])(\d{1,2})$')
_LOCAL_FORMAT = '%Y-%m-%d %H:%M:%S'
_STATUS_ORDER: dict[DeadlineStatus, int] = {'open': 0, 'tbd': 1, 'closed': 2}


class ConferenceSnapshotError(RuntimeError):
    """The packaged snapshot is missing, malformed, or uses an unknown timezone."""


def parse_timezone(label: str) -> tzinfo:
    """Map ccf-deadlines timezone labels to tzinfo.

    `AoE` (Anywhere on Earth) is UTC-12. `PT` follows US Pacific daylight saving,
    so it must be a real zone rather than a fixed offset.
    """
    if label == 'AoE':
        return timezone(timedelta(hours=-12))
    if label == 'UTC':
        return timezone.utc
    if label == 'PT':
        return ZoneInfo('America/Los_Angeles')
    match = _UTC_OFFSET.match(label)
    if match and int(match.group(2)) <= 14:
        hours = int(match.group(2))
        return timezone(timedelta(hours=-hours if match.group(1) == '-' else hours))
    raise ConferenceSnapshotError(f'Unsupported conference timezone: {label!r}')


def to_utc(local: str, zone: tzinfo) -> datetime:
    try:
        naive = datetime.strptime(local, _LOCAL_FORMAT)
    except ValueError as error:
        raise ConferenceSnapshotError(f'Invalid conference deadline: {local!r}') from error
    return naive.replace(tzinfo=zone).astimezone(timezone.utc)


def _edition(raw: SnapshotEdition) -> ConferenceEdition:
    zone = parse_timezone(raw.timezone)
    milestones: list[ConferenceMilestone] = []
    for entry in raw.timeline:
        for kind, local in (('abstract', entry.abstract_deadline), ('full', entry.deadline)):
            # An entry with no abstract round simply has no abstract milestone; a missing
            # full-paper deadline means the round exists but its date is still TBD.
            if local is None and kind == 'abstract':
                continue
            milestones.append(ConferenceMilestone(
                kind=kind,
                at=to_utc(local, zone) if local is not None else None,
                local=local,
                comment=entry.comment,
            ))
    milestones.sort(key=lambda item: (item.at is None, item.at or datetime.min.replace(tzinfo=timezone.utc)))
    return ConferenceEdition(
        year=raw.year,
        link=raw.link,
        timezone=raw.timezone,
        date=raw.date,
        place=raw.place,
        milestones=milestones,
    )


@dataclass(frozen=True)
class ConferenceRecord:
    conference: SnapshotConference
    editions: tuple[ConferenceEdition, ...]  # ascending by year
    search_text: str


@dataclass(frozen=True)
class ConferenceCatalog:
    snapshot: ConferenceSnapshotFile
    records: tuple[ConferenceRecord, ...]


def read_catalog(path: Path) -> ConferenceCatalog:
    try:
        snapshot = ConferenceSnapshotFile.model_validate(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ConferenceSnapshotError(f'Unable to read conference snapshot: {path}') from error

    category_ids = {category.id for category in snapshot.categories}
    ids = [conference.id for conference in snapshot.conferences]
    if len(set(ids)) != len(ids):
        raise ConferenceSnapshotError('Conference snapshot contains duplicate ids')
    if any(conference.category not in category_ids for conference in snapshot.conferences):
        raise ConferenceSnapshotError('Conference snapshot references an unknown category')

    records = tuple(
        ConferenceRecord(
            conference=conference,
            editions=tuple(_edition(edition) for edition in sorted(conference.editions, key=lambda e: e.year)),
            search_text=' '.join(
                part for part in (conference.title, conference.description, conference.dblp) if part
            ).casefold(),
        )
        for conference in snapshot.conferences
    )
    return ConferenceCatalog(snapshot=snapshot, records=records)


@lru_cache(maxsize=1)
def load_conference_catalog() -> ConferenceCatalog:
    return read_catalog(SNAPSHOT_PATH)


def _next_milestone(edition: ConferenceEdition, now: datetime) -> ConferenceMilestone | None:
    return next((item for item in edition.milestones if item.at is not None and item.at > now), None)


def evaluate(record: ConferenceRecord, now: datetime) -> ConferenceDeadline:
    """Pick the edition a researcher cares about right now.

    1. Any edition with an upcoming milestone -> the one whose next milestone is soonest.
    2. Otherwise, if the newest edition still has an unannounced (TBD) date -> `tbd`.
    3. Otherwise the newest edition, `closed`.
    """
    upcoming = [
        (milestone, edition)
        for edition in record.editions
        if (milestone := _next_milestone(edition, now)) is not None
    ]
    status: DeadlineStatus
    if upcoming:
        next_milestone, edition = min(upcoming, key=lambda pair: pair[0].at)
        status = 'open'
    else:
        next_milestone, edition = None, record.editions[-1]
        status = 'tbd' if any(item.at is None for item in edition.milestones) else 'closed'

    dated = [item.at for item in edition.milestones if item.at is not None]
    conference = record.conference
    return ConferenceDeadline(
        id=conference.id,
        title=conference.title,
        description=conference.description,
        category=conference.category,
        dblp=conference.dblp,
        rank=conference.rank,
        status=status,
        next_milestone=next_milestone,
        last_deadline_at=max(dated) if dated else None,
        edition=edition,
        edition_count=len(record.editions),
    )


def _sort_key(item: ConferenceDeadline) -> tuple:
    if item.status == 'open' and item.next_milestone and item.next_milestone.at:
        # Soonest first.
        return (_STATUS_ORDER['open'], item.next_milestone.at.timestamp(), item.title.casefold())
    if item.status == 'closed' and item.last_deadline_at:
        # Most recently closed first: these are the venues whose next call is closest.
        return (_STATUS_ORDER['closed'], -item.last_deadline_at.timestamp(), item.title.casefold())
    return (_STATUS_ORDER[item.status], 0.0, item.title.casefold())


def _rank_matches(value: str | None, wanted: Collection[str] | None) -> bool:
    return not wanted or (value or UNRANKED) in wanted


@dataclass(frozen=True)
class ConferenceFilters:
    categories: frozenset[str] = frozenset()
    ccf: frozenset[str] = frozenset()
    core: frozenset[str] = frozenset()
    thcpl: frozenset[str] = frozenset()
    statuses: frozenset[str] = frozenset()
    query: str | None = None
    # None = no restriction; an empty set matches nothing (e.g. a user following no conference).
    ids: frozenset[str] | None = None


class UnknownCategoryError(ValueError):
    pass


class ConferenceDeadlineService:
    def __init__(
        self,
        catalog_loader: Callable[[], ConferenceCatalog] = load_conference_catalog,
        now_provider: Callable[[], datetime] = utc_now,
    ):
        self._catalog_loader = catalog_loader
        self._now_provider = now_provider

    def categories(self) -> ConferenceCategoryList:
        catalog = self._catalog_loader()
        counts = Counter(record.conference.category for record in catalog.records)
        return ConferenceCategoryList(
            snapshot_id=catalog.snapshot.snapshot_id,
            items=[
                ConferenceCategory(
                    id=category.id, name=category.name, name_en=category.name_en,
                    count=counts.get(category.id, 0),
                )
                for category in catalog.snapshot.categories
            ],
        )

    def has_conference(self, conference_id: str) -> bool:
        return any(record.conference.id == conference_id for record in self._catalog_loader().records)

    def deadlines(self, filters: ConferenceFilters = ConferenceFilters()) -> ConferenceDeadlineList:
        """Rank filters are OR within one system and AND across systems."""
        catalog = self._catalog_loader()
        unknown = filters.categories - {category.id for category in catalog.snapshot.categories}
        if unknown:
            raise UnknownCategoryError(', '.join(sorted(unknown)))

        now = self._now_provider()
        needle = (filters.query or '').strip().casefold()
        items: list[ConferenceDeadline] = []
        for record in catalog.records:
            conference = record.conference
            if filters.ids is not None and conference.id not in filters.ids:
                continue
            if filters.categories and conference.category not in filters.categories:
                continue
            if not (
                _rank_matches(conference.rank.ccf, filters.ccf)
                and _rank_matches(conference.rank.core, filters.core)
                and _rank_matches(conference.rank.thcpl, filters.thcpl)
            ):
                continue
            if needle and needle not in record.search_text:
                continue
            item = evaluate(record, now)
            if filters.statuses and item.status not in filters.statuses:
                continue
            items.append(item)

        items.sort(key=_sort_key)
        return ConferenceDeadlineList(
            snapshot_id=catalog.snapshot.snapshot_id,
            data_as_of=catalog.snapshot.data_as_of,
            source_url=catalog.snapshot.source.url,
            generated_at=now,
            total=len(items),
            items=items,
        )
