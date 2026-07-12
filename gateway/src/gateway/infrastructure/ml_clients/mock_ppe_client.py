"""Mock `PPEDetectionClient` that returns sample detections — no real
ML service is called. Used in light dev mode (`MOCK_ML=true`) so the
gateway works without the CPU-heavy ppe-detection container.

The sample data mirrors `scripts/seed.py::SAMPLE_DETECTIONS` and the
real `ai_ml/ppe_detection/app.py::detect()` response shape exactly.
"""

from __future__ import annotations

import random

from gateway.application.ports import ServiceHealth
from gateway.domain.detection.models import PPEDetectionItem, PPEDetectionResult

_SAMPLE_RESULTS: list[PPEDetectionResult] = [
    PPEDetectionResult(
        detections=[
            PPEDetectionItem(
                class_name="helmet",
                confidence=0.95,
                bbox=(120.0, 80.0, 300.0, 250.0),
                tracker_id=1,
            )
        ]
    ),
    PPEDetectionResult(
        detections=[
            PPEDetectionItem(
                class_name="vest",
                confidence=0.88,
                bbox=(50.0, 100.0, 200.0, 300.0),
                tracker_id=2,
            )
        ]
    ),
    PPEDetectionResult(
        detections=[
            PPEDetectionItem(
                class_name="helmet",
                confidence=0.97,
                bbox=(130.0, 70.0, 310.0, 260.0),
                tracker_id=3,
            ),
            PPEDetectionItem(
                class_name="vest",
                confidence=0.91,
                bbox=(40.0, 90.0, 210.0, 310.0),
                tracker_id=4,
            ),
        ]
    ),
]


class MockPPEDetectionClient:
    """Implements `application.ports.PPEDetectionClient` structurally.

    Returns a random sample detection on every call — no network I/O,
    no model inference. Always reports healthy.
    """

    def __init__(self) -> None:
        pass

    async def health(self) -> ServiceHealth:
        return ServiceHealth.OK

    async def detect(
        self, image: bytes, *, filename: str, content_type: str
    ) -> PPEDetectionResult:
        return random.choice(_SAMPLE_RESULTS)
