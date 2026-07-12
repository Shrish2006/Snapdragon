"""FastAPI application factory.

Phase 1 wired configuration and preserved `GET /health`, required by
`docker-compose.yml`'s healthcheck, `k8s/gateway-deployment.yaml`'s
liveness/readiness probes, and `gateway/Dockerfile`'s `HEALTHCHECK`.

Phase 2 wired the composition root (`gateway.bootstrap.build_container`)
onto `app.state` and mounted the telemetry ingestion and helmet-state
routers.

Phase 3 added a `lifespan` to close the shared `httpx.AsyncClient` on
shutdown (mirroring the old gateway's `lifespan`/`_http.aclose()`
pattern), registered translation of ML client failures
(`MLServiceUnavailableError` -> 503, `MLServiceResponseError` -> 502) once
for every route instead of per-handler, and mounted the PPE detection and
status routers.

Phase 4 extended `lifespan` to initialize the event store (when it's the
SQLite backend) and run `Container.processing_pipeline` as a background
task for the app's lifetime.

Phase 5 added `Container.subscription_manager` as a second background task
(same start/cancel treatment as the pipeline — `_run_background_tasks`
below generalizes over both instead of duplicating the pattern), and
mounted the WebSocket streaming and event-history routers.

Phase 6 wires structured JSON logging (`logging_config.setup_logging`,
using the `Settings.log_level`/`log_file_path` that have existed since
Phase 1 marked "wired in Phase 6"), the HTTP observability middleware
(request metrics + one access-log line per request), `GET /metrics`, and
`app.state.ready` — flipped `True` only once the background tasks are
actually running, read by `GET /ready` (`api/http/health.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway.api.http import (
    detections,
    events,
    health,
    helmets,
    metrics,
    status,
    telemetry,
)
from gateway.api.http.middleware import observability_middleware
from gateway.api.ws import stream as ws_stream
from gateway.bootstrap import Container, build_container
from gateway.config import Settings, get_settings
from gateway.infrastructure.ml_clients.errors import (
    MLServiceResponseError,
    MLServiceUnavailableError,
)
from gateway.infrastructure.persistence.postgres import PostgresEventStore
from gateway.infrastructure.persistence.sqlite import SQLiteEventStore
from gateway.logging_config import setup_logging

logger = logging.getLogger("gateway.lifespan")


@asynccontextmanager
async def _run_background_tasks(
    *coroutines: Callable[[], Awaitable[None]],
) -> AsyncIterator[None]:
    """Start each `coroutines[i]()` as a task for the duration of the
    `async with` block; cancel all of them (in reverse start order) and
    wait for the cancellation to land on shutdown."""
    tasks = [asyncio.create_task(coro()) for coro in coroutines]
    try:
        yield
    finally:
        for task in reversed(tasks):
            task.cancel()
        for task in reversed(tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: Container = app.state.container
    logger.info("gateway starting")

    if isinstance(container.event_store, (SQLiteEventStore, PostgresEventStore)):
        await container.event_store.initialize()

    _bg: list[Callable[[], Awaitable[None]]] = [
        container.processing_pipeline.run,
        container.subscription_manager.run,
    ]
    if container.mqtt_ingestion_adapter is not None:
        _bg.append(container.mqtt_ingestion_adapter.run)
    if container.mqtt_presence_adapter is not None:
        _bg.append(container.mqtt_presence_adapter.run)
    async with _run_background_tasks(*_bg):
        app.state.ready = True
        logger.info("gateway ready")
        try:
            yield
        finally:
            await container.event_store.close()
            await container.http_client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI application.

    Accepting an optional `Settings` instance (rather than always reading
    from the environment) keeps the factory testable without env var
    monkeypatching.
    """
    settings = settings or get_settings()
    setup_logging(level=settings.log_level, file_path=settings.log_file_path)

    tags_metadata = [
        {
            "name": "telemetry",
            "description": "Ingest sensor readings from helmets.",
        },
        {
            "name": "helmets",
            "description": "Read-only real-time helmet state (online/offline, latest readings per sensor).",
        },
        {
            "name": "detections",
            "description": "On-demand ML detection (PPE). Upload a frame and get detection results.",
        },
        {
            "name": "status",
            "description": "Aggregate health of the gateway and its upstream ML services.",
        },
        {
            "name": "events",
            "description": "Historical event log — telemetry accepted, detections run, state transitions.",
        },
    ]
    app = FastAPI(
        title="SafeGuard Gateway",
        description=(
            "Real-time safety helmet telemetry ingestion, ML detection (PPE), "
            "and event streaming backend.\n\n"
            "Helmets report sensor readings (IMU, gas, environment, sound) via "
            "**MQTT** (Mosquitto broker, `safeguard/telemetry/{helmet_id}`) or "
            "**HTTP** (`POST /v1/telemetry`). "
            "The gateway validates, persists, and streams them to connected dashboards "
            "over WebSocket. On-demand PPE detection runs uploaded frames against a "
            "YOLO model.\n\n"
            "MQTT is enabled when `MQTT_BROKER_HOST` is set; omitting it leaves the "
            "gateway in HTTP-only mode.\n\n"
            "---\n"
            "**Liveness** `GET /health` — always 200 if the process is alive.\n"
            "**Readiness** `GET /ready` — 503 until background tasks finish starting "
            "and the event bus (Redis, if configured) responds.\n"
            "**Metrics** `GET /metrics` — Prometheus text format.\n"
            "**WebSocket** `GET /v1/ws` — real-time event stream (see the WebSocket tab below)."
        ),
        version="1.0.0",
        contact={
            "name": "SafeGuard Team",
            "url": "https://github.com/Shrish2006/Snapdragon",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        openapi_tags=tags_metadata,
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.container = build_container(settings)
    app.state.ready = False

    app.middleware("http")(observability_middleware)

    app.include_router(telemetry.router)
    app.include_router(helmets.router)
    app.include_router(detections.router)
    app.include_router(status.router)
    app.include_router(events.router)
    app.include_router(ws_stream.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    @app.exception_handler(MLServiceUnavailableError)
    async def _handle_unavailable(
        _: Request, exc: MLServiceUnavailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(MLServiceResponseError)
    async def _handle_response_error(
        _: Request, exc: MLServiceResponseError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
