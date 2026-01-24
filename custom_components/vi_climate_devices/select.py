"""Select platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
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
class ViClimateSelectEntityDescription(SelectEntityDescription):
    """Custom description for ViClimate select entities."""

    param_name: str | None = None
    command_name: str | None = None
    property_name: str | None = None


# Feature -> Description
SELECT_TYPES: dict[str, ViClimateSelectEntityDescription] = {
    "heating.dhw.operating.modes.active": ViClimateSelectEntityDescription(
        key="heating.dhw.operating.modes.active",
        translation_key="dhw_mode",
        icon="mdi:water-boiler-auto",
        entity_category=EntityCategory.CONFIG,
    ),
    # Add other known select types here if any
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices select based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                if not feature.is_writable:
                    continue

                # 1. Defined Entities
                if feature.name in SELECT_TYPES:
                    desc = SELECT_TYPES[feature.name]
                    entities.append(
                        ViClimateSelect(coordinator, map_key, feature.name, desc)
                    )
                    continue

                # 2. Automatic Discovery (Fallback)
                # Check for control options (Enum)
                if feature.control and feature.control.options:
                    # Valid Select Entity needs options
                    desc = ViClimateSelectEntityDescription(
                        key=feature.name,
                        name=feature.name,
                        entity_category=EntityCategory.CONFIG,
                    )
                    entities.append(
                        ViClimateSelect(coordinator, map_key, feature.name, desc)
                    )

    async_add_entities(entities)


class ViClimateSelect(CoordinatorEntity, SelectEntity):
    """Representation of a Viessmann Climate Devices Select Entity."""

    entity_description: ViClimateSelectEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: ViClimateSelectEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name

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

        # Initial Setup of Options
        feature = device.get_feature(feature_name)
        self._update_options(feature)

    def _update_options(self, feature: Feature):
        """Extract available options from feature control."""
        self._attr_options = []
        if feature.control and feature.control.options:
            # Options can be Dict[value, label] or List[value]
            # We normlize to list of strings
            self._attr_options = [str(opt) for opt in feature.control.options]

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
    def current_option(self) -> str | None:
        """Return the current value."""
        feat = self.feature_data
        if not feat:
            return None

        # Check if value is valid option
        val = str(feat.value)
        if val in self.options:
            return val

        # Try finding case-insensitive match?
        # Or maybe the value is a key in options dict (if we had access to labels)

        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            raise HomeAssistantError("Device not found")

        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # Optimistic update?
        # Maybe skip to avoid flicker if API fails

        try:
            client = self.coordinator.client
            _LOGGER.debug(
                "ViClimateSelect: Setting option %s for entity %s",
                option,
                self.entity_id,
            )
            # Library handles mapping option to command payload
            await client.set_feature(device, feat, option)

            # Refresh
            await self.coordinator.async_request_refresh()

        except Exception as e:
            raise HomeAssistantError(f"Failed to set option {option}: {e}") from e
