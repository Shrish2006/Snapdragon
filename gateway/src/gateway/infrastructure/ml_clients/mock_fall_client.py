"""Mock `MLServiceClient` for fall-detection — always reports healthy.

Used in light dev mode (`MOCK_ML=true`) so the gateway works without
the fall-detection container. Since fall-detection has no inference
endpoint yet (only `/health`), this is trivial.
"""

from __future__ import annotations

from gateway.application.ports import ServiceHealth


class MockFallDetectionClient:
    """Implements `application.ports.MLServiceClient` structurally.

    Always reports healthy — there is no inference contract to mock yet.
    """

    def __init__(self) -> None:
        pass

    async def health(self) -> ServiceHealth:
        return ServiceHealth.OK
