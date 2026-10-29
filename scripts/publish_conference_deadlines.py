#!/usr/bin/env python3
"""Publish the conference-deadline snapshot served by FastAPI.

The source is a raw ccf-deadlines style export (categories + conferences).
This command cleans it into the stable snapshot contract read by
`app.services.conferences`: it drops manual test records, normalizes rank
values and TBD placeholders, fixes known key typos and rejects anything it
does not understand. Deadline strings stay in their original local time plus
timezone so the published file can be diffed against upstream; conversion to
absolute instants happens in the backend service. No network requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'data' / 'conferences' / 'ccfddl-export-2026-10-29.json'
DEFAULT_SNAPSHOT = ROOT / 'apps' / 'backend' / 'app' / 'data' / 'conference_deadlines_snapshot.json'
SOURCE_URL = 'https://github.com/ccfddl/ccf-deadlines'

LOCAL_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
TIMEZONE = re.compile(r'^(?:AoE|PT|UTC|UTC[+-]\d{1,2})$')
RANK_VALUES = {
    'ccf': {'A', 'B', 'C'},
    'core': {'A*', 'A', 'B', 'C'},
    'thcpl': {'A', 'B', 'C'},
}
UNRANKED = {None, '', 'N'}
TIMELINE_KEY_ALIASES = {'abstract deadline': 'abstract_deadline'}
TIMELINE_KEYS = {'abstract_deadline', 'deadline', 'comment'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--snapshot', type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument('--check', action='store_true', help='Validate already-published output without rewriting it')
    return parser.parse_args()


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'expected text, got {value!r}')
    text = ' '.join(value.split())
    return text or None


def slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def local_deadline(value: Any, where: str) -> str | None:
    """`TBD` and empty strings mean the date has not been announced."""
    if value is None or value == '' or (isinstance(value, str) and value.upper() == 'TBD'):
        return None
    if not isinstance(value, str) or not LOCAL_DATETIME.match(value):
        raise ValueError(f'{where}: invalid deadline {value!r}')
    return value


def normalize_rank(raw: Any, where: str) -> dict[str, str | None]:
    if not isinstance(raw, dict):
        raise ValueError(f'{where}: rank must be an object')
    unknown = set(raw) - set(RANK_VALUES) - {'thc'}
    if unknown:
        raise ValueError(f'{where}: unknown rank systems {sorted(unknown)}')
    rank: dict[str, str | None] = {}
    for system, allowed in RANK_VALUES.items():
        value = raw.get(system, raw.get('thc') if system == 'thcpl' else None)
        if value in UNRANKED:
            rank[system] = None
        elif value in allowed:
            rank[system] = value
        else:
            raise ValueError(f'{where}: invalid {system} rank {value!r}')
    return rank


def normalize_timeline(raw: Any, where: str) -> list[dict[str, str | None]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f'{where}: timeline must be a non-empty list')
    entries = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f'{where}[{index}]: timeline entry must be an object')
        item = {TIMELINE_KEY_ALIASES.get(key, key): value for key, value in item.items()}
        unknown = set(item) - TIMELINE_KEYS
        if unknown:
            raise ValueError(f'{where}[{index}]: unknown timeline keys {sorted(unknown)}')
        entries.append({
            'abstract_deadline': local_deadline(item.get('abstract_deadline'), f'{where}[{index}]'),
            'deadline': local_deadline(item.get('deadline'), f'{where}[{index}]'),
            'comment': optional_text(item.get('comment')),
        })
    return entries


def normalize_edition(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f'{where}: edition must be an object')
    year = raw.get('year')
    if not isinstance(year, int) or isinstance(year, bool) or not 1950 <= year <= 2100:
        raise ValueError(f'{where}: invalid year {year!r}')
    timezone = raw.get('timezone')
    if not isinstance(timezone, str) or not TIMEZONE.match(timezone):
        raise ValueError(f'{where}: unsupported timezone {timezone!r}')
    return {
        'year': year,
        'link': optional_text(raw.get('link')),
        'timezone': timezone,
        'date': optional_text(raw.get('date')),
        'place': optional_text(raw.get('place')),
        'timeline': normalize_timeline(raw.get('timeline'), f'{where}.timeline'),
    }


def build_snapshot(source: Path) -> tuple[dict[str, Any], int]:
    payload = json.loads(source.read_text(encoding='utf-8'))
    exported_at = payload.get('exported_at')
    if not isinstance(exported_at, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', exported_at):
        raise ValueError('source exported_at must be YYYY-MM-DD')

    categories = []
    for raw in payload.get('categories') or []:
        categories.append({
            'id': raw['sub'],
            'name': optional_text(raw['name']),
            'name_en': optional_text(raw.get('name_en')),
        })
    category_ids = {category['id'] for category in categories}
    if not categories or len(category_ids) != len(categories):
        raise ValueError('categories must be a non-empty list with unique ids')

    conferences = []
    dropped = 0
    for raw in payload.get('conferences') or []:
        # Records created through the old admin form (`source: manual`) are test data.
        if raw.get('source') == 'manual':
            dropped += 1
            continue
        title = optional_text(raw.get('title'))
        category = raw.get('sub')
        where = f'{category}/{title}'
        if not title or category not in category_ids:
            raise ValueError(f'{where}: missing title or unknown category')
        editions = [
            normalize_edition(edition, f'{where}.confs[{index}]')
            for index, edition in enumerate(raw.get('confs') or [])
        ]
        years = [edition['year'] for edition in editions]
        if not editions or len(set(years)) != len(years):
            raise ValueError(f'{where}: editions must be non-empty with unique years')
        conferences.append({
            # The same acronym can name different venues (FSE, SEC) and one venue can be
            # listed under two CCF categories with different ranks (DCC): key by both.
            'id': f'{category.lower()}-{slug(title)}',
            'title': title,
            'description': optional_text(raw.get('description')) or title,
            'category': category,
            'dblp': optional_text(raw.get('dblp')),
            'rank': normalize_rank(raw.get('rank'), where),
            'editions': sorted(editions, key=lambda edition: edition['year']),
        })

    ids = [conference['id'] for conference in conferences]
    if len(set(ids)) != len(ids):
        raise ValueError('conference ids are not unique')
    conferences.sort(key=lambda conference: conference['id'])

    canonical = json.dumps(
        {'categories': categories, 'conferences': conferences},
        ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    )
    return {
        'schema_version': 1,
        'snapshot_id': f"ccfddl-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}",
        'data_as_of': exported_at,
        'source': {'name': 'ccf-deadlines', 'url': SOURCE_URL},
        'categories': categories,
        'conferences': conferences,
    }, dropped


def main() -> int:
    args = parse_args()
    try:
        snapshot, dropped = build_snapshot(args.source.resolve())
        if args.check:
            published = json.loads(args.snapshot.read_text(encoding='utf-8'))
            if published != snapshot:
                raise ValueError('Published snapshot is stale; run without --check')
        else:
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8',
            )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f'Publish failed: {error}', file=sys.stderr)
        return 1
    editions = sum(len(conference['editions']) for conference in snapshot['conferences'])
    print(
        f"snapshot={snapshot['snapshot_id']} conferences={len(snapshot['conferences'])} "
        f'editions={editions} dropped={dropped}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
