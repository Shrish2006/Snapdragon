"""End-to-end tests for `GET /v1/ws` — real app, real lifespan (background
`SubscriptionManager.run()` task included), real WebSocket round trip via
`TestClient.websocket_connect`.
"""

from __future__ import annotations

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


def test_connecting_receives_a_snapshot_first() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        with client.websocket_connect("/v1/ws") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"
            assert snapshot["helmets"] == []


def test_snapshot_reflects_helmets_already_known_at_connect_time() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        client.post("/v1/telemetry", json=_valid_batch())

        with client.websocket_connect("/v1/ws") as ws:
            snapshot = ws.receive_json()
            assert [h["helmet_id"] for h in snapshot["helmets"]] == ["HLM-0007"]


def test_accepted_telemetry_streams_a_matching_event_to_a_connected_client() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        with client.websocket_connect("/v1/ws") as ws:
            ws.receive_json()  # snapshot

            client.post("/v1/telemetry", json=_valid_batch())

            message = ws.receive_json()
            assert message["type"] == "event"
            assert message["event"]["type"] == "telemetry.received"
            assert message["event"]["helmet_id"] == "HLM-0007"


def test_subscribe_message_narrows_the_filter_to_one_helmet() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        with client.websocket_connect("/v1/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"action": "subscribe", "filter": {"helmet_id": "HLM-ONLY"}})

            client.post("/v1/telemetry", json=_valid_batch(helmet_id="HLM-OTHER", sequence=1))
            client.post("/v1/telemetry", json=_valid_batch(helmet_id="HLM-ONLY", sequence=1))

            message = ws.receive_json()
            assert message["type"] == "event"
            assert message["event"]["helmet_id"] == "HLM-ONLY"


def test_malformed_subscribe_message_gets_an_error_reply_not_a_dropped_connection() -> None:
    with TestClient(create_app(settings_for_tests())) as client:
        with client.websocket_connect("/v1/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_text("not json at all")

            reply = ws.receive_json()
            assert reply["type"] == "error"

            # connection still works afterward
            client.post("/v1/telemetry", json=_valid_batch())
            message = ws.receive_json()
            assert message["type"] == "event"
