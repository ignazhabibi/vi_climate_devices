"""The Viessmann Climate Devices integration."""

from __future__ import annotations

import logging

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.update_coordinator import UpdateFailed
from vi_api_client import AbstractAuth, ViClient as ViessmannClient

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator
from .exceptions import config_entry_auth_failed, config_entry_not_ready

_LOGGER = logging.getLogger(__name__)

type ViClimateDevicesConfigEntry = ConfigEntry[ViClimateDataUpdateCoordinator]

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ViClimateDevicesConfigEntry
) -> bool:
    """Set up Viessmann Climate Devices from a config entry.

    Raises:
        ConfigEntryAuthFailed: If the OAuth refresh token is rejected.
        ConfigEntryNotReady: If OAuth setup cannot complete temporarily.
    """
    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                hass, entry
            )
        )
    except config_entry_oauth2_flow.ImplementationUnavailableError as err:
        _LOGGER.warning("Viessmann OAuth implementation is unavailable: %s", err)
        raise config_entry_not_ready() from err

    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    # Ensure token is valid before starting.
    try:
        await session.async_ensure_token_valid()
    except OAuth2TokenRequestReauthError as err:
        _LOGGER.warning("Viessmann token refresh requires reauthentication: %s", err)
        raise config_entry_auth_failed() from err
    except (OAuth2TokenRequestError, ClientError, TimeoutError) as err:
        _LOGGER.warning("Viessmann token refresh failed: %s", err)
        raise config_entry_not_ready() from err

    # Create the Auth Bridge
    auth = HAAuth(session)

    # Initialize the library with the auth bridge
    client = ViessmannClient(auth=auth)

    # 1. Main Coordinator (Devices API)
    coordinator = ViClimateDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ViClimateDevicesConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Allow removal only after a fresh inventory confirms the device is absent."""
    del hass
    try:
        inventory = await entry.runtime_data.async_get_full_inventory()
    except (
        ClientError,
        ConfigEntryAuthFailed,
        OAuth2TokenRequestError,
        TimeoutError,
        UpdateFailed,
    ):
        return False

    inventory_identifiers = {
        (DOMAIN, f"{device.gateway_serial}-{device.id}") for device in inventory
    }
    return not bool(device_entry.identifiers & inventory_identifiers)


class HAAuth(AbstractAuth):
    """Home Assistant Auth Bridge for vi_api_client."""

    def __init__(self, session: config_entry_oauth2_flow.OAuth2Session) -> None:
        """Initialize the auth bridge."""
        self._session = session
        super().__init__(websession=async_get_clientsession(session.hass))

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._session.async_ensure_token_valid()
        return self._session.token["access_token"]
