"""Offline publisher and guarded online sync.

uv run --locked python -m app.services.conferences.cli publish --source PATH
uv run --locked --env-file .env python -m app.services.conferences.cli sync --dry-run
"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from app.services.conferences import SNAPSHOT_PATH
from app.services.conferences.source import snapshot_from_directory
from app.services.conferences.sync import ConferenceSync
from app.core.database import dispose_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--source", type=Path, required=True)
    publish.add_argument("--snapshot", type=Path, default=SNAPSHOT_PATH)
    publish.add_argument("--revision")
    publish.add_argument("--commit-date")
    publish.add_argument("--check", action="store_true")
    sync = commands.add_parser("sync")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "sync":

        async def run():
            try:
                print(
                    json.dumps(
                        await ConferenceSync().run(
                            dry_run=args.dry_run, force=args.force
                        )
                    )
                )
            finally:
                await dispose_engine()

        asyncio.run(run())
        return
    revision, commit_date = args.revision, args.commit_date
    if not revision or not commit_date:

        def git(*options):
            return subprocess.check_output(
                ["git", "-C", str(args.source), *options], text=True
            ).strip()

        revision = revision or git("rev-parse", "HEAD")
        commit_date = commit_date or git("show", "-s", "--format=%cI", "HEAD")[:10]
        if git("status", "--porcelain", "--", "conference", "accept_rates"):
            raise ValueError("Source has uncommitted conference changes")
    snapshot = snapshot_from_directory(args.source, revision, commit_date)
    previous = (
        json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.snapshot.exists()
        else None
    )
    removed = (
        sorted(
            {c["id"] for c in previous["conferences"]}
            - {c["id"] for c in snapshot["conferences"]}
        )
        if previous
        else []
    )
    if args.check:
        if previous != snapshot:
            raise ValueError("Published snapshot is stale")
    else:
        temporary = args.snapshot.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(args.snapshot)
    print(
        json.dumps(
            {
                "snapshot_id": snapshot["snapshot_id"],
                "conferences": len(snapshot["conferences"]),
                "removed_ids": removed,
            }
        )
    )


if __name__ == "__main__":
    main()
