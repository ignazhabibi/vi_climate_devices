"""Tests for the Viessmann Heat switch platform."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import CommandResponse, FeatureValue, FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.switch import ViClimateSwitch


@pytest.mark.asyncio
async def test_switch_handles_device_removed_by_refresh() -> None:
    """Reject writes after the coordinator loses the switch's device."""
    # Arrange: Build a switch for the writable one-time DHW charge feature.
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature_name = "heating.dhw.oneTimeCharge.active"
    coordinator = MagicMock(data={"device": device})
    entity = ViClimateSwitch(
        coordinator,
        "device",
        feature_name,
        SwitchEntityDescription(key=feature_name),
    )

    # Act: Simulate a refresh which removes the device.
    coordinator.data = {}

    # Assert: State and metadata clear, and the requested command is rejected.
    assert entity.feature_data is None
    assert entity.is_on is None
    assert entity.device_info is None

    # Act and assert: A write and a new entity both require an available device.
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_turn_on()

    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "feature_unavailable"
    assert error.value.translation_placeholders is None

    with pytest.raises(ValueError, match="Device missing"):
        ViClimateSwitch(
            MagicMock(data={}),
            "missing",
            feature_name,
            SwitchEntityDescription(key=feature_name),
        )


@pytest.mark.asyncio
async def test_switch_creation_and_services(hass: HomeAssistant, mock_client):
    """Test switch creation and turn_on/turn_off service calls."""
    # Arrange: Mock Config Entry.
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

    # Spy on set_feature to verify service calls.
    mock_client.set_feature = AsyncMock(wraps=mock_client.set_feature)

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
        # Act: Load Integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Test 1: Initial State (Offline/Fixture Data).

        # Verify the read-only hygiene state remains a binary sensor, not a switch.
        hygiene_switch = hass.states.get("switch.vitocal250a_dhw_hygiene")
        assert hygiene_switch is None
        hygiene_binary_sensor = hass.states.get(
            "binary_sensor.vitocal250a_dhw_hygiene_enabled"
        )
        assert hygiene_binary_sensor is not None
        assert hygiene_binary_sensor.state == STATE_OFF

        # Verify 'heating.dhw.oneTimeCharge.active' (Standard Switch).
        # Fixture value is false/off.
        one_time_charge = hass.states.get("switch.vitocal250a_one_time_dhw_charge")
        assert one_time_charge is not None
        assert one_time_charge.state == STATE_OFF
        registry_entry = er.async_get(hass).async_get(
            "switch.vitocal250a_one_time_dhw_charge"
        )
        assert registry_entry is not None
        assert (
            registry_entry.unique_id
            == "MOCK_GATEWAY_SERIAL-0-heating.dhw.oneTimeCharge.active"
        )

        # Test 2: Service Calls (turn_on).

        # Call turn_on service.
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.vitocal250a_one_time_dhw_charge"},
            blocking=True,
        )

        # Args: (Device, Feature, Value).
        # We need to verify it was called with value=True.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        # args[0] is Device, args[1] is Feature, args[2] is Value.
        assert args[1].name == "heating.dhw.oneTimeCharge.active"
        assert args[2] is True

        # Verify Optimistic State Update.
        # The switch should match the requested state immediately.
        one_time_charge = hass.states.get("switch.vitocal250a_one_time_dhw_charge")
        assert one_time_charge is not None
        assert one_time_charge.state == "on"

        # Test 3: Service Calls (turn_off).

        # Reset mock.
        mock_client.set_feature.reset_mock()

        # Call turn_off service.
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": "switch.vitocal250a_one_time_dhw_charge"},
            blocking=True,
        )

        # Verify set_feature called with value=False.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.dhw.oneTimeCharge.active"
        assert args[2] is False

        # Verify Optimistic State Update.
        one_time_charge = hass.states.get("switch.vitocal250a_one_time_dhw_charge")
        assert one_time_charge is not None
        assert one_time_charge.state == STATE_OFF

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_name", "entity_prefix"),
    [
        ("Vitocal250A", "vitocal250a"),
        ("Vitocal222S", "vitocal222s"),
        ("Vitodens200W", "vitodens200w"),
    ],
)
async def test_read_only_hygiene_does_not_create_switch_or_write(
    hass: HomeAssistant, device_name: str, entity_prefix: str
):
    """Keep read-only hygiene state as a binary sensor without a control."""
    # Arrange: Set up each fixture with a client-write spy.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "1", "token": "x"})
    entry.add_to_hass(hass)
    mock_client = FixtureViClient(device_name)
    mock_client.set_feature = AsyncMock(wraps=mock_client.set_feature)

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
        # Act: Load the integration and attempt to turn on the absent switch.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        hygiene_switch_id = f"switch.{entity_prefix}_dhw_hygiene"
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": hygiene_switch_id}, blocking=True
        )

        # Assert: The state remains available but cannot trigger a client write.
        assert hass.states.get(hygiene_switch_id) is None
        hygiene_binary_sensor = hass.states.get(
            f"binary_sensor.{entity_prefix}_dhw_hygiene_enabled"
        )
        assert hygiene_binary_sensor is not None
        mock_client.set_feature.assert_not_awaited()

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_switch_error_handling(hass: HomeAssistant, mock_client):
    """Test switch error handling and rollback."""
    # Arrange: Setup with a mock client that raises an error.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    # Simulate an API error during set_feature.

    # set_feature will raise an exception when called.
    async def mock_set_feature_error(device, feature, value):
        raise HomeAssistantError("API Error")

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature_error)

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
        # Act: Initialize integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Initial State Check (should be OFF according to fixture).
        switch_id = "switch.vitocal250a_one_time_dhw_charge"
        state = hass.states.get(switch_id)
        assert state is not None
        assert state.state == STATE_OFF

        # Act: Call turn_on service which will fail.
        # We expect a HomeAssistantError to be raised to the caller.
        with pytest.raises(HomeAssistantError) as error:
            await hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": switch_id},
                blocking=True,
            )

        assert error.value.translation_domain == DOMAIN
        assert error.value.translation_key == "switch_operation_failed"
        assert error.value.translation_placeholders is None
        assert isinstance(error.value.__cause__, HomeAssistantError)

        # Assert: State Rollback.
        # The switch should NOT be stuck in 'on' state; it should revert to 'off'.
        state = hass.states.get(switch_id)
        assert state is not None
        assert state.state == STATE_OFF

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_switch_api_rejection(hass: HomeAssistant):
    """Test switch handling of API logical rejection (success=False)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    mock_client = FixtureViClient("Vitocal250A")

    # Simulate API Logical Failure (Blocked).

    # set_feature returns success=False object.
    async def mock_set_feature_rejection(device, feature, value):
        response = CommandResponse(
            success=False, message="Blocked by device", reason=None
        )
        return (response, device)

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature_rejection)

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
        # Act: Initialize integration.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        switch_id = "switch.vitocal250a_one_time_dhw_charge"
        state = hass.states.get(switch_id)
        assert state is not None
        assert state.state == STATE_OFF

        # Act: Call turn_on.
        # We expect HomeAssistantError because success=False.
        with pytest.raises(ServiceValidationError) as error:
            await hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": switch_id},
                blocking=True,
            )

        assert error.value.translation_domain == DOMAIN
        assert error.value.translation_key == "command_rejected"
        assert error.value.translation_placeholders is None

        # Assert: Rollback occurred (State remains OFF).
        state = hass.states.get(switch_id)
        assert state is not None
        assert state.state == STATE_OFF

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("value", "expected_is_on"),
    [
        (True, True),
        ("on", True),
        ("active", True),
        (False, False),
        ("off", False),
        ("inactive", False),
        ("standby", None),
    ],
)
@pytest.mark.asyncio
async def test_switch_preserves_boolean_representations(
    mock_client, value: FeatureValue, expected_is_on: bool | None
) -> None:
    """Interpret supported boolean representations without losing availability.

    The "standby" case pins that a semantically invalid value yields an
    unknown state while the entity stays available.
    """
    # Arrange: Build a switch whose feature carries the given value.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    feature_name = "heating.dhw.oneTimeCharge.active"
    feature = dataclasses.replace(
        device.get_feature(feature_name), value=value, is_enabled=True
    )
    coordinator = MagicMock(
        data={"device": dataclasses.replace(device, features=[feature])}
    )
    entity = ViClimateSwitch(
        coordinator,
        "device",
        feature_name,
        SwitchEntityDescription(key=feature_name),
    )

    # Act and assert: The state reflects the value while the entity stays available.
    assert entity.is_on is expected_is_on
    assert entity.available


@pytest.mark.asyncio
async def test_switch_translates_client_validation_error(mock_client) -> None:
    """Translate client value validation without exposing its detail."""
    # Arrange: Reject the next write at the client's control-contract boundary.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    feature_name = "heating.dhw.oneTimeCharge.active"
    coordinator = MagicMock(data={"device": device})
    coordinator.async_set_feature = AsyncMock(side_effect=ValueError("private detail"))
    entity = ViClimateSwitch(
        coordinator,
        "device",
        feature_name,
        SwitchEntityDescription(key=feature_name, name="Charge"),
    )

    # Act and assert: The rejection surfaces as a translated error only.
    with (
        patch.object(entity, "async_write_ha_state"),
        pytest.raises(ServiceValidationError) as error,
    ):
        await entity.async_turn_on()

    assert error.value.translation_key == "command_rejected"
    assert isinstance(error.value.__cause__, ValueError)
