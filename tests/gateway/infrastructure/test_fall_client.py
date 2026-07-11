"""Tests for `gateway.infrastructure.ml_clients.fall_client.FallDetectionHttpClient`."""

import httpx

from gateway.application.ports import ServiceHealth
from gateway.infrastructure.ml_clients.fall_client import FallDetectionHttpClient


def _client(handler) -> FallDetectionHttpClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FallDetectionHttpClient(base_url="http://fall-detection:8000", http_client=http_client)


async def test_health_reflects_the_real_fall_detection_health_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    assert await _client(handler).health() == ServiceHealth.OK


async def test_health_reports_unreachable_on_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    assert await _client(handler).health() == ServiceHealth.UNREACHABLE


def test_client_has_no_inference_method() -> None:
    """`ai_ml/fall_detection` has no `/detect`-equivalent endpoint yet —
    this adapter must not pretend one exists."""
    client = _client(lambda request: httpx.Response(200))
    assert not hasattr(client, "detect")
