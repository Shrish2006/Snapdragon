"""In-memory `EventBus` adapter: `asyncio.Queue`-based fan-out to N
independent subscriber groups within one process.

Single-process, like `InMemoryHelmetRepository` — does not share events
across gateway replicas. This is the zero-infrastructure default; a
`RedisStreamsEventBus` implementing the same port (`redis_streams.py`) is
available for horizontal deployments, opt-in via
`Settings.event_bus_backend`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from gateway.domain.events.models import DomainEvent

_CLOSE_SENTINEL: object = object()
"""Pushed into a subscription's queue on `close()` so a pending
`await queue.get()` unblocks immediately, instead of waiting for the next
published event (or task cancellation) to notice the subscription closed."""


class _InMemorySubscription:
    """Implements `application.ports.EventSubscription` structurally."""

    def __init__(self, unregister: Callable[["_InMemorySubscription"], None]) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._unregister = unregister
        self._closed = False

    def put(self, event: DomainEvent[Any]) -> None:
        if not self._closed:
            self._queue.put_nowait(event)

    def __aiter__(self) -> AsyncIterator[DomainEvent[Any]]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[DomainEvent[Any]]:
        while True:
            item = await self._queue.get()
            if item is _CLOSE_SENTINEL:
                return
            yield item

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._unregister(self)
            self._queue.put_nowait(_CLOSE_SENTINEL)


class InMemoryEventBus:
    """Implements `application.ports.EventBus` structurally."""

    def __init__(self) -> None:
        self._groups: dict[str, list[_InMemorySubscription]] = {}

    async def publish(self, event: DomainEvent[Any]) -> None:
        for subscriptions in self._groups.values():
            for subscription in list(subscriptions):
                subscription.put(event)

    def subscribe(self, group: str) -> _InMemorySubscription:
        members = self._groups.setdefault(group, [])
        subscription = _InMemorySubscription(unregister=members.remove)
        members.append(subscription)
        return subscription
