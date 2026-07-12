"""Unit tests for `gateway.infrastructure.mqtt.adapter.MqttIngestionAdapter`.

Tests exercise `_handle()` directly — no MQTT broker required.  The broker
and `aiomqtt.Client` are bypassed entirely; only the adapter's business-logic
layer (topic parse → payload parse → cross-check → ingest call) is under
test, which is the layer that can actually contain bugs.

`IngestionService` is replaced with an `AsyncMock` so assertions are purely
about whether and how `ingest()` was called.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.application.ingestion_service import IngestResult
from gateway.infrastructure.mqtt.adapter import MqttIngestionAdapter


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_service() -> AsyncMock:
    service = AsyncMock()
    service.ingest.return_value = IngestResult(accepted=True)
    return service


@pytest.fixture()
def adapter(mock_service: AsyncMock) -> MqttIngestionAdapter:
    return MqttIngestionAdapter(
        mock_service,
        broker_host="localhost",
        broker_port=1883,
        username="gateway",
        password="test",
        topic_prefix="safeguard",
    )


def _make_message(topic: str, payload: str | bytes) -> MagicMock:
    """Minimal aiomqtt.Message stub — only `.topic` and `.payload` needed."""
    msg = MagicMock()
    msg.topic = topic
    msg.payload = payload if isinstance(payload, bytes) else payload.encode()
    return msg


def _valid_payload(helmet_id: str = "h1", sequence: int = 1) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return json.dumps({
        "helmet_id": helmet_id,
        "sequence": sequence,
        "sent_at": now,
        "readings": [
            {
                "captured_at": now,
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
            }
        ],
    })


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_valid_message_calls_ingest_with_correct_batch(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    await adapter._handle(
        _make_message("safeguard/telemetry/h1", _valid_payload("h1", sequence=5))
    )

    mock_service.ingest.assert_awaited_once()
    batch = mock_service.ingest.call_args[0][0]
    assert batch.helmet_id == "h1"
    assert batch.sequence == 5
    assert len(batch.readings) == 1


async def test_ingest_called_once_per_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    for seq in range(1, 4):
        # Reset accepted state (IngestionService would normally reject dups,
        # but the mock always returns accepted=True)
        await adapter._handle(
            _make_message("safeguard/telemetry/h1", _valid_payload("h1", sequence=seq))
        )

    assert mock_service.ingest.await_count == 3


# ── Rejection logging (ingest still called) ───────────────────────────────────

async def test_rejected_batch_does_not_raise(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    mock_service.ingest.return_value = IngestResult(accepted=False)
    # Should log a warning but not raise
    await adapter._handle(
        _make_message("safeguard/telemetry/h1", _valid_payload("h1"))
    )
    mock_service.ingest.assert_awaited_once()


# ── Drop conditions (ingest NOT called) ───────────────────────────────────────

async def test_mismatched_helmet_id_drops_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    """Topic says h2 but payload says h1 — cross-check fails."""
    await adapter._handle(
        _make_message("safeguard/telemetry/h2", _valid_payload("h1"))
    )
    mock_service.ingest.assert_not_called()


async def test_malformed_json_drops_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    await adapter._handle(
        _make_message("safeguard/telemetry/h1", b"not valid json")
    )
    mock_service.ingest.assert_not_called()


async def test_invalid_helmet_id_in_topic_drops_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    """Topic segment starts with special char — parse_helmet_id raises."""
    await adapter._handle(
        _make_message("safeguard/telemetry/$bad", _valid_payload("$bad"))
    )
    mock_service.ingest.assert_not_called()


async def test_too_short_topic_drops_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    await adapter._handle(
        _make_message("safeguard/h1", _valid_payload("h1"))
    )
    mock_service.ingest.assert_not_called()


async def test_empty_payload_drops_message(
    adapter: MqttIngestionAdapter,
    mock_service: AsyncMock,
) -> None:
    await adapter._handle(_make_message("safeguard/telemetry/h1", b""))
    mock_service.ingest.assert_not_called()
