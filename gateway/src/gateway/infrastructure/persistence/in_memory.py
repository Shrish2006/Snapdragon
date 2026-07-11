"""In-memory `EventStore` adapter: the direct successor to the old
gateway's `deque(maxlen=EVENT_BUFFER)` — same bounded hot buffer and the
same `EVENT_BUFFER` setting, now behind a port and populated by the
processing pipeline's `PersistenceProcessor` instead of being poked
inline from every call site that emits an event. Lost on restart, like
the original; `SQLiteEventStore` is the durable alternative.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.events.models import DomainEvent
from gateway.domain.events.types import EventType


class InMemoryEventStore:
    """Implements `application.ports.EventStore` structurally."""

    def __init__(self, max_size: int) -> None:
        self._events: deque[DomainEvent[Any]] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        return None

    async def append(self, event: DomainEvent[Any]) -> None:
        async with self._lock:
            self._events.append(event)

    async def query(
        self,
        *,
        helmet_id: HelmetId | None = None,
        event_type: EventType | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[DomainEvent[Any]]:
        async with self._lock:
            events = list(self._events)
        if helmet_id is not None:
            events = [event for event in events if event.helmet_id == helmet_id]
        if event_type is not None:
            events = [event for event in events if event.type == event_type]
        if since is not None:
            events = [event for event in events if event.occurred_at >= since]
        events.sort(key=lambda event: event.occurred_at, reverse=True)
        return events[:limit]
