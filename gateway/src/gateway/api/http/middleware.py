"""HTTP observability middleware: one pass over the request/response
cycle records both the Prometheus metrics and the structured access-log
line — no reason to measure duration twice for two different sinks.

Labels by the *matched route's path template*
(`request.scope["route"].path`, e.g. `/v1/helmets/{helmet_id}`), not the
raw request path — using the raw path would give `/v1/helmets/HLM-0007`
and `/v1/helmets/HLM-0008` distinct Prometheus label values, and label
cardinality that grows with the number of helmets is exactly the kind of
metrics-server memory leak this labeling scheme exists to avoid. Falls
back to the raw path only for unmatched routes (404s), which are bounded.
"""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from gateway.infrastructure.metrics.registry import (
    http_request_duration_seconds,
    http_requests_total,
)

logger = logging.getLogger("gateway.access")


async def observability_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration_seconds = time.perf_counter() - start

    route = request.scope.get("route")
    path = route.path if route is not None else request.url.path
    method = request.method

    http_requests_total.labels(
        method=method, path=path, status_code=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(
        duration_seconds
    )

    logger.info(
        "%s %s -> %d (%.1fms)",
        method,
        path,
        response.status_code,
        duration_seconds * 1000,
    )
    return response
