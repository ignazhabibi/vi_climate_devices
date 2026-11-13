"""Tests for the defined entities of legacy CU401B heat pumps."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import FixtureViClient

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
async def test_legacy_heat_pumps_define_cop_and_discharge_pressure(
    device_name: str,
) -> None:
    """Name the coefficients of performance and the discharge pressure."""
    # Arrange: Load the real legacy heat pump fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: The values are defined diagnostic sensors.
    for circuit in ("cooling", "dhw", "heating", "total"):
        cop = descriptions[f"heating.cop.{circuit}"]
        assert cop.translation_key == f"cop_{circuit}"
        assert cop.entity_category == "diagnostic"
    pressure = descriptions["heating.sensors.pressure.hotGas"]
    assert pressure.translation_key == "compressor_outlet_pressure"
    assert pressure.native_unit_of_measurement == "bar"


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
