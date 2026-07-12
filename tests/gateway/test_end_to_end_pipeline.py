"""End-to-end proof of Phase 4's wiring: a real HTTP request, through the
real app with its real `lifespan` (background pipeline task included, not
mocked), lands a persisted event — exercising `main.py`'s lifespan wiring,
not just `bootstrap.py`'s container construction (see `test_bootstrap.py`
for that narrower check).

Uses `httpx.ASGITransport` + `app.router.lifespan_context` instead of
`TestClient` specifically so the background `processing_pipeline.run()`
task actually starts — a plain `TestClient(app)` without entering it as a
context manager does not run ASGI lifespan events.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

import httpx

from gateway.config import settings_for_tests
from gateway.domain.events.types import EventType
from gateway.main import create_app


def _valid_batch(sequence: int = 1) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "helmet_id": "HLM-0007",
        "sequence": sequence,
        "sent_at": now,
        "readings": [
            {
                "value": {
                    "kind": "imu",
                    "accel_x_g": 0.01,
                    "accel_y_g": -0.02,
                    "accel_z_g": 1.0,
                    "accel_magnitude_g": 1.0002,
                    "gyro_x_dps": 0.5,
                    "gyro_y_dps": -0.5,
                    "gyro_z_dps": 0.0,
                },
                "captured_at": now,
            }
        ],
    }


async def _poll(coro_factory, predicate, *, attempts: int = 50, delay: float = 0.02):
    for _ in range(attempts):
        result = await coro_factory()
        if predicate(result):
            return result
        await asyncio.sleep(delay)
    return None


async def test_accepted_telemetry_is_persisted_via_the_real_background_pipeline() -> (
    None
):
    app = create_app(settings_for_tests())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post("/v1/telemetry", json=_valid_batch(sequence=1))
            assert response.status_code == 202

            store = app.state.container.event_store
            events = await _poll(
                lambda: store.query(event_type=EventType.TELEMETRY_RECEIVED, limit=10),
                lambda events: len(events) == 1,
            )

    assert events is not None
    assert events[0].helmet_id == "HLM-0007"
    assert events[0].payload.sequence == 1


async def test_rejected_telemetry_persists_a_validation_failed_event() -> None:
    app = create_app(settings_for_tests())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            batch = _valid_batch(sequence=1)
            await client.post("/v1/telemetry", json=batch)
            rejected = await client.post(
                "/v1/telemetry", json=batch
            )  # duplicate sequence
            assert rejected.status_code == 422

            store = app.state.container.event_store
            events = await _poll(
                lambda: store.query(event_type=EventType.VALIDATION_FAILED, limit=10),
                lambda events: len(events) == 1,
            )

    assert events is not None
    assert events[0].payload.issues[0].field == "sequence"


async def test_mqtt_ingestion_path_uses_the_same_pipeline_as_http() -> None:
    """MQTT adapter calls the same IngestionService → EventBus → Persistence
    pipeline as the HTTP route.

    Bypasses the broker by calling `_handle()` directly on the adapter —
    the broker connection is not under test here; the ingestion pipeline is.
    """
    from gateway.infrastructure.mqtt.adapter import MqttIngestionAdapter

    app = create_app(settings_for_tests())
    async with app.router.lifespan_context(app):
        container = app.state.container
        # Yield to the event loop so the background pipeline task can run
        # and subscribe to the event bus before we publish.  The HTTP test
        # gets this for free via FastAPI's multi-await request processing;
        # a direct _handle() call needs the explicit yield.
        await asyncio.sleep(0)
        adapter = MqttIngestionAdapter(
            container.ingestion_service,
            broker_host="localhost",  # not connected — _handle skips the broker
        )

        batch = _valid_batch(sequence=1)
        message = MagicMock()
        message.topic = f"safeguard/telemetry/{batch['helmet_id']}"
        message.payload = json.dumps(batch).encode()

        await adapter._handle(message)

        store = container.event_store
        events = await _poll(
            lambda: store.query(event_type=EventType.TELEMETRY_RECEIVED, limit=10),
            lambda evts: len(evts) == 1,
        )

    assert events is not None
    assert events[0].helmet_id == "HLM-0007"
    assert events[0].payload.sequence == 1
