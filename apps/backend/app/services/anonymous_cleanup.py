"""Explicit maintenance command for durable anonymous Chat data."""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from app.services.sessions import repository

DEFAULT_ANONYMOUS_TTL_SECONDS = 604800
logger = logging.getLogger(__name__)


def anonymous_ttl_seconds() -> int:
    raw = os.getenv('CHAT_ANONYMOUS_TTL_SECONDS', str(DEFAULT_ANONYMOUS_TTL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError('CHAT_ANONYMOUS_TTL_SECONDS must be a positive integer') from exc
    if value <= 0:
        raise ValueError('CHAT_ANONYMOUS_TTL_SECONDS must be a positive integer')
    return value


async def purge_expired_anonymous_sessions(now: datetime | None = None) -> int:
    if not repository.is_durable:
        raise RuntimeError('CHAT_DATABASE_URL is required for anonymous-session cleanup')
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=anonymous_ttl_seconds())
    return await repository.purge_expired_anonymous_sessions(cutoff)


async def main() -> int:
    try:
        deleted = await purge_expired_anonymous_sessions()
    except Exception:
        logger.exception('Anonymous session cleanup failed')
        return 1
    else:
        logger.info('Anonymous session cleanup completed deleted_sessions=%s', deleted)
        print(f'deleted_sessions={deleted}')
        return 0
    finally:
        await repository.close()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
