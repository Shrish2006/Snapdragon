"""Tests for `gateway.domain.helmets.models.HelmetState`."""

from datetime import datetime, timedelta, timezone

import pytest

from gateway.domain.helmets.models import HelmetState, HelmetStatus
from gateway.domain.telemetry.models import (
    AnalogGasReading,
    ImuReading,
    SensorReading,
    TelemetryBatch,
)
from gateway.domain.telemetry.sensors import SensorType

T0 = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=1)


def _imu_reading(captured_at: datetime = T0) -> SensorReading:
    return SensorReading(
        value=ImuReading(
            accel_x_g=0.0,
            accel_y_g=0.0,
            accel_z_g=1.0,
            accel_magnitude_g=1.0,
            gyro_x_dps=0.0,
            gyro_y_dps=0.0,
            gyro_z_dps=0.0,
        ),
        captured_at=captured_at,
    )


def _gas_reading(captured_at: datetime = T0) -> SensorReading:
    return SensorReading(
        value=AnalogGasReading(kind=SensorType.GAS_LPG, adc_raw=66),
        captured_at=captured_at,
    )


def test_first_contact_builds_initial_state_from_first_batch() -> None:
    batch = TelemetryBatch(
        helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
    )
    state = HelmetState.first_contact(batch)
    assert state.helmet_id == "HLM-0007"
    assert state.status is HelmetStatus.ONLINE
    assert state.first_seen_at == T0
    assert state.last_seen_at == T0
    assert state.last_sequence == 1
    assert SensorType.IMU in state.latest_readings


def test_apply_batch_merges_new_sensor_readings_without_dropping_old_ones() -> None:
    first = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
        )
    )
    second = first.apply_batch(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=2, sent_at=T1, readings=[_gas_reading(T1)]
        )
    )
    assert set(second.latest_readings) == {SensorType.IMU, SensorType.GAS_LPG}
    assert second.last_sequence == 2
    assert second.last_seen_at == T1
    assert second.first_seen_at == T0  # unchanged


def test_apply_batch_overwrites_same_sensor_type_with_latest_reading() -> None:
    first = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_gas_reading(T0)]
        )
    )
    second = first.apply_batch(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=2, sent_at=T1, readings=[_gas_reading(T1)]
        )
    )
    assert len(second.latest_readings) == 1
    assert second.latest_readings[SensorType.GAS_LPG].captured_at == T1


def test_apply_batch_rejects_mismatched_helmet_id() -> None:
    state = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
        )
    )
    other_batch = TelemetryBatch(
        helmet_id="HLM-9999", sequence=2, sent_at=T1, readings=[_imu_reading(T1)]
    )
    with pytest.raises(ValueError, match="HLM-9999"):
        state.apply_batch(other_batch)


def test_mark_offline_flips_status_without_touching_timestamps_or_readings() -> None:
    state = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
        )
    )
    offline = state.mark_offline()
    assert offline.status is HelmetStatus.OFFLINE
    assert offline.last_seen_at == state.last_seen_at
    assert offline.latest_readings == state.latest_readings


def test_is_stale_compares_against_threshold() -> None:
    state = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
        )
    )
    assert not state.is_stale(
        now=T0 + timedelta(seconds=5), threshold=timedelta(seconds=60)
    )
    assert state.is_stale(
        now=T0 + timedelta(seconds=120), threshold=timedelta(seconds=60)
    )


def test_state_is_immutable() -> None:
    state = HelmetState.first_contact(
        TelemetryBatch(
            helmet_id="HLM-0007", sequence=1, sent_at=T0, readings=[_imu_reading()]
        )
    )
    with pytest.raises(Exception):
        state.status = HelmetStatus.OFFLINE  # type: ignore[misc]
