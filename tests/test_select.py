"""Tests for the Viessmann Heat select platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.select import SERVICE_SELECT_OPTION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.models import CommandResponse

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_select_creation_and_services(hass: HomeAssistant, mock_client):
    """Test select entity creation and service calls."""
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

    # Spy on set_feature to verify service calls (returns tuple in v1.0.0).
    async def mock_set_feature(device, feature, value):
        response = CommandResponse(
            success=True, message=None, reason="COMMAND_EXECUTION_SUCCESS"
        )
        return (response, device)

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature)

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

        # Test 1: DHW Mode (Standard Entity).

        # Verify initial state and options from fixture.
        dhw_mode = hass.states.get("select.vitocal250a_dhw_mode")
        assert dhw_mode is not None
        assert dhw_mode.state == "efficient"
        assert "efficientWithMinComfort" in dhw_mode.attributes["options"]

        # Act: Select 'efficientWithMinComfort' option.
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {
                "entity_id": "select.vitocal250a_dhw_mode",
                "option": "efficientWithMinComfort",
            },
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.dhw.operating.modes.active"
        assert args[2] == "efficientWithMinComfort"

        # Verify Optimistic Update (Option A).
        dhw_mode = hass.states.get("select.vitocal250a_dhw_mode")
        assert dhw_mode.state == "efficientWithMinComfort"

        # Test 2: Circuit Mode (Circuit 0).

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Verify initial state.
        circuit_mode = hass.states.get(
            "select.vitocal250a_heating_circuit_0_operation_mode"
        )
        assert circuit_mode is not None
        assert circuit_mode.state == "heating"

        # Act: Select 'standby' option.
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {
                "entity_id": "select.vitocal250a_heating_circuit_0_operation_mode",
                "option": "standby",
            },
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.circuits.0.operating.modes.active"
        assert args[2] == "standby"

        # Verify Optimistic Update.
        circuit_mode = hass.states.get(
            "select.vitocal250a_heating_circuit_0_operation_mode"
        )
        assert circuit_mode.state == "standby"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_select_error_handling(hass: HomeAssistant, mock_client):
    """Test select error handling and rollback (Option B)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    # Simulate API Error.
    async def mock_set_feature_error(device, feature, value):
        raise HomeAssistantError("API Error")

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature_error)

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

        # Initial State Check.
        entity_id = "select.vitocal250a_dhw_mode"
        state = hass.states.get(entity_id)
        original_state = state.state
        assert original_state == "efficient"

        # Act: Try to change option (Should fail).
        target_option = "off"

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "select",
                SERVICE_SELECT_OPTION,
                {"entity_id": entity_id, "option": target_option},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state.state == original_state

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_select_api_rejection(hass: HomeAssistant, mock_client):
    """Test select handling of API logical rejection (success=False)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    # Simulate API Logical Failure.

    async def mock_set_feature_rejection(device, feature, value):
        response = CommandResponse(
            success=False, message="Rejected", reason="DEVICE_COMMUNICATION_ERROR"
        )
        return (response, device)

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature_rejection)

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
        # Act: Initialize.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "select.vitocal250a_dhw_mode"
        state = hass.states.get(entity_id)
        original_state = state.state  # "efficient"

        # Act: Try to change option.
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "select",
                SERVICE_SELECT_OPTION,
                {"entity_id": entity_id, "option": "comfort"},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state.state == original_state

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
