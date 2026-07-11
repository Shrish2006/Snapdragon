"""Sensor taxonomy and the extensibility registry.

Every physical sensor with a proven implementation in `helmet/*.ino` gets a
`SensorType` member and a `SensorSpec` registry entry. Sensors named in the
project README (MLX90614 IR thermometer, MAX30102 HR/SpO2, FSR, flex
sensor, GPS) are intentionally absent here — no firmware implements them,
so there is no contract to derive.

Adding a sensor once firmware for it exists means: add an enum member, add
a value model in `models.py`, register a `SensorSpec` below. Nothing in
ingestion, validation, or the event pipeline changes — this registry is the
system's Open/Closed extension point for new sensor types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SensorType(str, Enum):
    """One member per physical sensor with a working firmware test sketch."""

    IMU = "imu"  # helmet/mpu_test.ino (MPU-6050)
    GAS_LPG = "gas_lpg"  # helmet/MQ2_test/MQ2_test.ino (MQ-2)
    CARBON_MONOXIDE = "carbon_monoxide"  # helmet/MQ7_test/MQ7_test.ino (MQ-7)
    ENVIRONMENT = "environment"  # helmet/dht22_test/dht22_test.ino (DHT-22)
    SOUND_LEVEL = "sound_level"  # helmet/sound_sensor_test/sound_sensor_test.ino


class Unit(str, Enum):
    """Physical/electrical units actually produced by the sensors above."""

    G = "g"  # standard gravity, accelerometer axes + magnitude
    DEGREES_PER_SECOND = "dps"  # gyroscope axes
    CELSIUS = "celsius"
    PERCENT_RH = "percent_rh"
    ADC_RAW = "adc_raw"  # raw Arduino analogRead(), 10-bit: 0-1023


@dataclass(frozen=True, slots=True)
class FieldBounds:
    """Plausible min/max for one numeric field, used by the validation
    layer (`validation.py`). These are plausibility bounds — physically or
    electrically possible values — not calibrated accuracy; none of the
    firmware test sketches perform sensor calibration.
    """

    minimum: float
    maximum: float
    unit: Unit


@dataclass(frozen=True, slots=True)
class SensorSpec:
    """Registry entry: everything the gateway needs to know about a sensor
    type without hardcoding it into ingestion or validation logic."""

    sensor_type: SensorType
    description: str
    sample_interval_seconds: float
    fields: dict[str, FieldBounds]


# Every helmet sensor is read via Arduino's analogRead(), a 10-bit ADC that
# always returns 0-1023 regardless of which physical sensor is attached.
_ADC_BOUNDS = FieldBounds(minimum=0, maximum=1023, unit=Unit.ADC_RAW)

SENSOR_REGISTRY: dict[SensorType, SensorSpec] = {
    SensorType.IMU: SensorSpec(
        sensor_type=SensorType.IMU,
        description="MPU-6050 accelerometer + gyroscope (helmet/mpu_test.ino)",
        sample_interval_seconds=0.1,  # loop() ends with delay(100)
        fields={
            # mpu_test.ino converts raw registers using the MPU-6050's
            # power-on-default full-scale range (+/-2g at 16384 LSB/g,
            # +/-250 dps at 131 LSB/dps — the sketch never writes
            # ACCEL_CONFIG/GYRO_CONFIG to change it). Bounds here are
            # widened beyond that default range so a genuine high-g event
            # (e.g. the fall this system exists to detect), which would
            # saturate +/-2g, is not rejected as implausible.
            "accel_x_g": FieldBounds(-16.0, 16.0, Unit.G),
            "accel_y_g": FieldBounds(-16.0, 16.0, Unit.G),
            "accel_z_g": FieldBounds(-16.0, 16.0, Unit.G),
            "accel_magnitude_g": FieldBounds(0.0, 27.7, Unit.G),  # sqrt(3 * 16^2)
            "gyro_x_dps": FieldBounds(-2000.0, 2000.0, Unit.DEGREES_PER_SECOND),
            "gyro_y_dps": FieldBounds(-2000.0, 2000.0, Unit.DEGREES_PER_SECOND),
            "gyro_z_dps": FieldBounds(-2000.0, 2000.0, Unit.DEGREES_PER_SECOND),
        },
    ),
    SensorType.GAS_LPG: SensorSpec(
        sensor_type=SensorType.GAS_LPG,
        description=(
            "MQ-2 LPG/smoke/propane sensor, uncalibrated raw ADC "
            "(helmet/MQ2_test/MQ2_test.ino)"
        ),
        sample_interval_seconds=0.5,  # loop() ends with delay(500)
        fields={"adc_raw": _ADC_BOUNDS},
    ),
    SensorType.CARBON_MONOXIDE: SensorSpec(
        sensor_type=SensorType.CARBON_MONOXIDE,
        description=(
            "MQ-7 carbon monoxide sensor, uncalibrated raw ADC "
            "(helmet/MQ7_test/MQ7_test.ino)"
        ),
        sample_interval_seconds=0.5,  # loop() ends with delay(500)
        fields={"adc_raw": _ADC_BOUNDS},
    ),
    SensorType.ENVIRONMENT: SensorSpec(
        sensor_type=SensorType.ENVIRONMENT,
        description=(
            "DHT-22 temperature/humidity + computed heat index "
            "(helmet/dht22_test/dht22_test.ino)"
        ),
        sample_interval_seconds=2.0,  # loop() ends with delay(2000)
        fields={
            # DHT-22 datasheet operating range.
            "temperature_c": FieldBounds(-40.0, 80.0, Unit.CELSIUS),
            "humidity_pct": FieldBounds(0.0, 100.0, Unit.PERCENT_RH),
            "heat_index_c": FieldBounds(-40.0, 100.0, Unit.CELSIUS),
        },
    ),
    SensorType.SOUND_LEVEL: SensorSpec(
        sensor_type=SensorType.SOUND_LEVEL,
        description=(
            "Analog sound sensor, peak raw ADC sampled over a 100ms window "
            "(helmet/sound_sensor_test/sound_sensor_test.ino)"
        ),
        sample_interval_seconds=0.1,  # 100ms sample window, ~ back-to-back
        fields={"adc_raw": _ADC_BOUNDS},
    ),
}
