"""Snapshot tests for Viessmann Climate Devices discovery."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy import SnapshotAssertion

from custom_components.vi_climate_devices.const import DOMAIN


@pytest.mark.asyncio
async def test_discovery_snapshot(
    hass: HomeAssistant, snapshot: SnapshotAssertion, mock_client
):
    """Test that all entities are created correctly and match the snapshot."""
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
        # Act: Initialize the integration to trigger entity discovery.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify that all created entities (state + sorted attributes) match the golden snapshot.
        # We capture all states, sort them by entity_id to ensure deterministic order.
        # We strip dynamic fields like timestamps (last_changed/updated) and context.
        all_states = sorted(hass.states.async_all(), key=lambda s: s.entity_id)

        snapshot_data = [
            {
                "entity_id": state.entity_id,
                "state": state.state,
                "attributes": {
                    key: sorted(value) if isinstance(value, list) else value
                    for key, value in state.attributes.items()
                },
            }
            for state in all_states
        ]

        assert snapshot_data == snapshot

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
