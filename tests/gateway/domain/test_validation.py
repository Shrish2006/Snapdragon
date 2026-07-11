"""Tests for `gateway.domain.telemetry.validation`."""

from datetime import datetime, timedelta, timezone

from gateway.domain.telemetry.models import (
    AnalogGasReading,
    ImuReading,
    SensorReading,
    TelemetryBatch,
)
from gateway.domain.telemetry.sensors import SensorType
from gateway.domain.telemetry.validation import validate_batch, validate_reading

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _imu_reading(accel_x_g: float = 0.0) -> SensorReading:
    return SensorReading(
        value=ImuReading(
            accel_x_g=accel_x_g, accel_y_g=0.0, accel_z_g=1.0,
            accel_magnitude_g=1.0, gyro_x_dps=0.0, gyro_y_dps=0.0, gyro_z_dps=0.0,
        ),
        captured_at=NOW,
    )


def test_plausible_reading_is_valid() -> None:
    result = validate_reading(_imu_reading(accel_x_g=0.5))
    assert result.is_valid
    assert result.issues == ()


def test_implausible_reading_is_flagged() -> None:
    result = validate_reading(_imu_reading(accel_x_g=500.0))
    assert not result.is_valid
    assert any(issue.field == "accel_x_g" for issue in result.issues)


def test_gas_sensor_adc_out_of_10_bit_range_is_flagged() -> None:
    reading = SensorReading(
        value=AnalogGasReading(kind=SensorType.CARBON_MONOXIDE, adc_raw=2000),
        captured_at=NOW,
    )
    result = validate_reading(reading)
    assert not result.is_valid
    assert result.issues[0].field == "adc_raw"


def _batch(sequence: int, sent_at: datetime) -> TelemetryBatch:
    return TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=sequence,
        sent_at=sent_at,
        readings=[_imu_reading()],
    )


def test_batch_with_no_prior_sequence_and_fresh_timestamp_is_valid() -> None:
    result = validate_batch(_batch(1, NOW), previous_sequence=None, now=NOW)
    assert result.is_valid


def test_batch_with_non_monotonic_sequence_is_flagged() -> None:
    result = validate_batch(_batch(5, NOW), previous_sequence=5, now=NOW)
    assert not result.is_valid
    assert any(issue.field == "sequence" for issue in result.issues)


def test_batch_with_excessive_clock_skew_is_flagged() -> None:
    stale = NOW - timedelta(minutes=5)
    result = validate_batch(
        _batch(1, stale), previous_sequence=None, now=NOW, max_clock_skew=timedelta(seconds=30)
    )
    assert not result.is_valid
    assert any(issue.field == "sent_at" for issue in result.issues)


def test_batch_validation_aggregates_nested_reading_issues() -> None:
    batch = TelemetryBatch(
        helmet_id="HLM-0007",
        sequence=1,
        sent_at=NOW,
        readings=[_imu_reading(accel_x_g=999.0)],
    )
    result = validate_batch(batch, previous_sequence=None, now=NOW)
    assert not result.is_valid
    assert any(issue.field == "accel_x_g" for issue in result.issues)
