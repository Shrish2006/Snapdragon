"""Live dashboard event-history APIs — built directly on Phase 4's
`EventStore.query()`; the query parameters here are exactly that port's
filter set, exposed over HTTP.

Responses are plain `list[dict]` (`.model_dump(mode="json")` per event),
not a typed `response_model` of `DomainEvent` — the store returns a
heterogeneous mix of concrete event subclasses, and forcing that through
one generic `response_model` risks FastAPI/pydantic serializing against
the *declared* (generic) schema instead of each event's *actual* subclass
(see `api/ws/protocol.py`'s docstring for the same tradeoff on the
WebSocket side).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter

from gateway.api.http.deps import EventStoreDep
from gateway.domain.common.identifiers import HelmetId
from gateway.domain.events.types import EventType

router = APIRouter(prefix="/v1", tags=["events"])


@router.get(
    "/events",
    summary="Query recent event history, optionally filtered.",
    description=(
        "Returns a heterogeneous list of `DomainEvent` subclasses serialised "
        "as JSON objects. Filter by helmet, event type, or time window.\n\n"
        "**Event types** (`event_type`):\n"
        "- `telemetry.received` — a telemetry batch was accepted.\n"
        "- `telemetry.validation_failed` — a batch was rejected by validation.\n"
        "- `helmet.online` / `helmet.offline` — presence transitions.\n"
        "- `ml.ppe_detection` — a PPE detection result.\n"
        "- `ml.result` — generic ML result (fall detection, etc.)."
    ),
)
async def list_events(
    store: EventStoreDep,
    helmet_id: HelmetId | None = None,
    event_type: EventType | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    events = await store.query(
        helmet_id=helmet_id, event_type=event_type, since=since, limit=limit
    )
    return [event.model_dump(mode="json") for event in events]


@router.get(
    "/helmets/{helmet_id}/events",
    summary="Query one helmet's recent event history.",
    description=(
        "Same as `GET /events` but scoped to a single helmet. "
        "Accepts the same `event_type`, `since`, and `limit` filters."
    ),
)
async def list_helmet_events(
    helmet_id: HelmetId,
    store: EventStoreDep,
    event_type: EventType | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    events = await store.query(
        helmet_id=helmet_id, event_type=event_type, since=since, limit=limit
    )
    return [event.model_dump(mode="json") for event in events]
