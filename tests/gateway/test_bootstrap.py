"""Tests for `gateway.bootstrap.build_container` — proves `Settings`
backend selection actually wires the intended adapter, not just that
`build_container` doesn't crash."""

import asyncio

from gateway.bootstrap import build_container
from gateway.config import settings_for_tests, Settings
from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent
from gateway.infrastructure.bus.in_memory import InMemoryEventBus
from gateway.infrastructure.bus.redis_streams import RedisStreamsEventBus
from gateway.infrastructure.persistence.in_memory import InMemoryEventStore
from gateway.infrastructure.persistence.sqlite import SQLiteEventStore


def test_default_settings_wire_in_memory_backends() -> None:
    container = build_container(settings_for_tests())
    assert isinstance(container.event_bus, InMemoryEventBus)
    assert isinstance(container.event_store, InMemoryEventStore)


def test_redis_backend_selection_wires_redis_streams_event_bus() -> None:
    # `Redis.from_url(...)` is lazy — redis-py opens no connection until
    # the first command, so this is safe to construct without a server.
    container = build_container(
        Settings(_env_file=None, event_bus_backend="redis", redis_url="redis://localhost:6379/0")
    )
    assert isinstance(container.event_bus, RedisStreamsEventBus)


def test_sqlite_backend_selection_wires_sqlite_event_store(tmp_path) -> None:
    container = build_container(
        Settings(
            _env_file=None,
            event_store_backend="sqlite",
            sqlite_path=str(tmp_path / "events.db"),
        )
    )
    assert isinstance(container.event_store, SQLiteEventStore)


async def test_container_pipeline_persists_a_published_event_end_to_end() -> None:
    """Behavioral proof that the pipeline is actually wired to the
    persistence processor: publish through the container's real event
    bus, run the pipeline briefly, confirm the event landed in the
    container's real event store."""
    container = build_container(settings_for_tests())
    event = PPEDetectionEvent(source="test", payload=PPEDetectionResult(detections=[]))


    task = asyncio.create_task(container.processing_pipeline.run())
    await asyncio.sleep(0)  # let the pipeline subscribe before publishing
    await container.event_bus.publish(event)
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    stored = await container.event_store.query(limit=10)
    assert stored == [event]
