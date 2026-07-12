"""Telemetry ingestion use-case: the single entry point every transport
calls to submit a `TelemetryBatch`.

Transport-agnostic by design — `IngestionService.ingest()` takes and
returns plain domain/application types, with no HTTP/FastAPI/MQTT concept
anywhere in this module. `api/http/telemetry.py` is the concrete Phase 2
transport (HTTP, the only transport this codebase has any supporting
infrastructure for); adding a second one later (e.g. an MQTT subscriber
once firmware gains networking) means adding a new caller of this class,
not changing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from gateway.application.device_state_manager import DeviceStateManager
from gateway.application.ports import EventPublisher
from gateway.domain.events.models import (
    TelemetryReceivedEvent,
    ValidationFailedEvent,
    ValidationFailure,
)
from gateway.domain.helmets.models import HelmetState
from gateway.domain.telemetry.models import TelemetryBatch
from gateway.domain.telemetry.validation import ValidationIssue, validate_batch


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of one `ingest()` call — the transport layer maps this to
    an HTTP status/body (or an MQTT ack/nack, in the future)."""

    accepted: bool
    state: HelmetState | None = None
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)


class IngestionService:
    def __init__(
        self,
        state_manager: DeviceStateManager,
        event_publisher: EventPublisher,
        *,
        max_clock_skew: timedelta,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._state_manager = state_manager
        self._event_publisher = event_publisher
        self._max_clock_skew = max_clock_skew
        self._clock = clock
        # Injectable so tests can pin "now" instead of racing wall-clock
        # time when asserting clock-skew behavior; production uses real
        # UTC time via the default.

    async def ingest(self, batch: TelemetryBatch) -> IngestResult:
        previous_sequence = await self._state_manager.previous_sequence(batch.helmet_id)
        validation = validate_batch(
            batch,
            previous_sequence=previous_sequence,
            max_clock_skew=self._max_clock_skew,
            now=self._clock(),
        )
        if not validation.is_valid:
            # State is never mutated for a rejected batch; only presence
            # (`DeviceStateManager.apply_batch`) reflects accepted data.
            await self._event_publisher.publish(
                ValidationFailedEvent(
                    helmet_id=batch.helmet_id,
                    source="gateway.ingest",
                    payload=ValidationFailure(
                        helmet_id=batch.helmet_id,
                        sequence=batch.sequence,
                        issues=list(validation.issues),
                    ),
                )
            )
            return IngestResult(accepted=False, issues=validation.issues)

        state = await self._state_manager.apply_batch(batch)
        await self._event_publisher.publish(
            TelemetryReceivedEvent(
                helmet_id=batch.helmet_id,
                source="gateway.ingest",
                payload=batch,
            )
        )
        return IngestResult(accepted=True, state=state)
