"""Mock `FallDetectionClient` — always healthy, never detects a fall.

Used in light dev mode (`MOCK_ML=true`) so the gateway works without
the fall-detection container running.
"""

from __future__ import annotations

from gateway.application.ports import ServiceHealth
from gateway.domain.detection.models import FallDetectionResult


class MockFallDetectionClient:
    """Implements `application.ports.FallDetectionClient` structurally."""

    def __init__(self) -> None:
        pass

    async def health(self) -> ServiceHealth:
        return ServiceHealth.OK

    async def ingest(
        self,
        helmet_id: str,
        window: list[list[float]],
    ) -> FallDetectionResult:
        return FallDetectionResult(fall_detected=False, probability=0.0)
