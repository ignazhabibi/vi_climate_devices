"""DataUpdateCoordinator for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from vi_api_client import ViClient as ViessmannClient

from .const import DOMAIN, IGNORED_DEVICES

_LOGGER = logging.getLogger(__name__)


class ViClimateDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann data (Realtime)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViessmannClient,
    ) -> None:
        """Initialize."""
        self.client = client
        self.installation_id = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_data",
            update_interval=timedelta(minutes=60),
        )

    async def _perform_discovery(self) -> None:
        """Perform initial device discovery."""
        _LOGGER.debug("Performing initial discovery...")

        installations = await self.client.get_installations()
        _LOGGER.debug("Found %s installations", len(installations))

        gateways = await self.client.get_gateways()
        _LOGGER.debug("Found %s gateways", len(gateways))

        if not gateways:
            raise UpdateFailed("No gateways found")

        all_devices = []
        for gateway in gateways:
            try:
                _LOGGER.debug(
                    "Processing gateway serial: %s...",
                    gateway.serial[:4] if gateway.serial else "None",
                )
                # Our Model guarantees installation_id (String)
                # We use getattr just in case of mock/version mismatches,
                # but prioritize the property
                inst_id = getattr(gateway, "installation_id", None)

                # Fallback (just in case API sends data without it,
                # though unlikely with current models)
                if not inst_id and installations:
                    inst_id = installations[0].id

                if inst_id:
                    # Type-safe call
                    gw_devices = await self.client.get_devices(inst_id, gateway.serial)
                    _LOGGER.debug("Gateway returned %s devices", len(gw_devices))

                    # Filter out ignored devices
                    filtered_devices = [
                        d for d in gw_devices if d.id not in IGNORED_DEVICES
                    ]

                    if len(filtered_devices) < len(gw_devices):
                        _LOGGER.debug(
                            "Ignored %s devices (configured in const.py)",
                            len(gw_devices) - len(filtered_devices),
                        )

                    all_devices.extend(filtered_devices)
                else:
                    _LOGGER.warning(
                        "Skipping gateway %s (no installation ID)",
                        gateway.serial,
                    )

            except Exception as e:
                _LOGGER.error(
                    "Failed to fetch devices for gateway %s: %s",
                    gateway.serial,
                    e,
                )

        if not all_devices:
            raise UpdateFailed("No devices found")

        self.known_devices = all_devices

    async def _async_update_data(self) -> dict:
        """Update data via library."""
        try:
            # 1. Initial Discovery
            if not getattr(self, "known_devices", None):
                await self._perform_discovery()

            # 2. Update Loop (Refresh each device)
            updated_devices = []
            if self.known_devices:
                _LOGGER.debug("Updating %s known devices", len(self.known_devices))
                for device in self.known_devices:
                    _LOGGER.debug(
                        "Updating device ID: ...%s",
                        str(device.id)[-4:] if device.id else "unknown",
                    )
                    try:
                        # update_device is efficient! Uses internal IDs.
                        new_dev = await self.client.update_device(device)
                        updated_devices.append(new_dev)
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to update device %s: %s", device.id, err
                        )
                        updated_devices.append(device)  # Keep old data on failure

                self.known_devices = updated_devices

            # Map by UNIQUE KEY (GatewaySerial_DeviceID)
            return {f"{d.gateway_serial}_{d.id}": d for d in self.known_devices}

        except Exception as exception:
            raise UpdateFailed(exception) from exception

    async def _perform_discovery(self):
        """Perform initial device discovery."""
        _LOGGER.debug("Performing initial discovery...")

        installations = await self.client.get_installations()
        _LOGGER.debug("Found %s installations", len(installations))

        gateways = await self.client.get_gateways()
        _LOGGER.debug("Found %s gateways", len(gateways))

        if not gateways:
            raise UpdateFailed("No gateways found")

        all_devices = []
        for gateway in gateways:
            try:
                _LOGGER.debug(
                    "Processing gateway serial: %s...",
                    gateway.serial[:4] if gateway.serial else "None",
                )
                inst_id = getattr(gateway, "installation_id", None)

                if not inst_id and installations:
                    inst_id = installations[0].id

                if inst_id:
                    gw_devices = await self.client.get_devices(inst_id, gateway.serial)
                    _LOGGER.debug("Gateway returned %s devices", len(gw_devices))

                    filtered_devices = [
                        d for d in gw_devices if d.id not in IGNORED_DEVICES
                    ]

                    if len(filtered_devices) < len(gw_devices):
                        _LOGGER.debug(
                            "Ignored %s devices (configured in const.py)",
                            len(gw_devices) - len(filtered_devices),
                        )

                    all_devices.extend(filtered_devices)
                else:
                    _LOGGER.warning(
                        "Skipping gateway %s (no installation ID)", gateway.serial
                    )

            except Exception as e:
                _LOGGER.error(
                    "Failed to fetch devices for gateway %s: %s", gateway.serial, e
                )

        if not all_devices:
            raise UpdateFailed("No devices found")

        self.known_devices = all_devices


class ViClimateAnalyticsCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Viessmann Analytics data (Slow polling)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ViessmannClient,
        main_coordinator: ViClimateDataUpdateCoordinator,
    ) -> None:
        """Initialize."""
        self.client = client
        self.main_coordinator = main_coordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_analytics",
            update_interval=timedelta(minutes=60),  # Updated to 60m per guide
        )

    async def _async_update_data(self) -> dict:
        """Update data via library (Analytics)."""
        # 1. Identify all Heating Devices
        heating_devices = []
        if self.main_coordinator.data:
            for device in self.main_coordinator.data.values():
                # Check device type or fallback
                d_type = getattr(device, "device_type", "unknown")
                if d_type == "heating":
                    heating_devices.append(device)

        # Fallback for users where device_type might be missing/different
        # but they have a device
        if (
            not heating_devices
            and self.main_coordinator.data
            and len(self.main_coordinator.data) == 1
        ):
            # If we have only 1 device total, assume it's the heating one
            heating_devices.append(next(iter(self.main_coordinator.data.values())))

        if not heating_devices:
            _LOGGER.warning("No heating devices found for analytics.")
            return {}

        # 2. Fetch Data for EACH device
        # Result Structure: { "gateway_device": { "analytics.feature": Feature, ... } }
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
                for f in features_list:
                    name = f.name
                    if not name.startswith("analytics."):
                        name = f"analytics.{name}"
                    device_features[name] = f

                results[device_key] = device_features

            except Exception as err:
                _LOGGER.error(
                    "Failed to fetch analytics for device %s: %s", device.id, err
                )
                # We continue for other devices

        _LOGGER.debug("Analytics Data Refreshed: %s devices", len(results))
        return results
