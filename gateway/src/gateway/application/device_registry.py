"""Device registry: the roster of known helmets and their presence.

Answers "what helmets exist" and "are they currently online" — a read and
presence-lifecycle concern. Deliberately separate from
`DeviceStateManager`'s job (folding telemetry into a helmet's latest
readings): the two classes change for different reasons — this one changes
when presence policy changes (e.g. a different staleness threshold, a
future heartbeat signal), the other when telemetry-merge semantics change.
Both depend on the same `HelmetRepository` port; neither wraps the other.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gateway.application.ports import HelmetRepository
from gateway.domain.common.identifiers import HelmetId
from gateway.domain.helmets.models import HelmetState, HelmetStatus

DEFAULT_STALENESS_THRESHOLD = timedelta(seconds=60)
"""No sensor's sample interval (`SENSOR_REGISTRY`) exceeds 2s, so a helmet
that has sent nothing in 60s (30x its slowest sensor's cadence) is
considered offline rather than merely between samples."""


class DeviceRegistryService:
    def __init__(self, repository: HelmetRepository) -> None:
        self._repository = repository

    async def get(self, helmet_id: HelmetId) -> HelmetState | None:
        return await self._repository.get(helmet_id)

    async def list_all(self) -> list[HelmetState]:
        return await self._repository.list_all()

    async def list_online(self) -> list[HelmetState]:
        states = await self._repository.list_all()
        return [state for state in states if state.status is HelmetStatus.ONLINE]

    async def sweep_offline(
        self,
        *,
        now: datetime | None = None,
        staleness_threshold: timedelta = DEFAULT_STALENESS_THRESHOLD,
    ) -> list[HelmetState]:
        """Transition any ONLINE helmet whose last telemetry is older than
        `staleness_threshold` to OFFLINE.

        A pure on-demand method in this phase — scheduling it periodically
        is a background-task concern (a later phase's worker/scheduler);
        callable safely right now for tests and manual/API-triggered
        sweeps.
        """
        now = now or datetime.now(timezone.utc)
        changed: list[HelmetState] = []
        for state in await self._repository.list_all():
            if state.status is HelmetStatus.ONLINE and state.is_stale(
                now=now, threshold=staleness_threshold
            ):
                offline_state = state.mark_offline()
                await self._repository.upsert(offline_state)
                changed.append(offline_state)
        return changed
