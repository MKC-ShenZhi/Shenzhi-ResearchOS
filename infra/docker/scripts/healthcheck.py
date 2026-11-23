"""HTTP liveness plus DB connectivity/schema readiness; no external model calls."""
import asyncio
import os
import sys
import urllib.request

import asyncpg


async def main():
    agent = sys.argv[1] == 'agent'
    url = 'http://127.0.0.1:8101/internal/v1/health' if agent else 'http://127.0.0.1:8000/health'
    with urllib.request.urlopen(url, timeout=3) as response:
        assert response.status == 200
    raw = os.environ['AGENT_DATABASE_URL' if agent else 'CHAT_DATABASE_URL']
    db = await asyncpg.connect(raw.replace('postgresql+asyncpg://', 'postgresql://', 1), timeout=3)
    try:
        assert await db.fetchval('SELECT version_num FROM alembic_version')
    finally:
        await db.close()


asyncio.run(main())
