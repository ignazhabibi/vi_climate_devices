"""Tests for ViClimate water heater entities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.water_heater import (
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
    STATE_ECO,
    STATE_PERFORMANCE,
    WaterHeaterEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.mock_client import MockViClient

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.water_heater import (
    FEATURE_MODE,
    FEATURE_TARGET_TEMP,
)


@pytest.mark.asyncio
async def test_water_heater_creation_and_services(hass: HomeAssistant, mock_client):
    """Test water heater entity creation and service calls."""
    # Arrange: Mock Config Entry.
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
    ):
        # Act: Load Integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Get the Water Heater Entity.
        entity_id = "water_heater.vitocal250a_dhw_water_heater"
        state = hass.states.get(entity_id)
        assert state is not None

        # Verify Initial Attributes from Fixture.
        # Temp: 55.0, Current: 46.8, Mode: efficient -> STATE_ECO.
        assert state.state == STATE_ECO
        assert float(state.attributes["current_temperature"]) == 46.8
        assert float(state.attributes["temperature"]) == 55.0
        assert state.attributes["min_temp"] == 10.0
        assert state.attributes["max_temp"] == 60.0
        assert state.attributes["supported_features"] == (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
        )

        # Act: Set Temperature to 45.0.
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_TEMPERATURE,
            {"entity_id": entity_id, "temperature": 45.0},
            blocking=True,
        )

        # Verify Service Call (Set Temp).
        # We expect set_feature to be called with "heating.dhw.temperature.main" and 45.0.
        # Note: Since set_feature is called multiple times if we chain tests, we check specific call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == FEATURE_TARGET_TEMP
        assert args[2] == 45.0

        # Verify Optimistic Update (Temp).
        state = hass.states.get(entity_id)
        assert float(state.attributes["temperature"]) == 45.0

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Act: Set Mode to STATE_PERFORMANCE.
        # Based on mapping, STATE_PERFORMANCE maps to ["comfort", "efficientWithMinComfort"].
        # Fixture has "efficientWithMinComfort" available, so it should use that.
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_OPERATION_MODE,
            {"entity_id": entity_id, "operation_mode": STATE_PERFORMANCE},
            blocking=True,
        )

        # Verify Service Call (Set Mode).
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == FEATURE_MODE
        assert args[2] == "efficientWithMinComfort"

        # Verify Optimistic Update (Mode).
        state = hass.states.get(entity_id)
        assert state.state == STATE_PERFORMANCE


@pytest.mark.asyncio
async def test_water_heater_error_handling(hass: HomeAssistant):
    """Test water heater error handling and rollback (Option B)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
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
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "water_heater.vitocal250a_dhw_water_heater"
        state = hass.states.get(entity_id)
        original_temp = float(state.attributes["temperature"])

        # Act: Try to set temperature (Should fail).
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "water_heater",
                SERVICE_SET_TEMPERATURE,
                {"entity_id": entity_id, "temperature": 40.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert float(state.attributes["temperature"]) == original_temp
