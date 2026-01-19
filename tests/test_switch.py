"""Test ViClimate Switch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import Feature

from custom_components.vi_climate_devices.switch import SWITCH_TYPES, ViClimateSwitch


@pytest.mark.asyncio
async def test_switch_entity(hass: HomeAssistant):
    """Test switch entity properties and commands (setActive path)."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    # Mock Device & Feature
    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.oneTimeCharge"
    # Basic properties
    feature.properties = {"active": {"value": False}}
    # Commands available
    feature.commands = {
        "setActive": MagicMock(),
        "activate": MagicMock(),
        "deactivate": MagicMock(),
    }

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    # Mock features lookup (device.features is a list)
    device.features = [feature]

    coordinator.data = {"test_gw_0": device}

    # Instantiate
    desc = SWITCH_TYPES["heating.dhw.oneTimeCharge"]
    switch = ViClimateSwitch(coordinator, "test_gw_0", feature, desc)
    switch.hass = hass

    # Test Init
    assert switch.unique_id == "test_gw-0-heating.dhw.oneTimeCharge"
    assert switch.translation_key == "dhw_one_time_charge"

    # Test State Reading
    assert switch.is_on is False

    # Update state in mock
    feature.properties["active"]["value"] = True
    assert switch.is_on is True

    # Test Turn On (setActive path)
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()
    coordinator.client.execute_command.assert_called_with(
        feature, "setActive", {"active": True}
    )

    # Verify Optimistic Update happened on internal property
    assert feature.properties["active"]["value"] is True

    # Test Turn Off (setActive path)
    # Reset property for clean test of optimistic logic or just check call
    feature.properties["active"]["value"] = True
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_off()
    coordinator.client.execute_command.assert_called_with(
        feature, "setActive", {"active": False}
    )

    assert feature.properties["active"]["value"] is False


@pytest.mark.asyncio
async def test_switch_activate_deactivate_fallback(hass: HomeAssistant):
    """Test fallback to activate/deactivate if setActive is missing."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.oneTimeCharge"
    feature.properties = {"active": {"value": False}}
    # ONLY activate/deactivate available
    feature.commands = {"activate": MagicMock(), "deactivate": MagicMock()}

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    coordinator.data = {"test_gw_0": device}

    desc = SWITCH_TYPES["heating.dhw.oneTimeCharge"]
    switch = ViClimateSwitch(coordinator, "test_gw_0", feature, desc)
    switch.hass = hass

    # Turn On -> activate
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()
    coordinator.client.execute_command.assert_called_with(feature, "activate", {})

    # Turn Off -> deactivate
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_off()
    coordinator.client.execute_command.assert_called_with(feature, "deactivate", {})


@pytest.mark.asyncio
async def test_switch_hygiene_set_enabled(hass: HomeAssistant):
    """Test switch with setEnabled command (hygiene)."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.hygiene"
    feature.properties = {"enabled": {"value": False}}
    # Command setEnabled available
    feature.commands = {
        "setEnabled": MagicMock(),
    }
    # Mock params for setEnabled
    cmd_def = MagicMock()
    cmd_def.params = {"enabled": {"type": "boolean"}}
    feature.commands["setEnabled"] = cmd_def

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    coordinator.data = {"test_gw_0": device}

    desc = SWITCH_TYPES["heating.dhw.hygiene"]
    switch = ViClimateSwitch(coordinator, "test_gw_0", feature, desc)
    switch.hass = hass

    # Assert initial state
    assert switch.is_on is False
    assert switch.icon == "mdi:shield-check"

    # Turn On -> setEnabled(True)
    with patch.object(switch, "async_write_ha_state"):
        await switch.async_turn_on()

    coordinator.client.execute_command.assert_called_with(
        feature, "setEnabled", {"enabled": True}
    )
    # Verify optimistic update
    assert feature.properties["enabled"]["value"] is True
