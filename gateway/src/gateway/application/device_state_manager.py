"""Device state manager: folds incoming telemetry into a helmet's
real-time state.

Owns the "how does a new `TelemetryBatch` change what we know about this
helmet" algorithm. The actual merge logic (`HelmetState.first_contact` /
`.apply_batch`) is pure domain code; this class is the thin
persistence-aware wrapper that fetches, applies, and stores it.
"""

from __future__ import annotations

from gateway.application.ports import HelmetRepository
from gateway.domain.common.identifiers import HelmetId
from gateway.domain.helmets.models import HelmetState
from gateway.domain.telemetry.models import TelemetryBatch


class DeviceStateManager:
    def __init__(self, repository: HelmetRepository) -> None:
        self._repository = repository

    async def previous_sequence(self, helmet_id: HelmetId) -> int | None:
        """The last accepted sequence number for a helmet, or `None` if it
        has never been seen — the input `IngestionService` passes to
        `domain.telemetry.validation.validate_batch`.
        """
        state = await self._repository.get(helmet_id)
        return state.last_sequence if state else None

    async def apply_batch(self, batch: TelemetryBatch) -> HelmetState:
        existing = await self._repository.get(batch.helmet_id)
        new_state = (
            existing.apply_batch(batch)
            if existing is not None
            else HelmetState.first_contact(batch)
        )
        await self._repository.upsert(new_state)
        return new_state
