"""Test discovery ignore list functionality."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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
        patch("custom_components.vi_climate_devices.HAAuth"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_auto_discovery_ignore_list(hass: HomeAssistant, mock_client):
    """Test that features in IGNORED_FEATURES are not created as entities."""
    # Arrange: Use mock_client fixture
    # We want to ignore a specific feature that would normally be discovered.
    # From Vitocal250A: "heating.sensors.temperature.outside"
    ignored = [
        "heating.sensors.temperature.outside",
        "heating.circuits.0.sensors.temperature.supply",
    ]

    # Patch the IGNORED_FEATURES list in the platforms
    # We patch it where it is IMPORTED in the platform modules
    with (
        patch(
            "custom_components.vi_climate_devices.sensor.IGNORED_FEATURES",
            ignored,
        ),
    ):
        # Act: Initialize the integration (setup entry)
        await _setup_integration(hass, mock_client)

        # Assert: Verify the 'outside value' sensor is NOT created.
        # Standard entity name would be sensor.vitocal250a_outside_temperature
        state_outside = hass.states.get("sensor.vitocal250a_outside_temperature")
        assert state_outside is None

        # Assert: Verify the circuit supply sensor is NOT created.
        state_circuit = hass.states.get(
            "sensor.vitocal250a_heating_circuit_0_supply_temperature"
        )
        assert state_circuit is None

        # Assert: Verify OTHER sensors (not ignored) ARE created.
        state_return = hass.states.get("sensor.vitocal250a_return_temperature")
        assert state_return is not None


@pytest.mark.asyncio
async def test_schedule_active_features_are_not_created_as_entities(
    hass: HomeAssistant, mock_client
):
    """Test that read-only schedule active flags do not become binary sensors."""
    # Arrange: The fixture exposes separate active flags for its schedules.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    schedule_active_features = sorted(
        feature.name
        for feature in device.features
        if feature.name.endswith(".schedule.active")
    )
    assert schedule_active_features

    # Act: Initialize the integration with the real ignore list.
    await _setup_integration(hass, mock_client)

    # Assert: No entity is registered for any schedule active flag.
    registry = er.async_get(hass)
    registered_unique_ids = {
        entry.unique_id
        for entry in registry.entities.values()
        if entry.platform == DOMAIN
    }
    assert registered_unique_ids
    for feature_name in schedule_active_features:
        assert not any(
            unique_id.endswith(f"-{feature_name}")
            for unique_id in registered_unique_ids
        )
