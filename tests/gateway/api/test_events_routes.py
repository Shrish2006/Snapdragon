"""Tests for the live dashboard event-history APIs:
`GET /v1/events`, `GET /v1/helmets/{id}/events`.

Persistence happens via the background processing pipeline (Phase 4), so
these poll briefly instead of asserting immediately after ingestion.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from gateway.config import settings_for_tests
from gateway.main import create_app


def _valid_batch(helmet_id: str = "HLM-0007", sequence: int = 1) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "helmet_id": helmet_id,
        "sequence": sequence,
        "sent_at": now,
        "readings": [
            {
                "value": {
                    "kind": "imu",
                    "accel_x_g": 0.01, "accel_y_g": -0.02, "accel_z_g": 1.0,
                    "accel_magnitude_g": 1.0002,
                    "gyro_x_dps": 0.5, "gyro_y_dps": -0.5, "gyro_z_dps": 0.0,
                },
                "captured_at": now,
            }
        ],
    }


def _poll(client: TestClient, path: str, *, params: dict | None = None, attempts: int = 50) -> list:
    for _ in range(attempts):
        body = client.get(path, params=params or {}).json()
        if body:
            return body
        time.sleep(0.02)
    return []


def test_get_events_returns_a_persisted_event_after_ingestion() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        response = client.post("/v1/telemetry", json=_valid_batch())
        assert response.status_code == 202

        events = _poll(client, "/v1/events", params={"event_type": "telemetry.received"})
        assert len(events) == 1
        assert events[0]["type"] == "telemetry.received"
        assert events[0]["helmet_id"] == "HLM-0007"


def test_get_events_filters_by_event_type_that_never_occurred() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        client.post("/v1/telemetry", json=_valid_batch())
        # let ingestion's own event settle before asserting absence
        _poll(client, "/v1/events", params={"event_type": "telemetry.received"})

        response = client.get("/v1/events", params={"event_type": "ml.ppe_detection"})
        assert response.status_code == 200
        assert response.json() == []


def test_get_helmet_events_scopes_to_one_helmet() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        client.post("/v1/telemetry", json=_valid_batch(helmet_id="HLM-0001"))
        client.post("/v1/telemetry", json=_valid_batch(helmet_id="HLM-0002"))

        events = _poll(client, "/v1/helmets/HLM-0001/events")
        assert len(events) == 1
        assert events[0]["helmet_id"] == "HLM-0001"


def test_get_events_with_no_history_returns_an_empty_list() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        response = client.get("/v1/events")
        assert response.status_code == 200
        assert response.json() == []
