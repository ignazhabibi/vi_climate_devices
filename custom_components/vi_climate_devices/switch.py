"""Switch platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client import Feature

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateSwitchEntityDescription(SwitchEntityDescription):
    """Custom description for ViClimate switch entities."""

    # Optional override for logic mapping
    property_name: str | None = None


SWITCH_TYPES: dict[str, ViClimateSwitchEntityDescription] = {
    # Updated keys for Flat Architecture
    "heating.dhw.oneTimeCharge.active": ViClimateSwitchEntityDescription(
        key="heating.dhw.oneTimeCharge.active",
        translation_key="dhw_one_time_charge",
        icon="mdi:water-boiler",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    "heating.dhw.hygiene.enabled": ViClimateSwitchEntityDescription(
        key="heating.dhw.hygiene.enabled",
        translation_key="dhw_hygiene",
        icon="mdi:shield-check",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    "heating.circuits.0.heating.curve.active": ViClimateSwitchEntityDescription(
        key="heating.circuits.0.heating.curve.active",
        translation_key="heating_curve_active",
        icon="mdi:check",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices switch based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # 1. Defined Entities (Skip writable check for known overrides)
                if feature.name in SWITCH_TYPES:
                    desc = SWITCH_TYPES[feature.name]
                    entities.append(
                        ViClimateSwitch(coordinator, map_key, feature.name, desc)
                    )
                    continue

                # 2. Automatic Discovery (Must be writable)
                if not feature.is_writable:
                    continue

                # Automatic Discovery (Fallback)
                # If writable boolean
                if isinstance(feature.value, bool):
                    desc = ViClimateSwitchEntityDescription(
                        key=feature.name,
                        name=feature.name,
                        entity_category=EntityCategory.CONFIG,
                    )
                    entities.append(
                        ViClimateSwitch(coordinator, map_key, feature.name, desc)
                    )

    async_add_entities(entities)


class ViClimateSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Viessmann Climate Devices Switch Entity."""

    entity_description: ViClimateSwitchEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: ViClimateSwitchEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._property_name = description.property_name

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

        # Improve name for auto-discovered entities
        if (
            not hasattr(description, "translation_key")
            or not description.translation_key
        ):
            self._attr_name = feature_name

    @property
    def feature_data(self) -> Feature | None:
        """Get latest feature data from coordinator."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(self._feature_name)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{device.gateway_serial}-{device.id}")},
            name=device.model_id,
            manufacturer="Viessmann",
            model=device.model_id,
            serial_number=device.gateway_serial,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        feat = self.feature_data
        if not feat:
            return None

        # Handle "on"/"off" strings or Booleans
        val = feat.value
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("on", "true", "active", "1", "enabled")

        # Fallback
        return bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_set_state(False)

    async def _async_set_state(self, target_state: bool) -> None:
        """Execute the command."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            raise HomeAssistantError("Device not found")

        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # 1. Optimistic Update?
        # Maybe skip to avoid flicker if API fails

        try:
            client = self.coordinator.client
            _LOGGER.debug(
                "ViClimateSwitch: Setting state to %s for entity '%s'",
                target_state,
                self.entity_id,
            )
            await client.set_feature(device, feat, target_state)

            # Refresh
            await self.coordinator.async_request_refresh()

        except Exception as e:
            raise HomeAssistantError(f"Failed to switch {target_state}: {e}") from e
