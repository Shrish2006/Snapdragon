"""Tests for `gateway.application.device_state_manager.DeviceStateManager`."""

from datetime import datetime, timezone

from gateway.application.device_state_manager import DeviceStateManager
from gateway.domain.telemetry.models import ImuReading, SensorReading, TelemetryBatch
from gateway.domain.telemetry.sensors import SensorType
from gateway.infrastructure.registry.in_memory import InMemoryHelmetRepository

T0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def _batch(sequence: int) -> TelemetryBatch:
    return TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=sequence,
        sent_at=T0,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0, accel_y_g=0.0, accel_z_g=1.0,
                    accel_magnitude_g=1.0, gyro_x_dps=0.0, gyro_y_dps=0.0, gyro_z_dps=0.0,
                ),
                captured_at=T0,
            )
        ],
    )


async def test_previous_sequence_is_none_for_unknown_helmet() -> None:
    manager = DeviceStateManager(InMemoryHelmetRepository())
    assert await manager.previous_sequence("HLM-0007") is None


async def test_apply_batch_creates_state_on_first_contact() -> None:
    manager = DeviceStateManager(InMemoryHelmetRepository())
    state = await manager.apply_batch(_batch(1))
    assert state.helmet_id == "HLM-0007"
    assert state.last_sequence == 1
    assert SensorType.IMU in state.latest_readings


async def test_apply_batch_persists_and_updates_previous_sequence() -> None:
    manager = DeviceStateManager(InMemoryHelmetRepository())
    await manager.apply_batch(_batch(1))
    assert await manager.previous_sequence("HLM-0007") == 1

    await manager.apply_batch(_batch(2))
    assert await manager.previous_sequence("HLM-0007") == 2
