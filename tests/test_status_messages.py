"""Tests for the heat pump entities derived from the active status messages."""

import dataclasses
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, FeatureValue, FixtureViClient, JsonValue

from custom_components.vi_climate_devices.binary_sensor import (
    STATUS_BINARY_SENSOR_TYPES,
    ViClimateStatusBinarySensor,
)
from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.sensor import (
    STATUS_SENSOR_TYPES,
    ViClimateStatusSensor,
)
from custom_components.vi_climate_devices.status_messages import (
    HEAT_PUMP_STATE_CODES,
    STATUS_MESSAGES_FEATURE,
    get_heat_pump_state,
    parse_status_messages,
)

HEAT_PUMP_STATE_ENTITY = "sensor.vitocal250a_heat_pump_state"
HEATING_ROD_ENTITY = "sensor.vitocal250a_heating_rod"
DHW_HEATING_ENTITY = "binary_sensor.vitocal250a_dhw_heating_active"


def _entry(
    code: str, timestamp: str = "2026-10-17T09:24:28.000Z", bus_address: str = "1"
) -> dict[str, JsonValue]:
    """Return a raw status message entry as reported by the API."""
    return {
        "errorCode": code,
        "timestamp": timestamp,
        "busAddress": bus_address,
        "busType": "OwnBus",
        "accessLevel": "customer",
        "priority": "status",
        "audiences": ["IS-SUPPLIER"],
    }


def _status_value(*entries: dict[str, JsonValue]) -> FeatureValue:
    """Return the flattened feature value for the given entries."""
    return {"entries": {"type": "array", "value": list(entries)}}


async def _fixture_device(name: str = "Vitocal250A") -> Device:
    """Return the first device of a client fixture."""
    return (await FixtureViClient(name).get_full_installation_status("99999"))[0]


def _with_status_value(device: Device, value: FeatureValue) -> Device:
    """Return the device with replaced status messages."""
    return dataclasses.replace(
        device,
        features=[
            dataclasses.replace(feature, value=value)
            if feature.name == STATUS_MESSAGES_FEATURE
            else feature
            for feature in device.features
        ],
    )


async def _setup_integration(hass: HomeAssistant, mock_client) -> MockConfigEntry:
    """Set up the integration with the provided fixture client."""
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
    return entry


async def _publish_status_value(
    hass: HomeAssistant, entry: MockConfigEntry, value: FeatureValue
) -> None:
    """Replace the coordinator's status messages and update all entities."""
    coordinator = entry.runtime_data
    coordinator.data = {
        map_key: _with_status_value(device, value)
        for map_key, device in coordinator.data.items()
    }
    coordinator.async_update_listeners()
    await hass.async_block_till_done()


def _status_sensor(device: Device, translation_key: str) -> ViClimateStatusSensor:
    """Build a status sensor for a fixture device without Home Assistant."""
    map_key = f"{device.gateway_serial}_{device.id}"
    description = next(
        description
        for description in STATUS_SENSOR_TYPES
        if description.translation_key == translation_key
    )
    return ViClimateStatusSensor(
        MagicMock(data={map_key: device}),
        map_key,
        STATUS_MESSAGES_FEATURE,
        description,
    )


