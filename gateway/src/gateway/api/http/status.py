"""Aggregate integration health for dashboard/ops visibility.

Mirrors the old gateway's `GET /status`
(`{"gateway": "ok", "services": {...}}`), now backed by typed
`ServiceHealthService` instead of inline `httpx` calls in the route.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gateway.api.http.deps import ServiceHealthDep
from gateway.application.ports import ServiceHealth

router = APIRouter(prefix="/v1", tags=["status"])


class StatusResponse(BaseModel):
    gateway: str = "ok"
    services: dict[str, ServiceHealth]


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Gateway and integrated ML service health.",
    description=(
        'Returns `{"gateway": "ok"}` plus the health of every upstream '
        "ML service (PPE detection, fall detection, etc.).\n\n"
        "Each service reports one of: `ok`, `degraded`, or `unreachable`. "
        "This is the endpoint dashboards poll for aggregated ops visibility."
    ),
)
async def get_status(service_health: ServiceHealthDep) -> StatusResponse:
    return StatusResponse(services=await service_health.check_all())
