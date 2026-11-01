"""Sync the home-feed paper pool from the knowledge base.

Usage (scheduling stays external, like the platform stats snapshot):

    uv run --env-file .env python -m app.services.discovery_pool sync [--year 2026] [--dry-run]

``--dry-run`` reads the knowledge base and reports coverage without writing.
Re-running is safe: a year's pool is replaced in one transaction, and a run
that fails or would drop more than half of the pool leaves it untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog='python -m app.services.discovery_pool', description='同步首页论文候选池')
    commands = parser.add_subparsers(dest='command', required=True)
    sync = commands.add_parser('sync', help='从知识底座同步指定年份的可展示论文')
    sync.add_argument('--year', type=int, default=None, help='默认上海时区当前年份')
    sync.add_argument('--dry-run', action='store_true', help='只统计覆盖率，不写入数据库')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')

    from app.core.database import dispose_engine
    from app.services.discovery import _shanghai_today
    from app.services.discovery_pool.sync import DiscoveryPoolSync

    async def run():
        try:
            return await DiscoveryPoolSync().sync(args.year or _shanghai_today().year, dry_run=args.dry_run)
        finally:
            await dispose_engine()

    try:
        result = asyncio.run(run())
    except Exception as error:
        logging.getLogger(__name__).exception('Discovery pool sync failed')
        print(json.dumps({'ok': False, 'error': type(error).__name__}, ensure_ascii=False))
        return 1
    print(json.dumps({'ok': True, 'dry_run': args.dry_run, **result.summary()}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
