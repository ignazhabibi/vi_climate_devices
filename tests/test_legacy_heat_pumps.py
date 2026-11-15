"""Tests for the defined entities of legacy CU401B heat pumps."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.number import _discover_numbers
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors

LEGACY_HEAT_PUMPS = [
    "Vitocal200S",
    "Vitocal300G-CU401B",
    "Vitocal333G-with-Vitovent300F",
]

DUPLICATE_REFRIGERANT_FEATURES = {
    "heating.sensors.pressure.suctionGas": "heating.compressors.0.sensors.pressure.inlet",
    "heating.sensors.temperature.hotGas": "heating.compressors.0.sensors.temperature.outlet",
    "heating.sensors.temperature.liquidGas": "heating.evaporators.0.sensors.temperature.liquid",
    "heating.sensors.temperature.suctionGas": "heating.compressors.0.sensors.temperature.inlet",
}


@pytest.mark.parametrize("device_name", LEGACY_HEAT_PUMPS)
@pytest.mark.asyncio
async def test_duplicate_refrigerant_values_create_no_sensors(device_name: str) -> None:
    """Skip refrigerant values that a defined sensor already reports."""
    # Arrange: Load the real legacy heat pump fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    keys = {
        entity.entity_description.key
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: Each skipped value matches the reading of a defined sensor.
    for duplicate, defined in DUPLICATE_REFRIGERANT_FEATURES.items():
        assert duplicate not in keys
        assert defined in keys
        duplicate_feature = device.get_feature(duplicate)
        defined_feature = device.get_feature(defined)
        assert duplicate_feature is not None
        assert defined_feature is not None
        assert duplicate_feature.value == defined_feature.value


@pytest.mark.parametrize("device_name", ["Vitocal250A", "Vitocal252A"])
@pytest.mark.asyncio
async def test_writable_hysteresis_switch_off_creates_no_sensor(
    device_name: str,
) -> None:
    """Keep a writable switch-off hysteresis a number only."""
    # Arrange: Load a fixture that reports the hysteresis as writable.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]
    coordinator = MagicMock(data={"device": device})
    feature_name = "heating.dhw.temperature.hysteresis.switchOffValue"

    # Act: Discover the fixture's sensors and numbers.
    sensor_keys = {
        entity.entity_description.key
        for entity in _discover_realtime_sensors(coordinator)
    }
    number_keys = {
        entity.entity_description.key for entity in _discover_numbers(coordinator)
    }

    # Assert: Only the number exposes the hysteresis.
    assert feature_name in number_keys
    assert feature_name not in sensor_keys
