"""Shared, offline normalization of upstream conference YAML; no network or storage."""

from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
import yaml
from app.schemas.conferences import ConferenceSnapshotFile
from app.services.conferences import catalog_from_snapshot

SOURCE_URL = "https://github.com/ccfddl/ccf-deadlines"
LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
TIMEZONE = re.compile(r"^(?:AoE|PT|UTC|UTC[+-]\d{1,2})$")
RANK_VALUES = {
    "ccf": {"A", "B", "C"},
    "core": {"A*", "A", "B", "C"},
    "thcpl": {"A", "B", "C"},
}
UNRANKED = {None, "", "N"}
TIMELINE_KEY_ALIASES = {"abstract deadline": "abstract_deadline"}
TIMELINE_KEYS = {"abstract_deadline", "deadline", "comment"}


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected text, got {value!r}")
    text = " ".join(value.split())
    return text or None


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def local_deadline(value: Any, where: str) -> str | None:
    """`TBD` and empty strings mean the date has not been announced."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError(f"{where}: deadline must use the edition timezone")
        value = value.strftime("%Y-%m-%d %H:%M:%S")
    if (
        value is None
        or value == ""
        or (isinstance(value, str) and value.upper() == "TBD")
    ):
        return None
    if not isinstance(value, str) or not LOCAL_DATETIME.match(value):
        raise ValueError(f"{where}: invalid deadline {value!r}")
    return value


def normalize_rank(raw: Any, where: str) -> dict[str, str | None]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: rank must be an object")
    unknown = set(raw) - set(RANK_VALUES) - {"thc"}
    if unknown:
        raise ValueError(f"{where}: unknown rank systems {sorted(unknown)}")
    rank: dict[str, str | None] = {}
    for system, allowed in RANK_VALUES.items():
        value = raw.get(system, raw.get("thc") if system == "thcpl" else None)
        if value in UNRANKED:
            rank[system] = None
        elif value in allowed:
            rank[system] = value
        else:
            raise ValueError(f"{where}: invalid {system} rank {value!r}")
    return rank


def normalize_timeline(raw: Any, where: str) -> list[dict[str, str | None]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{where}: timeline must be a non-empty list")
    entries = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{where}[{index}]: timeline entry must be an object")
        item = {
            TIMELINE_KEY_ALIASES.get(key, key): value for key, value in item.items()
        }
        unknown = set(item) - TIMELINE_KEYS - {"rebuttal_deadline", "decision_deadline"}
        if unknown:
            raise ValueError(
                f"{where}[{index}]: unknown timeline keys {sorted(unknown)}"
            )
        entries.append(
            {
                "abstract_deadline": local_deadline(
                    item.get("abstract_deadline"), f"{where}[{index}]"
                ),
                "deadline": local_deadline(item.get("deadline"), f"{where}[{index}]"),
                "comment": optional_text(item.get("comment")),
            }
        )
    return entries


def normalize_edition(raw: Any, where: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: edition must be an object")
    year = raw.get("year")
    if not isinstance(year, int) or isinstance(year, bool) or not 1950 <= year <= 2100:
        raise ValueError(f"{where}: invalid year {year!r}")
    timezone = raw.get("timezone")
    if not isinstance(timezone, str) or not TIMEZONE.match(timezone):
        raise ValueError(f"{where}: unsupported timezone {timezone!r}")
    return {
        "year": year,
        "link": optional_text(raw.get("link")),
        "timezone": timezone,
        "date": optional_text(raw.get("date")),
        "place": optional_text(raw.get("place")),
        "timeline": normalize_timeline(raw.get("timeline"), f"{where}.timeline"),
    }


def build_snapshot(payload: dict, revision: str, exported_at: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full Git commit SHA")
    if not isinstance(exported_at, str) or not re.match(
        r"^\d{4}-\d{2}-\d{2}$", exported_at
    ):
        raise ValueError("source exported_at must be YYYY-MM-DD")

    categories = []
    for raw in payload.get("categories") or []:
        categories.append(
            {
                "id": raw["sub"],
                "name": optional_text(raw["name"]),
                "name_en": optional_text(raw.get("name_en")),
            }
        )
    category_ids = {category["id"] for category in categories}
    if not categories or len(category_ids) != len(categories):
        raise ValueError("categories must be a non-empty list with unique ids")

    conferences = []
    for raw in payload.get("conferences") or []:
        title = optional_text(raw.get("title"))
        category = raw.get("sub")
        where = f"{category}/{title}"
        if not title or category not in category_ids:
            raise ValueError(f"{where}: missing title or unknown category")
        editions = [
            normalize_edition(edition, f"{where}.confs[{index}]")
            for index, edition in enumerate(raw.get("confs") or [])
        ]
        years = [edition["year"] for edition in editions]
        if not editions or len(set(years)) != len(years):
            raise ValueError(f"{where}: editions must be non-empty with unique years")
        conferences.append(
            {
                # The same acronym can name different venues (FSE, SEC) and one venue can be
                # listed under two CCF categories with different ranks (DCC): key by both.
                "id": f"{category.lower()}-{slug(title)}",
                "title": title,
                "description": optional_text(raw.get("description")) or title,
                "category": category,
                "dblp": optional_text(raw.get("dblp")),
                "rank": normalize_rank(raw.get("rank"), where),
                "editions": sorted(editions, key=lambda edition: edition["year"]),
            }
        )

    ids = [conference["id"] for conference in conferences]
    if len(set(ids)) != len(ids):
        raise ValueError("conference ids are not unique")
    conferences.sort(key=lambda conference: conference["id"])

    canonical = json.dumps(
        {
            "categories": categories,
            "conferences": conferences,
            "revision": revision,
            "data_as_of": exported_at,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = {
        "schema_version": 1,
        "snapshot_id": f"ccfddl-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}",
        "data_as_of": exported_at,
        "source": {"name": "ccf-deadlines", "url": SOURCE_URL, "revision": revision},
        "categories": categories,
        "conferences": conferences,
    }
    catalog_from_snapshot(ConferenceSnapshotFile.model_validate(result))
    return result


def snapshot_from_files(
    files: dict[str, bytes], revision: str, commit_date: str
) -> dict:
    """Only accept the category catalog and direction/name.yml records."""
    if "conference/types.yml" not in files:
        raise ValueError("Missing conference/types.yml")
    categories = yaml.safe_load(files["conference/types.yml"])
    conferences = []
    for name, data in sorted(files.items()):
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == "conference" and name.endswith(".yml"):
            entries = yaml.safe_load(data)
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"{name}: expected a non-empty list")
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("sub") != parts[1]:
                    raise ValueError(f"{name}: category does not match directory")
            conferences.extend(entries)
    return build_snapshot(
        {"categories": categories, "conferences": conferences}, revision, commit_date
    )


def snapshot_from_directory(source: Path, revision: str, commit_date: str) -> dict:
    paths = [
        source / "conference/types.yml",
        *sorted((source / "conference").glob("*/*.yml")),
    ]
    files = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError(
                "Source must contain regular files inside the source directory"
            )
        files[path.relative_to(source).as_posix()] = path.read_bytes()
    return snapshot_from_files(files, revision, commit_date)
