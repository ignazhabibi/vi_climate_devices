"""DataUpdateCoordinator for Viessmann Climate Devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import OAuth2TokenRequestError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from vi_api_client import (
    CommandResponse,
    Device,
    FeatureValue,
    ViAuthError,
    ViClient as ViessmannClient,
    ViError,
)
from vi_api_client.utils import mask_pii

from .const import DOMAIN, IGNORED_DEVICES
from .exceptions import config_entry_auth_failed, update_failed

_LOGGER = logging.getLogger(__name__)

INVENTORY_INTERVAL = timedelta(hours=24)


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
            update_interval=update_interval or timedelta(seconds=90),
        )
        self.client = client
        self._known_devices: list[Device] = []
        self._last_inventory_at: datetime | None = None
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
        self, device_key: str, feature_name: str, value: FeatureValue
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

            try:
                response, updated_device = await self.client.set_feature(
                    device, feature, value
                )
            except ViAuthError as err:
                _LOGGER.warning(
                    "Viessmann authentication failed while writing a feature: %s", err
                )
                raise config_entry_auth_failed() from err
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

        self._known_devices = await self.async_get_full_inventory()
        self._last_inventory_at = dt_util.utcnow()

        if not self._known_devices:
            _LOGGER.warning("No devices found during discovery")

    async def async_get_full_inventory(self) -> list[Device]:
        """Return every non-ignored device in a complete account inventory.

        Raises:
            UpdateFailed: If the inventory cannot be completed.
        """
        try:
            installations = await self.client.get_installations()
            if not installations:
                raise update_failed()

            all_devices: list[Device] = []
            for installation in installations:
                _LOGGER.debug(
                    mask_pii(f"Fetching devices for installation ID: {installation.id}")
                )
                devices = await self.client.get_full_installation_status(
                    installation.id
                )
                all_devices.extend(devices)
        except OAuth2TokenRequestError:
            raise
        except ViAuthError as err:
            _LOGGER.warning("Viessmann authentication failed during discovery: %s", err)
            raise config_entry_auth_failed() from err
        except ViError as err:
            _LOGGER.warning("Viessmann discovery failed: %s", err)
            raise update_failed() from err

        return [device for device in all_devices if device.id not in IGNORED_DEVICES]

    async def _async_refresh_inventory(self) -> None:
        """Merge a complete inventory into the retained polling device set."""
        inventory = await self.async_get_full_inventory()
        known_devices = {
            f"{device.gateway_serial}_{device.id}": device
            for device in self._known_devices
        }
        for device in inventory:
            known_devices.setdefault(f"{device.gateway_serial}_{device.id}", device)
        self._known_devices = list(known_devices.values())
        self._last_inventory_at = dt_util.utcnow()

    def _is_inventory_due(self) -> bool:
        """Return whether a periodic complete account inventory is due."""
        return self._last_inventory_at is not None and (
            dt_util.utcnow() - self._last_inventory_at >= INVENTORY_INTERVAL
        )

    async def _async_ensure_inventory(self) -> None:
        """Populate initial devices or merge a due periodic inventory."""
        if not self._known_devices:
            await self._perform_discovery()
        elif self._is_inventory_due():
            await self._async_refresh_inventory()

    async def _async_update_data(self) -> dict[str, Device]:
        """Update data via library.

        Refreshes the state of all known devices.

        Returns:
            dict: A dictionary mapping unique device keys to Device objects.

        Raises:
            UpdateFailed: If the update process encounters an unhandled exception.
        """
        await self._async_ensure_inventory()

        updated_data: dict[str, Device] = {}
        failed_device_keys: set[str] = set()
        device_errors: dict[str, ViError] = {}
        previous_failed_device_keys = self._failed_device_keys

        if self._known_devices:
            _LOGGER.debug("Updating %s known devices", len(self._known_devices))
            devices_by_gateway: dict[tuple[str, str], list[Device]] = {}
            for device in self._known_devices:
                gateway_key = (device.installation_id, device.gateway_serial)
                devices_by_gateway.setdefault(gateway_key, []).append(device)

            for gateway_devices in devices_by_gateway.values():
                try:
                    refresh_result = await self.client.update_gateway_devices(
                        gateway_devices
                    )

                except ViAuthError as err:
                    _LOGGER.warning(
                        "Viessmann authentication failed while refreshing "
                        "gateway devices: %s",
                        err,
                    )
                    raise config_entry_auth_failed() from err

                except ViError as err:
                    for device in gateway_devices:
                        key = f"{device.gateway_serial}_{device.id}"
                        failed_device_keys.add(key)
                        device_errors[key] = err
                        # Keep old data for recovery, but mark its entities unavailable.
                        updated_data[key] = device

                else:
                    updated_devices_by_id = {
                        device.id: device for device in refresh_result.updated_devices
                    }
                    for device in gateway_devices:
                        key = f"{device.gateway_serial}_{device.id}"
                        refreshed_device = updated_devices_by_id.get(device.id)
                        if refreshed_device is not None:
                            updated_data[key] = refreshed_device
                            continue

                        error = refresh_result.errors_by_device_id[device.id]
                        failed_device_keys.add(key)
                        device_errors[key] = error
                        # Keep old data for recovery, but mark its entities unavailable.
                        updated_data[key] = device

            self._failed_device_keys = failed_device_keys
            for key in updated_data:
                self._log_device_availability(
                    key, device_errors.get(key), previous_failed_device_keys
                )

            if failed_device_keys and len(failed_device_keys) == len(updated_data):
                raise update_failed()

            self._known_devices = list(updated_data.values())

        return updated_data