@pytest.mark.asyncio
async def test_fixture_reports_off_and_all_active_codes(
    hass: HomeAssistant, mock_client
):
    """The Vitocal 250-A fixture is off with the heating rod switched off."""
    # Arrange: Use the installation time zone of the fixture device.
    await hass.config.async_set_time_zone("Europe/Berlin")

    # Act: Set up the integration with the unchanged fixture.
    await _setup_integration(hass, mock_client)

    # Assert: The states and the raw attribute reflect the fixture codes.
    state = hass.states.get(HEAT_PUMP_STATE_ENTITY)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"] == list(HEAT_PUMP_STATE_CODES.values())
    assert state.attributes["state_code"] == "S.123"
    assert state.attributes["active_codes"][:3] == [
        {"code": "S.134", "bus_address": "1", "since": "2026-10-11T10:03:07+02:00"},
        {"code": "S.123", "bus_address": "1", "since": "2026-10-11T10:03:04+02:00"},
        {
            "code": "S.165",
            "bus_address": "54",
            "since": "2026-05-17T09:01:28+02:00",
        },
    ]
    assert [entry["code"] for entry in state.attributes["active_codes"]].count(
        "S.165"
    ) == 2
    assert "entity_category" not in state.attributes

    heating_rod = hass.states.get(HEATING_ROD_ENTITY)
    assert heating_rod is not None
    assert heating_rod.state == "off"
    assert heating_rod.attributes["active_stages"] == []

    dhw_heating = hass.states.get(DHW_HEATING_ENTITY)
    assert dhw_heating is not None
    assert dhw_heating.state == "off"


@pytest.mark.asyncio
async def test_lock_binary_sensors_are_disabled_by_default(
    hass: HomeAssistant, mock_client
):
    """Create the utility lock and grid limitation sensors disabled."""
    # Arrange: Read the fixture identity for the unique IDs.
    device = await _fixture_device()

    # Act: Set up the integration.
    await _setup_integration(hass, mock_client)

    # Assert: Each status binary sensor is registered with its default.
    registry = er.async_get(hass)
    for description in STATUS_BINARY_SENSOR_TYPES:
        unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
        assert entity_id is not None
        registry_entry = registry.async_get(entity_id)
        assert registry_entry is not None
        is_enabled_by_default = description.entity_registry_enabled_default
        assert (registry_entry.disabled_by is None) is is_enabled_by_default
    assert [
        description.translation_key
        for description in STATUS_BINARY_SENSOR_TYPES
        if not description.entity_registry_enabled_default
    ] == ["utility_lock", "grid_power_limitation"]


@pytest.mark.parametrize(("code", "expected_state"), HEAT_PUMP_STATE_CODES.items())
@pytest.mark.asyncio
async def test_each_state_code_maps_to_its_state(
    hass: HomeAssistant, mock_client, code: str, expected_state: str
):
    """Report every mapped state code as its enum state."""
    # Arrange: Set up the integration.
    entry = await _setup_integration(hass, mock_client)

    # Act: Report only the state code under test.
    await _publish_status_value(hass, entry, _status_value(_entry(code)))

    # Assert: The sensor reports the mapped state.
    state = hass.states.get(HEAT_PUMP_STATE_ENTITY)
    assert state is not None
    assert state.state == expected_state


@pytest.mark.parametrize(
    ("codes", "expected_state", "expected_stages"),
    [
        (["S.131"], "stage_1", [1]),
        (["S.131", "S.132"], "stage_2", [1, 2]),
        (["S.133", "S.131", "S.132"], "stage_3", [1, 2, 3]),
        (["S.133", "S.217", "S.218"], "stage_1", [3]),
        (["S.130", "S.217", "S.218", "S.219"], "off", []),
    ],
)
@pytest.mark.asyncio
async def test_heating_rod_counts_active_stages(
    hass: HomeAssistant,
    mock_client,
    codes: list[str],
    expected_state: str,
    expected_stages: list[int],
):
    """Report the number of running stages and the stage numbers."""
    # Arrange: Set up the integration.
    entry = await _setup_integration(hass, mock_client)

    # Act: Report the heating rod codes under test.
    await _publish_status_value(
        hass, entry, _status_value(*(_entry(code) for code in codes))
    )

    # Assert: A lone higher stage still counts as one running stage.
    state = hass.states.get(HEATING_ROD_ENTITY)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes["active_stages"] == expected_stages


