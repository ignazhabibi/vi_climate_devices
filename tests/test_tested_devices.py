"""Tests that every tested device keeps the curated Vitocal 250-A experience."""

import re
from collections.abc import Callable, Sequence
from unittest.mock import MagicMock

import pytest
from homeassistant.helpers.entity import Entity
from vi_api_client import Device, FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    _discover_binary_sensors,
)
from custom_components.vi_climate_devices.const import TESTED_DEVICES
from custom_components.vi_climate_devices.number import _discover_numbers
from custom_components.vi_climate_devices.select import _discover_selects
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors
from custom_components.vi_climate_devices.switch import _discover_switches

# The curated reference device: its auto-discovered features are accepted.
REFERENCE_FIXTURE = "Vitocal250A"

# Auto-discovered features of other tested devices that are accepted although
# the reference device does not report them, with the reason. Sort the keys.
ACCEPTED_AUTO_DISCOVERED_FEATURES: dict[str, str] = {
    "heating.dhw.hygiene.active": (
        "Starting a hygiene run on demand is not verified on a real device; "
        "the defined switch enables the program."
    ),
    "heating.dhw.hygiene.trigger.startHour": (
        "Read-only schedule detail of the hygiene program."
    ),
    "heating.dhw.hygiene.trigger.startMinute": (
        "Read-only schedule detail of the hygiene program."
    ),
    "heating.dhw.hygiene.trigger.weekdays": (
        "Read-only schedule detail of the hygiene program."
    ),
}

DISCOVERERS: tuple[Callable[[MagicMock], Sequence[Entity]], ...] = (
    _discover_binary_sensors,
    _discover_numbers,
    _discover_realtime_sensors,
    _discover_selects,
    _discover_switches,
)

FIXTURE_NAMES = FixtureViClient.get_available_fixture_devices()


async def _fixture_devices(fixture_name: str) -> list[Device]:
    """Return every device of a bundled fixture."""
    return await FixtureViClient(fixture_name).get_full_installation_status("99999")


def _normalized(feature_name: str) -> str:
    """Replace component indices so repeated components compare equal."""
    return re.sub(r"\.\d+(?=\.|$)", ".N", feature_name)


def _auto_discovered_features(device: Device) -> set[str]:
    """Return the normalized features the device creates as fallback entities."""
    coordinator = MagicMock(data={"device": device})
    return {
        _normalized(entity.entity_description.key)
        for discover in DISCOVERERS
        for entity in discover(coordinator)
        if not entity.entity_description.translation_key
    }


async def _tested_fixture_devices() -> list[tuple[str, Device]]:
    """Return the fixture devices whose model ID is a tested device."""
    return [
        (fixture_name, device)
        for fixture_name in FIXTURE_NAMES
        for device in await _fixture_devices(fixture_name)
        if device.model_id in TESTED_DEVICES
    ]


@pytest.mark.asyncio
async def test_every_tested_device_is_backed_by_a_fixture() -> None:
    """Accept only model IDs that a real device fixture reports."""
    # Act: Collect the model IDs that the fixtures report.
    tested_model_ids = {
        device.model_id for _, device in await _tested_fixture_devices()
    }

    # Assert: No tested model ID lacks a fixture.
    assert tested_model_ids == set(TESTED_DEVICES)


@pytest.mark.asyncio
async def test_tested_devices_add_no_unaccepted_fallback_entities() -> None:
    """Hide only fallback entities the reference device already hides."""
    # Arrange: Collect the accepted features of the curated reference device.
    reference_devices = await _fixture_devices(REFERENCE_FIXTURE)
    accepted = set(ACCEPTED_AUTO_DISCOVERED_FEATURES).union(
        *(_auto_discovered_features(device) for device in reference_devices)
    )

    # Act: Collect the fallback features of every tested fixture device.
    unaccepted = {
        f"{fixture_name}: {feature_name}"
        for fixture_name, device in await _tested_fixture_devices()
        for feature_name in _auto_discovered_features(device) - accepted
    }

    # Assert: Every hidden fallback feature has a decision.
    assert not unaccepted, (
        "Define an entity, ignore the feature, or record it in "
        f"ACCEPTED_AUTO_DISCOVERED_FEATURES: {sorted(unaccepted)}"
    )


@pytest.mark.asyncio
async def test_accepted_features_are_still_reported() -> None:
    """Keep the accepted list limited to features a tested device reports."""
    # Act: Collect the fallback features of every tested fixture device.
    reported = set().union(
        *(
            _auto_discovered_features(device)
            for _, device in await _tested_fixture_devices()
        )
    )

    # Assert: No accepted feature is stale.
    assert set(ACCEPTED_AUTO_DISCOVERED_FEATURES) <= reported
