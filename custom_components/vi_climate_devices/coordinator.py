"""DataUpdateCoordinator for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from vi_api_client import ViClient as ViessmannClient

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ViClimateDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViessmannClient,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance.
            client: The authenticated Viessmann API client.
        """
        self.client = client
        self.installation_id = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_data",
            update_interval=timedelta(minutes=60),
        )

    async def _perform_discovery(self) -> None:
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
            self.known_devices = await self.client.get_full_installation_status(
                installations[0].id
            )
        except Exception as e:
            raise UpdateFailed(f"Failed to perform full discovery: {e}") from e

        if not self.known_devices:
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
            if not getattr(self, "known_devices", None):
                await self._perform_discovery()

            # 2. Update Loop (Refresh each device)
            updated_data = {}
            updated_devices_list = []

            if self.known_devices:
                _LOGGER.debug("Updating %s known devices", len(self.known_devices))
                for device in self.known_devices:
                    key = f"{device.gateway_serial}_{device.id}"
                    try:
                        new_device = await self.client.update_device(device)
                        updated_devices_list.append(new_device)
                        updated_data[key] = new_device

                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to update device %s: %s", device.id, err
                        )
                        # Graceful degradation: keep old data so entities stay available
                        updated_devices_list.append(device)
                        updated_data[key] = device

                # Update local reference with fresh immutable objects
                self.known_devices = updated_devices_list

            return updated_data

        except Exception as exception:
            raise UpdateFailed(exception) from exception


class ViClimateAnalyticsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann Analytics data (Slow polling)."""

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
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self) -> dict:
        """Update data (Analytics).

        Fetches daily energy consumption summaries for all heating devices.

        Returns:
            dict: A nested dictionary mapping device keys to analytics features.
        """
        # 1. Identify all Heating Devices
        heating_devices = []
        if self.main_coordinator.data:
            for device in self.main_coordinator.data.values():
                # Check device type or fallback
                device_type = getattr(device, "device_type", "unknown")
                if device_type == "heating":
                    heating_devices.append(device)

        if not heating_devices:
            _LOGGER.warning("No heating devices found for analytics.")
            return {}

        results = {}

        for device in heating_devices:
            _LOGGER.debug(
                "Fetching analytics for device ID: ...%s",
                str(device.id)[-4:] if device.id else "unknown",
            )
            device_key = f"{device.gateway_serial}_{device.id}"
            try:
                # Generic consumption call with explicit time range (Today local time)
                # dt_util.now() returns timezone-aware datetime configured in HA
                now = dt_util.now()
                start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_today = now.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

                features_list = await self.client.get_consumption(
                    device, start_dt=start_today, end_dt=end_today, metric="summary"
                )

                # Map Features for this device
                device_features = {}
                for feature in features_list:
                    name = feature.name
                    if not name.startswith("analytics."):
                        name = f"analytics.{name}"
                    device_features[name] = feature

                results[device_key] = device_features

            except Exception as err:
                _LOGGER.error(
                    "Failed to fetch analytics for device %s: %s", device.id, err
                )
                # We continue for other devices

        _LOGGER.debug("Analytics Data Refreshed: %s devices", len(results))
        return results
