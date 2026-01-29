"""Tests for the Viessmann Heat sensor platform."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, Feature

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
        patch("custom_components.vi_climate_devices.HAAuth"),
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

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_no_duplicate_entity_creation(hass: HomeAssistant, mock_client):
    """Ensure entities defined in SENSOR_TYPES or SENSOR_TEMPLATES are not also created as generic fallback sensors."""
    await _setup_integration(hass, mock_client)

    # Assert: Verify duplicate prevention for Defined Features.
    # The specific entity 'outside_temperature' should exist, but the generic fallback 'heating_sensors_...' should not.
    assert hass.states.get("sensor.vitocal250a_outside_temperature") is not None
    assert hass.states.get("sensor.vitocal250a_sensors_temperature_outside") is None

    # Assert: Verify duplicate prevention for Template Features.
    # The template entity 'compressor_0_speed' should exist, but the generic fallback 'heating_compressors_...' should not.
    assert hass.states.get("sensor.vitocal250a_compressor_0_speed") is not None
    assert (
        hass.states.get("sensor.vitocal250a_heating_compressors_0_speed_current")
        is None
    )

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_auto_discovery_unit_mapping(hass: HomeAssistant, mock_client):
    """Test that auto-discovered sensors get correct unit mapping based on feature.unit."""
    # Arrange: Create a mock device with features that have specific units but are NOT in SENSOR_TYPES.

    # Create Features with various units
    feat_celsius = Feature(
        name="test.unknown.temp",
        value=20.5,
        is_enabled=True,
        is_ready=True,
        unit="celsius",
    )

    feat_bar = Feature(
        name="test.unknown.pressure",
        value=1.5,
        is_enabled=True,
        is_ready=True,
        unit="bar",
    )

    feat_energy = Feature(
        name="test.unknown.energy",
        value=100.0,
        is_enabled=True,
        is_ready=True,
        unit="kilowattHour",
    )

    feat_flow = Feature(
        name="test.unknown.flow",
        value=500,
        is_enabled=True,
        is_ready=True,
        unit="liter/hour",
    )

    # Create Device
    mock_device = Device(
        id="0",
        gateway_serial="mock_gateway",
        installation_id=123,
        features=[feat_celsius, feat_bar, feat_energy, feat_flow],
        model_id="MockDevice",
        device_type="heating",
        status="online",
    )

    # Arrange: Patch the mock client to return our custom device.

    with (
        patch.object(
            mock_client, "get_full_installation_status", return_value=[mock_device]
        ),
        patch.object(mock_client, "update_device", return_value=mock_device),
    ):
        # Act
        await _setup_integration(hass, mock_client)

        registry = er.async_get(hass)

        # Assert: Check Celsius Mapping via Registry
        entry_temp = registry.async_get("sensor.mockdevice_test_unknown_temp")
        assert entry_temp is not None
        assert entry_temp.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert entry_temp.original_device_class == "temperature"

        # Assert: Check Bar Mapping
        entry_pressure = registry.async_get("sensor.mockdevice_test_unknown_pressure")
        assert entry_pressure is not None
        assert entry_pressure.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert entry_pressure.original_device_class == "pressure"

        # Assert: Check Energy Mapping
        entry_energy = registry.async_get("sensor.mockdevice_test_unknown_energy")
        assert entry_energy is not None
        assert entry_energy.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert entry_energy.original_device_class == "energy"

        # Assert: Check Flow Mapping
        entry_flow = registry.async_get("sensor.mockdevice_test_unknown_flow")
        assert entry_flow is not None
        assert entry_flow.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        # Flow doesn't have a default device class in our auto-discovery yet

        # Cleanup: Unload the integration to prevent thread leaks.
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_sensor_ignores_generic_on_off_string(hass: HomeAssistant, mock_client):
    """Test that a feature with 'on'/'off' string value is NOT created as a sensor.

    Using real fixture key: heating.dhw.status (value: "on")
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

        # Assert: Sensor should NOT exist for 'heating.dhw.status'.
        # The feature returns "on", so it should be picked up by binary_sensor, NOT sensor.
        sensor_entity = hass.states.get("sensor.vitocal250a_heating_dhw_status")
        assert sensor_entity is None

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
