"""Tests for the Viessmann Heat sensor platform."""
from unittest.mock import MagicMock
import pytest
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator

@pytest.mark.asyncio
async def test_sensor_creation(hass: HomeAssistant, mock_client):
    """Test that sensors are created correctly from the mock client."""
    # Setup Mock Returns for Discovery Flow using AsyncMock to override real methods
    from unittest.mock import AsyncMock
    
    # Mock Installation Object
    mock_install = MagicMock()
    mock_install.id = "123"
    mock_client.get_installations = AsyncMock(return_value=[mock_install])
    
    # Mock Gateway Object
    mock_gw = MagicMock()
    mock_gw.serial = "mock_serial"
    mock_client.get_gateways = AsyncMock(return_value=[mock_gw])
    
    # We need to construct a Mock Device that get_devices returns
    mock_device = MagicMock()
    mock_device.id = "0"
    mock_device.gateway_serial = "mock_serial"

    class MockFeature:
        def __init__(self, name, value):
            self.name = name
            self.value = value
            self.properties = {} 
            
    # Mock Feature flat list
    mock_device.features_flat = [MockFeature("heating.sensors.temperature.outside", 16.7)]
    mock_device.features = [] # Coordinator iterates this for commands, safe to be empty for sensor test
     
    mock_client.get_devices = AsyncMock(return_value=[mock_device])
    mock_client.update_device = AsyncMock(return_value=mock_device) # Return same device on update
    
    # Initialize the coordinator with the mock client
    coordinator = ViClimateDataUpdateCoordinator(hass, client=mock_client)
    
    # Refresh data
    await coordinator.async_refresh()
    
    assert coordinator.last_update_success
    
    # Verify data is populated
    assert coordinator.data is not None
    assert len(coordinator.data) > 0
    
    device = list(coordinator.data.values())[0] # Assuming first device
    
    # Check if the feature exists in the flattened list
    outside_temp = next((f for f in device.features_flat if f.name == "heating.sensors.temperature.outside"), None)
    assert outside_temp is not None
    assert outside_temp.value == 16.7 # Value from Vitodens200W profile
