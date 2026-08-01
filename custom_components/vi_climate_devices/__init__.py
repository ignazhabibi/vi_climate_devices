"""The Viessmann Climate Devices integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from vi_api_client import ViClient as ViessmannClient
from vi_api_client.auth import AbstractAuth

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
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

    # Ensure token is valid before starting.
    try:
        await session.async_ensure_token_valid()
    except OAuth2TokenRequestReauthError as err:
        raise ConfigEntryAuthFailed(
            "OAuth refresh token rejected by Viessmann - re-authentication required"
        ) from err
    except OAuth2TokenRequestError as err:
        raise ConfigEntryNotReady("Unable to refresh the Viessmann token") from err

    # Create the Auth Bridge
    auth = HAAuth(session)

    # Initialize the library with the auth bridge
    client = ViessmannClient(auth=auth)

    # 1. Main Coordinator (Devices API)
    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator}

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
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]
