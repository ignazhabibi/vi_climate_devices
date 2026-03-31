"""Tests for coordinator discovery and refresh behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from vi_api_client import Device, Feature, ViAuthError

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)


def _build_device(
    *,
    device_id: str,
    gateway_serial: str,
    model_id: str = "Vitocal250A",
) -> Device:
    """Create a minimal Viessmann device for coordinator tests."""
    return Device(
        id=device_id,
        gateway_serial=gateway_serial,
        installation_id="installation-1",
        model_id=model_id,
        device_type="heating",
        status="online",
        features=[
            Feature(
                name="heating.sensors.temperature.outside",
                value=12.2,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
            )
        ],
    )


@pytest.mark.asyncio
async def test_data_coordinator_raises_when_no_installations_exist(
    hass: HomeAssistant, mock_client
) -> None:
    """Test discovery raises UpdateFailed when the account has no installations."""
    # Arrange: Return an empty installation list from the Viessmann client.
    mock_client.get_installations = AsyncMock(return_value=[])
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)

    # Act and Assert: The first refresh aborts with a clear update failure.
    with pytest.raises(UpdateFailed, match="No installations found"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_discovers_devices_and_filters_ignored_ids(
    hass: HomeAssistant, mock_client
) -> None:
    """Test discovery keeps regular devices and drops configured ignored device ids."""
    # Arrange: Return one real device and one ignored gateway pseudo-device.
    active_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    ignored_device = _build_device(
        device_id="gateway",
        gateway_serial="gw-ignored",
        model_id="Gateway",
    )
    mock_client.get_installations = AsyncMock(
        return_value=[SimpleNamespace(id="installation-1")]
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[active_device, ignored_device]
    )
    mock_client.update_device = AsyncMock(return_value=active_device)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)

    # Act: Run the first coordinator refresh with discovery enabled.
    result = await coordinator._async_update_data()

    # Assert: Only the real device survives discovery and is tracked for updates.
    assert result == {"gw-main_device-0": active_device}
    assert coordinator._known_devices == [active_device]


@pytest.mark.asyncio
async def test_data_coordinator_keeps_last_device_state_when_refresh_fails(
    hass: HomeAssistant, mock_client
) -> None:
    """Test refresh falls back to the previous immutable device when one update fails."""
    # Arrange: Seed one known device and make its refresh raise a transient error.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    mock_client.update_device = AsyncMock(side_effect=RuntimeError("device offline"))
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act: Refresh the coordinator with the failing device update.
    result = await coordinator._async_update_data()

    # Assert: The previous device object stays available in coordinator data.
    assert result == {"gw-main_device-0": known_device}
    assert coordinator._known_devices == [known_device]


@pytest.mark.asyncio
async def test_data_coordinator_raises_reauth_when_device_update_loses_auth(
    hass: HomeAssistant, mock_client
) -> None:
    """Test refresh raises ConfigEntryAuthFailed when device polling loses auth."""
    # Arrange: Seed one known device and make the update raise ViAuthError.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    mock_client.update_device = AsyncMock(side_effect=ViAuthError("token expired"))
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: The auth failure is escalated to Home Assistant reauth.
    with pytest.raises(ConfigEntryAuthFailed, match="token expired"):
        await coordinator._async_update_data()
