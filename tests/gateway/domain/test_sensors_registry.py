"""Tests for `gateway.domain.telemetry.sensors` — the extensibility
registry must stay internally consistent as sensors are added."""

from gateway.domain.telemetry.sensors import SENSOR_REGISTRY, SensorType


def test_every_sensor_type_is_registered() -> None:
    assert set(SENSOR_REGISTRY) == set(SensorType)


def test_every_field_bounds_are_ordered() -> None:
    for spec in SENSOR_REGISTRY.values():
        for field_name, bounds in spec.fields.items():
            assert (
                bounds.minimum < bounds.maximum
            ), f"{spec.sensor_type}.{field_name} has inverted bounds"


def test_every_spec_has_a_positive_sample_interval() -> None:
    for spec in SENSOR_REGISTRY.values():
        assert spec.sample_interval_seconds > 0


def test_analog_adc_sensors_share_the_10_bit_bound() -> None:
    for sensor_type in (
        SensorType.GAS_LPG,
        SensorType.CARBON_MONOXIDE,
        SensorType.SOUND_LEVEL,
    ):
        bounds = SENSOR_REGISTRY[sensor_type].fields["adc_raw"]
        assert (bounds.minimum, bounds.maximum) == (0, 1023)
