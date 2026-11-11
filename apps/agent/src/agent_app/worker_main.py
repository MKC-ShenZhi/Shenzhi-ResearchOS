"""Independent Agent Worker process entry point."""
import asyncio
import logging

from agent_app.worker.host import run_worker_forever


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker_forever())


if __name__ == '__main__':
    main()
