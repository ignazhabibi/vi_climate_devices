"""Tests for coordinator discovery and refresh behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed
from vi_api_client import Device, Feature, ViAuthError, ViConnectionError

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


def _make_reauth_error() -> OAuth2TokenRequestReauthError:
    """Create a reauth-class OAuth token error."""
    return OAuth2TokenRequestReauthError(
        request_info=MagicMock(),
        history=(),
        status=400,
        message="Bad Request",
        headers=MagicMock(),
        domain="vi_climate_devices",
    )


def _make_token_error() -> OAuth2TokenRequestError:
    """Create a transient OAuth token error."""
    return OAuth2TokenRequestError(
        request_info=MagicMock(),
        history=(),
        status=500,
        message="Internal Server Error",
        headers=MagicMock(),
        domain="vi_climate_devices",
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
async def test_data_coordinator_raises_when_all_device_updates_fail(
    hass: HomeAssistant, mock_client
) -> None:
    """Test refresh fails when no known device can be updated."""
    # Arrange: Seed one known device and make its refresh raise a transient error.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    mock_client.update_device = AsyncMock(
        side_effect=ViConnectionError("device offline")
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Treat the failed poll as an unavailable coordinator update.
    with pytest.raises(UpdateFailed, match="Failed to update all devices"):
        await coordinator._async_update_data()

    # Assert: Keep the immutable device reference for a later recovery attempt.
    assert coordinator._known_devices == [known_device]
    assert not coordinator.is_device_available("gw-main_device-0")


@pytest.mark.asyncio
async def test_data_coordinator_marks_only_failed_device_unavailable(
    hass: HomeAssistant, mock_client
) -> None:
    """Test partial refresh failures only make the affected device unavailable."""
    # Arrange: Refresh one device and fail the second device with a transient error.
    refreshed_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    failing_device = _build_device(device_id="device-1", gateway_serial="gw-backup")
    mock_client.update_device = AsyncMock(
        side_effect=[refreshed_device, ViConnectionError("device offline")]
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [refreshed_device, failing_device]
    coordinator._failed_device_keys = {"gw-main_device-0"}

    # Act: Refresh the coordinator with one successful and one failed device poll.
    result = await coordinator._async_update_data()

    # Assert: Preserve the failed device for recovery while exposing its outage.
    assert result == {
        "gw-main_device-0": refreshed_device,
        "gw-backup_device-1": failing_device,
    }
    assert coordinator.is_device_available("gw-main_device-0")
    assert not coordinator.is_device_available("gw-backup_device-1")


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


@pytest.mark.asyncio
async def test_data_coordinator_propagates_oauth_reauth_error(
    hass: HomeAssistant, mock_client
) -> None:
    """Test polling preserves an OAuth error that requires reauthentication."""
    # Arrange: Seed a device and reject its refresh token during polling.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    reauth_error = _make_reauth_error()
    mock_client.update_device = AsyncMock(side_effect=reauth_error)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Home Assistant receives the original reauth-class error.
    with pytest.raises(OAuth2TokenRequestReauthError) as raised_error:
        await coordinator._async_update_data()
    assert raised_error.value is reauth_error


@pytest.mark.asyncio
async def test_data_coordinator_propagates_transient_oauth_error(
    hass: HomeAssistant, mock_client
) -> None:
    """Test polling preserves a transient OAuth error for coordinator retry."""
    # Arrange: Seed a device and simulate a temporary token endpoint failure.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    token_error = _make_token_error()
    mock_client.update_device = AsyncMock(side_effect=token_error)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Home Assistant receives the original retryable error.
    with pytest.raises(OAuth2TokenRequestError) as raised_error:
        await coordinator._async_update_data()
    assert raised_error.value is token_error
