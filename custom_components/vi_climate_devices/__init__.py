"""The Viessmann Climate Devices integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from vi_api_client import ViClient as ViessmannClient
from vi_api_client.auth import AbstractAuth, ViAuthError

from .const import DOMAIN
from .coordinator import ViClimateAnalyticsCoordinator, ViClimateDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.WATER_HEATER,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Viessmann Climate Devices component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Viessmann Climate Devices from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    # Ensure token is valid before starting
    try:
        await session.async_ensure_token_valid()
    except Exception as err:
        _LOGGER.error("Error ensuring token validity: %s", err)
        return False

    # Create the Auth Bridge
    auth = HAAuth(session)

    # Initialize the library with the auth bridge
    client = ViessmannClient(auth=auth)

    # 1. Main Coordinator (Devices API)
    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    # 2. Analytics Coordinator (Analytics API)
    analytics_coordinator = ViClimateAnalyticsCoordinator(hass, client, coordinator)

    # Attempt to fetch initial analytics data, but don't fail setup
    try:
        await analytics_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Failed to fetch initial analytics data: %s", err)

    hass.data[DOMAIN][entry.entry_id] = {
        "data": coordinator,
        "analytics": analytics_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class HAAuth(AbstractAuth):
    """Home Assistant Auth Bridge for vi_api_client."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session) -> None:
        """Initialize the auth bridge."""
        # We don't use the lib's websession directly for requests here
        super().__init__(websession=None)
        self._session = session
        self.websession = async_get_clientsession(session.hass)

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        try:
            await self._session.async_ensure_token_valid()
            return self._session.token["access_token"]
        except Exception as err:
            raise ViAuthError(f"Failed to refresh HA token: {err}") from err
