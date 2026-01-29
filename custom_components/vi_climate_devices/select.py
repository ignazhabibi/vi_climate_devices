"""Select platform for Viessmann Climate Devices."""

from __future__ import annotations

import dataclasses
import logging
import re
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

from .const import DOMAIN, IGNORED_FEATURES
from .coordinator import ViClimateDataUpdateCoordinator
from .utils import beautify_name, is_feature_ignored

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


# Dynamic Templates
SELECT_TEMPLATES = [
    # Heating Circuit Operating Modes (heating.circuits.N.operating.modes.active)
    {
        "pattern": re.compile(r"^heating\.circuits\.(\d+)\.operating\.modes\.active$"),
        "description": ViClimateSelectEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_operation_mode",
            icon="mdi:home-thermometer-auto",
            entity_category=EntityCategory.CONFIG,
        ),
    },
]


def _get_select_entity_description(
    feature_name: str,
) -> tuple[ViClimateSelectEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name.

    Returns:
        tuple: (description, translation_placeholders) or None
    """
    for template in SELECT_TEMPLATES:
        match = template["pattern"].match(feature_name)
        if match:
            index = match.group(1)
            base_desc: ViClimateSelectEntityDescription = template["description"]

            # Clone and Format
            new_desc = dataclasses.replace(
                base_desc,
                key=feature_name,
                translation_key=base_desc.translation_key,
            )
            return new_desc, {"index": index}
    return None


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
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                if not feature.is_writable:
                    continue

                # 1. Defined Entities
                if feature.name in SELECT_TYPES:
                    desc = SELECT_TYPES[feature.name]
                    entities.append(
                        ViClimateSelect(coordinator, map_key, feature.name, desc)
                    )
                    continue

                # 2. Dynamic Templates
                if match_result := _get_select_entity_description(feature.name):
                    description, placeholders = match_result
                    entities.append(
                        ViClimateSelect(
                            coordinator,
                            map_key,
                            feature.name,
                            description,
                            translation_placeholders=placeholders,
                        )
                    )
                    continue

                # 3. Automatic Discovery (Fallback)
                # Check for control options (Enum)
                if feature.control and feature.control.options:
                    # Valid Select Entity needs options
                    desc = ViClimateSelectEntityDescription(
                        key=feature.name,
                        name=beautify_name(feature.name),
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
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._attr_translation_placeholders = translation_placeholders or {}

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

        # Improve name for auto-discovered entities
        if (
            not hasattr(description, "translation_key")
            or not description.translation_key
        ):
            if description.name:
                self._attr_name = description.name
            else:
                self._attr_name = beautify_name(feature_name)

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
        # Return optimistic option if set
        if hasattr(self, "_optimistic_option") and self._optimistic_option is not None:
            return self._optimistic_option

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

        # 1. OPTIMISTIC UPDATE - Store locally and update UI immediately
        self._optimistic_option = option
        self.async_write_ha_state()

        try:
            client = self.coordinator.client
            _LOGGER.debug(
                "ViClimateSelect: Setting option %s for entity %s",
                option,
                self.entity_id,
            )
            # Library handles mapping option to command payload
            await client.set_feature(device, feat, option)

            # Clear optimistic option - let next poll pick up real value
            self._optimistic_option = None

        except Exception as e:
            # ROLLBACK on error
            self._optimistic_option = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set option {option}: {e}") from e
