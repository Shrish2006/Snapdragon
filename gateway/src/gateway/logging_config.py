"""Structured JSON logging setup.

Mirrors `ai_ml/config.py`'s `_JSONFormatter`/`setup_logging()` exactly in
output shape, so every service in this system (ppe-detection,
fall-detection, gateway) emits the same log line format for downstream
aggregation. Duplicated rather than extracted into a shared library:
each service is a separately-built Docker image with its own dependency
tree and build context (`ai_ml/ppe_detection/Dockerfile` vs
`gateway/Dockerfile`) — a shared package would need its own distribution
mechanism across both, for the ~30 lines below.

One deliberate improvement over `ai_ml/config.py`'s version: that module
reads `LOG_LEVEL`/`LOG_FILE_PATH` from `os.getenv` directly at import
time, a second source of truth alongside this app's parsed `Settings`.
`setup_logging()` here takes them as explicit parameters instead, called
once from `main.py` with the already-validated `Settings` values.

A second improvement: idempotency is tracked with a dedicated module
flag, not `ai_ml/config.py`'s `if root.handlers: return`. Checking for
*any* handler on the root logger is too broad — anything else that
attaches one first (a test runner's own log capturing, an ASGI server's
default config) would make this function silently skip configuring JSON
logging at all, forever, for the rest of the process.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

_configured = False


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, str] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(*, level: str, file_path: str) -> None:
    """Idempotent: a second call in the same process is a no-op (guards
    against `create_app()` being called more than once per process, e.g.
    across tests).
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(_JSONFormatter())
    root.addHandler(stdout_handler)

    if file_path:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        file_handler = logging.FileHandler(file_path)
        file_handler.setFormatter(_JSONFormatter())
        root.addHandler(file_handler)
