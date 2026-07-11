"""PPE detection use-case: submit an image, get typed detections, publish
an event.

Mirrors the old gateway's `POST /detect/ppe` proxy behavior (forward an
image to ppe-detection, emit the result as an event) but built on a typed
client (`PPEDetectionClient`) and a typed event (`PPEDetectionEvent`)
instead of an inline `httpx` call and an untyped `dict`.

PPE detection is camera-scoped, not helmet-scoped — the fixed camera feed
covers a work zone, independent of any individual helmet (see README.md's
architecture diagram: "USB camera (fixed mount)" is a separate input from
the helmet). `PPEDetectionEvent.helmet_id` is therefore left `None`,
consistent with `domain.events.models.DomainEvent`'s documented meaning of
that field.
"""

from __future__ import annotations

from dataclasses import dataclass

from gateway.application.ports import EventPublisher, PPEDetectionClient
from gateway.domain.detection.models import PPEDetectionResult
from gateway.domain.events.models import PPEDetectionEvent


@dataclass(frozen=True, slots=True)
class DetectPPERequest:
    """One frame submitted for PPE detection."""

    image: bytes
    filename: str
    content_type: str


class PPEDetectionService:
    def __init__(
        self, client: PPEDetectionClient, event_publisher: EventPublisher
    ) -> None:
        self._client = client
        self._event_publisher = event_publisher

    async def detect(self, request: DetectPPERequest) -> PPEDetectionResult:
        result = await self._client.detect(
            request.image,
            filename=request.filename,
            content_type=request.content_type,
        )
        await self._event_publisher.publish(
            PPEDetectionEvent(source="ppe-detection", payload=result)
        )
        return result
