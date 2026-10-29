"""Per-process identity and heartbeat supervision for durable background work."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

# Model calls default to 90s and the Vercel backend cap is 300s. This is a
# process-loss grace, refreshed independently of model output every 30 seconds.
LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30

T = TypeVar('T')
logger = logging.getLogger(__name__)

_worker_pid = os.getpid()
_worker_id = uuid.uuid4().hex


def current_worker_id() -> str:
    """Return one stable identity per OS process, including after a fork."""
    global _worker_id, _worker_pid
    pid = os.getpid()
    if pid != _worker_pid:
        _worker_id = uuid.uuid4().hex
        _worker_pid = pid
    return _worker_id


class WorkerLeaseLost(RuntimeError):
    pass


async def _heartbeat(
    renew: Callable[[], Awaitable[bool | None]], interval_seconds: float, lease_seconds: float,
) -> None:
    loop = asyncio.get_running_loop()
    renewed_at = loop.time()
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            renewed = await renew()
        except Exception:
            # A transient database error must not abort healthy work while the
            # last durable lease is still valid. Give up only when the next
            # attempt could land after expiry, when another worker may recover it.
            if loop.time() - renewed_at + interval_seconds >= lease_seconds:
                raise
            logger.warning('Worker lease renewal failed; retrying before expiry', exc_info=True)
            continue
        if renewed is None:
            return
        if not renewed:
            raise WorkerLeaseLost('worker lease is no longer active')
        renewed_at = loop.time()


async def run_with_heartbeat(
    operation: Callable[[], Awaitable[T]],
    renew: Callable[[], Awaitable[bool | None]],
    *,
    interval_seconds: float = HEARTBEAT_SECONDS,
    lease_seconds: float = LEASE_SECONDS,
) -> T:
    """Run work until it completes, canceling it if renewal fails or ownership is lost."""
    operation_task = asyncio.create_task(operation())
    heartbeat_task = asyncio.create_task(_heartbeat(renew, interval_seconds, lease_seconds))
    try:
        done, _ = await asyncio.wait(
            (operation_task, heartbeat_task), return_when=asyncio.FIRST_COMPLETED,
        )
        if operation_task in done:
            return await operation_task
        if heartbeat_task in done:
            await heartbeat_task
            return await operation_task
    finally:
        for task in (operation_task, heartbeat_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(operation_task, heartbeat_task, return_exceptions=True)
