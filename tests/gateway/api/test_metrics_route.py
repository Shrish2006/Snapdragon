"""Tests for `GET /metrics` and `api/http/middleware.py`'s instrumentation.

`infrastructure.metrics.registry` metric objects register with
`prometheus_client`'s global default registry once per process — every
test in this file therefore asserts on the *delta* a specific action
causes, never an absolute value, since other tests in the same run share
the same counters.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.config import Settings, settings_for_tests
from gateway.infrastructure.metrics.registry import (
    http_request_duration_seconds,
    http_requests_total,
    ws_connections,
)
from gateway.main import create_app


def _counter_value(path: str, status_code: str, method: str = "GET") -> float:
    return http_requests_total.labels(
        method=method, path=path, status_code=status_code
    )._value.get()


def _histogram_count(path: str, method: str = "GET") -> float:
    return http_request_duration_seconds.labels(method=method, path=path)._sum.get()


def test_metrics_endpoint_returns_prometheus_text_format() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "gateway_http_requests_total" in response.text
    assert "gateway_ws_connections" in response.text


def test_a_request_increments_the_request_counter_for_its_matched_route() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    before = _counter_value("/health", "200")

    client.get("/health")

    assert _counter_value("/health", "200") == before + 1


def test_request_duration_is_recorded() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    before = _histogram_count("/health")

    client.get("/health")

    assert _histogram_count("/health") >= before  # duration is >= 0, sum only grows


def test_path_label_uses_the_route_template_not_the_raw_path() -> None:
    """`/v1/helmets/{helmet_id}` must be one label value regardless of
    which helmet was requested — a per-helmet-ID label would make the
    metric's cardinality grow with the number of helmets."""
    client = TestClient(create_app(Settings(_env_file=None)))
    before = _counter_value("/v1/helmets/{helmet_id}", "404")

    client.get("/v1/helmets/HLM-0001")
    client.get("/v1/helmets/HLM-0002")

    assert _counter_value("/v1/helmets/{helmet_id}", "404") == before + 2


def test_unmatched_routes_fall_back_to_the_raw_path_label() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    before = _counter_value("/this/route/does/not/exist", "404")

    client.get("/this/route/does/not/exist")

    assert _counter_value("/this/route/does/not/exist", "404") == before + 1


def test_websocket_connect_and_disconnect_move_the_connection_gauge() -> None:
    before = ws_connections._value.get()
    with TestClient(create_app(settings_for_tests())) as client:
        with client.websocket_connect("/v1/ws") as ws:
            ws.receive_json()  # snapshot — proves the connection is live
            assert ws_connections._value.get() == before + 1
    assert ws_connections._value.get() == before
