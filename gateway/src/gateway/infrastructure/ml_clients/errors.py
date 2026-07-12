"""ML client adapter failure modes.

Distinct from `domain.common.errors` — these describe the outside world
misbehaving (an ML service down, or responding with something the adapter
can't parse), not a business-rule violation. `api/http` translates them
into HTTP responses (see `main.py`'s exception handlers); nothing below
`api/` needs to know an HTTP status code exists.
"""

from __future__ import annotations


class MLServiceError(Exception):
    """Base class for ML client adapter failures."""


class MLServiceUnavailableError(MLServiceError):
    """The service could not be reached at all (connection refused,
    timeout, DNS failure) — maps to HTTP 503."""

    def __init__(self, service: str, cause: Exception) -> None:
        self.service = service
        self.cause = cause
        super().__init__(f"{service} unreachable: {cause}")


class MLServiceResponseError(MLServiceError):
    """The service responded but with an error status or a body that
    doesn't match its documented contract — maps to HTTP 502."""

    def __init__(self, service: str, status_code: int, detail: str) -> None:
        self.service = service
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{service} returned {status_code}: {detail}")
