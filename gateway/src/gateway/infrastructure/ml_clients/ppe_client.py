"""Concrete `PPEDetectionClient` adapter for the ppe-detection service.

Mirrors `ai_ml/ppe_detection/app.py::detect()` exactly: `POST /detect` with
a multipart `file` field, response body `{"detections": [...]}`, parsed
into the typed `PPEDetectionResult` from `domain.detection.models`
(Phase 1) — the same shape the real service returns today, not an assumed
one.
"""

from __future__ import annotations

import httpx
from pydantic import ValidationError

from gateway.domain.detection.models import PPEDetectionResult
from gateway.infrastructure.ml_clients.base import BaseHttpMLServiceClient
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)


class PPEDetectionHttpClient(BaseHttpMLServiceClient):
    """Implements `application.ports.PPEDetectionClient` structurally."""

    def __init__(self, *, base_url: str, http_client: httpx.AsyncClient) -> None:
        super().__init__(service_name="ppe-detection", base_url=base_url, http_client=http_client)

    async def detect(
        self, image: bytes, *, filename: str, content_type: str
    ) -> PPEDetectionResult:
        try:
            response = await self._http.post(
                f"{self._base_url}/detect",
                files={"file": (filename, image, content_type)},
            )
        except httpx.RequestError as exc:
            raise MLServiceUnavailableError(self._service_name, exc) from exc

        if response.is_error:
            raise MLServiceResponseError(self._service_name, response.status_code, response.text)

        try:
            return PPEDetectionResult.model_validate(response.json())
        except ValidationError as exc:
            raise MLServiceResponseError(
                self._service_name,
                response.status_code,
                f"response did not match the expected detection schema: {exc}",
            ) from exc
