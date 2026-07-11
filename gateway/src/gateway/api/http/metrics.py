"""Prometheus metrics endpoint. Reads whatever
`infrastructure.metrics.registry` has accumulated — no service-layer
involvement, no `Container` dependency."""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get(
    "/metrics",
    summary="Prometheus metrics.",
    description=(
        "Exposes process and application metrics in Prometheus text format. "
        "Includes HTTP request counters, durations, WebSocket connection "
        "gauge, and Python GC metrics."
    ),
)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
