"""Generate the local Scholar layout preview from the supplied dataset."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
import json
import shutil

def orcid_identifier(ids):
    observed = {value for value in ids.get("observed_orcids", []) if value}
    value = ids.get("orcid")
    if not isinstance(value, str) or observed - {value}:
        return None
    match = re.fullmatch(r"https://orcid.org/(\d{4}-\d{4}-\d{4}-\d{3}[0-9X])", value)
    if not match:
        return None
    identifier = match[1]
    digits = identifier.replace("-", "")
    total = 0
    for digit in digits[:-1]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return identifier if digits[-1] == ("X" if check == 10 else str(check)) else None


repo = Path(__file__).resolve().parents[1]
source = repo / "scholar"
output = repo / "apps/web/public/images/scholar-preview"
records = [(path, json.loads(path.read_text(encoding="utf-8-sig"))) for path in source.glob("*.json")]
if not records:
    raise SystemExit("No scholar JSON files found.")
references = Counter(record.get("avatar_path") for _, record in records)
profiles = []
for path, record in sorted(records, key=lambda item: (item[1]["display_name"].casefold(), item[0].name)):
    preview_id = sha256(path.stem.encode()).hexdigest()[:20]
    avatar_ref = record.get("avatar_path") or ""
    avatar = source / avatar_ref
    avatar_url = None
    if (
        references[avatar_ref] == 1
        and avatar.resolve().parent == (source / "avatar").resolve()
        and avatar.suffix.lower() in {".jpg", ".webp"}
        and avatar.is_file()
    ):
        filename = preview_id + avatar.suffix.lower()
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(avatar, output / filename)
        avatar_url = f"/images/scholar-preview/{filename}"

    institutions = record["last_known_institutions"] or record["affiliations"]
    institution = next((item["institution"]["display_name"] for item in institutions if item["institution"]["display_name"]), None)
    profiles.append({
        "scholar_id": f"preview-{preview_id}",
        "name_en": record["display_name"],
        "aliases": record["display_name_alternatives"],
        "avatar_path": avatar_url,
        "affiliations": [{"institution": institution}] if institution else [],
        "employment": [
            {key: entry.get(key) or None for key in (
                "organization", "role_title", "department", "start_date", "end_date",
            )}
            for entry in record["employment"]
            if entry.get("organization") or entry.get("role_title")
        ],
        "external_ids": {"orcid": orcid_identifier(record["ids"])},
        "metrics": {
            "source_work_count": record["works_count"],
            "citation_count": record["cited_by_count"],
            "h_index": record["summary_stats"]["h_index"],
            "i10_index": record["summary_stats"]["i10_index"],
        },
        "topics": list(dict.fromkeys(topic["display_name"] for topic in record["topics"] if topic["display_name"])),
        "bio_en": record["biographies"]["en"],
        "annual_citations": [
            {"year": row["year"], "count": row["cited_by_count"]}
            for row in record["counts_by_year"] if row["year"] <= 2026
        ],
    })

output.mkdir(parents=True, exist_ok=True)
(output / "profiles.json").write_text(json.dumps(profiles, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"Generated {len(profiles)} profiles and {sum(bool(profile['avatar_path']) for profile in profiles)} avatars.")

# The homepage snapshot provides matching metadata and figures for offline preview.
discovery = repo / "apps/backend/app/data/home_discovery_snapshot.json"
public = repo / "apps/web/public"
featured = []
for paper in json.loads(discovery.read_text(encoding="utf-8"))["items"]:
    thumbnail = paper.get("thumbnail_url") or ""
    if thumbnail.startswith("/paper-thumbnails/") and (public / thumbnail.lstrip("/")).is_file():
        featured.append(paper)
    if len(featured) == 10:
        break
if len(featured) != 10:
    raise SystemExit("Expected 10 homepage papers with local thumbnails.")
(output / "featured-papers.json").write_text(
    json.dumps(featured, ensure_ascii=False), encoding="utf-8",
)
