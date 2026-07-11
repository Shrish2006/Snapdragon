"""Standalone event-processing worker — the same `ProcessingPipeline` as
`main.py`'s in-process background task, runnable as its own
process/container.

Only meaningful with the Redis event bus backend
(`EVENT_BUS_BACKEND=redis`): the in-memory bus is process-local, so a
separate process reading from it would be an isolated bus seeing nothing
the gateway API process publishes.

Run: `python -m gateway.workers.processor_worker`
"""

from __future__ import annotations

import asyncio

from gateway.bootstrap import build_container
from gateway.config import get_settings


async def main() -> None:
    settings = get_settings()
    container = build_container(settings)
    await container.processing_pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())
