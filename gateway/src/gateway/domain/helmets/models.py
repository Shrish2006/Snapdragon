"""The `HelmetState` aggregate: real-time state for one helmet.

Presence in this system is entirely telemetry-derived — there is no
separate heartbeat/LWT signal anywhere in the current firmware or
transport, so "online" simply means "we received telemetry recently
enough". `status` is nonetheless stored explicitly (not computed on every
read) so API/WebSocket consumers get a stable value without recomputing
staleness themselves; `is_stale()` plus an explicit `mark_offline()` call
(driven by `application.device_registry.DeviceRegistryService.sweep_offline`)
is how it transitions.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.telemetry.models import SensorReading, TelemetryBatch
from gateway.domain.telemetry.sensors import SensorType


class HelmetStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class HelmetState(BaseModel):
    """Immutable snapshot of one helmet. Every mutation returns a new
    instance (`model_copy`) rather than mutating in place — safe to hand
    out to WebSocket subscribers or cache without defensive copying.
    """

    model_config = ConfigDict(frozen=True)

    helmet_id: HelmetId
    status: HelmetStatus
    first_seen_at: datetime
    last_seen_at: datetime
    last_sequence: int
    latest_readings: dict[SensorType, SensorReading] = Field(default_factory=dict)
    """Most recent reading per sensor type. A batch only ever contains a
    subset of sensors (each fires on its own cadence — see
    `SensorSpec.sample_interval_seconds`), so this is a merge across
    batches over time, not a snapshot of one batch."""

    @classmethod
    def first_contact(cls, batch: TelemetryBatch) -> HelmetState:
        """Build the initial state for a helmet the registry has never
        seen before."""
        return cls(
            helmet_id=batch.helmet_id,
            status=HelmetStatus.ONLINE,
            first_seen_at=batch.sent_at,
            last_seen_at=batch.sent_at,
            last_sequence=batch.sequence,
            latest_readings=_merge(batch.readings),
        )

    def apply_batch(self, batch: TelemetryBatch) -> HelmetState:
        """Fold a new batch into this state: overwrite each sensor's
        latest reading, bump presence, and go online (any accepted batch
        is, by definition, current contact)."""
        if batch.helmet_id != self.helmet_id:
            raise ValueError(
                f"batch for {batch.helmet_id!r} applied to state for "
                f"{self.helmet_id!r}"
            )
        merged = dict(self.latest_readings)
        merged.update(_merge(batch.readings))
        return self.model_copy(
            update={
                "status": HelmetStatus.ONLINE,
                "last_seen_at": batch.sent_at,
                "last_sequence": batch.sequence,
                "latest_readings": merged,
            }
        )

    def mark_offline(self) -> HelmetState:
        """Presence-only transition — does not touch `last_seen_at` or
        `latest_readings`, which remain historical fact."""
        return self.model_copy(update={"status": HelmetStatus.OFFLINE})

    def is_stale(self, *, now: datetime, threshold: timedelta) -> bool:
        return (now - self.last_seen_at) > threshold


def _merge(readings: Iterable[SensorReading]) -> dict[SensorType, SensorReading]:
    return {reading.sensor_type: reading for reading in readings}
