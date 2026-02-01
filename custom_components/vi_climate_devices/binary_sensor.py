"""Binary sensor platform for Viessmann Climate Devices."""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client.api import Feature

from .const import DOMAIN, IGNORED_FEATURES, TESTED_DEVICES
from .coordinator import ViClimateDataUpdateCoordinator
from .utils import (
    beautify_name,
    get_feature_bool_value,
    is_feature_boolean_like,
    is_feature_ignored,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Custom description for ViClimate binary sensors."""


# Templates with regex patterns for dynamic feature names
BINARY_SENSOR_TEMPLATES = [
    # Circulation Pumps (heating.circuits.N.circulation.pump.status)
    {
        "pattern": re.compile(r"^heating\.circuits\.(\d+)\.circulation\.pump\.status$"),
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="circulation_pump",  # Generic key with {index}
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Frost Protection (heating.circuits.N.frostprotection.status)
    {
        "pattern": re.compile(r"^heating\.circuits\.(\d+)\.frostprotection\.status$"),
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="frost_protection",
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Compressors Active (heating.compressors.N.active)
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.active$"),
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="compressor_active",  # Generic key with {index}
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Crankcase Heater (heating.compressors.N.heater.crankcase.active)
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.heater\.crankcase\.active$"
        ),
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="compressor_crankcase_heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Evaporator Base Heater (heating.evaporators.N.heater.base.active)
    {
        "pattern": re.compile(r"^heating\.evaporators\.(\d+)\.heater\.base\.active$"),
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_base_heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
]

BINARY_SENSOR_TYPES: dict[str, BinarySensorEntityDescription] = {
    # DHW Charging (heating.dhw.charging)
    "heating.dhw.charging": BinarySensorEntityDescription(
        key="heating.dhw.charging",
        translation_key="dhw_charging",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # One Time Charge (heating.dhw.oneTimeCharge.active)
    "heating.dhw.oneTimeCharge.active": BinarySensorEntityDescription(
        key="heating.dhw.oneTimeCharge.active",
        translation_key="one_time_charge",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # DHW Circulation Pump (heating.dhw.pumps.circulation.status)
    "heating.dhw.pumps.circulation.status": BinarySensorEntityDescription(
        key="heating.dhw.pumps.circulation.status",
        translation_key="dhw_circulation_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # DHW Primary Pump (heating.dhw.pumps.primary.status)
    "heating.dhw.pumps.primary.status": BinarySensorEntityDescription(
        key="heating.dhw.pumps.primary.status",
        translation_key="dhw_primary_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # Outdoor Defrosting (heating.outdoor.defrosting.active)
    "heating.outdoor.defrosting.active": BinarySensorEntityDescription(
        key="heating.outdoor.defrosting.active",
        translation_key="outdoor_defrosting",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    # Solar Pump (heating.solar.pumps.circuit.status)
    "heating.solar.pumps.circuit.status": BinarySensorEntityDescription(
        key="heating.solar.pumps.circuit.status",
        translation_key="solar_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
}


def _get_binary_sensor_entity_description(
    feature_name: str,
) -> tuple[BinarySensorEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name.

    Returns:
        tuple: (description, translation_placeholders) or None
    """
    for template in BINARY_SENSOR_TEMPLATES:
        match = template["pattern"].match(feature_name)
        if match:
            index = match.group(1)
            base_desc: BinarySensorEntityDescription = template["description"]

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
    """Set up Viessmann Climate Devices binary sensor based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                if feature.name in BINARY_SENSOR_TYPES:
                    description = BINARY_SENSOR_TYPES[feature.name]
                    entities.append(
                        ViClimateBinarySensor(
                            coordinator, map_key, feature.name, description
                        )
                    )
                    continue

                if match_result := _get_binary_sensor_entity_description(feature.name):
                    description, placeholders = match_result
                    entities.append(
                        ViClimateBinarySensor(
                            coordinator,
                            map_key,
                            feature.name,
                            description,
                            translation_placeholders=placeholders,
                        )
                    )
                    continue

                # Automatic Discovery
                # Read-only Boolean OR "on"/"off" String -> Binary Sensor
                if not feature.is_writable and is_feature_boolean_like(feature.value):
                    desc = BinarySensorEntityDescription(
                        key=feature.name,
                        name=beautify_name(feature.name),
                        entity_category=EntityCategory.DIAGNOSTIC,
                    )
                    # Only disable entities by default for thoroughly tested devices
                    is_tested = device.model_id in TESTED_DEVICES
                    entities.append(
                        ViClimateBinarySensor(
                            coordinator,
                            map_key,
                            feature.name,
                            desc,
                            enabled_default=not is_tested,
                        )
                    )

    async_add_entities(entities)


class ViClimateBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a generic Viessmann Climate Devices Binary Sensor."""

    def __init__(  # noqa: PLR0913
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: BinarySensorEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._attr_translation_placeholders = translation_placeholders or {}
        self._attr_entity_registry_enabled_default = enabled_default

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
    def feature_data(self) -> Feature | None:
        """Retrieve the specific feature from coordinator data."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(self._feature_name)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        feat = self.feature_data
        if feat and feat.value is not None:
            return get_feature_bool_value(feat.value)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes."""
        return {"viessmann_feature_name": self._feature_name}

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        feat = self.feature_data
        return self.coordinator.last_update_success and feat and feat.is_enabled
