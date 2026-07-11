"""Tests for `gateway.application.detection_service.PPEDetectionService`."""

from typing import Any

from gateway.application.detection_service import DetectPPERequest, PPEDetectionService
from gateway.application.ports import ServiceHealth
from gateway.domain.detection.models import PPEDetectionItem, PPEDetectionResult
from gateway.domain.events.models import DomainEvent, PPEDetectionEvent


class _FakePPEClient:
    def __init__(self, result: PPEDetectionResult) -> None:
        self._result = result
        self.calls: list[tuple[bytes, str, str]] = []

    async def detect(
        self, image: bytes, *, filename: str, content_type: str
    ) -> PPEDetectionResult:
        self.calls.append((image, filename, content_type))
        return self._result

    async def health(self) -> ServiceHealth:
        raise NotImplementedError  # unused by PPEDetectionService


class _RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent[Any]] = []

    async def publish(self, event: DomainEvent[Any]) -> None:
        self.events.append(event)


def _detection_result() -> PPEDetectionResult:
    return PPEDetectionResult(
        detections=[
            PPEDetectionItem(class_name="helmet", confidence=0.9, bbox=(0.0, 0.0, 1.0, 1.0), tracker_id=1)
        ]
    )


async def test_detect_forwards_the_image_and_returns_the_typed_result() -> None:
    expected = _detection_result()
    client = _FakePPEClient(expected)
    service = PPEDetectionService(client, _RecordingPublisher())

    result = await service.detect(
        DetectPPERequest(image=b"jpeg", filename="a.jpg", content_type="image/jpeg")
    )

    assert result == expected
    assert client.calls == [(b"jpeg", "a.jpg", "image/jpeg")]


async def test_detect_publishes_a_ppe_detection_event_scoped_to_no_helmet() -> None:
    result = _detection_result()
    client = _FakePPEClient(result)
    publisher = _RecordingPublisher()
    service = PPEDetectionService(client, publisher)

    await service.detect(DetectPPERequest(image=b"x", filename="a.jpg", content_type="image/jpeg"))

    assert len(publisher.events) == 1
    event = publisher.events[0]
    assert isinstance(event, PPEDetectionEvent)
    assert event.helmet_id is None  # PPE detection is camera-scoped, not helmet-scoped
    assert event.payload == result
    assert event.source == "ppe-detection"
