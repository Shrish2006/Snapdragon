"""Tests for `gateway.domain.telemetry.models`."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gateway.domain.telemetry.models import (
    AnalogGasReading,
    EnvironmentReading,
    ImuReading,
    SensorReading,
    SoundLevelReading,
    TelemetryBatch,
)
from gateway.domain.telemetry.sensors import SensorType

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_imu_reading_from_raw_dict_matches_mpu_test_ino_fields() -> None:
    """Mirrors the exact values `mpu_test.ino` prints per loop iteration."""
    reading = SensorReading.model_validate(
        {
            "value": {
                "kind": "imu",
                "accel_x_g": 0.01,
                "accel_y_g": -0.02,
                "accel_z_g": 1.00,
                "accel_magnitude_g": 1.0002,
                "gyro_x_dps": 0.5,
                "gyro_y_dps": -0.5,
                "gyro_z_dps": 0.0,
            },
            "captured_at": NOW.isoformat(),
        }
    )
    assert isinstance(reading.value, ImuReading)
    assert reading.sensor_type is SensorType.IMU


@pytest.mark.parametrize("kind", ["gas_lpg", "carbon_monoxide"])
def test_analog_gas_reading_accepts_both_mq_sensors(kind: str) -> None:
    reading = SensorReading.model_validate(
        {"value": {"kind": kind, "adc_raw": 66}, "captured_at": NOW.isoformat()}
    )
    assert isinstance(reading.value, AnalogGasReading)
    assert reading.sensor_type.value == kind


def test_environment_reading_matches_dht22_test_ino_fields() -> None:
    reading = SensorReading.model_validate(
        {
            "value": {
                "kind": "environment",
                "temperature_c": 26.1,
                "humidity_pct": 59.8,
                "heat_index_c": 27.02,
            },
            "captured_at": NOW.isoformat(),
        }
    )
    assert isinstance(reading.value, EnvironmentReading)
    assert reading.sensor_type is SensorType.ENVIRONMENT


def test_sound_level_reading_matches_sound_sensor_test_ino() -> None:
    reading = SensorReading.model_validate(
        {
            "value": {"kind": "sound_level", "adc_raw": 1031},
            "captured_at": NOW.isoformat(),
        }
    )
    assert isinstance(reading.value, SoundLevelReading)
    assert reading.sensor_type is SensorType.SOUND_LEVEL


def test_unknown_sensor_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SensorReading.model_validate(
            {"value": {"kind": "heart_rate", "bpm": 80}, "captured_at": NOW.isoformat()}
        )


def test_telemetry_batch_requires_at_least_one_reading() -> None:
    with pytest.raises(ValidationError):
        TelemetryBatch(
            helmet_id="HLM-0007",
            sequence=1,
            sent_at=NOW,
            readings=[],
        )


def test_telemetry_batch_rejects_invalid_helmet_id() -> None:
    reading = SensorReading(
        value=SoundLevelReading(adc_raw=67),
        captured_at=NOW,
    )
    with pytest.raises(ValidationError):
        TelemetryBatch(
            helmet_id="bad/slash",
            sequence=1,
            sent_at=NOW,
            readings=[reading],
        )


def test_telemetry_batch_accepts_a_mixed_multi_sensor_payload() -> None:
    batch = TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=42,
        sent_at=NOW,
        readings=[
            SensorReading(
                value=ImuReading(
                    accel_x_g=0.0,
                    accel_y_g=0.0,
                    accel_z_g=1.0,
                    accel_magnitude_g=1.0,
                    gyro_x_dps=0.0,
                    gyro_y_dps=0.0,
                    gyro_z_dps=0.0,
                ),
                captured_at=NOW,
            ),
            SensorReading(
                value=AnalogGasReading(kind=SensorType.GAS_LPG, adc_raw=66),
                captured_at=NOW,
            ),
            SensorReading(value=SoundLevelReading(adc_raw=67), captured_at=NOW),
        ],
    )
    assert len(batch.readings) == 3
    assert batch.readings[0].sensor_type is SensorType.IMU
