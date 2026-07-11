"""Domain-level exceptions.

Raised by pure domain logic and deliberately independent of any transport
concern — no HTTP status codes, no FastAPI imports here. The API layer
(added in later phases) is responsible for translating these into HTTP/WS
responses.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-layer errors."""


class InvalidHelmetIdError(DomainError):
    """Raised when a helmet identifier fails structural validation."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"invalid helmet id: {value!r}")
