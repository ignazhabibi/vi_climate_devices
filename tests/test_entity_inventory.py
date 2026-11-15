"""Snapshot the entities every bundled fixture creates."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.utils import normalize_sensor_value

FIXTURE_NAMES = FixtureViClient.get_available_fixture_devices()

# Values the API reports instead of a reading; an entity may show them as
# unknown.
PLACEHOLDER_VALUES = frozenset({"", "nothing", "unknown"})


async def _setup_integration(hass: HomeAssistant, fixture_name: str) -> str:
    """Set up the integration with a fixture client and return the entry ID."""
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
            return_value=FixtureViClient(fixture_name),
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
    return entry.entry_id


def _describe(entry: er.RegistryEntry) -> str:
    """Return one line with the structure of an entity, without its state."""
    parts = [
        entry.entity_id,
        entry.translation_key or "(auto-discovered)",
        "disabled" if entry.disabled_by else "enabled",
    ]
    if entry.entity_category:
        parts.append(entry.entity_category)
    if entry.original_device_class:
        parts.append(f"class={entry.original_device_class}")
    if entry.unit_of_measurement:
        parts.append(f"unit={entry.unit_of_measurement}")
    if entry.capabilities:
        capabilities = {str(key): value for key, value in entry.capabilities.items()}
        parts.append(json.dumps(capabilities, sort_keys=True, ensure_ascii=False))
    return " | ".join(parts)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
@pytest.mark.asyncio
async def test_entity_inventory(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    caplog: pytest.LogCaptureFixture,
    fixture_name: str,
) -> None:
    """Create the same entities, and read every reported value."""
    # Arrange: Load the fixture's feature values.
    client = FixtureViClient(fixture_name)
    devices = await client.get_full_installation_status("99999")
    values = {
        feature.name: feature.value for device in devices for feature in device.features
    }

    # Act: Set up the integration with the fixture.
    caplog.set_level(logging.WARNING, logger="custom_components.vi_climate_devices")
    entry_id = await _setup_integration(hass, fixture_name)

    # Assert: The entities match the snapshot.
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry_id)
    assert sorted(_describe(entry) for entry in entries) == snapshot

    # Assert: Setup logs no warning or error.
    assert not [
        record
        for record in caplog.records
        if record.name.startswith("custom_components.vi_climate_devices")
        and record.levelno >= logging.WARNING
    ]

    # Assert: No entity is unavailable, and no defined entity is unknown while
    # its feature reports a value.
    for state in hass.states.async_all():
        assert state.state != STATE_UNAVAILABLE, state.entity_id
        entry = registry.async_get(state.entity_id)
        feature_name = state.attributes.get("viessmann_feature_name")
        if entry is None or entry.translation_key is None or feature_name is None:
            continue
        value = normalize_sensor_value(values.get(str(feature_name)))
        if value is None or value in PLACEHOLDER_VALUES:
            continue
        assert state.state != STATE_UNKNOWN, (state.entity_id, value)
