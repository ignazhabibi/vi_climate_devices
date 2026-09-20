"""Tests for the Viessmann Heat select platform."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.select import (
    SERVICE_SELECT_OPTION,
    SelectEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import (
    CommandResponse,
    FeatureControl,
    FeatureValue,
    FixtureViClient,
)

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.exceptions import config_entry_auth_failed
from custom_components.vi_climate_devices.select import ViClimateSelect


@pytest.mark.asyncio
async def test_select_handles_device_removed_by_refresh() -> None:
    """Do not expose stale options after the coordinator loses a device."""
    # Arrange: Build a select using the fixture's writable DHW mode feature.
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature_name = "heating.dhw.operating.modes.active"
    coordinator = MagicMock(data={"device": device})
    entity = ViClimateSelect(
        coordinator,
        "device",
        feature_name,
        SelectEntityDescription(key=feature_name),
    )

    # Act: Simulate a refresh which removes the device.
    coordinator.data = {}

    # Assert: State, metadata, and attempted writes fail safely.
    assert entity.feature_data is None
    assert entity.current_option is None
    assert entity.device_info is None

    # Act and assert: A write and a new entity both require an available device.
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_select_option("efficient")

    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "feature_unavailable"
    assert error.value.translation_placeholders is None

    with pytest.raises(ValueError, match="Device missing"):
        ViClimateSelect(
            MagicMock(data={}),
            "missing",
            feature_name,
            SelectEntityDescription(key=feature_name),
        )


@pytest.mark.asyncio
async def test_select_creation_and_services(hass: HomeAssistant, mock_client):
    """Test select entity creation and service calls."""
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

        # Test 1: DHW Mode (Standard Entity).

        # Verify initial state and options from fixture.
        dhw_mode = hass.states.get("select.vitocal250a_dhw_mode")
        assert dhw_mode is not None
        assert dhw_mode.state == "efficient"
        assert "efficientWithMinComfort" in dhw_mode.attributes["options"]

        # Act: Select 'efficientWithMinComfort' option.
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {
                "entity_id": "select.vitocal250a_dhw_mode",
                "option": "efficientWithMinComfort",
            },
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.dhw.operating.modes.active"
        assert args[2] == "efficientWithMinComfort"

        # Verify Optimistic Update (Option A).
        dhw_mode = hass.states.get("select.vitocal250a_dhw_mode")
        assert dhw_mode is not None
        assert dhw_mode.state == "efficientWithMinComfort"

        # Test 2: Circuit Mode (Circuit 0).

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Verify initial state.
        circuit_mode = hass.states.get(
            "select.vitocal250a_heating_circuit_0_operation_mode"
        )
        assert circuit_mode is not None
        assert circuit_mode.state == "heating"

        # Act: Select 'standby' option.
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {
                "entity_id": "select.vitocal250a_heating_circuit_0_operation_mode",
                "option": "standby",
            },
            blocking=True,
        )

        # Verify Service Call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == "heating.circuits.0.operating.modes.active"
        assert args[2] == "standby"

        # Verify Optimistic Update.
        circuit_mode = hass.states.get(
            "select.vitocal250a_heating_circuit_0_operation_mode"
        )
        assert circuit_mode is not None
        assert circuit_mode.state == "standby"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_select_error_handling(hass: HomeAssistant, mock_client):
    """Test select error handling and rollback (Option B)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    # Simulate API Error.
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

        # Initial State Check.
        entity_id = "select.vitocal250a_dhw_mode"
        state = hass.states.get(entity_id)
        assert state is not None
        original_state = state.state
        assert original_state == "efficient"

        # Act: Try to change option (Should fail).
        target_option = "off"

        with pytest.raises(HomeAssistantError) as error:
            await hass.services.async_call(
                "select",
                SERVICE_SELECT_OPTION,
                {"entity_id": entity_id, "option": target_option},
                blocking=True,
            )

        assert error.value.translation_domain == DOMAIN
        assert error.value.translation_key == "selection_failed"
        assert error.value.translation_placeholders is None
        assert isinstance(error.value.__cause__, HomeAssistantError)

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == original_state

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_select_api_rejection(hass: HomeAssistant, mock_client):
    """Test select handling of API logical rejection (success=False)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {"access_token": "mock", "expires_at": 9999999999},
        },
    )
    entry.add_to_hass(hass)

    # Simulate API Logical Failure.

    async def mock_set_feature_rejection(device, feature, value):
        response = CommandResponse(
            success=False, message="Rejected", reason="DEVICE_COMMUNICATION_ERROR"
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
        # Act: Initialize.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "select.vitocal250a_dhw_mode"
        state = hass.states.get(entity_id)
        assert state is not None
        original_state = state.state  # "efficient"

        # Act: Try to change option.
        with pytest.raises(ServiceValidationError) as error:
            await hass.services.async_call(
                "select",
                SERVICE_SELECT_OPTION,
                {"entity_id": entity_id, "option": "off"},
                blocking=True,
            )

        assert error.value.translation_domain == DOMAIN
        assert error.value.translation_key == "command_rejected"
        assert error.value.translation_placeholders is None

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == original_state

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_select_preserves_reauthentication_failure() -> None:
    """Preserve reauthentication signals from a select action."""
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature_name = "heating.dhw.operating.modes.active"
    coordinator = MagicMock(data={"device": device})
    coordinator.async_set_feature = AsyncMock(side_effect=config_entry_auth_failed())
    entity = ViClimateSelect(
        coordinator,
        "device",
        feature_name,
        SelectEntityDescription(key=feature_name, name="Mode"),
    )

    with (
        patch.object(entity, "async_write_ha_state"),
        pytest.raises(ConfigEntryAuthFailed) as error,
    ):
        await entity.async_select_option("off")

    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "authentication_failed"


@pytest.mark.asyncio
async def test_select_options_reject_non_string_shapes() -> None:
    """Build options only from string entries, never by stringifying JSON."""
    # Arrange: Replace the mode feature with a control carrying mixed shapes.
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature_name = "heating.dhw.operating.modes.active"
    control = FeatureControl(
        command_name="setMode",
        param_name="mode",
        required_params=(),
        parent_feature_name="heating.dhw.operating.modes",
        uri="https://mock.local/command",
        options=(
            5,
            True,
            ["efficient"],
            {"value": 5},
            {"label": "misplaced"},
            {"value": "ok"},
            "standby",
        ),
    )
    feature = device.get_feature(feature_name)
    assert feature is not None
    feature = dataclasses.replace(feature, control=control, is_enabled=True)
    coordinator = MagicMock(
        data={"device": dataclasses.replace(device, features=[feature])}
    )
    entity = ViClimateSelect(
        coordinator,
        "device",
        feature_name,
        SelectEntityDescription(key=feature_name),
    )

    # Act and assert: Only strings and string-valued entries become options.
    assert entity.options == ["ok", "standby"]


@pytest.mark.parametrize(
    ("value", "expected_current_option"),
    [
        ("efficient", "efficient"),
        (5, None),
        (["efficient"], None),
        ({"active": "efficient"}, None),
        ("bogus", None),
    ],
)
@pytest.mark.asyncio
async def test_select_reports_unknown_state_for_non_option_values(
    mock_client, value: FeatureValue, expected_current_option: str | None
) -> None:
    """Expose unknown states for values outside the announced options.

    The non-string cases pin that states are never fabricated by converting
    arbitrary JSON lists or objects to strings.
    """
    # Arrange: Build a select whose feature carries the given value.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    feature_name = "heating.dhw.operating.modes.active"
    feature = dataclasses.replace(
        device.get_feature(feature_name), value=value, is_enabled=True
    )
    coordinator = MagicMock(
        data={"device": dataclasses.replace(device, features=[feature])}
    )
    entity = ViClimateSelect(
        coordinator,
        "device",
        feature_name,
        SelectEntityDescription(key=feature_name),
    )

    # Act and assert: Only announced string options become states.
    assert entity.current_option == expected_current_option
    assert entity.available


@pytest.mark.asyncio
async def test_select_translates_client_validation_error(mock_client) -> None:
    """Translate client value validation without exposing its detail."""
    # Arrange: Reject the next write at the client's control-contract boundary.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    feature_name = "heating.dhw.operating.modes.active"
    coordinator = MagicMock(data={"device": device})
    coordinator.async_set_feature = AsyncMock(side_effect=ValueError("private detail"))
    entity = ViClimateSelect(
        coordinator,
        "device",
        feature_name,
        SelectEntityDescription(key=feature_name, name="Mode"),
    )

    # Act and assert: The rejection surfaces as a translated error only.
    with (
        patch.object(entity, "async_write_ha_state"),
        pytest.raises(ServiceValidationError) as error,
    ):
        await entity.async_select_option("off")

    assert error.value.translation_key == "command_rejected"
    assert isinstance(error.value.__cause__, ValueError)
