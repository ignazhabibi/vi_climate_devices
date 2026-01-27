"""Tests for the Viessmann Heat sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vi_climate_devices.const import DOMAIN


async def _setup_integration(hass: HomeAssistant, mock_client):
    """Helper to setup the integration with the provided mock client."""
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
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_sensor_values(hass: HomeAssistant, mock_client):
    """Test that sensors are created correctly from the fixture data."""
    # Act: Setup the integration with the global mock_client (Vitocal250A).
    await _setup_integration(hass, mock_client)

    # Assert: Verify a Standard Sensor (Outside Temperature).
    # Fixture value is 12.2 -> State '12.2'.
    outside_temp = hass.states.get("sensor.vitocal250a_outside_temperature")
    assert outside_temp is not None
    assert outside_temp.state == "12.2"
    assert outside_temp.attributes["unit_of_measurement"] == "°C"

    # Assert: Verify a Template/Regex Sensor (Compressor Speed).
    # Checks if regex matches 'heating.compressors.0.speed.current' correctly.
    compressor_speed = hass.states.get("sensor.vitocal250a_compressor_0_speed")
    assert compressor_speed is not None
    assert compressor_speed.state == "0"
    assert (
        compressor_speed.attributes["friendly_name"] == "Vitocal250A Compressor 0 Speed"
    )

    # Assert: Verify a Complex Data Sensor (Messages Info).
    # Ensures that large lists are not set as state, but preserved in attributes.
    messages_info = hass.states.get("sensor.vitocal250a_device_messages_info_raw")
    assert messages_info is not None
    assert messages_info.state == "Complex Data"
    assert "raw_value" in messages_info.attributes
    assert isinstance(messages_info.attributes["raw_value"], dict)


@pytest.mark.asyncio
async def test_no_duplicate_entity_creation(hass: HomeAssistant, mock_client):
    """Ensure entities defined in SENSOR_TYPES or SENSOR_TEMPLATES are not also created as generic fallback sensors."""
    await _setup_integration(hass, mock_client)

    # Assert: Verify duplicate prevention for Defined Features.
    # The specific entity 'outside_temperature' should exist, but the generic fallback 'heating_sensors_...' should not.
    assert hass.states.get("sensor.vitocal250a_outside_temperature") is not None
    assert (
        hass.states.get("sensor.vitocal250a_heating_sensors_temperature_outside")
        is None
    )

    # Assert: Verify duplicate prevention for Template Features.
    # The template entity 'compressor_0_speed' should exist, but the generic fallback 'heating_compressors_...' should not.
    assert hass.states.get("sensor.vitocal250a_compressor_0_speed") is not None
    assert (
        hass.states.get("sensor.vitocal250a_heating_compressors_0_speed_current")
        is None
    )
