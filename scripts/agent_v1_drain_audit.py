"""Read-only audit of V1 Agent work before retiring compatibility paths.

Run from the repository root with both CHAT_DATABASE_URL and AGENT_DATABASE_URL
configured. The command never prints connection strings, owners, or record IDs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


ACTIVE_TASK_STATUSES = ('queued', 'running', 'paused', 'cancelling')
ACTIVE_RUN_STATUSES = ('pending', 'running')


def async_database_url(raw: str):
    url = make_url(raw)
    if url.drivername == 'postgresql':
        url = url.set(drivername='postgresql+asyncpg')
    if url.drivername != 'postgresql+asyncpg':
        raise ValueError('PostgreSQL async URLs are required')
    return url


async def fetch_counts(raw_url: str, *, role: str) -> dict:
    engine = create_async_engine(
        async_database_url(raw_url),
        connect_args={'server_settings': {'default_transaction_read_only': 'on'}},
    )
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                # This must be the first statement in the transaction. The
                # server-side default above provides a second read-only guard.
                await connection.execute(text('SET TRANSACTION READ ONLY'))
                identity = (await connection.execute(text(
                    'SELECT current_database(), inet_server_addr()::text, inet_server_port()'
                ))).one()
                fingerprint_input = '|'.join(str(part or '') for part in identity)
                database_fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:12]

                if role == 'agent':
                    has_metering = await connection.scalar(text(
                        "SELECT to_regclass('public.agent_task_metering') IS NOT NULL"
                    ))
                    if not has_metering:
                        raise RuntimeError('Agent metering migration is not present')
                    task_rows = (await connection.execute(text("""
                        SELECT task.status, count(*)::bigint AS count
                        FROM agent_tasks AS task
                        LEFT JOIN agent_task_metering AS metering ON metering.task_id = task.task_id
                        WHERE metering.task_id IS NULL
                        GROUP BY task.status ORDER BY task.status
                    """))).mappings().all()
                    run_rows = (await connection.execute(text("""
                        SELECT run.status, count(*)::bigint AS count
                        FROM agent_runs AS run
                        JOIN agent_tasks AS task ON task.task_id = run.task_id
                        LEFT JOIN agent_task_metering AS metering ON metering.task_id = task.task_id
                        WHERE metering.task_id IS NULL
                        GROUP BY run.status ORDER BY run.status
                    """))).mappings().all()
                    tasks_by_status = {row['status']: row['count'] for row in task_rows}
                    runs_by_status = {row['status']: row['count'] for row in run_rows}
                    return {
                        'database_fingerprint': database_fingerprint,
                        'legacy_tasks_by_status': tasks_by_status,
                        'legacy_runs_by_status': runs_by_status,
                        'legacy_task_total': sum(tasks_by_status.values()),
                        'active_legacy_task_total': sum(
                            tasks_by_status.get(status, 0) for status in ACTIVE_TASK_STATUSES
                        ),
                        'active_legacy_run_total': sum(
                            runs_by_status.get(status, 0) for status in ACTIVE_RUN_STATUSES
                        ),
                    }

                has_turns = await connection.scalar(text(
                    "SELECT to_regclass('public.agent_turns') IS NOT NULL"
                ))
                if not has_turns:
                    raise RuntimeError('Backend Session migration is not present')
                row = (await connection.execute(text("""
                    SELECT
                      count(*) FILTER (
                        WHERE status = 'running'
                          AND settings->>'_agent_protocol' IS DISTINCT FROM '2'
                      )::bigint AS active_legacy_turns,
                      count(*) FILTER (
                        WHERE settings->>'_agent_protocol' IS DISTINCT FROM '2'
                          AND settings->>'agent_task_id' IS NOT NULL
                      )::bigint AS legacy_turns_linked_to_agent_tasks
                    FROM agent_turns
                """))).mappings().one()
                return {
                    'database_fingerprint': database_fingerprint,
                    'active_legacy_turns': row['active_legacy_turns'],
                    'legacy_turns_linked_to_agent_tasks': row['legacy_turns_linked_to_agent_tasks'],
                }
    finally:
        await engine.dispose()


async def main() -> int:
    agent_url = os.getenv('AGENT_DATABASE_URL', '').strip()
    backend_url = os.getenv('CHAT_DATABASE_URL', '').strip()
    if not agent_url or not backend_url:
        print('Set AGENT_DATABASE_URL and CHAT_DATABASE_URL to the intended databases.', file=sys.stderr)
        return 2

    try:
        agent, backend = await asyncio.gather(
            fetch_counts(agent_url, role='agent'),
            fetch_counts(backend_url, role='backend'),
        )
    except Exception:
        # Driver errors may echo credential-bearing DSNs. Keep output sanitized.
        print('Audit failed. Check database URLs, connectivity, and required migrations; details suppressed.',
              file=sys.stderr)
        return 2

    if agent['database_fingerprint'] == backend['database_fingerprint']:
        print('Refusing to audit: Agent and Backend URLs resolve to the same database.', file=sys.stderr)
        return 2

    data_drain_clear = (
        agent['active_legacy_task_total'] == 0
        and agent['active_legacy_run_total'] == 0
        and backend['active_legacy_turns'] == 0
    )
    backend_legacy_readers_clear = backend['legacy_turns_linked_to_agent_tasks'] == 0
    retirement_data_clear = data_drain_clear and backend_legacy_readers_clear
    result = {
        'agent': agent,
        'backend': backend,
        'database_drain_clear': data_drain_clear,
        'backend_legacy_task_references_clear': backend_legacy_readers_clear,
        'retirement_data_clear': retirement_data_clear,
        'external_v1_callers_verified': False,
        'v1_retirement_proven': False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if retirement_data_clear else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
