"""Tests for features that change their entity platform with vi_api_client 7."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN

ALL_FIXTURES = (
    "Vitocal200S",
    "Vitocal222S",
    "Vitocal250A",
    "Vitocal333G-with-Vitovent300F",
    "Vitocharge03",
    "Vitodens200W",
    "Vitopure350",
)

# Boolean features written through an on/off command pair since 7.0.0, with
# the switch name they get on the fixture that reports them.
COMMAND_PAIR_SWITCHES = (
    pytest.param(
        "Vitocal250A",
        "heating.circuits.0.operating.programs.forcedLastFromSchedule.active",
        "Last Schedule Phase Forced",
        id="forced-last-from-schedule",
    ),
    pytest.param(
        "Vitocal200S",
        "heating.circuits.1.operating.programs.comfort.active",
        "Comfort Program Heating Circuit 2",
        id="comfort-numbered",
    ),
    pytest.param(
        "Vitocal333G-with-Vitovent300F",
        "heating.circuits.0.operating.programs.eco.active",
        "Eco Program Heating Circuit 1",
        id="eco-numbered",
    ),
    pytest.param(
        "Vitodens200W",
        "heating.circuits.0.operating.programs.comfort.active",
        "Comfort Program",
        id="comfort-never-executable",
    ),
    pytest.param(
        "Vitocal333G-with-Vitovent300F",
        "ventilation.quickmodes.comfort.active",
        "Ventilation Quick Mode Comfort",
        id="quick-mode-comfort",
    ),
    pytest.param(
        "Vitocal333G-with-Vitovent300F",
        "ventilation.quickmodes.eco.active",
        "Ventilation Quick Mode Eco",
        id="quick-mode-eco",
    ),
    pytest.param(
        "Vitopure350",
        "ventilation.quickmodes.forcedLevelFour.active",
        "Ventilation Quick Mode Forced Level Four",
        id="quick-mode-forced-level-four",
    ),
    pytest.param(
        "Vitopure350",
        "ventilation.quickmodes.silent.active",
        "Ventilation Quick Mode Silent",
        id="quick-mode-silent",
    ),
)

HOLIDAY_DATE_FEATURES = (
    "heating.operating.programs.holiday.end",
    "heating.operating.programs.holiday.start",
    "heating.operating.programs.holidayAtHome.end",
    "heating.operating.programs.holidayAtHome.start",
    "ventilation.quickmodes.holiday.end",
    "ventilation.quickmodes.holiday.start",
)


async def _fixture_device(fixture_name: str) -> Device:
    """Return the single device of a library fixture."""
    return (await FixtureViClient(fixture_name).get_full_installation_status("99999"))[
        0
    ]


def _unique_id(device: Device, feature_name: str) -> str:
    """Return the unique ID the integration assigns to a feature entity."""
    return f"{device.gateway_serial}-{device.id}-{feature_name}"


async def _setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry, fixture_name: str
) -> None:
    """Set up the integration for one library fixture."""
    client = FixtureViClient(fixture_name)
    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=client,
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
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _platform_unique_ids(
    hass: HomeAssistant, entry: MockConfigEntry
) -> dict[str, set[str]]:
    """Return the entry's registry unique IDs grouped by platform domain."""
    unique_ids: dict[str, set[str]] = {}
    for registry_entry in er.async_entries_for_config_entry(
        er.async_get(hass), entry.entry_id
    ):
        unique_ids.setdefault(registry_entry.domain, set()).add(
            registry_entry.unique_id
        )
    return unique_ids


