"""Tests for `gateway.application.ingestion_service.IngestionService`."""

from datetime import datetime, timedelta, timezone
from typing import Any

from gateway.application.device_state_manager import DeviceStateManager
from gateway.application.ingestion_service import IngestionService
from gateway.domain.events.models import (
    DomainEvent,
    TelemetryReceivedEvent,
    ValidationFailedEvent,
)
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.infrastructure.registry.in_memory import InMemoryHelmetRepository

T0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent[Any]] = []

    async def publish(self, event: DomainEvent[Any]) -> None:
        self.events.append(event)


def _batch(sequence: int, sent_at: datetime = T0) -> TelemetryBatch:
    return TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=sequence,
        sent_at=sent_at,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0, accel_y_g=0.0, accel_z_g=1.0,
                    accel_magnitude_g=1.0, gyro_x_dps=0.0, gyro_y_dps=0.0, gyro_z_dps=0.0,
                ),
                captured_at=sent_at,
            )
        ],
    )


def _service() -> tuple[IngestionService, _RecordingPublisher, InMemoryHelmetRepository]:
    repo = InMemoryHelmetRepository()
    publisher = _RecordingPublisher()
    # `clock=lambda: T0` pins "now" so clock-skew assertions are
    # deterministic and never race real wall-clock time.
    service = IngestionService(
        DeviceStateManager(repo),
        publisher,
        max_clock_skew=timedelta(seconds=30),
        clock=lambda: T0,
    )
    return service, publisher, repo


async def test_valid_batch_is_accepted_updates_state_and_publishes_event() -> None:
    service, publisher, repo = _service()

    result = await service.ingest(_batch(1, sent_at=T0))

    assert result.accepted
    assert result.issues == ()
    assert result.state is not None
    assert result.state.last_sequence == 1
    assert (await repo.get("HLM-0007")) == result.state

    assert len(publisher.events) == 1
    assert isinstance(publisher.events[0], TelemetryReceivedEvent)
    assert publisher.events[0].helmet_id == "HLM-0007"


async def test_second_batch_must_have_a_higher_sequence() -> None:
    service, publisher, _repo = _service()
    await service.ingest(_batch(5, sent_at=T0))

    result = await service.ingest(_batch(5, sent_at=T0))  # duplicate sequence

    assert not result.accepted
    assert result.state is None
    assert any(issue.field == "sequence" for issue in result.issues)

    # one TelemetryReceivedEvent for the accepted batch, one
    # ValidationFailedEvent for the rejected one
    assert len(publisher.events) == 2
    rejection = publisher.events[1]
    assert isinstance(rejection, ValidationFailedEvent)
    assert rejection.helmet_id == "HLM-0007"
    assert rejection.payload.sequence == 5
    assert any(issue.field == "sequence" for issue in rejection.payload.issues)


async def test_rejected_batch_does_not_mutate_helmet_state() -> None:
    service, _publisher, repo = _service()
    await service.ingest(_batch(1, sent_at=T0))
    state_before = await repo.get("HLM-0007")

    await service.ingest(_batch(1, sent_at=T0))  # non-monotonic, rejected

    assert await repo.get("HLM-0007") == state_before


async def test_batch_with_excessive_clock_skew_is_rejected() -> None:
    service, publisher, _repo = _service()
    stale_sent_at = T0 - timedelta(hours=1)

    result = await service.ingest(_batch(1, sent_at=stale_sent_at))

    assert not result.accepted
    assert any(issue.field == "sent_at" for issue in result.issues)

    assert len(publisher.events) == 1
    assert isinstance(publisher.events[0], ValidationFailedEvent)
    assert any(issue.field == "sent_at" for issue in publisher.events[0].payload.issues)
