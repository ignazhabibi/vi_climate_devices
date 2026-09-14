"""Tests for the Viessmann Heat binary sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import ViClimateBinarySensor
from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_binary_sensor_handles_device_removed_by_refresh() -> None:
    """Expose an unavailable state when a refreshed device is no longer present."""
    # Arrange: Build an auto-discovered entity from a fixture device.
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature = device.features[0]
    coordinator = MagicMock(data={"device": device})
    entity = ViClimateBinarySensor(
        coordinator,
        "device",
        feature.name,
        BinarySensorEntityDescription(key=feature.name),
    )

    # Act: Simulate a refresh which no longer includes the device.
    coordinator.data = {}

    # Assert: Entity state and device metadata safely become unavailable.
    assert entity.feature_data is None
    assert entity.is_on is None
    assert entity.device_info is None
    assert entity.available is False

    # Act and assert: An entity cannot be created for an absent device.
    with pytest.raises(ValueError, match="Device missing"):
        ViClimateBinarySensor(
            MagicMock(data={}),
            "missing",
            feature.name,
            BinarySensorEntityDescription(key=feature.name),
        )


@pytest.mark.asyncio
async def test_binary_sensor_values(hass: HomeAssistant, mock_client):
    """Test that binary sensors are created correctly from the fixture data."""
    # Arrange: Setup Viessmann integration with MockConfigEntry.
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

        # Assert: Verify a Standard Binary Sensor (One Time Charge).
        # Fixture value is 'off' -> State 'off'.
        dhw_active = hass.states.get("binary_sensor.vitocal250a_one_time_charge")
        assert dhw_active is not None
        assert dhw_active.state == "off"

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
    # Arrange: Setup integration and mock client fixture.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "1", "token": "x"})
    entry.add_to_hass(hass)

    # Note: MockClient provided by fixture.

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
        # Act: Initialize the integration to trigger discovery.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify the generic 'on' feature is discovered as a binary sensor.
        registry = er.async_get(hass)

        # heating.dhw.status (auto-discovered) - Vitocal250A is not E3_Vitocal_16
        # so this should be enabled by default
        reg_entry = registry.async_get("binary_sensor.vitocal250a_dhw_status")
        assert reg_entry is not None
        # Vitocal250A is not in TESTED_DEVICES, so should be enabled
        assert reg_entry.disabled_by is None

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
