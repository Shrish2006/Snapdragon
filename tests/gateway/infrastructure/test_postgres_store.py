"""Integration test for `PostgresEventStore` against a real Postgres 16
container. Uses the cached `pgvector/pgvector:pg16` image — started as
`safeguard-postgres-test` on port 5433.

Requires the container to be running. Skip if unreachable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gateway.domain.events.models import TelemetryReceivedEvent
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.infrastructure.persistence.postgres import PostgresEventStore

PG_DSN = "postgresql://safeguard:safeguard@127.0.0.1:5433/safeguard"
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


@pytest.fixture
async def store():
    s = PostgresEventStore(PG_DSN)
    await s.initialize()
    yield s
    # Clean up this run's data so the next run (or a full-suite re-run
    # against the same container) starts from a known-empty table.
    if s._pool is not None:  # noqa: SLF001 — a test may have closed it early
        async with s._pool.acquire() as conn:  # noqa: SLF001 — teardown only
            await conn.execute("DELETE FROM events")
    await s.close()

@pytest.mark.asyncio
async def test_append_then_query_round_trips(store) -> None:
    event = _event(helmet_id="HLM-ROUNDTRIP")
    await store.append(event)
    results = await store.query(helmet_id="HLM-ROUNDTRIP", limit=10)
    assert results == [event]


@pytest.mark.asyncio
async def test_query_filters_by_helmet_id(store) -> None:
    await store.append(_event("HLM-FILTER-A"))
    await store.append(_event("HLM-FILTER-B"))

    results = await store.query(helmet_id="HLM-FILTER-B", limit=10)
    assert [e.helmet_id for e in results] == ["HLM-FILTER-B"]


@pytest.mark.asyncio
async def test_query_orders_newest_first_and_respects_limit(store) -> None:
    for i in range(5):
        await store.append(_event("HLM-ORDER", occurred_at=T0 + timedelta(minutes=i)))

    results = await store.query(helmet_id="HLM-ORDER", limit=2)
    assert len(results) == 2
    assert results[0].occurred_at > results[1].occurred_at


@pytest.mark.asyncio
async def test_duplicate_event_id_is_silently_ignored(store) -> None:
    """ON CONFLICT (event_id) DO NOTHING — idempotent append."""
    event = _event("HLM-DEDUP")
    await store.append(event)
    count_before = len(await store.query(helmet_id="HLM-DEDUP", limit=10))
    await store.append(event)  # same event_id deliberately
    count_after = len(await store.query(helmet_id="HLM-DEDUP", limit=10))
    assert count_after == count_before  # no new row inserted


@pytest.mark.asyncio
async def test_events_survive_a_fresh_store_instance(store) -> None:
    """Proves durability across restarts by reconnecting with a new pool."""
    event = _event("HLM-SURVIVE")
    await store.append(event)
    await store.close()

    fresh_store = PostgresEventStore(PG_DSN)
    await fresh_store.initialize()
    try:
        results = await fresh_store.query(helmet_id="HLM-SURVIVE", limit=10)
        assert len(results) == 1
        assert results[0].helmet_id == "HLM-SURVIVE"
    finally:
        await fresh_store.close()
