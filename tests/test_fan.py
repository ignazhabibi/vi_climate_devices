"""Tests for the ventilation fan platform."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.fan.const import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    SERVICE_SET_PERCENTAGE,
    SERVICE_SET_PRESET_MODE,
    FanEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import FixtureViClient, ViCommandRejectedError

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.fan import FEATURE_MODE, ViClimateFan

VITOAIR_FAN = "fan.e3_viair_300f_13_ventilation"
VITOPURE_FAN = "fan.e3_vitopure_ventilation"
VITOVENT_FAN = "fan.vitocal333g_with_vitovent300f_ventilation"


def _create_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a config entry with a valid token to Home Assistant."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_integration(
    hass: HomeAssistant, client: FixtureViClient, entry: MockConfigEntry | None = None
) -> MockConfigEntry:
    """Set up the integration with the given fixture client."""
    entry = entry or _create_config_entry(hass)
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _spy_client(fixture_name: str) -> tuple[FixtureViClient, AsyncMock, AsyncMock]:
    """Return a fixture client with recorders for writes and commands."""
    client = FixtureViClient(fixture_name)
    set_feature = AsyncMock(wraps=client.set_feature)
    run_command = AsyncMock(return_value=None)
    client.set_feature = set_feature
    client.run_command = run_command
    return client, set_feature, run_command


async def _call(hass: HomeAssistant, service: str, data: dict[str, object]) -> None:
    """Call a fan service and wait for it."""
    await hass.services.async_call("fan", service, data, blocking=True)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_fan_reports_mode_and_level(hass: HomeAssistant) -> None:
    """Expose the operating modes as presets and the level as speed."""
    # Act: Set up the Vitoair FS 300E fixture.
    await _setup_integration(hass, FixtureViClient("VitoairFs300E"))

    # Assert: Presets, the current preset, and the level come from the fixture.
    state = hass.states.get(VITOAIR_FAN)
    assert state is not None
    assert state.state == "on"
    assert state.attributes[ATTR_PRESET_MODES] == [
        "permanent",
        "ventilation",
        "sensor_override",
        "sensor_driven",
    ]
    assert state.attributes[ATTR_PRESET_MODE] == "sensor_override"
    assert state.attributes[ATTR_PERCENTAGE] == 50
    assert state.attributes[ATTR_PERCENTAGE_STEP] == 25
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        FanEntityFeature.PRESET_MODE | FanEntityFeature.SET_SPEED
    )


@pytest.mark.asyncio
async def test_fan_sets_level_in_permanent_mode(hass: HomeAssistant) -> None:
    """Switch to the permanent mode and run the level command."""
    # Arrange: Record the writes of the Vitoair FS 300E fixture.
    client, set_feature, run_command = _spy_client("VitoairFs300E")
    await _setup_integration(hass, client)

    # Act: Set the speed to the third of four levels.
    await _call(
        hass, SERVICE_SET_PERCENTAGE, {"entity_id": VITOAIR_FAN, ATTR_PERCENTAGE: 75}
    )

    # Assert: The permanent mode is written before the level command.
    mode_args, _ = set_feature.call_args
    assert mode_args[1].name == FEATURE_MODE
    assert mode_args[2] == "permanent"
    command_args, _ = run_command.call_args
    assert command_args[1:] == (
        "ventilation.operating.modes.permanent",
        "setLevel",
        {"level": "levelThree"},
    )


@pytest.mark.asyncio
async def test_fan_sets_preset_mode(hass: HomeAssistant) -> None:
    """Write the API mode of the selected preset."""
    # Arrange: Record the writes of the Vitoair FS 300E fixture.
    client, set_feature, _run_command = _spy_client("VitoairFs300E")
    await _setup_integration(hass, client)

    # Act: Select the schedule preset.
    await _call(
        hass,
        SERVICE_SET_PRESET_MODE,
        {"entity_id": VITOAIR_FAN, ATTR_PRESET_MODE: "sensor_driven"},
    )

    # Assert: The camelCase API mode is written.
    args, _ = set_feature.call_args
    assert args[2] == "sensorDriven"


@pytest.mark.asyncio
async def test_fan_switches_with_the_standby_quick_mode(hass: HomeAssistant) -> None:
    """Switch the Vitopure 350 through its standby quick mode."""
    # Arrange: Record the writes of the Vitopure 350 fixture in standby.
    client, set_feature, _run_command = _spy_client("Vitopure350")
    await _setup_integration(hass, client)
    state = hass.states.get(VITOPURE_FAN)
    assert state is not None
    assert state.state == "off"
    assert state.attributes[ATTR_PERCENTAGE] == 0

    # Act: Turn the fan on, then off through a zero speed.
    await _call(hass, SERVICE_TURN_ON, {"entity_id": VITOPURE_FAN})
    await _call(
        hass, SERVICE_SET_PERCENTAGE, {"entity_id": VITOPURE_FAN, ATTR_PERCENTAGE: 0}
    )

    # Assert: The standby quick mode is written both ways.
    written = [(call.args[1].name, call.args[2]) for call in set_feature.call_args_list]
    assert written == [
        ("ventilation.quickmodes.standby.active", False),
        ("ventilation.quickmodes.standby.active", True),
    ]


@pytest.mark.asyncio
async def test_fan_switches_with_the_standby_mode(hass: HomeAssistant) -> None:
    """Switch a Vitovent without speed control through its standby mode."""
    # Arrange: Record the writes of the Vitocal 333-G with Vitovent 300-F.
    client, set_feature, _run_command = _spy_client("Vitocal333G-with-Vitovent300F")
    await _setup_integration(hass, client)
    state = hass.states.get(VITOVENT_FAN)
    assert state is not None
    assert state.attributes[ATTR_PRESET_MODES] == ["standard", "ventilation"]
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    # Act: Turn the fan off.
    await _call(hass, SERVICE_TURN_OFF, {"entity_id": VITOVENT_FAN})

    # Assert: The standby mode is written.
    args, _ = set_feature.call_args
    assert args[1].name == FEATURE_MODE
    assert args[2] == "standby"


@pytest.mark.asyncio
async def test_fan_leaves_standby_mode_with_schedule() -> None:
    """Leave the standby mode with the schedule mode and an optional level."""
    # Arrange: Put the Vitovent fixture into its standby mode.
    device = (
        await FixtureViClient(
            "Vitocal333G-with-Vitovent300F"
        ).get_full_installation_status("99999")
    )[0]
    device = replace(
        device,
        features=[
            replace(feature, value="standby")
            if feature.name == FEATURE_MODE
            else feature
            for feature in device.features
        ],
    )
    coordinator = MagicMock(data={"device": device})
    coordinator.async_set_feature = AsyncMock(return_value=None)
    entity = ViClimateFan(coordinator, "device")
    assert entity.is_on is False
    assert entity.preset_mode is None

    # Act: Turn the fan on with a preset.
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_turn_on()
        await entity.async_turn_on(preset_mode="standard")

    # Assert: The schedule mode is written first, then the preset.
    written = [call.args[2] for call in coordinator.async_set_feature.call_args_list]
    assert written == ["ventilation", "standard"]


@pytest.mark.asyncio
async def test_fan_rejects_unsupported_controls(hass: HomeAssistant) -> None:
    """Reject presets, speeds, and standby the device does not report."""
    # Arrange: Set up fixtures with and without speed and standby controls.
    await _setup_integration(hass, FixtureViClient("Vitocal333G-with-Vitovent300F"))
    entity = hass.data["entity_components"]["fan"].get_entity(VITOVENT_FAN)
    assert isinstance(entity, ViClimateFan)

    # Act and assert: Unknown presets and missing levels are rejected.
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_set_preset_mode("standby")
    assert error.value.translation_key == "unsupported_mode"
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_set_percentage(50)
    assert error.value.translation_key == "unsupported_mode"


@pytest.mark.asyncio
async def test_fan_without_standby_cannot_turn_off() -> None:
    """Reject turning off a device without standby control."""
    # Arrange: Build the Vitoair fan, which reports no standby control.
    device = (
        await FixtureViClient("VitoairFs300E").get_full_installation_status("99999")
    )[0]
    entity = ViClimateFan(MagicMock(data={"device": device}), "device")

    # Act and assert: Turning off is rejected.
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_turn_off()
    assert error.value.translation_key == "unsupported_mode"


@pytest.mark.asyncio
async def test_fan_translates_a_rejected_level_command(hass: HomeAssistant) -> None:
    """Translate a rejected level command into a validation error."""
    # Arrange: Reject the level command of the Vitoair FS 300E.
    client, _set_feature, run_command = _spy_client("VitoairFs300E")
    run_command.side_effect = ViCommandRejectedError(
        "Rejected", reason="COMMAND_NOT_EXECUTABLE"
    )
    await _setup_integration(hass, client)

    # Act and assert: The rejection reaches the caller as a validation error.
    with pytest.raises(ServiceValidationError) as error:
        await _call(
            hass,
            SERVICE_SET_PERCENTAGE,
            {"entity_id": VITOAIR_FAN, ATTR_PERCENTAGE: 25},
        )
    assert error.value.translation_key == "command_rejected"


@pytest.mark.asyncio
async def test_fan_replaces_the_mode_select(hass: HomeAssistant) -> None:
    """Remove the former auto-discovered ventilation mode select."""
    # Arrange: Register the select entry of an earlier release.
    client = FixtureViClient("VitoairFs300E")
    device = (await client.get_full_installation_status("99999"))[0]
    entry = _create_config_entry(hass)
    registry = er.async_get(hass)
    select = registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{device.gateway_serial}-{device.id}-{FEATURE_MODE}",
        config_entry=entry,
    )

    # Act: Set up the integration.
    await _setup_integration(hass, client, entry)

    # Assert: The fan replaces the select.
    assert registry.async_get(select.entity_id) is None
    assert hass.states.get(VITOAIR_FAN) is not None
