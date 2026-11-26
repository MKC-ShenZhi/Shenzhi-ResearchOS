"""Independent Agent Worker process entry point."""
import asyncio
import logging
import signal

from agent_app.worker.host import run_worker_forever


async def run() -> None:
    loop = asyncio.get_running_loop()
    worker = asyncio.create_task(run_worker_forever())
    registered = False
    try:
        loop.add_signal_handler(signal.SIGTERM, worker.cancel)
        registered = True
    except NotImplementedError:
        pass
    try:
        await worker
    except asyncio.CancelledError:
        pass
    finally:
        if registered:
            loop.remove_signal_handler(signal.SIGTERM)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == '__main__':
    main()
