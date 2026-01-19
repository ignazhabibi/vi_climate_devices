"""Tests for the Viessmann Heat binary sensor platform."""
from unittest.mock import MagicMock
import pytest
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator
from custom_components.vi_climate_devices.binary_sensor import ViClimateBinarySensor, BINARY_SENSOR_TEMPLATES
import re
import dataclasses

@pytest.mark.asyncio
async def test_binary_sensor_value_parsing(hass: HomeAssistant):
    """Test that binary sensor parses values correctly."""
    # Mock coordinator and device
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"
    device.model_id = "TestDevice"
    
    # Mock data return
    coordinator.data = {"serial_0": device}
    coordinator.last_update_success = True
    
    # Test cases: (raw_value, expected_state)
    test_cases = [
        ("on", True),
        ("active", True),
        ("1", True),
        (True, True),
        ("off", False),
        ("standby", False),
        ("0", False),
        (False, False),
    ]
    
    for raw_val, expected in test_cases:
        # Create a feature with the test value
        # Manually set the value
        mock_feature = MagicMock()
        mock_feature.name = "heating.circuits.0.circulation.pump"
        # Mock the value property directly on the object. 
        # In the actual code we access feature.value
        mock_feature.value = raw_val
        mock_feature.is_enabled = True
        
        device.features_flat = [mock_feature]
        
        # Initialize sensor
        # Initialize sensor via Template Lookup
        description = None
        for tmpl in BINARY_SENSOR_TEMPLATES:
             m = re.match(tmpl["pattern"], "heating.circuits.0.circulation.pump")
             if m:
                 base = tmpl["description"]
                 description = dataclasses.replace(
                     base,
                     key="heating.circuits.0.circulation.pump",
                     translation_key=base.translation_key # Generic key
                 )
                 break
        assert description is not None
        sensor = ViClimateBinarySensor(
            coordinator, 
            "serial_0", 
            "heating.circuits.0.circulation.pump", 
            description,
            translation_placeholders={"index": "0"}
        )
        
        # Verify
        assert sensor.is_on == expected, f"Failed for value: {raw_val}"

