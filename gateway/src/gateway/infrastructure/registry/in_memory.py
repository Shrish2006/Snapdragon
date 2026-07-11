"""In-memory `HelmetRepository` adapter.

Single-process, `asyncio.Lock`-guarded dict. Correct for one gateway
instance; does not share state across replicas. This is the Phase 2
baseline for local development and single-instance deployment — the
production storage recommendation (Redis-backed, shared across instances)
lands in a later phase behind the same `HelmetRepository` port, so nothing
above this adapter (the application services, the API layer) changes when
it's swapped.
"""

from __future__ import annotations

import asyncio

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.helmets.models import HelmetState


class InMemoryHelmetRepository:
    """Implements `application.ports.HelmetRepository` structurally (no
    explicit inheritance — `Protocol` conformance is duck-typed)."""

    def __init__(self) -> None:
        self._states: dict[HelmetId, HelmetState] = {}
        self._lock = asyncio.Lock()

    async def get(self, helmet_id: HelmetId) -> HelmetState | None:
        async with self._lock:
            return self._states.get(helmet_id)

    async def upsert(self, state: HelmetState) -> None:
        async with self._lock:
            self._states[state.helmet_id] = state

    async def list_all(self) -> list[HelmetState]:
        async with self._lock:
            return list(self._states.values())
