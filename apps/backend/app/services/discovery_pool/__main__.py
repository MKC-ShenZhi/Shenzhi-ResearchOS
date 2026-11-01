"""Maintain the home-feed paper pool and its daily editions.

Usage (scheduling stays external, like the platform stats snapshot):

    uv run --env-file .env python -m app.services.discovery_pool sync [--year 2026] [--dry-run]
    uv run --env-file .env python -m app.services.discovery_pool publish [--date 2026-11-02] [--dry-run]

``sync`` replaces a year's pool from the knowledge base in one transaction; a
run that fails or would drop more than half of the pool leaves it untouched.
``publish`` builds the day's shared edition from the pool (default: today in
Shanghai). Both are safe to re-run; ``--dry-run`` reports without writing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date


def main() -> int:
    parser = argparse.ArgumentParser(prog='python -m app.services.discovery_pool', description='同步首页论文候选池')
    commands = parser.add_subparsers(dest='command', required=True)
    sync = commands.add_parser('sync', help='从知识底座同步指定年份的可展示论文')
    sync.add_argument('--year', type=int, default=None, help='默认上海时区当前年份')
    sync.add_argument('--dry-run', action='store_true', help='只统计覆盖率，不写入数据库')
    publish = commands.add_parser('publish', help='从候选池生成指定日期的全站每日精选')
    publish.add_argument('--date', type=date.fromisoformat, default=None, help='默认上海时区今天')
    publish.add_argument('--dry-run', action='store_true', help='只生成并统计，不写入数据库')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')

    from app.core.database import dispose_engine
    from app.services.discovery import _shanghai_today
    from app.services.discovery_pool.edition import DailyEditionBuilder
    from app.services.discovery_pool.sync import DiscoveryPoolSync

    async def run():
        try:
            if args.command == 'publish':
                builder = DailyEditionBuilder()
                edition_date = args.date or _shanghai_today()
                return await (builder.build if args.dry_run else builder.publish)(edition_date)
            return await DiscoveryPoolSync().sync(args.year or _shanghai_today().year, dry_run=args.dry_run)
        finally:
            await dispose_engine()

    try:
        result = asyncio.run(run())
    except Exception as error:
        logging.getLogger(__name__).exception('Discovery pool %s failed', args.command)
        print(json.dumps({'ok': False, 'error': type(error).__name__}, ensure_ascii=False))
        return 1
    print(json.dumps({'ok': True, 'dry_run': args.dry_run, **result.summary()}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
