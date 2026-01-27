"""Tests for ViClimate analytics sensors."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_analytics_sensors_setup_and_data(hass: HomeAssistant, mock_client):
    """Test that analytics sensors are set up and receive data."""
    # Arrange: Mock Config Entry.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

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
        # Act: Setup Integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify total consumption sensor.
        # Entity ID derived from translation key "consumption_total" -> "Power Consumption Total Today"
        state = hass.states.get("sensor.vitocal250a_power_consumption_total_today")
        assert state is not None
        assert state.state == "41.8"
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["device_class"] == "energy"
        assert state.attributes["state_class"] == "total_increasing"

        # Assert: Verify heating consumption sensor.
        state = hass.states.get("sensor.vitocal250a_power_consumption_heating_today")
        assert state is not None
        assert state.state == "31.6"

        # Assert: Verify DHW consumption sensor.
        state = hass.states.get("sensor.vitocal250a_power_consumption_dhw_today")
        assert state is not None
        assert state.state == "10.2"
