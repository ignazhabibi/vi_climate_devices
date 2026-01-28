"""Tests for the Viessmann Heat switch platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.mock_client import MockViClient

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_switch_creation_and_services(hass: HomeAssistant, mock_client):
    """Test switch creation and turn_on/turn_off service calls."""
    # Arrange: Mock Config Entry.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "expires_at": 3800000000,
                "token_type": "Bearer",
            },
        },
    )
    entry.add_to_hass(hass)

    # Spy on set_feature to verify service calls.
    # Note: We must patch it on the instance that ends up in the coordinator.
    mock_client.set_feature = AsyncMock()

    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=mock_client,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            return_value=None,
        ),
        patch("custom_components.vi_climate_devices.HAAuth"),
    ):
        # Act: Load Integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Test 1: Initial State (Offline/Fixture Data).

        # Verify 'heating.dhw.hygiene.enabled' (Standard Switch).
        # Fixture value is false/off.
        hygiene_switch = hass.states.get("switch.vitocal250a_dhw_hygiene")
        assert hygiene_switch is not None
        assert hygiene_switch.state == STATE_OFF

        # Verify 'heating.dhw.oneTimeCharge.active' (Standard Switch).
        # Fixture value is false/off.
        one_time_charge = hass.states.get("switch.vitocal250a_one_time_dhw_charge")
        assert one_time_charge is not None
        assert one_time_charge.state == STATE_OFF

        # Test 2: Service Calls (turn_on).

        # Call turn_on service.
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.vitocal250a_dhw_hygiene"},
            blocking=True,
        )

        # Verify MockViClient.set_feature was called.
        # Args: (Device, Feature, Value).
        # We need to verify it was called with value=True.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        # args[0] is Device, args[1] is Feature, args[2] is Value.
        assert args[1].name == "heating.dhw.hygiene.enabled"
        assert args[2] is True

        # Verify Optimistic State Update.
        # The switch should match the requested state immediately.
        hygiene_switch = hass.states.get("switch.vitocal250a_dhw_hygiene")
        assert hygiene_switch.state == "on"

        # Test 3: Service Calls (turn_off).

        # Reset mock.
        mock_client.set_feature.reset_mock()

        # Call turn_off service.
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.vitocal250a_dhw_hygiene"},
            blocking=True,
        )

        # Verify set_feature called with value=False.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.dhw.hygiene.enabled"
        assert args[2] is False

        # Verify Optimistic State Update.
        hygiene_switch = hass.states.get("switch.vitocal250a_dhw_hygiene")
        assert hygiene_switch.state == STATE_OFF

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_switch_error_handling(hass: HomeAssistant):
    """Test switch error handling and rollback."""
    # Arrange: Setup with a mock client that raises an error.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    mock_client = MockViClient(device_name="Vitocal250A")
    # Simulate an API error during set_feature.

    # set_feature will raise an exception when called.
    mock_client.set_feature = AsyncMock(side_effect=HomeAssistantError("API Error"))

    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=mock_client,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            return_value=None,
        ),
        patch("custom_components.vi_climate_devices.HAAuth"),
    ):
        # Act: Initialize integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Initial State Check (should be OFF according to fixture).
        switch_id = "switch.vitocal250a_dhw_hygiene"
        assert hass.states.get(switch_id).state == STATE_OFF

        # Act: Call turn_on service which will fail.
        # We expect a HomeAssistantError to be raised to the caller.
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": switch_id},
                blocking=True,
            )

        # Assert: State Rollback.
        # The switch should NOT be stuck in 'on' state; it should revert to 'off'.
        assert hass.states.get(switch_id).state == STATE_OFF

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
