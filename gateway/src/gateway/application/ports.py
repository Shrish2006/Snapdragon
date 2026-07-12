"""Application ports (interfaces) that use-cases depend on.

Concrete adapters live in `infrastructure/` and are wired in
`gateway.bootstrap`'s composition root. Use-cases only ever depend on
these `Protocol`s — never on a concrete adapter — so swapping the
in-memory repository for a Redis-backed one, the in-memory event bus for
the Redis Streams one, or the in-memory event store for the SQLite one
(all selectable via `Settings`, see `bootstrap.py`) touches zero
application code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.detection.models import FallDetectionResult, PPEDetectionResult
from gateway.domain.events.models import DomainEvent
from gateway.domain.events.types import EventType
from gateway.domain.helmets.models import HelmetState


class HelmetRepository(Protocol):
    """Persistence port for helmet state.

    `InMemoryHelmetRepository` (Phase 2) is single-process and correct for
    one gateway instance. A Redis-backed adapter behind this same port is
    the natural swap for horizontal scale (hundreds of helmets across
    multiple gateway instances).
    """

    async def get(self, helmet_id: HelmetId) -> HelmetState | None: ...

    async def upsert(self, state: HelmetState) -> None: ...

    async def list_all(self) -> list[HelmetState]: ...


class EventPublisher(Protocol):
    """Publishing port for domain events. Every `EventBus` (below) is
    also an `EventPublisher`; services that only need to publish
    (`IngestionService`, `PPEDetectionService`) depend on this narrower
    Protocol rather than the full bus — Interface Segregation: they have
    no business subscribing to anything."""

    async def publish(self, event: DomainEvent[Any]) -> None: ...


class EventSubscription(Protocol):
    """A handle for one subscriber's stream of events. `async for event in
    subscription:` yields events as they arrive; `close()` stops iteration
    and releases the subscription (idempotent)."""

    def __aiter__(self) -> AsyncIterator[DomainEvent[Any]]: ...

    async def close(self) -> None: ...


class EventBus(EventPublisher, Protocol):
    """Publish + subscribe port for the event bus.

    `subscribe(group)` is fan-out, not competing-consumers: every
    independent `group` receives every published event (the processing
    pipeline's `"processing"` group and, from Phase 5, a WebSocket
    fan-out group each see the full stream). `InMemoryEventBus` (Phase 4
    default) is `asyncio.Queue`-based and process-local.
    `RedisStreamsEventBus` implements the same contract via Redis
    consumer groups, so multiple gateway instances share one event
    history and a restarted subscriber resumes where it left off — opt in
    via `Settings.event_bus_backend = "redis"`.
    """

    def subscribe(self, group: str) -> EventSubscription: ...


class EventStore(Protocol):
    """Durable event history port.

    `InMemoryEventStore` (Phase 4 default) is the direct successor to the
    old gateway's `deque(maxlen=EVENT_BUFFER)` — bounded, lost on
    restart. `SQLiteEventStore` persists across restarts with zero extra
    infrastructure; a Postgres/TimescaleDB adapter (the approved
    architecture's storage recommendation for multi-instance production
    deployments) implements this same port when that infrastructure is
    provisioned — not built here, since it can't be verified without a
    running database.
    """

    async def append(self, event: DomainEvent[Any]) -> None: ...

    async def query(
        self,
        *,
        helmet_id: HelmetId | None = None,
        event_type: EventType | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[DomainEvent[Any]]: ...


class ServiceHealth(str, Enum):
    """Outcome of one `MLServiceClient.health()` call.

    Three states, not a bool — mirrors the old gateway's `/status`
    behavior, which distinguished a service that responded with a
    non-success status (`DEGRADED`) from one that couldn't be reached at
    all (`UNREACHABLE`)."""

    OK = "ok"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


class MLServiceClient(Protocol):
    """Minimal client port every ML service satisfies: a health check.

    `GET /health` is the one contract proven across every ML service in
    this codebase today (`ai_ml/ppe_detection/app.py`,
    `ai_ml/fall_detection/app.py`) — including fall-detection, which
    exposes nothing else yet. `FallDetectionHttpClient` implements exactly
    this Protocol; it grows a typed inference method (mirroring
    `PPEDetectionClient.detect`) only once `ai_ml/fall_detection` defines
    one.
    """

    async def health(self) -> ServiceHealth: ...


class PPEDetectionClient(MLServiceClient, Protocol):
    """Client port for the ppe-detection service. `detect()` mirrors
    `ai_ml/ppe_detection/app.py::detect()` exactly: raw image bytes in,
    typed `PPEDetectionResult` out."""

    async def detect(
        self, image: bytes, *, filename: str, content_type: str
    ) -> PPEDetectionResult: ...


class FallDetectionClient(MLServiceClient, Protocol):
    """Client port for the fall-detection service.

    `ingest()` receives a complete 200-sample window assembled by
    `FallDetectionProcessor` and returns a raw probability from the ONNX
    model. The processor owns the buffer and debounce; this client is a
    thin HTTP adapter over the stateless inference endpoint."""

    async def ingest(
        self,
        helmet_id: str,
        window: list[list[float]],
    ) -> FallDetectionResult: ...
