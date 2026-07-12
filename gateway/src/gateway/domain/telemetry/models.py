"""Core telemetry domain models: what a helmet actually reports today.

Grounded strictly in `helmet/*.ino` — every field on every reading model
corresponds to a value the matching test sketch actually `Serial.print`s.
Nothing here is speculative.

`TelemetryBatch` is the one exception worth calling out explicitly: it is a
*gateway-side ingest contract*, not a reverse-engineered firmware format —
`helmet/helmet_firmware.ino` (the integrated firmware) is currently a
2-line stub and produces nothing. Field types and units below are derived
from the proven, per-sensor test sketches; firmware must produce this shape
to integrate with the gateway (see Phase 2/3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from gateway.domain.common.identifiers import HelmetId
from gateway.domain.telemetry.sensors import SensorType


class ImuReading(BaseModel):
    """helmet/mpu_test.ino: one atomic 14-byte burst read from the MPU-6050
    (accel X/Y/Z, temperature register skipped, gyro X/Y/Z), plus the
    accelerometer-magnitude the sketch computes from it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal[SensorType.IMU] = SensorType.IMU
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float
    accel_magnitude_g: float
    gyro_x_dps: float
    gyro_y_dps: float
    gyro_z_dps: float


class AnalogGasReading(BaseModel):
    """Shared shape for MQ-2 (LPG/smoke/propane) and MQ-7 (CO): both
    sketches emit exactly one raw 10-bit ADC sample and nothing else — no
    calibrated ppm conversion exists in either. `kind` disambiguates which
    physical sensor produced the sample.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal[SensorType.GAS_LPG, SensorType.CARBON_MONOXIDE]
    adc_raw: int


class EnvironmentReading(BaseModel):
    """helmet/dht22_test/dht22_test.ino: one `dht.read()` call yields
    temperature + humidity together; heat index is derived from both in the
    same loop iteration, so all three travel as one reading."""

    model_config = ConfigDict(frozen=True)

    kind: Literal[SensorType.ENVIRONMENT] = SensorType.ENVIRONMENT
    temperature_c: float
    humidity_pct: float
    heat_index_c: float


class SoundLevelReading(BaseModel):
    """helmet/sound_sensor_test/sound_sensor_test.ino: peak raw ADC value
    sampled over a 100ms window."""

    model_config = ConfigDict(frozen=True)

    kind: Literal[SensorType.SOUND_LEVEL] = SensorType.SOUND_LEVEL
    adc_raw: int


SensorValue = Annotated[
    Union[ImuReading, AnalogGasReading, EnvironmentReading, SoundLevelReading],
    Field(discriminator="kind"),
]
"""Discriminated union over every sensor's reading shape. Adding a sensor
means adding one more member here (see `sensors.py` for the registry side
of the same extension point)."""


class SensorReading(BaseModel):
    """One self-contained sample from a single physical sensor."""

    model_config = ConfigDict(frozen=True)

    value: SensorValue
    captured_at: datetime  # device-reported capture time (UTC)

    @property
    def sensor_type(self) -> SensorType:
        """The physical sensor this reading came from — derived from
        `value.kind` rather than stored twice, so it can never disagree
        with the payload it describes."""
        return self.value.kind


class TelemetryBatch(BaseModel):
    """One uplink transmission from a helmet: one or more sensor readings,
    captured close together in time, sent as a single packet.

    Batching is a gateway design decision (see module docstring), not an
    existing firmware behavior: the current sensor test sketches are
    independent Arduino sketches, each with its own `loop()` cadence, never
    combined into a single uplink today.
    """

    model_config = ConfigDict(frozen=True)

    helmet_id: HelmetId
    sequence: int = Field(ge=0)
    sent_at: datetime
    readings: list[SensorReading] = Field(min_length=1)
