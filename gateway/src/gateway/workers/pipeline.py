"""Event-processing pipeline: subscribes to the event bus, fans each
event out to every registered `EventProcessor`.

Runs as a background asyncio task inside the gateway process (wired in
`main.py`'s lifespan) for this phase — the same pipeline is also runnable
as a standalone process via `processor_worker.py`, meaningful once the bus
backend is Redis (the in-memory bus is process-local, so a separate
process reading from it would see nothing the API process publishes).

One processor raising never stops the others, or the pipeline itself — a
persistence write failure, say, shouldn't also suppress a future
alerting/notification processor for the same event.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from gateway.application.ports import EventBus
from gateway.domain.events.models import DomainEvent

logger = logging.getLogger(__name__)


class EventProcessor(Protocol):
    """One unit of work run for every event the pipeline receives."""

    async def process(self, event: DomainEvent[Any]) -> None: ...


class ProcessingPipeline:
    def __init__(
        self, bus: EventBus, processors: list[EventProcessor], *, group: str = "processing"
    ) -> None:
        self._bus = bus
        self._processors = processors
        self._group = group

    async def run(self) -> None:
        subscription = self._bus.subscribe(self._group)
        try:
            async for event in subscription:
                await self._dispatch(event)
        finally:
            await subscription.close()

    async def _dispatch(self, event: DomainEvent[Any]) -> None:
        results = await asyncio.gather(
            *(processor.process(event) for processor in self._processors),
            return_exceptions=True,
        )
        for processor, result in zip(self._processors, results, strict=True):
            if isinstance(result, BaseException):
                logger.error(
                    "processor %s failed for event %s (%s): %s",
                    type(processor).__name__,
                    event.event_id,
                    event.type.value,
                    result,
                )
