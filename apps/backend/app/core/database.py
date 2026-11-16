"""Async SQLAlchemy engine shared by every business table (CHAT_DATABASE_URL)."""
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def database_url() -> str | None:
    url = os.getenv('CHAT_DATABASE_URL', '').strip()
    return url or None


def _normalize_url(url: str) -> str:
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql+asyncpg://', 1)
    return url


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        raw = database_url()
        if not raw:
            raise RuntimeError('CHAT_DATABASE_URL is not configured')
        _engine = create_async_engine(_normalize_url(raw), pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
