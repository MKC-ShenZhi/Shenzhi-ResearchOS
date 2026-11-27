"""Single migration entrypoint; PostgreSQL advisory locks serialize operators too."""
import asyncio
import os
import subprocess
import sys

import asyncpg
from auth_migrations import load_auth_migrations


async def main():
    target = sys.argv[1]
    variable = 'AGENT_DATABASE_URL' if target == 'agent' else 'CHAT_DATABASE_URL'
    url = os.environ[variable].replace('postgresql+asyncpg://', 'postgresql://', 1)
    connection = await asyncpg.connect(url)
    try:
        # All three paths use the same database lock namespace.
        await connection.execute('SELECT pg_advisory_lock(73492001)')
        if target != 'auth':
            subprocess.run(['alembic', 'upgrade', 'head'], check=True)
            return
        await connection.execute('CREATE TABLE IF NOT EXISTS docker_auth_migrations '
                                 '(name text PRIMARY KEY, sha256 text NOT NULL)')
        for name, sql, digest in load_auth_migrations():
            previous = await connection.fetchval('SELECT sha256 FROM docker_auth_migrations WHERE name=$1', name)
            if previous is not None:
                if previous != digest:
                    raise RuntimeError(f'Applied migration changed: {name}')
                continue
            async with connection.transaction():
                await connection.execute(sql)
                await connection.execute('INSERT INTO docker_auth_migrations VALUES ($1,$2)', name, digest)
            print(f'Applied {name}', flush=True)
    finally:
        await connection.close()


asyncio.run(main())
