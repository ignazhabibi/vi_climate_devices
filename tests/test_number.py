"""Tests for the Viessmann Heat number platform."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    SERVICE_SET_VALUE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.mock_client import MockViClient

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_number_creation_and_services(hass: HomeAssistant, mock_client):
    """Test number entity creation, values, and service calls."""
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

        # Test 1: Heating Curve Slope (Regex/Template Entity).

        # Verify initial state and attributes from fixture.
        # Fixture: Value=0.6, Min=0.2, Max=3.5, Step=0.1.
        slope = hass.states.get("number.vitocal250a_heating_circuit_0_curve_slope")
        assert slope is not None
        assert slope.state == "0.6"
        assert slope.attributes[ATTR_MIN] == 0.2
        assert slope.attributes[ATTR_MAX] == 3.5
        assert slope.attributes[ATTR_STEP] == 0.1

        # Verify precision on entity
        component = hass.data.get("number")
        entity_id = "number.vitocal250a_heating_circuit_0_curve_slope"
        entity = component.get_entity(entity_id)
        assert entity.suggested_display_precision == 1

        # Act: Set slope to 1.6.
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {
                "entity_id": "number.vitocal250a_heating_circuit_0_curve_slope",
                "value": 1.6,
            },
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.circuits.0.heating.curve.slope"
        assert args[2] == 1.6

        # Verify Optimistic Update (Option A).
        # State should update immediately to 1.6.
        slope = hass.states.get("number.vitocal250a_heating_circuit_0_curve_slope")
        assert slope.state == "1.6"

        # Test 2: DHW Target Temperature (Standard Entity).

        # Verify initial state (Fixture has 55.0).
        dhw_temp = hass.states.get("number.vitocal250a_dhw_target_temperature")
        assert dhw_temp is not None
        assert float(dhw_temp.state) == 55.0
        assert dhw_temp.attributes[ATTR_MIN] == 10.0
        assert dhw_temp.attributes[ATTR_MAX] == 60.0

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Act: Set DHW Temp to 45.0.
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {"entity_id": "number.vitocal250a_dhw_target_temperature", "value": 45.0},
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.dhw.temperature.main"
        assert args[2] == 45.0

        # Verify Optimistic Update.
        dhw_temp = hass.states.get("number.vitocal250a_dhw_target_temperature")
        assert float(dhw_temp.state) == 45.0

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_number_error_handling(hass: HomeAssistant):
    """Test number entity error handling and rollback (Option B)."""
    # Arrange: Setup integration with mock client.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    mock_client = MockViClient(device_name="Vitocal250A")
    # Simulate API Error.
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

        # Check Initial State.
        entity_id = "number.vitocal250a_heating_circuit_0_curve_slope"
        state = hass.states.get(entity_id)
        assert state.state == "0.6"

        # Act: Try to set value to 2.0 (Should fail).
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": entity_id, "value": 2.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        # State should still be 0.6, not 2.0.
        state = hass.states.get(entity_id)
        assert state.state == "0.6"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_number_api_rejection(hass: HomeAssistant):
    """Test number handling of API logical rejection (success=False)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    mock_client = MockViClient(device_name="Vitocal250A")

    # Simulate API Logical Failure.

    mock_client.set_feature = AsyncMock(
        return_value=SimpleNamespace(
            success=False, reason="Parameter out of range", message=None
        )
    )

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

        entity_id = "number.vitocal250a_heating_circuit_0_curve_slope"
        state = hass.states.get(entity_id)
        original_state = state.state  # "0.6"

        # Act: Try to set value.
        with pytest.raises(
            HomeAssistantError, match="Command rejected: Parameter out of range"
        ):
            await hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": entity_id, "value": 2.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state.state == original_state

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
