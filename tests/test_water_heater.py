"""Tests for ViClimate water heater entities."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.water_heater import (
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
    STATE_ECO,
    STATE_GAS,
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
    WaterHeaterEntityFeature,
)
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.mock_client import MockViClient
from vi_api_client.models import CommandResponse, Device, Feature

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.water_heater import (
    FEATURE_MODE,
    FEATURE_TARGET_TEMP,
    ViClimateWaterHeater,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("device_name", "api_mode", "api_modes", "ha_mode", "expected_api_mode"),
    [
        pytest.param(
            "Vitodens200W",
            "balanced",
            ["balanced", "off"],
            STATE_GAS,
            "balanced",
            id="vitodens-balanced-is-gas",
        ),
        pytest.param(
            "Vitodens200W",
            "standard",
            ["standard", "off"],
            STATE_GAS,
            "standard",
            id="vitodens-standard-is-gas",
        ),
        pytest.param(
            "Vitocal250A",
            "balanced",
            ["balanced", "off"],
            STATE_HEAT_PUMP,
            "balanced",
            id="vitocal-balanced-is-heat-pump",
        ),
    ],
)
async def test_water_heater_maps_device_family_operation_modes(
    device_name: str,
    api_mode: str,
    api_modes: list[str],
    ha_mode: str,
    expected_api_mode: str,
) -> None:
    """Expose and set device-family-specific water-heater operations."""
    # Arrange: Create a device with the requested DHW mode configuration.
    client = MockViClient(device_name=device_name)
    fixture_device = (await client.get_full_installation_status("99999"))[0]
    mode_feature = fixture_device.get_feature(FEATURE_MODE)
    assert mode_feature is not None
    assert mode_feature.control is not None
    configured_mode_feature = replace(
        mode_feature,
        value=api_mode,
        control=replace(mode_feature.control, options=api_modes),
    )
    device = replace(
        fixture_device,
        features=[
            configured_mode_feature if feature.name == FEATURE_MODE else feature
            for feature in fixture_device.features
        ],
    )
    coordinator = MagicMock()
    coordinator.data = {"device": device}
    coordinator.async_set_feature = AsyncMock(
        return_value=CommandResponse(success=True)
    )
    target_feature = device.get_feature(FEATURE_TARGET_TEMP)
    assert target_feature is not None
    entity = ViClimateWaterHeater(coordinator, "device", target_feature)

    # Act and assert: Report only the standard HA operation and translate it back.
    assert entity.current_operation == ha_mode
    assert entity.operation_list == [ha_mode, STATE_OFF]
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_operation_mode(ha_mode)

    coordinator.async_set_feature.assert_awaited_once_with(
        "device", FEATURE_MODE, expected_api_mode
    )


@pytest.mark.asyncio
async def test_water_heater_omits_unknown_api_operation_modes() -> None:
    """Do not expose unknown API modes as Home Assistant operations."""
    # Arrange: Create a Vitocal device reporting an unsupported mode.
    client = MockViClient(device_name="Vitocal250A")
    fixture_device = (await client.get_full_installation_status("99999"))[0]
    mode_feature = fixture_device.get_feature(FEATURE_MODE)
    assert mode_feature is not None
    assert mode_feature.control is not None
    unknown_mode_feature = replace(
        mode_feature,
        value="unknownMode",
        control=replace(mode_feature.control, options=["unknownMode"]),
    )
    device = replace(
        fixture_device,
        features=[
            unknown_mode_feature if feature.name == FEATURE_MODE else feature
            for feature in fixture_device.features
        ],
    )
    coordinator = MagicMock()
    coordinator.data = {"device": device}
    target_feature = device.get_feature(FEATURE_TARGET_TEMP)
    assert target_feature is not None
    entity = ViClimateWaterHeater(coordinator, "device", target_feature)

    # Act and assert: Do not pass unknown vendor values to Home Assistant.
    assert entity.current_operation is None
    assert entity.operation_list == []


@pytest.mark.asyncio
async def test_water_heater_creation_and_services(hass: HomeAssistant, mock_client):
    """Test water heater entity creation and service calls."""
    # Arrange: Mock Config Entry.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {
                "access_token": "mock",
                "refresh_token": "mock",
                "expires_at": 9999999999,
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

        # Get the Water Heater Entity.
        entity_id = "water_heater.vitocal250a_dhw_water_heater"
        state = hass.states.get(entity_id)
        assert state is not None

        # Verify Initial Attributes from Fixture.
        # Temp: 55.0, Current: 46.8, Mode: efficient -> STATE_ECO.
        assert state.state == STATE_ECO
        assert float(state.attributes["current_temperature"]) == 46.8
        assert float(state.attributes["temperature"]) == 55.0
        assert state.attributes["min_temp"] == 10.0
        assert state.attributes["max_temp"] == 60.0
        # Verify constraints on entity
        component = hass.data.get("water_heater")
        assert component is not None
        entity = component.get_entity(entity_id)
        assert entity is not None
        # Use getattr because property might not exist in all HA versions
        assert (
            getattr(entity, "target_temperature_step", None) == 1.0
            or getattr(entity, "_attr_target_temperature_step", None) == 1.0
        )
        assert entity.suggested_display_precision == 0

        # Verify it is also in attributes (via extra_state_attributes)
        assert state.attributes["target_temp_step"] == 1.0
        assert state.attributes["supported_features"] == (
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE
        )

        # Act: Set Temperature to 45.0.
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_TEMPERATURE,
            {"entity_id": entity_id, "temperature": 45.0},
            blocking=True,
        )

        # Verify Service Call (Set Temp).
        # We expect set_feature to be called with "heating.dhw.temperature.main" and 45.0.
        # Note: Since set_feature is called multiple times if we chain tests, we check specific call.
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == FEATURE_TARGET_TEMP
        assert args[2] == 45.0

        # Verify Optimistic Update (Temp).
        state = hass.states.get(entity_id)
        assert state is not None
        assert float(state.attributes["temperature"]) == 45.0

        # Reset Mock.
        mock_client.set_feature.reset_mock()

        # Act: Set Mode to STATE_PERFORMANCE.
        # Based on mapping, STATE_PERFORMANCE maps to ["comfort", "efficientWithMinComfort"].
        # Fixture has "efficientWithMinComfort" available, so it should use that.
        await hass.services.async_call(
            "water_heater",
            SERVICE_SET_OPERATION_MODE,
            {"entity_id": entity_id, "operation_mode": STATE_PERFORMANCE},
            blocking=True,
        )

        # Verify Service Call (Set Mode).
        assert mock_client.set_feature.call_count == 1
        args, _ = mock_client.set_feature.call_args
        assert args[1].name == FEATURE_MODE
        assert args[2] == "efficientWithMinComfort"

        # Verify Optimistic Update (Mode).
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_PERFORMANCE

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_feature_name", "read_only_feature_name"),
    [
        pytest.param(FEATURE_MODE, None, id="missing-mode-control"),
        pytest.param(None, FEATURE_TARGET_TEMP, id="read-only-target-control"),
    ],
)
async def test_water_heater_requires_writable_target_and_mode(
    hass: HomeAssistant,
    mock_client,
    missing_feature_name: str | None,
    read_only_feature_name: str | None,
) -> None:
    """Do not create a water heater without both writable controls."""
    fixture_device = (await mock_client.get_full_installation_status("99999"))[0]
    device_without_controls = Device(
        id=fixture_device.id,
        gateway_serial=fixture_device.gateway_serial,
        installation_id=fixture_device.installation_id,
        model_id=fixture_device.model_id,
        device_type=fixture_device.device_type,
        status=fixture_device.status,
        features=[
            Feature(
                name=feature.name,
                value=feature.value,
                unit=feature.unit,
                is_enabled=feature.is_enabled,
                is_ready=feature.is_ready,
                control=None,
            )
            if feature.name == read_only_feature_name
            else feature
            for feature in fixture_device.features
            if feature.name != missing_feature_name
        ],
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[device_without_controls]
    )
    mock_client.update_device = AsyncMock(return_value=device_without_controls)

    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
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

        assert hass.states.get("water_heater.vitocal250a_dhw_water_heater") is None

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_water_heater_error_handling(hass: HomeAssistant, mock_client):
    """Test water heater error handling and rollback (Option B)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "water_heater.vitocal250a_dhw_water_heater"
        state = hass.states.get(entity_id)
        assert state is not None
        original_temp = float(state.attributes["temperature"])

        # Act: Try to set temperature (Should fail).
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "water_heater",
                SERVICE_SET_TEMPERATURE,
                {"entity_id": entity_id, "temperature": 40.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state is not None
        assert float(state.attributes["temperature"]) == original_temp

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_water_heater_api_rejection(hass: HomeAssistant, mock_client):
    """Test water heater handling of API logical rejection (success=False)."""
    # Arrange: Setup integration.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)

    # Simulate API Logical Failure.

    async def mock_set_feature_rejection(device, feature, value):
        response = CommandResponse(success=False, message="Locked", reason=None)
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "water_heater.vitocal250a_dhw_water_heater"
        state = hass.states.get(entity_id)
        assert state is not None
        original_temp = float(state.attributes["temperature"])

        # Act: Try to set temperature.
        with pytest.raises(HomeAssistantError, match="Command rejected: Locked"):
            await hass.services.async_call(
                "water_heater",
                SERVICE_SET_TEMPERATURE,
                {"entity_id": entity_id, "temperature": 40.0},
                blocking=True,
            )

        # Assert: Rollback occurred.
        state = hass.states.get(entity_id)
        assert state is not None
        assert float(state.attributes["temperature"]) == original_temp

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
