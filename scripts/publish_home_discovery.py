#!/usr/bin/env python3
"""Publish the curated home-discovery seed and its selected thumbnails.

The source seed remains untouched. This command creates the deployment-ready
FastAPI snapshot and exactly one optimized WebP thumbnail per selected paper.
It performs no network requests and is safe to repeat.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'data' / 'discovery' / 'home-seed-300.json'
DEFAULT_SNAPSHOT = ROOT / 'apps' / 'backend' / 'app' / 'data' / 'home_discovery_snapshot.json'
DEFAULT_ASSET_DIR = ROOT / 'apps' / 'web' / 'public' / 'paper-thumbnails'
ARXIV_ID = re.compile(r'^\d{4}\.\d{4,5}(?:v[1-9]\d*)?$')
TITLE_SUFFIX = re.compile(
    r'\s+(?:Thanks?|Acknowledg(?:e)?ments?|Conference|Journal|CCS|ISBN|DOI|Volume):\s*',
    re.IGNORECASE,
)
AUTHOR_NOISE = re.compile(
    r'(?:[{}\\]|https?://|@|\b(?:university|institute|laboratory|department|section|'
    r'equal contribution|corresponding author|work was done|code and data|project leader)\b)',
    re.IGNORECASE,
)
REPEATED_FOOTNOTE_NUMBER = re.compile(r'\s+([1-9])(?:\s+\1){2}(?=\s)')
TRAILING_AUTHOR_FOOTNOTE = re.compile(
    r'\s+[†‡](?:\s*[†‡])*\s+(?:footnotetext:\s*)?[†‡]?\s*'
    r'(?:corresponding author(?:s)?|project leader).*$',
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--snapshot', type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument('--asset-dir', type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--quality', type=int, default=82)
    parser.add_argument('--check', action='store_true', help='Validate already-published output without rewriting it')
    return parser.parse_args()


def compact_text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return ' '.join(value.replace('\x00', ' ').split()).strip()


def display_title(value: Any) -> str:
    title = compact_text(value)
    marker = TITLE_SUFFIX.search(title)
    if marker and marker.start() >= 12:
        title = title[:marker.start()].rstrip(' -;,.:')
    return re.sub(r'\s+([,:;])', r'\1', title)


def display_abstract(value: Any) -> str:
    abstract = compact_text(value)
    abstract = REPEATED_FOOTNOTE_NUMBER.sub('', abstract)
    abstract = TRAILING_AUTHOR_FOOTNOTE.sub('', abstract)
    return re.sub(r'\s+([,.;:!?])', r'\1', abstract).strip()


def display_authors(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for candidate in value:
        author = compact_text(candidate).strip(' ,;.')
        if not (2 <= len(author) <= 85) or AUTHOR_NOISE.search(author):
            continue
        if re.fullmatch(r'[a-z][a-z0-9_.-]{3,}', author):
            continue
        if not any(character.isalpha() for character in author):
            continue
        if author not in authors:
            authors.append(author)
    return authors


def build_snapshot(source: Path) -> tuple[dict[str, Any], list[tuple[Path, str]]]:
    payload = json.loads(source.read_text(encoding='utf-8'))
    raw_items = payload.get('items')
    if not isinstance(raw_items, list):
        raise ValueError('Seed must contain an items array')

    items: list[dict[str, Any]] = []
    assets: list[tuple[Path, str]] = []
    seen_ids: set[str] = set()
    seen_assets: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValueError(f'Item {index} is not an object')
        paper_id = compact_text(raw.get('paper_id'))
        arxiv_id = compact_text(raw.get('arxiv_id'))
        image_value = raw.get('thumbnail_local_path')
        image_path = Path(image_value) if isinstance(image_value, str) else None
        if image_path is not None and not image_path.is_absolute():
            image_path = ROOT / image_path
        if not paper_id or paper_id in seen_ids:
            raise ValueError(f'Item {index} has a missing or duplicate paper_id')
        if not ARXIV_ID.fullmatch(arxiv_id):
            raise ValueError(f'Item {paper_id} has an invalid arXiv id')
        if image_path is None or not image_path.is_file():
            raise ValueError(f'Item {paper_id} has no readable selected thumbnail')
        title = display_title(raw.get('title'))
        abstract = display_abstract(raw.get('abstract'))
        authors = display_authors(raw.get('authors'))
        year = raw.get('year')
        priority = raw.get('priority')
        if not title or not abstract or not authors or not isinstance(year, int):
            raise ValueError(f'Item {paper_id} has incomplete display metadata')
        if not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 4:
            raise ValueError(f'Item {paper_id} has an invalid discovery priority')

        asset_name = f'{arxiv_id}.webp'
        if asset_name in seen_assets:
            raise ValueError(f'Duplicate thumbnail target: {asset_name}')
        seen_ids.add(paper_id)
        seen_assets.add(asset_name)
        assets.append((image_path, asset_name))
        items.append({
            'id': paper_id,
            'title': title,
            'abstract': abstract,
            'authors': authors,
            'year': year,
            'venue': compact_text(raw.get('venue')) or None,
            'pdf_url': compact_text(raw.get('pdf_url')) or None,
            'thumbnail_url': f'/paper-thumbnails/{asset_name}',
            'priority': priority,
        })

    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    snapshot_id = f"seed-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"
    return {
        'schema_version': 1,
        'snapshot_id': snapshot_id,
        'source_generated_at': payload.get('generated_at'),
        'items': items,
    }, assets


def encode_assets(assets: list[tuple[Path, str]], target: Path, width: int, quality: int) -> None:
    encoder = shutil.which('cwebp')
    if encoder is None:
        raise RuntimeError('cwebp is required to publish optimized discovery thumbnails')
    target.mkdir(parents=True, exist_ok=True)
    expected = {name for _, name in assets}
    for existing in target.iterdir():
        if existing.is_file() and existing.suffix.lower() == '.webp' and existing.name not in expected:
            existing.unlink()
    for source, name in assets:
        destination = target / name
        result = subprocess.run(
            [encoder, '-quiet', '-mt', '-m', '6', '-q', str(quality), '-resize', str(width), '0',
             str(source), '-o', str(destination)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f'Unable to encode thumbnail: {source}')


def main() -> int:
    args = parse_args()
    if args.width < 320 or not 1 <= args.quality <= 100:
        print('--width must be >= 320 and --quality must be between 1 and 100', file=sys.stderr)
        return 2
    try:
        snapshot, assets = build_snapshot(args.source.resolve())
        if args.check:
            published = json.loads(args.snapshot.read_text(encoding='utf-8'))
            if published != snapshot:
                raise ValueError('Published snapshot is stale; run without --check')
            missing = [name for _, name in assets if not (args.asset_dir / name).is_file()]
            if missing:
                raise ValueError(f'{len(missing)} published thumbnails are missing')
        else:
            encode_assets(assets, args.asset_dir, args.width, args.quality)
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            args.snapshot.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8',
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f'Publish failed: {error}', file=sys.stderr)
        return 1
    total_bytes = sum((args.asset_dir / name).stat().st_size for _, name in assets)
    print(f"snapshot={snapshot['snapshot_id']} papers={len(assets)} assets={total_bytes / 1048576:.1f}MiB")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
