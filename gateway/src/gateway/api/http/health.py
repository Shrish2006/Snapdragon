"""Liveness and readiness checks.

`GET /health` (liveness) — unconditional 200 once the process can respond
at all. This is the one contract every deployment surface has depended on
since before this rewrite began: `docker-compose.yml`'s healthcheck,
`k8s/gateway-deployment.yaml`'s liveness probe, `gateway/Dockerfile`'s
`HEALTHCHECK`. It must never depend on anything that could itself be
degraded — that's what `/ready` is for.

`GET /ready` (readiness) — gates traffic. 503 until `main.py`'s lifespan
has finished starting the background tasks and initializing the event
store; 503 again if the event bus backend is Redis and Redis becomes
unreachable mid-flight. Mirrors `ai_ml/ppe_detection/app.py`'s `/ready`
(503 until the model is loaded), generalized to this app's own
dependencies. `k8s/gateway-deployment.yaml`'s readiness probe targets
this endpoint (Phase 6); the liveness probe stays on `/health`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from gateway.infrastructure.bus.redis_streams import RedisStreamsEventBus

router = APIRouter()


@router.get("/health", summary="Liveness — is the process up?")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness — can this instance serve traffic?")
async def ready(request: Request) -> dict[str, str]:
    if not request.app.state.ready:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="startup not complete")

    event_bus = request.app.state.container.event_bus
    if isinstance(event_bus, RedisStreamsEventBus) and not await event_bus.ping():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="event bus unreachable")

    return {"status": "ok"}
