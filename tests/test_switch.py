"""Test ViClimate Switch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import Feature

from custom_components.vi_climate_devices.switch import SWITCH_TYPES, ViClimateSwitch


@pytest.mark.asyncio
async def test_switch_entity(hass: HomeAssistant):
    """Test switch entity properties and commands."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    coordinator.client.set_feature = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    # Mock Device & Feature
    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.oneTimeCharge"
    feature.value = False  # Initial state

    # Switch.py uses feature.value

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    device.get_feature.return_value = feature  # Mock lookup

    coordinator.data = {"test_gw_0": device}

    # Instantiate
    desc = SWITCH_TYPES["heating.dhw.oneTimeCharge"]
    switch = ViClimateSwitch(coordinator, "test_gw_0", feature.name, desc)
    switch.hass = hass

    # Test Init
    assert switch.unique_id == "test_gw-0-heating.dhw.oneTimeCharge"
    assert switch.translation_key == "dhw_one_time_charge"

    # Test State Reading
    assert switch.is_on is False

    # Update state in mock
    feature.value = True
    assert switch.is_on is True

    # Test Turn On
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()

    # Expect client.set_feature
    coordinator.client.set_feature.assert_called_with(device, feature, True)

    # Test Turn Off
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_off()

    coordinator.client.set_feature.assert_called_with(device, feature, False)


@pytest.mark.asyncio
async def test_switch_hygiene_set_enabled(hass: HomeAssistant):
    """Test switch with hygiene (enabled property mapped automatically by lib)."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    coordinator.client.set_feature = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.hygiene"
    feature.value = False

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    device.get_feature.return_value = feature

    coordinator.data = {"test_gw_0": device}

    desc = SWITCH_TYPES["heating.dhw.hygiene"]
    switch = ViClimateSwitch(coordinator, "test_gw_0", feature.name, desc)
    switch.hass = hass

    # Assert initial state
    assert switch.is_on is False
    assert switch.icon == "mdi:shield-check"

    # Turn On
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()

    coordinator.client.set_feature.assert_called_with(device, feature, True)
