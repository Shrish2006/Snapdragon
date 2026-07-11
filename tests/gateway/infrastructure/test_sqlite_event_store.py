"""Tests for `gateway.infrastructure.persistence.sqlite.SQLiteEventStore`."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from gateway.domain.events.models import TelemetryReceivedEvent
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.infrastructure.persistence.sqlite import SQLiteEventStore

T0 = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _event(helmet_id: str = "HLM-0007", occurred_at: datetime = T0) -> TelemetryReceivedEvent:
    batch = TelemetryBatch(
        helmet_id=helmet_id,
        sequence=1,
        sent_at=occurred_at,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0, accel_y_g=0.0, accel_z_g=1.0,
                    accel_magnitude_g=1.0, gyro_x_dps=0.0, gyro_y_dps=0.0, gyro_z_dps=0.0,
                ),
                captured_at=occurred_at,
            )
        ],
    )
    return TelemetryReceivedEvent(
        helmet_id=helmet_id, source="test", payload=batch, occurred_at=occurred_at
    )


async def test_append_then_query_round_trips_the_typed_event(tmp_path: Path) -> None:
    store = SQLiteEventStore(str(tmp_path / "events.db"))
    await store.initialize()
    event = _event()

    await store.append(event)
    results = await store.query(limit=10)

    assert results == [event]


async def test_query_filters_by_helmet_id(tmp_path: Path) -> None:
    store = SQLiteEventStore(str(tmp_path / "events.db"))
    await store.initialize()
    await store.append(_event("HLM-0001"))
    await store.append(_event("HLM-0002"))

    results = await store.query(helmet_id="HLM-0002", limit=10)
    assert [e.helmet_id for e in results] == ["HLM-0002"]


async def test_query_orders_newest_first_and_respects_limit(tmp_path: Path) -> None:
    store = SQLiteEventStore(str(tmp_path / "events.db"))
    await store.initialize()
    for i in range(5):
        await store.append(_event(occurred_at=T0 + timedelta(minutes=i)))

    results = await store.query(limit=2)
    assert len(results) == 2
    assert results[0].occurred_at > results[1].occurred_at


async def test_events_survive_a_fresh_store_instance_against_the_same_file(tmp_path: Path) -> None:
    """Proves durability across restarts — the actual point of this
    adapter over `InMemoryEventStore`."""
    path = str(tmp_path / "events.db")
    first_process_store = SQLiteEventStore(path)
    await first_process_store.initialize()
    await first_process_store.append(_event())

    second_process_store = SQLiteEventStore(path)
    await second_process_store.initialize()  # idempotent: CREATE TABLE IF NOT EXISTS
    results = await second_process_store.query(limit=10)

    assert len(results) == 1
    assert results[0].helmet_id == "HLM-0007"
