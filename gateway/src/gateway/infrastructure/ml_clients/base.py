"""Shared HTTP plumbing for ML service client adapters.

`GET /health` is the one contract proven across every ML service in this
codebase (`ai_ml/ppe_detection/app.py`, `ai_ml/fall_detection/app.py`), so
`BaseHttpMLServiceClient` owns it — each concrete adapter (`ppe_client.py`,
`fall_client.py`) only implements what's specific to that service.
"""

from __future__ import annotations

import httpx

from gateway.application.ports import ServiceHealth

_HEALTH_CHECK_TIMEOUT_SECONDS = 5.0
"""Matches the old gateway's `/status` health-check timeout — a health
probe should fail fast, independent of the client's general request
timeout (used for actual inference calls)."""


class BaseHttpMLServiceClient:
    """Implements `application.ports.MLServiceClient` structurally (no
    explicit inheritance — `Protocol` conformance is duck-typed)."""

    def __init__(self, *, service_name: str, base_url: str, http_client: httpx.AsyncClient) -> None:
        self._service_name = service_name
        self._base_url = base_url.rstrip("/")
        self._http = http_client

    async def health(self) -> ServiceHealth:
        try:
            response = await self._http.get(
                f"{self._base_url}/health", timeout=_HEALTH_CHECK_TIMEOUT_SECONDS
            )
        except httpx.RequestError:
            return ServiceHealth.UNREACHABLE
        return ServiceHealth.OK if response.is_success else ServiceHealth.DEGRADED
