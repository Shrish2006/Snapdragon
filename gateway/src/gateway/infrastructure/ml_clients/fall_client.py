"""Concrete `FallDetectionClient` adapter for the fall-detection service.

`POST /ingest` receives a pre-assembled 200-sample window from
`FallDetectionProcessor` (the gateway owns the buffer and debounce state)
and returns a `FallDetectionResult` with the raw probability from the ONNX
model. The service is stateless; only the gateway processor has memory of
per-helmet history.
"""

from __future__ import annotations

import httpx
from pydantic import ValidationError

from gateway.domain.detection.models import FallDetectionResult
from gateway.infrastructure.ml_clients.base import BaseHttpMLServiceClient
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)


class FallDetectionHttpClient(BaseHttpMLServiceClient):
    """Implements `application.ports.FallDetectionClient` structurally."""

    def __init__(self, *, base_url: str, http_client: httpx.AsyncClient) -> None:
        super().__init__(
            service_name="fall-detection", base_url=base_url, http_client=http_client
        )

    async def ingest(
        self,
        helmet_id: str,
        window: list[list[float]],
    ) -> FallDetectionResult:
        """Send a 200-sample IMU window; return fall probability."""
        try:
            response = await self._http.post(
                f"{self._base_url}/ingest",
                json={"helmet_id": helmet_id, "window": window},
            )
        except httpx.RequestError as exc:
            raise MLServiceUnavailableError(self._service_name, exc) from exc

        if response.is_error:
            raise MLServiceResponseError(
                self._service_name, response.status_code, response.text
            )

        try:
            return FallDetectionResult.model_validate(response.json())
        except ValidationError as exc:
            raise MLServiceResponseError(
                self._service_name,
                response.status_code,
                f"response did not match expected schema: {exc}",
            ) from exc
