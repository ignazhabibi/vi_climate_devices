"""Tests for the defined entities of gas boilers."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from vi_api_client import Feature, FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    _discover_binary_sensors,
)
from custom_components.vi_climate_devices.sensor import (
    _discover_realtime_sensors,
    _get_auto_discovery_description,
)

GAS_CONSUMPTION_FEATURES = {
    "heating.gas.consumption.summary.dhw.currentDay": (
        "gas_consumption_dhw_current_day"
    ),
    "heating.gas.consumption.summary.dhw.currentYear": (
        "gas_consumption_dhw_current_year"
    ),
    "heating.gas.consumption.summary.heating.currentDay": (
        "gas_consumption_heating_current_day"
    ),
    "heating.gas.consumption.summary.heating.currentYear": (
        "gas_consumption_heating_current_year"
    ),
}


@pytest.mark.parametrize(
    "device_name", ["Vitodens100W", "Vitodens200W", "Vitodens300W-B3HF-19"]
)
@pytest.mark.asyncio
async def test_gas_consumption_is_defined_for_day_and_year(device_name: str) -> None:
    """Expose daily and yearly gas consumption and hide the other periods."""
    # Arrange: Load the real boiler fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: Day and year are defined resetting gas counters in m³.
    for feature_name, translation_key in GAS_CONSUMPTION_FEATURES.items():
        description = descriptions[feature_name]
        assert description.translation_key == translation_key
        assert description.native_unit_of_measurement == "m³"
        assert description.device_class == "gas"
        assert description.state_class == SensorStateClass.TOTAL_INCREASING

    # Assert: Other periods and the raw history arrays create no sensors.
    other_gas_features = {
        key
        for key in descriptions
        if key.startswith("heating.gas.consumption.")
        and key not in GAS_CONSUMPTION_FEATURES
    }
    assert not other_gas_features


@pytest.mark.asyncio
async def test_burner_and_hydraulic_separator_are_defined() -> None:
    """Name the burner state and the hydraulic separator temperature."""
    # Arrange: Load the E3 Vitodens 300-W fixture.
    device = (
        await FixtureViClient("Vitodens300W-B3HF-19").get_full_installation_status(
            "99999"
        )
    )[0]
    coordinator = MagicMock(data={"device": device})

    # Act: Discover the fixture's binary sensors and sensors.
    binary_descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_binary_sensors(coordinator)
    }
    sensor_descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_realtime_sensors(coordinator)
    }

    # Assert: Both features are defined entities.
    burner = binary_descriptions["heating.burners.0.active"]
    assert burner.translation_key == "burner_active"
    assert burner.device_class == "running"
    separator = sensor_descriptions["heating.sensors.temperature.hydraulicSeparator"]
    assert separator.translation_key == "hydraulic_separator_temperature"
    assert separator.native_unit_of_measurement == "°C"


def test_unknown_gas_volume_feature_gets_the_gas_unit() -> None:
    """Map an auto-discovered gas volume to m³ without a state class."""
    # Arrange: Build a gas volume feature without a defined entity.
    feature = Feature(
        name="heating.gas.consumption.custom",
        value=1.5,
        unit="cubicMeter",
        is_enabled=True,
        is_ready=True,
    )

    # Act: Describe the fallback sensor.
    description = _get_auto_discovery_description(feature)

    # Assert: The gas unit is kept without counter semantics.
    assert description.native_unit_of_measurement == "m³"
    assert description.device_class == "gas"
    assert description.state_class is None
