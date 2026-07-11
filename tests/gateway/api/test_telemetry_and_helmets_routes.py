"""End-to-end HTTP tests: `POST /v1/telemetry` and `GET /v1/helmets*`.

The composition root wires `IngestionService` with the real wall-clock
(`gateway.bootstrap.build_container` does not inject a fixed clock — only
unit tests of `IngestionService` itself do that, see
`tests/gateway/application/test_ingestion_service.py`). So every payload's
`sent_at`/`captured_at` here is generated at test-run time, never
hardcoded, or the default `telemetry_max_clock_skew_seconds` window would
make these tests flaky against real time.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from gateway.config import settings_for_tests
from gateway.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(settings_for_tests()))


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


def test_post_telemetry_accepts_a_valid_batch_and_returns_202() -> None:
    client = _client()
    response = client.post("/v1/telemetry", json=_valid_batch())
    assert response.status_code == 202
    body = response.json()
    assert body == {
        "accepted": True,
        "helmet_id": "HLM-0007",
        "sequence": 1,
        "status": "online",
    }


def test_post_telemetry_rejects_malformed_body_with_422() -> None:
    client = _client()
    response = client.post("/v1/telemetry", json={"helmet_id": "HLM-0007"})
    assert response.status_code == 422


def test_post_telemetry_rejects_non_monotonic_sequence_with_422_and_issues() -> None:
    client = _client()
    batch = _valid_batch(sequence=1)
    first = client.post("/v1/telemetry", json=batch)
    assert first.status_code == 202

    second = client.post("/v1/telemetry", json=batch)  # same sequence again
    assert second.status_code == 422
    body = second.json()
    assert body["accepted"] is False
    assert any(issue["field"] == "sequence" for issue in body["issues"])


def test_get_helmets_lists_helmets_seen_via_ingestion() -> None:
    client = _client()
    client.post("/v1/telemetry", json=_valid_batch())

    response = client.get("/v1/helmets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["helmet_id"] == "HLM-0007"
    assert body[0]["status"] == "online"


def test_get_helmet_by_id_returns_its_current_state() -> None:
    client = _client()
    client.post("/v1/telemetry", json=_valid_batch())

    response = client.get("/v1/helmets/HLM-0007")
    assert response.status_code == 200
    body = response.json()
    assert body["last_sequence"] == 1
    assert "imu" in body["latest_readings"]


def test_get_unknown_helmet_returns_404() -> None:
    client = _client()
    response = client.get("/v1/helmets/HLM-9999")
    assert response.status_code == 404
