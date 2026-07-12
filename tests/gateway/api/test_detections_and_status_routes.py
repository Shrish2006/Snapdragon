"""End-to-end HTTP tests for `/v1/detections/ppe` and `/v1/status`, using
FastAPI dependency overrides so no real ML service is contacted."""

from fastapi.testclient import TestClient

from gateway.api.http.deps import get_ppe_detection_service, get_service_health
from gateway.application.detection_service import DetectPPERequest, PPEDetectionService
from gateway.application.ports import ServiceHealth
from gateway.config import Settings
from gateway.domain.detection.models import PPEDetectionItem, PPEDetectionResult
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)
from gateway.main import create_app


class _FakePPEDetectionService:
    def __init__(self, result: PPEDetectionResult | Exception) -> None:
        self._result = result

    async def detect(self, request: DetectPPERequest) -> PPEDetectionResult:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeServiceHealth:
    def __init__(self, health: dict[str, ServiceHealth]) -> None:
        self._health = health

    async def check_all(self) -> dict[str, ServiceHealth]:
        return self._health


def _client_with_overrides(
    ppe_service: PPEDetectionService | _FakePPEDetectionService,
    service_health: _FakeServiceHealth,
) -> TestClient:
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ppe_detection_service] = lambda: ppe_service
    app.dependency_overrides[get_service_health] = lambda: service_health
    return TestClient(app)


def test_post_detect_ppe_returns_typed_detections() -> None:
    result = PPEDetectionResult(
        detections=[
            PPEDetectionItem(
                class_name="vest",
                confidence=0.8,
                bbox=(0.0, 0.0, 1.0, 1.0),
                tracker_id=None,
            )
        ]
    )
    client = _client_with_overrides(
        _FakePPEDetectionService(result), _FakeServiceHealth({})
    )

    response = client.post(
        "/v1/detections/ppe", files={"file": ("frame.jpg", b"fake-bytes", "image/jpeg")}
    )
    assert response.status_code == 200
    assert response.json()["detections"][0]["class_name"] == "vest"


def test_post_detect_ppe_maps_unavailable_error_to_503() -> None:
    error = MLServiceUnavailableError("ppe-detection", ConnectionError("refused"))
    client = _client_with_overrides(
        _FakePPEDetectionService(error), _FakeServiceHealth({})
    )

    response = client.post(
        "/v1/detections/ppe", files={"file": ("frame.jpg", b"x", "image/jpeg")}
    )
    assert response.status_code == 503


def test_post_detect_ppe_maps_response_error_to_502() -> None:
    error = MLServiceResponseError("ppe-detection", 500, "model not loaded")
    client = _client_with_overrides(
        _FakePPEDetectionService(error), _FakeServiceHealth({})
    )

    response = client.post(
        "/v1/detections/ppe", files={"file": ("frame.jpg", b"x", "image/jpeg")}
    )
    assert response.status_code == 502


def test_get_status_reports_gateway_and_service_health() -> None:
    health = {
        "ppe-detection": ServiceHealth.OK,
        "fall-detection": ServiceHealth.UNREACHABLE,
    }
    client = _client_with_overrides(
        _FakePPEDetectionService(PPEDetectionResult(detections=[])),
        _FakeServiceHealth(health),
    )

    response = client.get("/v1/status")
    assert response.status_code == 200
    assert response.json() == {
        "gateway": "ok",
        "services": {"ppe-detection": "ok", "fall-detection": "unreachable"},
    }
