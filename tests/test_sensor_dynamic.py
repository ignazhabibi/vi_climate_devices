from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.sensor import (
    ViClimateSensor,
    _get_sensor_entity_description,
)


@pytest.mark.asyncio
async def test_sensor_dynamic_generation(hass: HomeAssistant):
    """Test dynamic sensor generation using the helper function."""
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"
    device.model_id = "Device"
    coordinator.data = {"serial_0": device}

    feature_name = "heating.circuits.1.sensors.temperature.supply"

    # Use helper function
    result = _get_sensor_entity_description(feature_name)
    assert result is not None
    description, placeholders = result

    assert description.translation_key == "heating_circuit_supply_temperature"
    assert placeholders == {"index": "1"}
    assert description.key == feature_name

    # Instantiate
    sensor = ViClimateSensor(
        coordinator,
        "serial_0",
        feature_name,
        description,
        translation_placeholders=placeholders,
    )

    assert sensor.translation_key == "heating_circuit_supply_temperature"
    assert sensor._attr_translation_placeholders == {"index": "1"}


@pytest.mark.asyncio
async def test_sensor_static_no_placeholders(hass: HomeAssistant):
    """Test static sensor instantiation with default (None) placeholders."""
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"
    device.model_id = "Device"
    coordinator.data = {"serial_0": device}

    feature_name = "heating.sensors.temperature.outside"
    description = SensorEntityDescription(
        key=feature_name, translation_key="outside_temperature"
    )

    # Instantiate with DEFAULT placeholders (None in signature, but should be converted to {})
    sensor = ViClimateSensor(coordinator, "serial_0", feature_name, description)

    # Verify it is converted to empty dict
    assert sensor._attr_translation_placeholders == {}
    assert sensor._attr_translation_placeholders is not None
