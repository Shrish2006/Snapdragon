"""Redis Streams `EventBus` adapter — the event bus backend named in the
approved architecture: one ordered stream, consumer groups per subscriber
group. Multiple gateway instances publishing to and reading from the same
Redis therefore share one event history, and a restarted subscriber
resumes from its group's last-acknowledged position (Redis tracks this
server-side) instead of missing events published while it was down.

Verified against `fakeredis.asyncio.FakeRedis` — no real Redis server is
required to exercise this adapter's logic; a real Redis/Valkey server is
wire-compatible with the same client. Opt in via
`Settings.event_bus_backend = "redis"` / `Settings.redis_url` once Redis
infrastructure is provisioned — not added to `docker-compose.yml` in this
phase, since the default backend remains in-memory and an idle Redis
container would serve no purpose until then (see `bootstrap.py`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from gateway.domain.events.models import EVENT_TYPE_REGISTRY, DomainEvent
from gateway.domain.events.types import EventType

_STREAM_KEY = "gateway:events"
_BLOCK_MS = 5000
"""Upper bound on how long `close()` can take to actually stop a
subscription's read loop: a blocking `XREADGROUP` only re-checks
`_closed` after this timeout elapses or a message arrives. Acceptable —
comparable to a Kafka consumer's poll timeout — and avoiding it would mean
a second Redis connection per subscription just to interrupt the first."""


def _serialize(event: DomainEvent[Any]) -> dict[str, str]:
    return {"payload": event.model_dump_json()}


def _deserialize(fields: dict[bytes, bytes]) -> DomainEvent[Any]:
    raw = json.loads(fields[b"payload"])
    model = EVENT_TYPE_REGISTRY[EventType(raw["type"])]
    return model.model_validate(raw)


class _RedisStreamSubscription:
    """Implements `application.ports.EventSubscription` structurally."""

    def __init__(self, redis: Redis, group: str) -> None:
        self._redis = redis
        self._group = group
        self._consumer = f"consumer-{uuid4().hex[:8]}"
        self._closed = False

    def __aiter__(self) -> AsyncIterator[DomainEvent[Any]]:
        return self._iterate()

    async def _ensure_group(self) -> None:
        try:
            # id="0": deliver every message not yet seen by this group,
            # including ones added before the group existed — a
            # newly-created group should never silently skip history.
            await self._redis.xgroup_create(_STREAM_KEY, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise  # group already exists — fine, resume from its offset

    async def _iterate(self) -> AsyncIterator[DomainEvent[Any]]:
        await self._ensure_group()
        while not self._closed:
            response = await self._redis.xreadgroup(
                self._group, self._consumer, {_STREAM_KEY: ">"}, count=10, block=_BLOCK_MS
            )
            if not response:
                continue
            for _stream_key, messages in response:
                for message_id, fields in messages:
                    # Acked before yielding, not after the consumer
                    # finishes processing: `workers.pipeline` already
                    # catches and only logs a processor's exception rather
                    # than retrying, so "redeliver on failure" has no
                    # consumer that would act on it — acking eagerly here
                    # avoids a message getting stuck permanently pending
                    # if a subscriber reads it and is then cancelled
                    # before ever asking for the next one.
                    await self._redis.xack(_STREAM_KEY, self._group, message_id)
                    yield _deserialize(fields)

    async def close(self) -> None:
        self._closed = True


class RedisStreamsEventBus:
    """Implements `application.ports.EventBus` structurally."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, event: DomainEvent[Any]) -> None:
        await self._redis.xadd(_STREAM_KEY, _serialize(event))

    def subscribe(self, group: str) -> _RedisStreamSubscription:
        return _RedisStreamSubscription(self._redis, group)

    async def ping(self) -> bool:
        """Not part of `application.ports.EventBus` — an extra capability
        `api/http/health.py`'s `/ready` check uses (via `isinstance`) when
        this backend is selected, the same pattern
        `main.py`'s lifespan already uses for
        `SQLiteEventStore.initialize()`."""
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
