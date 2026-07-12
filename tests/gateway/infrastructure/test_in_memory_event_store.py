"""Tests for `gateway.infrastructure.persistence.in_memory.InMemoryEventStore`."""

from datetime import datetime, timedelta, timezone

from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent, TelemetryReceivedEvent
from gateway.domain.events.types import EventType
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.infrastructure.persistence.in_memory import InMemoryEventStore

T0 = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _telemetry_event(helmet_id: str, occurred_at: datetime) -> TelemetryReceivedEvent:
    batch = TelemetryBatch(
        helmet_id=helmet_id,
        sequence=1,
        sent_at=occurred_at,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0,
                    accel_y_g=0.0,
                    accel_z_g=1.0,
                    accel_magnitude_g=1.0,
                    gyro_x_dps=0.0,
                    gyro_y_dps=0.0,
                    gyro_z_dps=0.0,
                ),
                captured_at=occurred_at,
            )
        ],
    )
    return TelemetryReceivedEvent(
        helmet_id=helmet_id, source="test", payload=batch, occurred_at=occurred_at
    )


async def test_append_then_query_returns_it() -> None:
    store = InMemoryEventStore(max_size=200)
    event = _telemetry_event("HLM-0007", T0)
    await store.append(event)

    results = await store.query(limit=10)
    assert results == [event]


async def test_query_filters_by_helmet_id() -> None:
    store = InMemoryEventStore(max_size=200)
    await store.append(_telemetry_event("HLM-0001", T0))
    await store.append(_telemetry_event("HLM-0002", T0))

    results = await store.query(helmet_id="HLM-0002", limit=10)
    assert [e.helmet_id for e in results] == ["HLM-0002"]


async def test_query_filters_by_event_type() -> None:
    store = InMemoryEventStore(max_size=200)
    await store.append(_telemetry_event("HLM-0007", T0))
    await store.append(
        PPEDetectionEvent(source="test", payload=PPEDetectionResult(detections=[]))
    )

    results = await store.query(event_type=EventType.PPE_DETECTION, limit=10)
    assert len(results) == 1
    assert results[0].type is EventType.PPE_DETECTION


async def test_query_filters_by_since() -> None:
    store = InMemoryEventStore(max_size=200)
    old = _telemetry_event("HLM-0007", T0)
    recent = _telemetry_event("HLM-0007", T0 + timedelta(hours=1))
    await store.append(old)
    await store.append(recent)

    results = await store.query(since=T0 + timedelta(minutes=30), limit=10)
    assert results == [recent]


async def test_query_respects_limit_and_orders_newest_first() -> None:
    store = InMemoryEventStore(max_size=200)
    for i in range(5):
        await store.append(_telemetry_event("HLM-0007", T0 + timedelta(minutes=i)))

    results = await store.query(limit=2)
    assert len(results) == 2
    assert results[0].occurred_at > results[1].occurred_at


async def test_store_is_bounded_by_max_size() -> None:
    store = InMemoryEventStore(max_size=3)
    for i in range(5):
        await store.append(_telemetry_event("HLM-0007", T0 + timedelta(minutes=i)))

    results = await store.query(limit=10)
    assert len(results) == 3
    # the three most recently appended survive
    assert {e.occurred_at for e in results} == {
        T0 + timedelta(minutes=2),
        T0 + timedelta(minutes=3),
        T0 + timedelta(minutes=4),
    }
