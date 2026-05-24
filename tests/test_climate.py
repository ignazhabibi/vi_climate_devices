"""Tests for ViClimate climate entities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate import (
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.models import CommandResponse

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_climate_creation_and_services(hass: HomeAssistant, mock_client) -> None:
    """Test climate entity creation, attributes, and service calls."""
    # Arrange: Mock Config Entry and setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {
                "access_token": "mock",
                "refresh_token": "mock",
                "expires_at": 9999999999,
                "token_type": "Bearer",
            },
        },
    )
    entry.add_to_hass(hass)

    # Spy on set_feature to verify service calls.
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

        # Retrieve the climate entity.
        entity_id = "climate.vitocal250a_heating_circuit_0"
        state = hass.states.get(entity_id)
        assert state is not None

        # Assert: Verify initial attributes mapped from Vitocal250A fixture.
        # Mode: 'heating' maps to HVACMode.HEAT.
        # Active program: 'normalHeating' maps to preset_mode='home'.
        # Target Temp: 20.0 (from normalHeating program temperature).
        # Min Temp: 3.0, Max Temp: 37.0, Step: 1.0 (from normalHeating program control).
        assert state.state == HVACMode.HEAT
        assert float(state.attributes["temperature"]) == 20.0
        assert state.attributes["min_temp"] == 3.0
        assert state.attributes["max_temp"] == 37.0
        assert state.attributes["target_temp_step"] == 1.0
        assert state.attributes["preset_mode"] == PRESET_HOME
        assert sorted(state.attributes["preset_modes"]) == sorted(
            [PRESET_COMFORT, PRESET_ECO, PRESET_HOME, PRESET_SLEEP]
        )
        assert sorted(state.attributes["hvac_modes"]) == sorted(
            [HVACMode.HEAT, HVACMode.OFF]
        )

        # Act: Set temperature to 22.0.
        await hass.services.async_call(
            "climate",
            SERVICE_SET_TEMPERATURE,
            {"entity_id": entity_id, "temperature": 22.0},
            blocking=True,
        )

        # Assert: We expect set_feature to be called with the target program's feature name and 22.0.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert (
            args[1].name
            == "heating.circuits.0.operating.programs.normalHeating.temperature"
        )
        assert args[2] == 22.0

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Act: Set HVAC mode to HVACMode.OFF.
        await hass.services.async_call(
            "climate",
            SERVICE_SET_HVAC_MODE,
            {"entity_id": entity_id, "hvac_mode": HVACMode.OFF},
            blocking=True,
        )

        # Assert: We expect set_feature to write 'standby' to the operating modes active feature.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.circuits.0.operating.modes.active"
        assert args[2] == "standby"

        # Act & Assert: Attempting to set preset mode raises HomeAssistantError.
        with pytest.raises(HomeAssistantError, match="Preset modes are read-only"):
            await hass.services.async_call(
                "climate",
                SERVICE_SET_PRESET_MODE,
                {"entity_id": entity_id, "preset_mode": PRESET_COMFORT},
                blocking=True,
            )

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_climate_error_handling_and_rollback(
    hass: HomeAssistant, mock_client
) -> None:
    """Test climate temperature service error handling and state rollback."""
    # Arrange: Setup integration and simulate API error.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)

    async def mock_set_feature_error(device, feature, value):
        raise HomeAssistantError("Connection Error")

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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "climate.vitocal250a_heating_circuit_0"
        state = hass.states.get(entity_id)
        original_temp = float(state.attributes["temperature"])

        # Act: Set temperature to 25.0 (should fail).
        with pytest.raises(HomeAssistantError, match="Connection Error"):
            await hass.services.async_call(
                "climate",
                SERVICE_SET_TEMPERATURE,
                {"entity_id": entity_id, "temperature": 25.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert float(state.attributes["temperature"]) == original_temp

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