@pytest.mark.parametrize(
    ("translation_key", "code"),
    [
        ("dhw_heating", "S.141"),
        ("utility_lock", "S.195"),
        ("utility_lock", "S.196"),
        ("grid_power_limitation", "S.427"),
    ],
)
@pytest.mark.asyncio
async def test_binary_sensors_follow_their_codes(translation_key: str, code: str):
    """Turn a status binary sensor on only while one of its codes is active."""
    # Arrange: Build the binary sensor for the fixture device.
    device = await _fixture_device()
    map_key = f"{device.gateway_serial}_{device.id}"
    coordinator = MagicMock(data={map_key: device})
    description = next(
        description
        for description in STATUS_BINARY_SENSOR_TYPES
        if description.translation_key == translation_key
    )
    sensor = ViClimateStatusBinarySensor(
        coordinator, map_key, STATUS_MESSAGES_FEATURE, description
    )

    # Act and assert: The fixture does not report the code.
    assert sensor.is_on is False

    # Act and assert: The code becomes active.
    coordinator.data = {
        map_key: _with_status_value(device, _status_value(_entry(code)))
    }
    assert sensor.is_on is True

    # Act and assert: Unreadable messages or a missing device are unknown.
    coordinator.data = {map_key: _with_status_value(device, "broken")}
    assert sensor.is_on is None
    coordinator.data = {}
    assert sensor.is_on is None


@pytest.mark.asyncio
async def test_newest_state_code_wins_and_duplicates_are_kept(
    hass: HomeAssistant, mock_client
):
    """Pick the newest state and keep codes reported by several bus addresses."""
    # Arrange: Set up the integration.
    entry = await _setup_integration(hass, mock_client)
    value = _status_value(
        _entry("S.123", "2026-10-17T09:24:28.000Z"),
        _entry("S.129", "2026-10-17T09:20:00.000Z"),
        _entry("S.165", "2026-05-17T09:01:28.000Z", bus_address="54"),
        _entry("S.165", "2025-10-31T11:28:46.000Z", bus_address="1"),
    )

    # Act: Publish overlapping state codes and duplicate codes.
    await _publish_status_value(hass, entry, value)

    # Assert: The newest state wins and both S.165 entries are exposed.
    state = hass.states.get(HEAT_PUMP_STATE_ENTITY)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["state_code"] == "S.123"
    assert [
        (active["code"], active["bus_address"])
        for active in state.attributes["active_codes"]
    ] == [("S.123", "1"), ("S.129", "1"), ("S.165", "54"), ("S.165", "1")]


@pytest.mark.parametrize(
    ("timestamp", "expected_since"),
    [
        ("2026-10-17T09:24:28.000Z", "2026-10-17T09:24:28+02:00"),
        ("2026-12-01T09:24:28.000Z", "2026-12-01T09:24:28+01:00"),
    ],
)
@pytest.mark.asyncio
async def test_since_is_installation_local_time_not_utc(
    hass: HomeAssistant, mock_client, timestamp: str, expected_since: str
):
    """Read the Z-suffixed activation time as installation local time."""
    # Arrange: Set up the integration in the installation time zone.
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await _setup_integration(hass, mock_client)

    # Act: Report a state code with a Z-suffixed local activation time.
    await _publish_status_value(hass, entry, _status_value(_entry("S.123", timestamp)))

    # Assert: The wall-clock time is kept and only the local offset is added.
    state = hass.states.get(HEAT_PUMP_STATE_ENTITY)
    assert state is not None
    assert state.attributes["active_codes"][0]["since"] == expected_since


@pytest.mark.asyncio
async def test_active_codes_are_not_recorded(hass: HomeAssistant, mock_client):
    """Exclude the message list, but not the state code, from the recorder."""
    # Act: Set up the integration.
    await _setup_integration(hass, mock_client)

    # Assert: The entity marks only the message list as unrecorded.
    entity = hass.data["entity_components"]["sensor"].get_entity(HEAT_PUMP_STATE_ENTITY)
    assert entity is not None
    unrecorded_attributes = entity._state_info["unrecorded_attributes"]
    assert "active_codes" in unrecorded_attributes
    assert "state_code" not in unrecorded_attributes


