
from custom_components.vi_climate_devices.sensor import ViClimateSensor, SENSOR_TEMPLATES
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator
from homeassistant.components.sensor import SensorEntityDescription
import pytest
from unittest.mock import MagicMock
import re
import dataclasses

@pytest.mark.asyncio
async def test_sensor_dynamic_generation(hass: HomeAssistant):
    """Test dynamic sensor generation from templates."""
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"
    device.model_id = "Device"
    coordinator.data = {"serial_0": device}
    
    feature_name = "heating.circuits.1.sensors.temperature.supply"
    
    # Simulate Discovery Logic
    description = None
    placeholders = None
    
    for tmpl in SENSOR_TEMPLATES:
        match = re.match(tmpl["pattern"], feature_name)
        if match:
            index = match.group(1)
            base = tmpl["description"]
            description = dataclasses.replace(
                base,
                key=feature_name,
                translation_key=base.translation_key
            )
            placeholders = {"index": index}
            break
            
    assert description is not None
    assert description.translation_key == "heating_circuit_supply_temperature"
    assert placeholders == {"index": "1"}
    
    # Instantiate
    sensor = ViClimateSensor(coordinator, "serial_0", feature_name, description, translation_placeholders=placeholders)
    
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
    description = SensorEntityDescription(key=feature_name, translation_key="outside_temperature")
    
    # Instantiate with DEFAULT placeholders (None in signature, but should be converted to {})
    sensor = ViClimateSensor(coordinator, "serial_0", feature_name, description)
    
    # Verify it is converted to empty dict
    assert sensor._attr_translation_placeholders == {}
    assert sensor._attr_translation_placeholders is not None
