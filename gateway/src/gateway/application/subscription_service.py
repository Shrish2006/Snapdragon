"""Subscription management: fans one shared event-bus subscription out to
many independent, filtered client queues.

This is the layer between the event bus (Phase 4) and any push transport —
WebSocket today (`api/ws/stream.py`), conceivably Server-Sent Events later
— transport-agnostic by design, matching `IngestionService`'s approach to
transport independence.

Deliberately one `EventBus.subscribe("websocket")` call total, not one per
connected client: with the Redis backend, a consumer group is a
server-side resource that persists until explicitly destroyed, and this
system has many short-lived WebSocket connections. Fan-out to individual
clients happens in-process instead, via bounded per-client queues.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from gateway.application.ports import EventBus
from gateway.domain.common.identifiers import HelmetId
from gateway.domain.events.models import DomainEvent
from gateway.domain.events.types import EventType, Severity

DEFAULT_QUEUE_SIZE = 100


class EventFilter(BaseModel):
    """What one subscriber wants to see. Every field `None`/absent means
    "no restriction on this dimension" — a fresh `EventFilter()` matches
    everything, the same broadcast-everything default the old gateway's
    `/ws` had, until a client narrows it."""

    model_config = ConfigDict(frozen=True)

    helmet_id: HelmetId | None = None
    event_types: set[EventType] | None = None
    severities: set[Severity] | None = None

    def matches(self, event: DomainEvent[Any]) -> bool:
        if self.helmet_id is not None and event.helmet_id != self.helmet_id:
            return False
        if self.event_types is not None and event.type not in self.event_types:
            return False
        if self.severities is not None and event.severity not in self.severities:
            return False
        return True


@dataclass(slots=True)
class Subscriber:
    """One connected client's live state: its current filter (mutable —
    a client can narrow/widen it any time after connecting) and its
    bounded outbound queue."""

    id: str
    filter: EventFilter
    queue: asyncio.Queue[DomainEvent[Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=DEFAULT_QUEUE_SIZE)
    )


class SubscriptionManager:
    """Runs the single shared bus subscription (`run()`, wired as a
    background task in `main.py`'s lifespan) and maintains the registry of
    connected subscribers that `run()` fans events out to.

    Backpressure: a full queue drops the incoming event for `INFO`/
    `WARNING` severities — a slow client falls behind but the fan-out loop
    (shared by every other client) is never blocked waiting on it.
    `CRITICAL` events are never dropped; a full queue instead evicts its
    own oldest entry to make room, since a critical alert arriving late is
    still far better than not arriving.
    """

    def __init__(self, bus: EventBus, *, group: str = "websocket") -> None:
        self._bus = bus
        self._group = group
        self._subscribers: dict[str, Subscriber] = {}
        self._lock = asyncio.Lock()

    async def run(self) -> None:
        subscription = self._bus.subscribe(self._group)
        try:
            async for event in subscription:
                await self._fan_out(event)
        finally:
            await subscription.close()

    async def register(self, event_filter: EventFilter | None = None) -> Subscriber:
        subscriber = Subscriber(id=str(uuid4()), filter=event_filter or EventFilter())
        async with self._lock:
            self._subscribers[subscriber.id] = subscriber
        return subscriber

    async def update_filter(
        self, subscriber_id: str, event_filter: EventFilter
    ) -> None:
        async with self._lock:
            subscriber = self._subscribers.get(subscriber_id)
            if subscriber is not None:
                subscriber.filter = event_filter

    async def unregister(self, subscriber_id: str) -> None:
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    async def _fan_out(self, event: DomainEvent[Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            if subscriber.filter.matches(event):
                _enqueue(subscriber.queue, event)


def _enqueue(queue: asyncio.Queue[DomainEvent[Any]], event: DomainEvent[Any]) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        if event.severity is Severity.CRITICAL:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            queue.put_nowait(event)
        # else: drop this event — the client is falling behind on a
        # non-critical stream; the next one still gets a chance.
