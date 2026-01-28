"""Tests for the Viessmann Heat binary sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_binary_sensor_values(hass: HomeAssistant, mock_client):
    """Test that binary sensors are created correctly from the fixture data."""
    # Arrange: Setup Viessmann integration with MockConfigEntry and MockViClient.
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
        # Act: Initialize the integration (setup entry).
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify a Standard Binary Sensor (DHW Active).
        # Fixture value is 'on' -> State 'on'.
        dhw_active = hass.states.get("binary_sensor.vitocal250a_heating_dhw_active")
        assert dhw_active is not None
        assert dhw_active.state == "on"

        # Assert: Verify a Template/Regex Binary Sensor (Circulation Pump).
        # Fixture value is 'on' -> State 'on'.
        pump = hass.states.get(
            "binary_sensor.vitocal250a_circulation_pump_heating_circuit_0"
        )
        assert pump is not None
        assert pump.state == "on"
        assert pump.attributes["device_class"] == "running"

        # Assert: Verify a Generic 'Off' Sensor (Compressor Active).
        # This confirms that 'off' values in the fixture are correctly mapped.
        compressor = hass.states.get("binary_sensor.vitocal250a_compressor_0_active")
        assert compressor is not None
        assert compressor.state == "off"

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_binary_sensor_discovers_generic_on_off_string(
    hass: HomeAssistant, mock_client
):
    """Test that a feature with 'on'/'off' string value IS created as a binary sensor.

    Using real fixture key: heating.dhw.status (value: "on")
    This feature is NOT in BINARY_SENSOR_TYPES, so it tests the generic discovery.
    """
    # Arrange: Configure the integration with the mock client fixture.
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
        entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "1", "token": "x"})
        entry.add_to_hass(hass)

        # Act: Initialize the integration to trigger discovery.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify the generic 'on' feature is discovered as a binary sensor.
        entity = hass.states.get("binary_sensor.vitocal250a_heating_dhw_status")
        assert entity is not None
        assert entity.state == "on"
        assert entity.attributes["viessmann_feature_name"] == "heating.dhw.status"

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