@pytest.mark.asyncio
async def test_unknown_codes_are_kept_without_a_state(hass: HomeAssistant, mock_client):
    """Ignore unknown codes for the state but keep them in the attribute."""
    # Arrange: Set up the integration in the installation time zone.
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry = await _setup_integration(hass, mock_client)

    # Act: Report only an unmapped code.
    await _publish_status_value(hass, entry, _status_value(_entry("S.999")))

    # Assert: The state is unknown, the code is still listed.
    state = hass.states.get(HEAT_PUMP_STATE_ENTITY)
    assert state is not None
    assert state.state == "unknown"
    assert state.attributes["state_code"] is None
    assert state.attributes["active_codes"] == [
        {"code": "S.999", "bus_address": "1", "since": "2026-10-17T09:24:28+02:00"}
    ]
    heating_rod = hass.states.get(HEATING_ROD_ENTITY)
    assert heating_rod is not None
    assert heating_rod.state == "off"


@pytest.mark.asyncio
async def test_status_sensor_handles_unreadable_messages():
    """Report unknown without detail attributes for unreadable messages."""
    # Arrange: Build the state sensor from a device with a malformed value.
    device = _with_status_value(await _fixture_device(), {"entries": "broken"})
    sensor = _status_sensor(device, "heat_pump_state")

    # Act and assert: The malformed value is unknown and has no detail.
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {
        "viessmann_feature_name": STATUS_MESSAGES_FEATURE
    }
    assert sensor.available is True

    # Act and assert: A device missing after refresh is unknown and unavailable.
    sensor.coordinator.data = {}
    assert sensor.native_value is None
    assert sensor.available is False


@pytest.mark.parametrize(
    ("device_name", "has_status_entities"),
    [
        ("Vitocal222S", True),
        ("Vitodens200W", False),
        ("Vitocharge03", False),
    ],
)
@pytest.mark.asyncio
async def test_status_entities_only_for_heat_pumps(
    hass: HomeAssistant, device_name: str, *, has_status_entities: bool
):
    """Create status entities only for devices with a compressor."""
    # Arrange: Read the fixture identity for the unique IDs.
    mock_client = FixtureViClient(device_name)
    device = await _fixture_device(device_name)

    # Act: Set up the integration with the fixture.
    await _setup_integration(hass, mock_client)

    # Assert: Heat pump entities exist only for the heat pump fixture.
    registry = er.async_get(hass)
    for platform, descriptions in (
        ("sensor", STATUS_SENSOR_TYPES),
        ("binary_sensor", STATUS_BINARY_SENSOR_TYPES),
    ):
        for description in descriptions:
            unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
            entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
            assert (entity_id is not None) is has_status_entities


def test_parse_status_messages_skips_malformed_entries():
    """Skip entries without a code and tolerate missing or invalid fields."""
    # Arrange: Mix valid entries with malformed ones.
    value: FeatureValue = {
        "entries": {
            "type": "array",
            "value": [
                "not-an-object",
                {"timestamp": "2026-10-17T09:24:28.000Z"},
                {"errorCode": "S.125", "timestamp": "yesterday"},
                {"errorCode": "S.124", "timestamp": 5, "busAddress": 1},
                _entry("S.129", "2026-10-17T09:24:28.000+02:00"),
            ],
        }
    }

    # Act: Parse the messages.
    messages = parse_status_messages(value)

    # Assert: Only coded entries remain; the offset is dropped, not converted.
    assert messages is not None
    time_zone = ZoneInfo("Europe/Berlin")
    assert [message.as_attribute(time_zone) for message in messages] == [
        {"code": "S.125", "bus_address": None, "since": None},
        {"code": "S.124", "bus_address": None, "since": None},
        {"code": "S.129", "bus_address": "1", "since": "2026-10-17T09:24:28+02:00"},
    ]
    assert get_heat_pump_state(messages) == "post_run"
    assert parse_status_messages(None) is None
    assert parse_status_messages({"entries": {"value": "broken"}}) is None
