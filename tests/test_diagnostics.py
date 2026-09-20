"""Tests for privacy-safe integration diagnostics."""

import json
from typing import cast
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion
from vi_api_client import Device, Feature, FeatureControl, FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _contains_value(value: object, canary: str) -> bool:
    """Return whether a nested diagnostics value contains a canary."""
    if isinstance(value, dict):
        return any(_contains_value(item, canary) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value(item, canary) for item in value)
    return canary in str(value)


@pytest.mark.asyncio
async def test_config_entry_diagnostics_matches_snapshot(
    hass: HomeAssistant, mock_client: FixtureViClient, snapshot: SnapshotAssertion
) -> None:
    """Test diagnostics serialize the cached representative device snapshot."""
    # Arrange: Put the fixture device in the entry coordinator cache.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    entry = MockConfigEntry(domain=DOMAIN)
    entry.runtime_data = MagicMock(data={"gateway-device": device})

    # Act: Request the config-entry diagnostics through Home Assistant's hook.
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Assert: The complete safe projection stays stable and JSON-compatible.
    assert diagnostics == snapshot
    json.dumps(diagnostics, sort_keys=True)


@pytest.mark.asyncio
async def test_config_entry_diagnostics_omit_sensitive_cached_data(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics redact sensitive values without consulting a client."""
    # Arrange: Put distinctive sensitive values only in the cached device snapshot.
    installation_canary = "installation-canary"
    gateway_serial_canary = "gateway-serial-canary"
    device_id_canary = "device-id-canary"
    user_alias_canary = "user-alias-canary"
    description_canary = "description-canary"
    location_canary = "location-canary"
    serial_number_canary = "serial-number-canary"
    raw_message_canary = "raw-message-canary"
    address_canary = "address-canary"
    coordinate_canary = "coordinate-canary"
    device = Device(
        id=device_id_canary,
        gateway_serial=gateway_serial_canary,
        installation_id=installation_canary,
        model_id="Vitocal test model",
        device_type="heating",
        status="connected",
        features=[
            Feature(
                name="device.configuration.houseLocation",
                value={
                    "alias": user_alias_canary,
                    "value": location_canary,
                },
                unit=None,
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="device.serialNumber",
                value=serial_number_canary,
                unit=None,
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="device.messages.info.raw",
                value={
                    "description": description_canary,
                    "message": raw_message_canary,
                },
                unit=None,
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="heating.configuration.summary",
                value={
                    "address": address_canary,
                    "coordinates": coordinate_canary,
                    "resourceId": "resource-identifier-canary",
                    "deviceID": "uppercase-id-canary",
                    "RESOURCE_ID": "uppercase-underscore-id-canary",
                    "accessToken": "cached-token-canary",
                    "credential": "cached-credential-canary",
                },
                unit=None,
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="heating.diagnostics.unsupportedValue",
                # A deliberately non-JSON probe: diagnostics must handle values
                # outside the FeatureValue contract without crashing or leaking.
                value=object(),  # pyright: ignore[reportArgumentType]
                unit=None,
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="heating.configuration.targetTemperature",
                value=20.0,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
                control=FeatureControl(
                    command_name="setTargetTemperature",
                    param_name="temperature",
                    required_params=(),
                    parent_feature_name="heating.configuration.targetTemperature",
                    uri="https://api.example.invalid/command-uri-canary",
                    min=3.0,
                    max=37.0,
                    step=0.1,
                    value_type="number",
                    options=(
                        "option-a",
                        "https://example.invalid/scalar-uri-canary",
                        {
                            "id": "option-id-canary",
                            "uri": "option-uri-canary",
                            "token": "option-token-canary",
                        },
                    ),
                ),
            ),
        ],
    )
    coordinator = MagicMock(data={"cache-key-canary": device})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="entry-title-canary",
        unique_id="unique-id-canary",
        data={
            "token": {
                "access_token": "access-token-canary",
                "refresh_token": "refresh-token-canary",
            },
            "client_id": "credential-canary",
        },
        options={"option-canary": "option-value-canary"},
    )
    entry.runtime_data = coordinator

    # Act: Request diagnostics from the coordinator cache.
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Assert: Identifiers and all sensitive canaries are absent at every depth.
    for canary in [
        installation_canary,
        gateway_serial_canary,
        device_id_canary,
        user_alias_canary,
        description_canary,
        location_canary,
        serial_number_canary,
        raw_message_canary,
        address_canary,
        coordinate_canary,
        "command-uri-canary",
        "cache-key-canary",
        "entry-title-canary",
        "unique-id-canary",
        "access-token-canary",
        "refresh-token-canary",
        "credential-canary",
        "option-canary",
        "option-value-canary",
        "resource-identifier-canary",
        "cached-token-canary",
        "cached-credential-canary",
        "option-id-canary",
        "option-uri-canary",
        "option-token-canary",
        "uppercase-id-canary",
        "uppercase-underscore-id-canary",
        "scalar-uri-canary",
    ]:
        assert not _contains_value(diagnostics, canary)
    assert diagnostics["devices"][0]["installation"] == "installation_1"
    assert diagnostics["devices"][0]["gateway"] == "gateway_1"
    assert diagnostics["devices"][0]["device"] == "device_1"
    diagnostic_features = cast(
        list[dict[str, object]], diagnostics["devices"][0]["features"]
    )
    target_feature = next(
        feature
        for feature in diagnostic_features
        if feature["name"] == "heating.configuration.targetTemperature"
    )
    assert cast(dict[str, object], target_feature["constraints"]) == {
        "max": 37.0,
        "min": 3.0,
        "options": [
            "option-a",
            "<redacted>",
            {"id": "<redacted>", "token": "<redacted>", "uri": "<redacted>"},
        ],
        "step": 0.1,
        "value_type": "number",
    }
    unsupported_feature = next(
        feature
        for feature in diagnostic_features
        if feature["name"] == "heating.diagnostics.unsupportedValue"
    )
    assert unsupported_feature["value"] is None
    assert coordinator.mock_calls == []
