"""Tests for `gateway.infrastructure.ml_clients.ppe_client.PPEDetectionHttpClient`.

Uses `httpx.MockTransport` — no real ppe-detection service is contacted.
"""

import httpx
import pytest

from gateway.application.ports import ServiceHealth
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)
from gateway.infrastructure.ml_clients.ppe_client import PPEDetectionHttpClient

REAL_DETECTION_BODY = {
    "detections": [
        {"class_name": "helmet", "confidence": 0.9, "bbox": [1.0, 2.0, 3.0, 4.0], "tracker_id": 1},
    ]
}


def _client(handler) -> PPEDetectionHttpClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PPEDetectionHttpClient(base_url="http://ppe-detection:8000", http_client=http_client)


async def test_detect_parses_a_successful_response_matching_the_real_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/detect"
        assert request.method == "POST"
        return httpx.Response(200, json=REAL_DETECTION_BODY)

    result = await _client(handler).detect(
        b"jpeg-bytes", filename="f.jpg", content_type="image/jpeg"
    )
    assert len(result.detections) == 1
    assert result.detections[0].class_name == "helmet"
    assert result.detections[0].tracker_id == 1


async def test_detect_raises_response_error_on_upstream_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model not loaded")

    with pytest.raises(MLServiceResponseError) as exc_info:
        await _client(handler).detect(b"x", filename="f.jpg", content_type="image/jpeg")
    assert exc_info.value.status_code == 500
    assert exc_info.value.service == "ppe-detection"


async def test_detect_raises_response_error_on_malformed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(MLServiceResponseError):
        await _client(handler).detect(b"x", filename="f.jpg", content_type="image/jpeg")


async def test_detect_raises_unavailable_error_on_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(MLServiceUnavailableError) as exc_info:
        await _client(handler).detect(b"x", filename="f.jpg", content_type="image/jpeg")
    assert exc_info.value.service == "ppe-detection"


async def test_health_reports_ok_degraded_and_unreachable() -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    def degraded_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unavailable"})

    def unreachable_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    assert await _client(ok_handler).health() == ServiceHealth.OK
    assert await _client(degraded_handler).health() == ServiceHealth.DEGRADED
    assert await _client(unreachable_handler).health() == ServiceHealth.UNREACHABLE
