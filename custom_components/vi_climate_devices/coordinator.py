"""DataUpdateCoordinator for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from vi_api_client import (
    Device,
    Feature,
    ViAuthError,
    ViClient as ViessmannClient,
)
from vi_api_client.utils import mask_pii

from .const import DOMAIN, IGNORED_DEVICES

_LOGGER = logging.getLogger(__name__)


class ViClimateDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViessmannClient,
        update_interval: timedelta | None = None,
        analytics_enabled: bool = True,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_data",
            update_interval=update_interval or timedelta(minutes=2),
        )
        self.client = client
        self._known_devices: list[Device] = []
        self.analytics_enabled = analytics_enabled

    async def _perform_discovery(self):
        """Perform initial device discovery.

        Fetches all installations and their devices/features to populate the
        internal device registry.

        Raises:
            UpdateFailed: If no installations are found or discovery fails.
        """
        _LOGGER.debug("Performing initial discovery...")

        installations = await self.client.get_installations()
        if not installations:
            raise UpdateFailed("No installations found")

        try:
            # Fetch devices from ALL installations
            all_devices: list[Device] = []
            for installation in installations:
                _LOGGER.debug(
                    mask_pii(f"Fetching devices for installation ID: {installation.id}")
                )
                devices = await self.client.get_full_installation_status(
                    installation.id
                )
                all_devices.extend(devices)

            # Filter out ignored devices
            self._known_devices = [
                device for device in all_devices if device.id not in IGNORED_DEVICES
            ]
        except ViAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed during discovery: {err}"
            ) from err
        except Exception as e:
            raise UpdateFailed(f"Failed to perform full discovery: {e}") from e

        if not self._known_devices:
            _LOGGER.warning("No devices found during discovery")

    async def _async_update_data(self) -> dict:
        """Update data via library.

        Refreshes the state of all known devices.

        Returns:
            dict: A dictionary mapping unique device keys to Device objects.

        Raises:
            UpdateFailed: If the update process encounters an unhandled exception.
        """
        try:
            # 1. Initial Discovery
            if not self._known_devices:
                await self._perform_discovery()

            # 2. Update Loop (Refresh each device)
            updated_data: dict[str, Device] = {}

            if self._known_devices:
                _LOGGER.debug("Updating %s known devices", len(self._known_devices))
                for device in self._known_devices:
                    key = f"{device.gateway_serial}_{device.id}"
                    try:
                        new_device = await self.client.update_device(device)
                        updated_data[key] = new_device

                    except ViAuthError as err:
                        # Trigger HA re-auth flow immediately
                        raise ConfigEntryAuthFailed(
                            f"Authentication failed for device {device.id}: {err}"
                        ) from err

                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to update device %s: %s", device.id, err
                        )
                        # Graceful degradation: keep old data so entities stay available
                        updated_data[key] = device

                # Update local reference with fresh immutable objects
                self._known_devices = list(updated_data.values())

            return updated_data

        except ViAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except Exception as exception:
            raise UpdateFailed(exception) from exception


class ViClimateAnalyticsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann Analytics data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViessmannClient,
        main_coordinator: ViClimateDataUpdateCoordinator,
    ) -> None:
        """Initialize the analytics coordinator.

        Args:
            hass: The Home Assistant instance.
            client: The authenticated Viessmann API client.
            main_coordinator: Reference to the main data coordinator to access
                discovered devices.
        """
        self.client = client
        self.main_coordinator = main_coordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_analytics",
            update_interval=timedelta(hours=1),
        )

    async def _async_update_data(self) -> dict:
        """Update data (Analytics).

        Fetches daily energy consumption summaries for all heating devices.

        Returns:
            dict: A nested dictionary mapping device keys to analytics features.
        """
        devices = (
            self.main_coordinator.data.values() if self.main_coordinator.data else []
        )

        if not devices:
            return {}

        heating_devices: list[Device] = [
            device for device in devices if device.device_type == "heating"
        ]

        if not heating_devices:
            _LOGGER.warning("No heating devices found for analytics.")
            return {}

        results: dict[str, dict[str, Feature]] = {}

        for device in heating_devices:
            _LOGGER.debug("Fetching analytics for device %s", device.id)
            device_key = f"{device.gateway_serial}_{device.id}"
            try:
                start_today, end_today = self._get_today_time_range()

                features_list = await self.client.get_consumption(
                    device, start_dt=start_today, end_dt=end_today, metric="summary"
                )

                # Map Features for this device
                device_features: dict[str, Feature] = {}
                for feature in features_list:
                    device_features[feature.name] = feature

                results[device_key] = device_features

            except ViAuthError as err:
                raise ConfigEntryAuthFailed(
                    f"Analytics Auth failed for {device.id}: {err}"
                ) from err

            except Exception as err:
                _LOGGER.error(
                    "Failed to fetch analytics for device %s: %s", device.id, err
                )

        _LOGGER.debug("Analytics Data Refreshed: %s devices", len(results))
        return results

    def _get_today_time_range(self) -> tuple[datetime, datetime]:
        """Calculate the start and end datetime for the current day.

        Returns:
            tuple[datetime, datetime]: A tuple containing (start_of_day, end_of_day).
        """
        now = dt_util.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
