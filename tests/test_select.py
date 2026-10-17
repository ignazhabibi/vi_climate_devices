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

# Heating circuit and DHW modes have no select; the ventilation mode of the
# Vitopure 350 is an auto-discovered select.
VENTILATION_FIXTURE = "Vitopure350"
VENTILATION_MODE_FEATURE = "ventilation.operating.modes.active"
VENTILATION_MODE_ENTITY = "select.vitopure350_ventilation_operating_modes_active"


async def _setup_integration(hass: HomeAssistant, client: FixtureViClient) -> None:
    """Set up the integration with the given fixture client."""
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

    # Assert: State, availability, and attempted writes fail safely.
    assert entity.feature_data is None
    assert entity.current_option is None
    assert not entity.available

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
async def test_heating_and_dhw_modes_have_no_select(hass: HomeAssistant, mock_client):
    """Set heating circuit and DHW modes only through climate and water heater."""
    # Act: Set up the integration with the Vitocal 250-A fixture.
    await _setup_integration(hass, mock_client)

    # Assert: No select exists, the climate and water heater entities do.
    assert hass.states.async_entity_ids("select") == []
    assert hass.states.get("climate.vitocal250a_heating_circuit") is not None
    assert hass.states.get("water_heater.vitocal250a_dhw_water_heater") is not None


@pytest.mark.asyncio
async def test_select_creation_and_services(hass: HomeAssistant):
    """Create an auto-discovered select and write the selected option."""
    # Arrange: Spy on writes of the ventilation fixture client.
    client = FixtureViClient(VENTILATION_FIXTURE)
    client.set_feature = AsyncMock(wraps=client.set_feature)
    await _setup_integration(hass, client)

    # Assert: The initial state and options come from the fixture.
    state = hass.states.get(VENTILATION_MODE_ENTITY)
    assert state is not None
    assert state.state == "sensorDriven"
    assert state.attributes["options"] == ["permanent", "ventilation", "sensorDriven"]

    # Act: Select another option.
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {"entity_id": VENTILATION_MODE_ENTITY, "option": "permanent"},
        blocking=True,
    )

    # Assert: The option is written and shown.
    assert client.set_feature.call_count == 1
    args, _ = client.set_feature.call_args
    assert args[1].name == VENTILATION_MODE_FEATURE
    assert args[2] == "permanent"
    state = hass.states.get(VENTILATION_MODE_ENTITY)
    assert state is not None
    assert state.state == "permanent"


@pytest.mark.asyncio
async def test_select_error_handling(hass: HomeAssistant):
    """Roll back the optimistic option when the write fails."""
    # Arrange: Fail every write.
    client = FixtureViClient(VENTILATION_FIXTURE)
    client.set_feature = AsyncMock(side_effect=HomeAssistantError("API Error"))
    await _setup_integration(hass, client)

    # Act: Try to change the option.
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {"entity_id": VENTILATION_MODE_ENTITY, "option": "permanent"},
            blocking=True,
        )

    # Assert: The error is translated and the previous option is restored.
    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "selection_failed"
    assert error.value.translation_placeholders is None
    assert isinstance(error.value.__cause__, HomeAssistantError)
    state = hass.states.get(VENTILATION_MODE_ENTITY)
    assert state is not None
    assert state.state == "sensorDriven"


@pytest.mark.asyncio
async def test_select_api_rejection(hass: HomeAssistant):
    """Roll back the optimistic option when the API rejects the command."""

    # Arrange: Reject every write logically.
    async def reject(device, feature, value):
        response = CommandResponse(
            success=False, message="Rejected", reason="DEVICE_COMMUNICATION_ERROR"
        )
        return (response, device)

    client = FixtureViClient(VENTILATION_FIXTURE)
    client.set_feature = AsyncMock(side_effect=reject)
    await _setup_integration(hass, client)

    # Act: Try to change the option.
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            "select",
            SERVICE_SELECT_OPTION,
            {"entity_id": VENTILATION_MODE_ENTITY, "option": "permanent"},
            blocking=True,
        )

    # Assert: The rejection is translated and the previous option is restored.
    assert error.value.translation_domain == DOMAIN
    assert error.value.translation_key == "command_rejected"
    assert error.value.translation_placeholders is None
    state = hass.states.get(VENTILATION_MODE_ENTITY)
    assert state is not None
    assert state.state == "sensorDriven"


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
    # Assert: The unconfirmed option is not left visible after the failure.
    assert entity.current_option == "efficient"


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
        parameter_name="mode",
        required_parameters=(),
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
