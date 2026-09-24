"""Tests for privacy-safe write-command logging across entity platforms."""

import logging
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import CommandResponse, FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN

_COORDINATOR_LOGGER = "custom_components.vi_climate_devices.coordinator"


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False], ids=["accepted", "rejected"])
@pytest.mark.parametrize(
    "case",
    [
        (
            "number",
            "set_value",
            {
                "entity_id": "number.vitocal250a_heating_circuit_0_curve_slope",
                "value": 1.6,
            },
            "heating.circuits.0.heating.curve.slope",
        ),
        (
            "select",
            "select_option",
            {"entity_id": "select.vitocal250a_dhw_mode", "option": "off"},
            "heating.dhw.operating.modes.active",
        ),
        (
            "switch",
            "turn_on",
            {"entity_id": "switch.vitocal250a_one_time_dhw_charge"},
            "heating.dhw.oneTimeCharge.active",
        ),
        (
            "climate",
            "set_temperature",
            {"entity_id": "climate.vitocal250a_heating_circuit_0", "temperature": 21.0},
            "heating.circuits.0.operating.programs.normalHeating.temperature",
        ),
        (
            "water_heater",
            "set_temperature",
            {
                "entity_id": "water_heater.vitocal250a_dhw_water_heater",
                "temperature": 45.0,
            },
            "heating.dhw.temperature.main",
        ),
    ],
)
async def test_command_response_is_logged_once_without_private_data(
    hass: HomeAssistant,
    mock_client: FixtureViClient,
    caplog: pytest.LogCaptureFixture,
    case: tuple[str, str, dict[str, str | float], str],
    success: bool,
) -> None:
    """Every writable platform reports one safe response per API command."""
    # Arrange: Load one writable fixture device and a response with private text.
    domain, service, data, feature_name = case
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)
    reason = "COMMAND_EXECUTION_SUCCESS" if success else "DEVICE_COMMUNICATION_ERROR"
    response = CommandResponse(
        success=success,
        message="secret response for installation-123 and gw-main",
        reason=reason,
    )

    async def set_feature(device, feature, value):
        return response, device

    mock_client.set_feature = AsyncMock(side_effect=set_feature)

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
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Act: Issue one Home Assistant service call through the platform.
        with caplog.at_level(logging.DEBUG, logger=_COORDINATOR_LOGGER):
            expected_error = (
                nullcontext() if success else pytest.raises(ServiceValidationError)
            )
            with expected_error:
                await hass.services.async_call(domain, service, data, blocking=True)

        # Assert: One result describes API acceptance, never the raw message.
        result_logs = [
            record.getMessage()
            for record in caplog.records
            if record.name.startswith("custom_components.vi_climate_devices")
            and "command response" in record.getMessage().lower()
        ]
        assert result_logs == [
            f"Feature command response {'accepted' if success else 'rejected'}: "
            f"feature={feature_name}, success={success}, reason={reason}"
        ]
        result_text = "\n".join(result_logs)
        assert "secret response" not in result_text
        assert "installation-123" not in result_text
        assert "gw-main" not in result_text
        assert "MOCK_GATEWAY_SERIAL" not in result_text
        assert "abc" not in result_text
        mock_client.set_feature.assert_awaited_once()

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
