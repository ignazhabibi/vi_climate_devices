"""DataUpdateCoordinator for Viessmann Climate Devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, OAuth2TokenRequestError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from vi_api_client import (
    Device,
    ViAuthError,
    ViClient as ViessmannClient,
    ViError,
)
from vi_api_client.models import CommandResponse
from vi_api_client.utils import mask_pii

from .const import DOMAIN, IGNORED_DEVICES

_LOGGER = logging.getLogger(__name__)


class ViClimateDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Device]]):
    """Class to manage fetching Viessmann data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry[ViClimateDataUpdateCoordinator],
        client: ViessmannClient,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_data",
            update_interval=update_interval or timedelta(minutes=3),
        )
        self.client = client
        self._known_devices: list[Device] = []
        self._failed_device_keys: set[str] = set()
        self._refresh_write_lock = asyncio.Lock()

    def is_device_available(self, device_key: str) -> bool:
        """Return whether the most recent refresh succeeded for a device."""
        return device_key not in self._failed_device_keys

    def _log_device_availability(
        self,
        device_key: str,
        error: ViError | None,
        previous_failed_device_keys: set[str],
    ) -> None:
        """Log a device availability transition once."""
        if error is None:
            if device_key in previous_failed_device_keys:
                _LOGGER.info("Device %s is back online", device_key)
        elif device_key not in previous_failed_device_keys:
            _LOGGER.info("Device %s is unavailable: %s", device_key, error)

    async def async_set_feature(
        self, device_key: str, feature_name: str, value: object
    ) -> CommandResponse:
        """Set a feature while serializing writes with refreshes.

        Raises:
            ValueError: If the device or feature is absent from coordinator data.
        """
        async with self._refresh_write_lock:
            device = self.data.get(device_key)
            if device is None:
                raise ValueError(f"Device {device_key} not found in coordinator data")

            feature = device.get_feature(feature_name)
            if feature is None:
                raise ValueError(f"Feature {feature_name} not found in device data")

            response, updated_device = await self.client.set_feature(
                device, feature, value
            )
            if response.success:
                updated_data = dict(self.data)
                updated_data[device_key] = updated_device
                self._known_devices = list(updated_data.values())
                # A command confirms values, not refresh availability. Preserve
                # the scheduled poll and the outcome of the last refresh.
                self.data = updated_data
                self.async_update_listeners()
            return response

    async def _async_refresh(
        self,
        log_failures: bool = True,
        raise_on_auth_failed: bool = False,
        scheduled: bool = False,
        raise_on_entry_error: bool = False,
    ) -> None:
        """Refresh data without racing successful writes."""
        async with self._refresh_write_lock:
            await super()._async_refresh(
                log_failures=log_failures,
                raise_on_auth_failed=raise_on_auth_failed,
                scheduled=scheduled,
                raise_on_entry_error=raise_on_entry_error,
            )

    async def _perform_discovery(self) -> None:
        """Perform initial device discovery.

        Fetches all installations and their devices/features to populate the
        internal device registry.

        Raises:
            UpdateFailed: If no installations are found or discovery fails.
        """
        _LOGGER.debug("Performing initial discovery")

        try:
            installations = await self.client.get_installations()
            if not installations:
                raise UpdateFailed("No installations found")

            all_devices: list[Device] = []
            for installation in installations:
                _LOGGER.debug(
                    mask_pii(f"Fetching devices for installation ID: {installation.id}")
                )
                devices = await self.client.get_full_installation_status(
                    installation.id
                )
                all_devices.extend(devices)

            self._known_devices = [
                device for device in all_devices if device.id not in IGNORED_DEVICES
            ]
        except OAuth2TokenRequestError:
            raise
        except ViAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed during discovery: {err}"
            ) from err
        except ViError as err:
            raise UpdateFailed(f"Failed to perform full discovery: {err}") from err

        if not self._known_devices:
            _LOGGER.warning("No devices found during discovery")

    async def _async_update_data(self) -> dict[str, Device]:
        """Update data via library.

        Refreshes the state of all known devices.

        Returns:
            dict: A dictionary mapping unique device keys to Device objects.

        Raises:
            UpdateFailed: If the update process encounters an unhandled exception.
        """
        if not self._known_devices:
            await self._perform_discovery()

        updated_data: dict[str, Device] = {}
        failed_device_keys: set[str] = set()
        device_errors: dict[str, ViError] = {}
        previous_failed_device_keys = self._failed_device_keys

        if self._known_devices:
            _LOGGER.debug("Updating %s known devices", len(self._known_devices))
            for device in self._known_devices:
                key = f"{device.gateway_serial}_{device.id}"
                try:
                    new_device = await self.client.update_device(device)
                    updated_data[key] = new_device

                except ViAuthError as err:
                    raise ConfigEntryAuthFailed(
                        f"Authentication failed for device {device.id}: {err}"
                    ) from err

                except ViError as err:
                    failed_device_keys.add(key)
                    device_errors[key] = err
                    # Keep old data for recovery, but mark its entities unavailable.
                    updated_data[key] = device

            self._failed_device_keys = failed_device_keys
            for key in updated_data:
                self._log_device_availability(
                    key, device_errors.get(key), previous_failed_device_keys
                )

            if failed_device_keys and len(failed_device_keys) == len(updated_data):
                raise UpdateFailed("Failed to update all devices")

            self._known_devices = list(updated_data.values())

        return updated_data
