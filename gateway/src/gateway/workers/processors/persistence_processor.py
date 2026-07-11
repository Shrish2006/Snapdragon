"""The one processor this phase ships: durable event persistence.

Every event the bus carries gets appended to the configured `EventStore` —
this is what makes "Event persistence" (Phase 4's third deliverable)
actually happen, decoupled from ingestion/detection call sites (the old
gateway called `_push()` inline everywhere; here, publishing and
persisting are two independent concerns connected only by the bus).
"""

from __future__ import annotations

from typing import Any

from gateway.application.ports import EventStore
from gateway.domain.events.models import DomainEvent


class PersistenceProcessor:
    """Implements `workers.pipeline.EventProcessor` structurally."""

    def __init__(self, store: EventStore) -> None:
        self._store = store

    async def process(self, event: DomainEvent[Any]) -> None:
        await self._store.append(event)
