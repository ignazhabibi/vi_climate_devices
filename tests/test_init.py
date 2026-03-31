"""Tests for integration setup, unload, and auth bridge behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.auth import ViAuthError

from custom_components.vi_climate_devices import (
    PLATFORMS,
    HAAuth,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.vi_climate_devices.const import DOMAIN


def _build_entry() -> MockConfigEntry:
    """Create a config entry with OAuth token data."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "token": {
                "access_token": "initial-token",
                "expires_at": 3_800_000_000,
                "refresh_token": "refresh-token",
                "token_type": "Bearer",
            }
        },
    )


@pytest.mark.asyncio
async def test_async_setup_entry_returns_false_when_token_validation_fails(
    hass: HomeAssistant,
) -> None:
    """Test setup aborts early when Home Assistant cannot validate the token."""
    # Arrange: Register a config entry and force token validation to fail.
    entry = _build_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            side_effect=RuntimeError("token refresh failed"),
        ),
    ):
        # Act: Attempt to set up the integration entry.
        result = await async_setup_entry(hass, entry)

    # Assert: Setup fails without storing runtime data for the entry.
    assert result is False
    assert hass.data[DOMAIN] == {}


@pytest.mark.asyncio
async def test_async_setup_entry_keeps_loading_when_analytics_refresh_fails(
    hass: HomeAssistant,
) -> None:
    """Test setup keeps runtime data when only the initial analytics refresh fails."""
    # Arrange: Build entry, coordinators, and forward-setup stub for the success path.
    entry = _build_entry()
    entry.add_to_hass(hass)
    client = MagicMock()
    auth_bridge = MagicMock()
    main_coordinator = MagicMock()
    main_coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
    analytics_coordinator = MagicMock()
    analytics_coordinator.async_config_entry_first_refresh = AsyncMock(
        side_effect=RuntimeError("analytics unavailable")
    )
    forward_entry_setups = AsyncMock(return_value=None)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            return_value=None,
        ),
        patch(
            "custom_components.vi_climate_devices.HAAuth",
            return_value=auth_bridge,
        ),
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=client,
        ) as mock_client_class,
        patch(
            "custom_components.vi_climate_devices.ViClimateDataUpdateCoordinator",
            return_value=main_coordinator,
        ),
        patch(
            "custom_components.vi_climate_devices.ViClimateAnalyticsCoordinator",
            return_value=analytics_coordinator,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            forward_entry_setups,
        ),
    ):
        # Act: Set up the integration despite the analytics warm-up failure.
        result = await async_setup_entry(hass, entry)

    # Assert: Setup succeeds, stores both coordinators, and forwards all platforms.
    assert result is True
    assert hass.data[DOMAIN][entry.entry_id] == {
        "data": main_coordinator,
        "analytics": analytics_coordinator,
    }
    mock_client_class.assert_called_once_with(auth=auth_bridge)
    main_coordinator.async_config_entry_first_refresh.assert_awaited_once()
    analytics_coordinator.async_config_entry_first_refresh.assert_awaited_once()
    forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_async_unload_entry_removes_runtime_data_after_platform_unload(
    hass: HomeAssistant,
) -> None:
    """Test unloading removes stored runtime data when platform unload succeeds."""
    # Arrange: Seed runtime data and make platform unload succeed.
    entry = _build_entry()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"data": MagicMock()}
    unload_platforms = AsyncMock(return_value=True)

    with patch.object(hass.config_entries, "async_unload_platforms", unload_platforms):
        # Act: Unload the config entry.
        result = await async_unload_entry(hass, entry)

    # Assert: The entry unloads cleanly and runtime data is removed.
    assert result is True
    assert entry.entry_id not in hass.data[DOMAIN]
    unload_platforms.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_runtime_data_when_platform_unload_fails(
    hass: HomeAssistant,
) -> None:
    """Test unloading keeps runtime data intact when platform unload fails."""
    # Arrange: Seed runtime data and make platform unload fail.
    entry = _build_entry()
    runtime_data = {"data": MagicMock()}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data
    unload_platforms = AsyncMock(return_value=False)

    with patch.object(hass.config_entries, "async_unload_platforms", unload_platforms):
        # Act: Attempt to unload the config entry.
        result = await async_unload_entry(hass, entry)

    # Assert: The failure is reported and runtime data stays registered.
    assert result is False
    assert hass.data[DOMAIN][entry.entry_id] is runtime_data
    unload_platforms.assert_awaited_once_with(entry, PLATFORMS)


@pytest.mark.asyncio
async def test_haauth_async_get_access_token_returns_refreshed_token(
    hass: HomeAssistant,
) -> None:
    """Test the auth bridge returns the refreshed Home Assistant access token."""
    # Arrange: Provide a Home Assistant OAuth session with a valid token payload.
    oauth_session = MagicMock()
    oauth_session.hass = hass
    oauth_session.token = {"access_token": "fresh-token"}
    oauth_session.async_ensure_token_valid = AsyncMock(return_value=None)
    websession = object()

    with patch(
        "custom_components.vi_climate_devices.async_get_clientsession",
        return_value=websession,
    ):
        auth_bridge = HAAuth(oauth_session)

    # Act: Request the access token through the auth bridge.
    token = await auth_bridge.async_get_access_token()

    # Assert: The bridge reuses the refreshed token and cached aiohttp session.
    assert token == "fresh-token"
    assert auth_bridge.websession is websession
    oauth_session.async_ensure_token_valid.assert_awaited_once()


@pytest.mark.asyncio
async def test_haauth_async_get_access_token_wraps_refresh_errors(
    hass: HomeAssistant,
) -> None:
    """Test the auth bridge wraps Home Assistant token refresh errors for the client."""
    # Arrange: Provide a session that fails during token refresh.
    oauth_session = MagicMock()
    oauth_session.hass = hass
    oauth_session.token = {"access_token": "stale-token"}
    oauth_session.async_ensure_token_valid = AsyncMock(
        side_effect=RuntimeError("refresh exploded")
    )

    with patch(
        "custom_components.vi_climate_devices.async_get_clientsession",
        return_value=object(),
    ):
        auth_bridge = HAAuth(oauth_session)

    # Act and Assert: The client receives a ViAuthError with the original message.
    with pytest.raises(ViAuthError, match="refresh exploded"):
        await auth_bridge.async_get_access_token()
