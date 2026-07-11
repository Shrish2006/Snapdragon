"""The canonical event envelope published on the event bus (Phase 4) and
fanned out over WebSocket (Phase 5).

`DomainEvent` is generic over its payload type so every concrete event
(`TelemetryReceivedEvent`, `PPEDetectionEvent`, `MLResultEvent`,
`ValidationFailedEvent`) gets envelope fields (id, severity, timing,
correlation) for free while its `payload` is concretely typed — consumers
never downcast from `dict`, and a wrong payload type is a
`pydantic.ValidationError` at construction, not a runtime `KeyError` three
services downstream.

`EVENT_TYPE_REGISTRY` maps `EventType -> concrete DomainEvent subclass`,
used by any adapter that has to reconstruct a typed event from a stored/
wire representation (`infrastructure/persistence/sqlite.py`,
`infrastructure/bus/redis_streams.py`) — a JSON blob alone doesn't carry
enough information to know which `DomainEvent[...]` subclass to parse it
as; this registry is the single place that mapping is declared. Adding a
new concrete event type means adding one entry here too.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.detection.models import MLServiceResult, PPEDetectionResult
from gateway.domain.events.types import EventType, Severity
from gateway.domain.telemetry.models import TelemetryBatch
from gateway.domain.telemetry.validation import ValidationIssue

TPayload = TypeVar("TPayload", bound=BaseModel)


class DomainEvent(BaseModel, Generic[TPayload]):
    """`event.v1` envelope. Concrete event classes below parametrize
    `TPayload` and pin `type`; nothing else needs to redeclare envelope
    fields.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "event.v1"
    event_id: UUID = Field(default_factory=uuid4)
    type: EventType
    severity: Severity = Severity.INFO
    helmet_id: HelmetId | None = None
    """`None` for events not scoped to a single helmet (e.g. a future
    system-level event); every telemetry/detection event today sets it."""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    """Producer identity, e.g. `"gateway.ingest"`, `"ppe-detection"`."""
    payload: TPayload
    correlation_id: UUID | None = None
    """Links a derived event (e.g. a future risk-score event) back to the
    event that triggered it."""


class TelemetryReceivedEvent(DomainEvent[TelemetryBatch]):
    """Published for every `TelemetryBatch` accepted by the ingestion
    layer (Phase 2)."""

    type: EventType = EventType.TELEMETRY_RECEIVED


class PPEDetectionEvent(DomainEvent[PPEDetectionResult]):
    """Published for every `PPEDetectionResult` received from the
    ppe-detection service (Phase 3)."""

    type: EventType = EventType.PPE_DETECTION


class MLResultEvent(DomainEvent[MLServiceResult]):
    """Published for any ML service output without a typed event of its
    own yet — today, fall-detection (Phase 3)."""

    type: EventType = EventType.ML_RESULT


class ValidationFailure(BaseModel):
    """Payload for `ValidationFailedEvent`: the batch that was rejected
    and why, per `domain.telemetry.validation.validate_batch`."""

    model_config = ConfigDict(frozen=True)

    helmet_id: HelmetId
    sequence: int
    issues: list[ValidationIssue]


class ValidationFailedEvent(DomainEvent[ValidationFailure]):
    """Published when `domain.telemetry.validation` rejects a batch
    (Phase 4's processing pipeline; publishing wired in
    `application.ingestion_service.IngestionService`)."""

    type: EventType = EventType.VALIDATION_FAILED
    severity: Severity = Severity.WARNING


EVENT_TYPE_REGISTRY: dict[EventType, type[DomainEvent[Any]]] = {
    EventType.TELEMETRY_RECEIVED: TelemetryReceivedEvent,
    EventType.VALIDATION_FAILED: ValidationFailedEvent,
    EventType.PPE_DETECTION: PPEDetectionEvent,
    EventType.ML_RESULT: MLResultEvent,
}
"""`EventType.HELMET_ONLINE`/`HELMET_OFFLINE` are intentionally absent —
no concrete `DomainEvent` subclass publishes them yet (device-registry
presence transitions aren't wired onto the bus in this phase); add them
here when they are."""
