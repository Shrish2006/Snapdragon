"""Concrete `MLServiceClient` adapter for the fall-detection service.

`ai_ml/fall_detection/app.py` exposes only `GET /health` today —
`ai_ml/fall_detection/fall_detection.py` is an unimplemented `# TODO` stub
with no inference endpoint at all. This adapter therefore only implements
health checking (inherited from `BaseHttpMLServiceClient`) and adds
nothing else. Do not add a speculative `.detect()` method here — extend it
(mirroring `PPEDetectionHttpClient`) once `ai_ml/fall_detection` actually
defines a response contract.
"""

from __future__ import annotations

import httpx

from gateway.infrastructure.ml_clients.base import BaseHttpMLServiceClient


class FallDetectionHttpClient(BaseHttpMLServiceClient):
    """Implements `application.ports.MLServiceClient` structurally."""

    def __init__(self, *, base_url: str, http_client: httpx.AsyncClient) -> None:
        super().__init__(service_name="fall-detection", base_url=base_url, http_client=http_client)
