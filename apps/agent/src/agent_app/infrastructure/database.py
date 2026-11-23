"""Agent-owned PostgreSQL connection; Backend database settings are never read."""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _database_url() -> str:
    value = os.getenv('AGENT_DATABASE_URL', '').strip()
    if not value:
        raise RuntimeError('AGENT_DATABASE_URL is required for Agent persistence')
    return value


engine = None
SessionFactory = None


async def get_session():
    global engine, SessionFactory
    if SessionFactory is None:
        engine = create_async_engine(_database_url(), pool_pre_ping=True)
        SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionFactory() as session:
        yield session
