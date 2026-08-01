"""Tests for integration setup, unload, and auth bridge behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
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


def _make_reauth_error() -> OAuth2TokenRequestReauthError:
    """Create a mock OAuth2TokenRequestReauthError for testing."""
    return OAuth2TokenRequestReauthError(
        request_info=MagicMock(),
        history=(),
        status=400,
        message="Bad Request",
        headers=MagicMock(),
        domain=DOMAIN,
    )


def _make_token_error() -> OAuth2TokenRequestError:
    """Create a mock OAuth2TokenRequestError for testing."""
    return OAuth2TokenRequestError(
        request_info=MagicMock(),
        history=(),
        status=500,
        message="Internal Server Error",
        headers=MagicMock(),
        domain=DOMAIN,
    )


@pytest.mark.asyncio
async def test_async_setup_entry_raises_config_entry_auth_failed_on_reauth_error(
    hass: HomeAssistant,
) -> None:
    """Test setup raises ConfigEntryAuthFailed when the refresh token is rejected."""
    # Arrange: Register a config entry and force a reauth-class token error.
    entry = _build_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            side_effect=_make_reauth_error(),
        ),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        # Act: A 400-class token error triggers HA's reauth flow.
        await async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_returns_false_on_transient_token_error(
    hass: HomeAssistant,
) -> None:
    """Test setup returns False on non-reauth token errors without raising."""
    # Arrange: Register a config entry and force a transient token error.
    entry = _build_entry()
    entry.add_to_hass(hass)

    with (
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            side_effect=_make_token_error(),
        ),
    ):
        # Act: Attempt to set up the integration entry.
        result = await async_setup_entry(hass, entry)

    # Assert: Setup fails gracefully without raising.
    assert result is False
    assert hass.data[DOMAIN] == {}


@pytest.mark.asyncio
async def test_async_setup_entry_stores_only_main_coordinator(
    hass: HomeAssistant,
) -> None:
    """Test setup stores only the main coordinator in runtime data."""
    # Arrange: Build entry, coordinator, and forward-setup stub for the success path.
    entry = _build_entry()
    entry.add_to_hass(hass)
    client = MagicMock()
    auth_bridge = MagicMock()
    main_coordinator = MagicMock()
    main_coordinator.async_config_entry_first_refresh = AsyncMock(return_value=None)
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
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            forward_entry_setups,
        ),
    ):
        # Act: Set up the integration and store runtime data for the entry.
        result = await async_setup_entry(hass, entry)

    # Assert: Setup succeeds, stores the main coordinator, and forwards all platforms.
    assert result is True
    assert hass.data[DOMAIN][entry.entry_id] == {"data": main_coordinator}
    mock_client_class.assert_called_once_with(auth=auth_bridge)
    main_coordinator.async_config_entry_first_refresh.assert_awaited_once()
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
async def test_haauth_wraps_reauth_error_as_vi_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test the auth bridge wraps reauth-class errors as ViAuthError for the client."""
    # Arrange: Provide a session that fails with a reauth-class error.
    oauth_session = MagicMock()
    oauth_session.hass = hass
    oauth_session.token = {"access_token": "stale-token"}
    oauth_session.async_ensure_token_valid = AsyncMock(
        side_effect=_make_reauth_error(),
    )

    with patch(
        "custom_components.vi_climate_devices.async_get_clientsession",
        return_value=object(),
    ):
        auth_bridge = HAAuth(oauth_session)

    # Act and Assert: The client receives a ViAuthError with the original context.
    with pytest.raises(ViAuthError, match="expired or revoked"):
        await auth_bridge.async_get_access_token()


@pytest.mark.asyncio
async def test_haauth_wraps_token_error_as_vi_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test the auth bridge wraps transient token errors as ViAuthError for the client."""
    # Arrange: Provide a session that fails with a transient token error.
    oauth_session = MagicMock()
    oauth_session.hass = hass
    oauth_session.token = {"access_token": "stale-token"}
    oauth_session.async_ensure_token_valid = AsyncMock(
        side_effect=_make_token_error(),
    )

    with patch(
        "custom_components.vi_climate_devices.async_get_clientsession",
        return_value=object(),
    ):
        auth_bridge = HAAuth(oauth_session)

    # Act and Assert: The client receives a ViAuthError with the refresh failure message.
    with pytest.raises(ViAuthError, match="Failed to refresh HA token"):
        await auth_bridge.async_get_access_token()
