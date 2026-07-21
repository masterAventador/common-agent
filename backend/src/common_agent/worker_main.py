from __future__ import annotations

import asyncio
import signal

from common_agent.worker_app import run_worker


async def _main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop.set)
    await run_worker(stop)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
