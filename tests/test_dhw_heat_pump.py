"""Tests for the defined entities of domestic hot water heat pumps."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import Feature, FixtureViClient

from custom_components.vi_climate_devices.sensor import (
    _discover_realtime_sensors,
    _get_auto_discovery_description,
)

CYLINDER_LAYERS = {
    "heating.dhw.sensors.temperature.hotWaterStorage.top": (
        "dhw_storage_top_temperature",
        "heating.dhw.sensors.temperature.dhwCylinder.top",
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage.middle": (
        "dhw_storage_middle_temperature",
        "heating.dhw.sensors.temperature.dhwCylinder.middle",
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage.bottom": (
        "dhw_storage_bottom_temperature",
        "heating.dhw.sensors.temperature.dhwCylinder.bottom",
    ),
}


@pytest.mark.asyncio
async def test_vitocal_262a_defines_cylinder_and_comfort_sensors() -> None:
    """Name the cylinder layers, the anode current, and the comfort minimum."""
    # Arrange: Load the Vitocal 262-A domestic hot water heat pump fixture.
    device = (
        await FixtureViClient("Vitocal262A-T2H-R290").get_full_installation_status(
            "99999"
        )
    )[0]

    # Act: Discover the fixture's sensors.
    entities = {
        entity.entity_description.key: entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: Each layer is defined once and reads the dhwCylinder successor.
    for feature_name, (translation_key, successor) in CYLINDER_LAYERS.items():
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.extra_state_attributes["viessmann_feature_name"] == successor
        assert successor not in entities

    # Assert: The anode current and the comfort minimum are diagnostic sensors.
    anode = entities["heating.dhw.sensors.dhwCylinder.rustSurveillance.anode"]
    assert anode.entity_description.translation_key == "dhw_anode_current"
    assert anode.native_value == 0.804
    comfort = entities["heating.configuration.dhw.temperature.minimumComfort"]
    assert (
        comfort.entity_description.translation_key == "dhw_minimum_comfort_temperature"
    )
    assert "heating.dhw.configuration.temperature.minimumComfort" not in entities


def test_unknown_milliampere_feature_gets_the_current_unit() -> None:
    """Map an auto-discovered milliampere value to a current sensor."""
    # Arrange: Build a milliampere feature without a defined entity.
    feature = Feature(
        name="heating.custom.current",
        value=0.5,
        unit="milliAmpere",
        is_enabled=True,
        is_ready=True,
    )

    # Act: Describe the fallback sensor.
    description = _get_auto_discovery_description(feature)

    # Assert: The current unit and device class are mapped.
    assert description.native_unit_of_measurement == "mA"
    assert description.device_class == "current"