def _new_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a config entry for one integration setup."""
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)
    return entry


def _other_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a second, disabled entry that only owns registry entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"client_id": "456", "token": "def"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "feature_name", "name"), COMMAND_PAIR_SWITCHES
)
async def test_command_pair_feature_becomes_disabled_switch(
    hass: HomeAssistant, fixture_name: str, feature_name: str, name: str
) -> None:
    """Create a named, disabled switch instead of a binary sensor."""
    # Arrange: Read the fixture device the feature belongs to.
    device = await _fixture_device(fixture_name)
    unique_id = _unique_id(device, feature_name)
    entry = _new_entry(hass)

    # Act: Set up the integration for the fixture.
    await _setup_integration(hass, entry, fixture_name)

    # Assert: Only a switch is registered, disabled until the user enables it.
    registry = er.async_get(hass)
    switch_id = registry.async_get_entity_id(Platform.SWITCH, DOMAIN, unique_id)
    assert switch_id is not None
    switch_entry = registry.async_get(switch_id)
    assert switch_entry is not None
    assert switch_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert switch_entry.original_name == name
    assert (
        registry.async_get_entity_id(Platform.BINARY_SENSOR, DOMAIN, unique_id) is None
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_feature_entities_use_one_platform_per_unique_id(
    hass: HomeAssistant, fixture_name: str
) -> None:
    """Never register a feature on a platform and on the one it supersedes."""
    # Arrange: Use one entry per fixture.
    entry = _new_entry(hass)

    # Act: Set up the integration for the fixture.
    await _setup_integration(hass, entry, fixture_name)

    # Assert: The superseded-domain cleanup can never remove a live entity.
    unique_ids = _platform_unique_ids(hass, entry)
    empty: set[str] = set()
    assert (
        unique_ids.get(Platform.SWITCH, empty)
        & unique_ids.get(Platform.BINARY_SENSOR, empty)
        == set()
    )
    assert (
        unique_ids.get(Platform.SENSOR, empty) & unique_ids.get(Platform.NUMBER, empty)
        == set()
    )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
async def test_read_only_holiday_dates_create_no_entity(
    hass: HomeAssistant, fixture_name: str
) -> None:
    """Ignore holiday dates that report placeholders when no holiday is planned."""
    # Arrange: Use one entry per fixture.
    device = await _fixture_device(fixture_name)
    entry = _new_entry(hass)

    # Act: Set up the integration for the fixture.
    await _setup_integration(hass, entry, fixture_name)

    # Assert: No platform registers a holiday date.
    registered = set().union(*_platform_unique_ids(hass, entry).values())
    assert {
        _unique_id(device, feature_name) for feature_name in HOLIDAY_DATE_FEATURES
    } & registered == set()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "feature_name", "old_domain", "new_domain"),
    [
        pytest.param(
            "Vitocal250A",
            "heating.circuits.0.operating.programs.forcedLastFromSchedule.active",
            Platform.BINARY_SENSOR,
            Platform.SWITCH,
            id="binary-sensor-to-switch",
        ),
        pytest.param(
            "Vitodens200W",
            "heating.dhw.hygiene.enabled",
            Platform.BINARY_SENSOR,
            Platform.SWITCH,
            id="defined-hygiene-switch",
        ),
        pytest.param(
            "Vitodens200W",
            "heating.dhw.hygiene.trigger.startHour",
            Platform.NUMBER,
            Platform.SENSOR,
            id="number-to-sensor",
        ),
    ],
)
async def test_superseded_registry_entry_is_removed(
    hass: HomeAssistant,
    fixture_name: str,
    feature_name: str,
    old_domain: Platform,
    new_domain: Platform,
) -> None:
    """Remove the entry an upgraded installation kept on the previous platform."""
    # Arrange: Register the feature on its previous platform for this entry and
    # for an unrelated entry of the same integration.
    device = await _fixture_device(fixture_name)
    unique_id = _unique_id(device, feature_name)
    entry = _new_entry(hass)
    other_entry = _other_entry(hass)
    registry = er.async_get(hass)
    old_entry = registry.async_get_or_create(
        old_domain, DOMAIN, unique_id, config_entry=entry
    )
    foreign_entry = registry.async_get_or_create(
        old_domain, DOMAIN, f"{unique_id}-foreign", config_entry=other_entry
    )

    # Act: Set up the integration, which now provides the new platform.
    await _setup_integration(hass, entry, fixture_name)

    # Assert: The old entry is gone, the new one exists, others are untouched.
    assert registry.async_get(old_entry.entity_id) is None
    assert registry.async_get_entity_id(new_domain, DOMAIN, unique_id) is not None
    assert registry.async_get(foreign_entry.entity_id) is not None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_superseded_entry_of_another_config_entry_is_kept(
    hass: HomeAssistant,
) -> None:
    """Leave an entry with the same unique ID alone if another entry owns it."""
    # Arrange: Another config entry owns a binary sensor with the same unique ID.
    feature_name = "heating.circuits.0.operating.programs.forcedLastFromSchedule.active"
    device = await _fixture_device("Vitocal250A")
    unique_id = _unique_id(device, feature_name)
    entry = _new_entry(hass)
    other_entry = _other_entry(hass)
    registry = er.async_get(hass)
    other_owned = registry.async_get_or_create(
        Platform.BINARY_SENSOR, DOMAIN, unique_id, config_entry=other_entry
    )

    # Act: Set up the integration for the first entry.
    await _setup_integration(hass, entry, "Vitocal250A")

    # Assert: The other entry's registry entry survives.
    assert registry.async_get(other_owned.entity_id) is not None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
