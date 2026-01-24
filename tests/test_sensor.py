"""Tests for the Viessmann Heat sensor platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)


@pytest.mark.asyncio
async def test_sensor_creation(hass: HomeAssistant, mock_client):
    """Test that sensors are created correctly from the mock client."""
    # Setup Mock Returns for Discovery Flow

    # We need to construct a Mock Device that get_full_installation_status returns
    mock_device = MagicMock()
    mock_device.id = "0"
    mock_device.gateway_serial = "mock_serial"
    mock_device.model_id = "TestDevice"

    class MockFeature:
        def __init__(self, name, value):
            self.name = name
            self.value = value
            self.properties = {}
            self.is_writable = False
            self.is_enabled = True
            self.control = None

    # Mock Feature list (flat)
    mock_device.features = [MockFeature("heating.sensors.temperature.outside", 16.7)]

    # Mock get_full_installation_status
    mock_client.get_full_installation_status = AsyncMock(return_value=[mock_device])

    # Mock update_device
    mock_client.update_device = AsyncMock(return_value=mock_device)

    # Initialize the coordinator with the mock client
    coordinator = ViClimateDataUpdateCoordinator(hass, client=mock_client)

    # Refresh data
    await coordinator.async_refresh()

    assert coordinator.last_update_success

    # Verify data is populated
    assert coordinator.data is not None
    assert len(coordinator.data) > 0

    device = next(iter(coordinator.data.values()))  # Assuming first device

    # Check if the feature exists in the features list
    outside_temp = next(
        (f for f in device.features if f.name == "heating.sensors.temperature.outside"),
        None,
    )
    assert outside_temp is not None
    assert outside_temp.value == 16.7
