"""Prometheus metric definitions — the one module in this codebase that
imports `prometheus_client` directly.

Metric objects are module-level singletons (the standard
`prometheus_client` pattern: a `Counter`/`Histogram`/`Gauge` registers
itself with the global default registry on construction) and are imported
directly at measurement sites (`api/http/middleware.py`,
`api/ws/stream.py`) rather than threaded through application services
behind a port. This is a deliberate exception to this codebase's
ports-and-adapters discipline elsewhere: a metric counter isn't a
swappable business dependency the way `EventBus`/`HelmetRepository` are —
it's instrumentation, used the same pragmatic way `logging.getLogger(__name__)`
already is everywhere, not something anything ever depends on for its
behavior.

Kept to three metrics, each covering something genuinely not derivable
from anywhere else:
- `http_requests_total` / `http_request_duration_seconds`: could not be
  reconstructed from logs without re-parsing every access-log line.
- `ws_connections`: not an HTTP request/response at all — WebSocket
  traffic doesn't pass through `api/http/middleware.py`.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "gateway_http_requests_total",
    "Total HTTP requests handled, by method/path/status.",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "gateway_http_request_duration_seconds",
    "HTTP request duration in seconds, by method/path.",
    ["method", "path"],
)

ws_connections = Gauge(
    "gateway_ws_connections",
    "Currently connected WebSocket clients.",
)
