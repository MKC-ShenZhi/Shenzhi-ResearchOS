"""Generate the daily platform statistics snapshot.

Usage (the repository does not own the deployment topology, so scheduling stays
external — cron / systemd timer / platform scheduler):

    uv run --env-file .env python -m app.services.stats

Re-running the same day is safe: the day is rebuilt in one transaction.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='python -m app.services.stats',
        description='生成并发布上海时区当天的平台聚合快照',
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    from app.services.stats.snapshot import SnapshotService

    try:
        # The source tables only contain current relationships. A past --date
        # would label today's counts as historical data, so the CLI only builds
        # the current Shanghai calendar day.
        result = asyncio.run(SnapshotService().build())
    except Exception:
        print(json.dumps({'ok': False}, ensure_ascii=False))
        return 1

    print(json.dumps({
        'ok': True,
        'snapshot_date': result.snapshot_date.isoformat(),
        'snapshot_version': result.snapshot_version,
        'computed_at': result.computed_at.isoformat(),
        'paper_count': result.paper_count,
        'topic_count': result.topic_count,
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
