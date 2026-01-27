"""Tests for the Viessmann Heat sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.mock_client import MockViClient

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_sensor_values(hass: HomeAssistant):
    """Test that sensors are created correctly from the fixture data."""
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

    # Initialize MockViClient with a real fixture (Vitocal250A).
    mock_client = MockViClient(device_name="Vitocal250A")

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
        # Act: Initialize the integration (setup entry).
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

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
            compressor_speed.attributes["friendly_name"]
            == "Vitocal250A Compressor 0 Speed"
        )

        # Assert: Verify a Complex Data Sensor (Messages Info).
        # Ensures that large lists are not set as state, but preserved in attributes.
        messages_info = hass.states.get("sensor.vitocal250a_device_messages_info_raw")
        assert messages_info is not None
        assert messages_info.state == "Complex Data"
        assert "raw_value" in messages_info.attributes
        assert isinstance(messages_info.attributes["raw_value"], dict)
