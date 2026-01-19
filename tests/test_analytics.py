"""Tests for the Viessmann Heat analytics."""
from unittest.mock import MagicMock, AsyncMock
import pytest
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator, ViClimateAnalyticsCoordinator
from custom_components.vi_climate_devices.sensor import ANALYTICS_Types

@pytest.mark.asyncio
async def test_analytics_sensor_setup_and_data(hass: HomeAssistant):
    """Test that analytics sensors are set up and receive data."""
    # 1. Setup Mock Client
    mock_client = AsyncMock()
    
    # 2. Main Coordinator Setup
    # Create a heating device
    heating_device = MagicMock()
    heating_device.id = "0"
    heating_device.gateway_serial = "serial"
    heating_device.device_type = "heating" # CRITICAL Property
    heating_device.model_id = "Vitodens"
    
    main_coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    # New Key Structure
    main_coordinator.data = {"serial_0": heating_device}
    main_coordinator.last_update_success = True
    
    # 3. Analytics Coordinator Setup
    analytics_coordinator = ViClimateAnalyticsCoordinator(hass, mock_client, main_coordinator)
    
    # Mock get_today_consumption return
    # Feature(name, value, properties, commands, is_enabled, is_ready) or similar order.
    # Looking at the error "missing 2 required positional arguments: 'is_enabled' and 'is_ready'"
    # and likely properties/commands are optional or positional?
    # Actually, inspecting library or error implicitly:
    # If I just used name, value, it failed.
    # Let's use kwargs or positional if we know them.
    # Mocking Feature entirely might be safer if constructor is complex, but let's try pos args.
    # Assuming: name, value, properties, commands, is_enabled, is_ready
    
    class MockFeature:
        def __init__(self, name, value):
            self.name = name
            self.value = value
            self.is_enabled = True

    feat1 = MockFeature("analytics.heating.power.consumption.total", 10.5)
    feat2 = MockFeature("analytics.heating.power.consumption.heating", 8.0)
    feat3 = MockFeature("analytics.heating.power.consumption.dhw", 2.5)
    
    mock_client.get_consumption.return_value = [feat1, feat2, feat3]
    
    # Refresh Analytics
    await analytics_coordinator._async_update_data()
    # Manually populate data since _async_update_data internal doesn't set self.data on the mock?
    # Wait, calling the method returns the dict. The coordinator infrastructure normally sets self.data.
    # Let's call async_refresh logic or just set data for the test of the ENTITY.
    
    # But first, verify the COORDINATOR logic finds the device
    data = await analytics_coordinator._async_update_data()
    assert data is not None
    # Data is now nested by device key
    assert "serial_0" in data
    device_data = data["serial_0"]
    assert "analytics.heating.power.consumption.total" in device_data
    assert device_data["analytics.heating.power.consumption.total"].value == 10.5
    
    # Check that it called client with correct args
    assert mock_client.get_consumption.called
    args, kwargs = mock_client.get_consumption.call_args
    assert args[0] == heating_device # Device is 1st arg
    assert kwargs["metric"] == "summary"

    # 4. Entity Setup
    analytics_coordinator.data = data
    analytics_coordinator.last_update_success = True
    
    # Retrieve the class to test (ViClimateConsumptionSensor)
    # We can import it or use a simplified test of logic
    from custom_components.vi_climate_devices.sensor import ViClimateConsumptionSensor
    
    desc = ANALYTICS_Types["analytics.heating.power.consumption.total"]
    sensor = ViClimateConsumptionSensor(analytics_coordinator, heating_device, desc)
    
    # Verify State
    assert sensor.native_value == 10.5
    assert sensor.available is True
    assert sensor.unique_id == "serial-0-analytics.heating.power.consumption.total"
