"""Number platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client import Feature

from .const import DOMAIN, IGNORED_FEATURES
from .coordinator import ViClimateDataUpdateCoordinator
from .utils import is_feature_ignored

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateNumberEntityDescription(NumberEntityDescription):
    """Custom description for ViClimate number entities."""

    param_name: str | None = None
    command_name: str | None = None
    property_name: str | None = None
    # Optional: logic name to read from properties if different from param_name


# Definition maps: feature_name -> List of descriptions
# Dynamic Templates

# Dynamic Templates
# Each template matches a single flat feature name
NUMBER_TEMPLATES = [
    {
        "pattern": re.compile(r"^heating\.circuits\.(\d+)\.heating\.curve\.slope$"),
        "description": ViClimateNumberEntityDescription(
            key="placeholder",
            translation_key="heating_curve_slope",  # Generic key
            icon="mdi:slope-uphill",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
        ),
    },
    {
        "pattern": re.compile(r"^heating\.circuits\.(\d+)\.heating\.curve\.shift$"),
        "description": ViClimateNumberEntityDescription(
            key="placeholder",
            translation_key="heating_curve_shift",  # Generic key
            icon="mdi:arrow-up-down",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    },
    {
        # Matches: comfort, normal, reduced, eco, comfortCooling, comfortHeating, etc.
        # Flat name example: heating.circuits.0.operating.programs.comfort.temperature
        "pattern": re.compile(
            r"^heating\.circuits\.(\d+)\.operating\.programs\."
            r"((?:comfort|normal|reduced|eco)(?:Cooling|Heating|))\.temperature$"
        ),
        "description": ViClimateNumberEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_program_temperature",
            icon="mdi:thermometer",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    },
]

NUMBER_TYPES: dict[str, ViClimateNumberEntityDescription] = {
    # Hysteresis entities (v0.2.1+ of vi_api_client)
    "heating.dhw.temperature.hysteresis": ViClimateNumberEntityDescription(
        key="heating.dhw.temperature.hysteresis",
        translation_key="dhw_hysteresis",
        icon="mdi:thermometer-lines",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        device_class=NumberDeviceClass.TEMPERATURE,
    ),
    "heating.dhw.temperature.hysteresis.switchOnValue": (
        ViClimateNumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.switchOnValue",
            translation_key="dhw_hysteresis_on",
            icon="mdi:thermometer-plus",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE,
        )
    ),
    "heating.dhw.temperature.hysteresis.switchOffValue": (
        ViClimateNumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.switchOffValue",
            translation_key="dhw_hysteresis_off",
            icon="mdi:thermometer-minus",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE,
        )
    ),
    "heating.dhw.temperature.main": ViClimateNumberEntityDescription(
        key="heating.dhw.temperature.main",
        translation_key="dhw_target_temperature",
        icon="mdi:thermometer",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    ),
}


def _get_number_entity_description(
    feature_name: str,
) -> tuple[ViClimateNumberEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name."""
    for template in NUMBER_TEMPLATES:
        match = template["pattern"].match(feature_name)
        if match:
            groups = match.groups()
            index = groups[0]
            # If pattern has 2 groups, second is program
            program = groups[1] if len(groups) > 1 else None

            base_desc: ViClimateNumberEntityDescription = template["description"]

            placeholders = {"index": index}
            new_key = feature_name  # We use the actual feature name
            new_trans_key = base_desc.translation_key

            # Program specific logic
            if program:
                program_snake = re.sub(r"(?<!^)(?=[A-Z])", "_", program).lower()
                new_trans_key = f"heating_circuit_program_{program_snake}_temperature"
                # No program in placeholder for specific key if desired
                # but we kept index.

            new_desc = replace(
                base_desc,
                key=new_key,
                translation_key=new_trans_key,
            )
            return new_desc, placeholders
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices number based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                # 1. Defined Entities (Skip writable check for known overrides)
                if feature.name in NUMBER_TYPES:
                    desc = NUMBER_TYPES[feature.name]
                    entities.append(
                        ViClimateNumber(coordinator, map_key, feature.name, desc)
                    )
                    continue

                if not feature.is_writable:
                    continue

                # 2. Configured Templates
                if match_result := _get_number_entity_description(feature.name):
                    desc, placeholders = match_result
                    entities.append(
                        ViClimateNumber(
                            coordinator,
                            map_key,
                            feature.name,
                            desc,
                            translation_placeholders=placeholders,
                        )
                    )
                    continue

                # 3. Automatic Discovery
                if (
                    feature.control
                    and feature.control.min is not None
                    and feature.control.max is not None
                ):
                    desc = ViClimateNumberEntityDescription(
                        key=feature.name,
                        name=feature.name,
                        mode=NumberMode.BOX,  # Safer default
                        entity_category=EntityCategory.CONFIG,
                    )
                    entities.append(
                        ViClimateNumber(coordinator, map_key, feature.name, desc)
                    )

    async_add_entities(entities)


class ViClimateNumber(CoordinatorEntity, NumberEntity):
    """Representation of a Viessmann Climate Devices Number Entity."""

    entity_description: ViClimateNumberEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: ViClimateNumberEntityDescription,
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
            self._attr_name = feature_name

        # Initial Setup of Constraints from Feature Control
        feature = device.get_feature(feature_name)
        self._update_constraints(feature)

    def _update_constraints(self, feature: Feature):
        """Extract min/max/step from feature control."""
        if feature.control:
            if feature.control.min is not None:
                self._attr_native_min_value = float(feature.control.min)
            if feature.control.max is not None:
                self._attr_native_max_value = float(feature.control.max)
            if feature.control.step is not None:
                self._attr_native_step = float(feature.control.step)
            # Default fallback if step is missing?
            if self._attr_native_step is None:
                self._attr_native_step = 1.0

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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "viessmann_feature_name": self._feature_name,
        }

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # Return optimistic value if set, otherwise from coordinator
        if hasattr(self, "_optimistic_value") and self._optimistic_value is not None:
            return self._optimistic_value
        feat = self.feature_data
        if not feat:
            return None
        return feat.value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            raise HomeAssistantError("Device not found")

        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # 1. OPTIMISTIC UPDATE - Store locally and update UI immediately
        self._optimistic_value = value
        self.async_write_ha_state()

        # 2. EXECUTE COMMAND
        try:
            client = self.coordinator.client
            await client.set_feature(device, feat, value)

            # 3. Clear optimistic value - let next poll pick up real value
            self._optimistic_value = None

        except Exception as e:
            # 4. ROLLBACK on error
            self._optimistic_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set value: {e}") from e
