"""Binary sensor platform for Viessmann Climate Devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Custom description for ViClimate binary sensors."""


# Dynamic Templates
BINARY_SENSOR_TEMPLATES = [
    # Circulation Pumps (heating.circuits.N.circulation.pump)
    {
        "pattern": r"^heating\.circuits\.(\d+)\.circulation\.pump$",
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="circulation_pump",  # Generic key with {index}
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Frost Protection (heating.circuits.N.frostprotection)
    {
        "pattern": r"^heating\.circuits\.(\d+)\.frostprotection$",
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="frost_protection",
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Compressors Active (heating.compressors.N.active)
    {
        "pattern": r"^heating\.compressors\.(\d+)\.active$",
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="compressor_active",  # Generic key with {index}
            device_class=BinarySensorDeviceClass.RUNNING,
        ),
    },
    # Crankcase Heater (heating.compressors.N.heater.crankcase)
    {
        "pattern": r"^heating\.compressors\.(\d+)\.heater\.crankcase$",
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="compressor_crankcase_heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Evaporator Base Heater (heating.evaporators.N.heater.base)
    {
        "pattern": r"^heating\.evaporators\.(\d+)\.heater\.base$",
        "description": BinarySensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_base_heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
]

BINARY_SENSOR_TYPES: dict[str, BinarySensorEntityDescription] = {
    # Static / Named components
    "heating.dhw.pumps.circulation": BinarySensorEntityDescription(
        key="heating.dhw.pumps.circulation",
        translation_key="dhw_circulation_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    "heating.dhw.pumps.primary": BinarySensorEntityDescription(
        key="heating.dhw.pumps.primary",
        translation_key="dhw_primary_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    "heating.dhw.charging": BinarySensorEntityDescription(
        key="heating.dhw.charging",
        translation_key="dhw_charging",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    "heating.dhw.oneTimeCharge": BinarySensorEntityDescription(
        key="heating.dhw.oneTimeCharge",
        translation_key="one_time_charge",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    "heating.solar.pumps.circuit": BinarySensorEntityDescription(
        key="heating.solar.pumps.circuit",
        translation_key="solar_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    "heating.errors.active": BinarySensorEntityDescription(
        key="heating.errors.active",
        translation_key="device_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
}


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
            for feature in device.features_flat:
                if feature.name in BINARY_SENSOR_TYPES:
                    description = BINARY_SENSOR_TYPES[feature.name]
                    entities.append(
                        ViClimateBinarySensor(
                            coordinator, map_key, feature.name, description
                        )
                    )
                else:
                    # Check templates
                    for template in BINARY_SENSOR_TEMPLATES:
                        match = re.match(template["pattern"], feature.name)
                        if match:
                            index = match.group(1)
                            # Create specific description
                            base_desc: BinarySensorEntityDescription = template[
                                "description"
                            ]

                            # Clone and Format
                            import dataclasses

                            # key is placeholder, can just assume feature.name (unique per device)
                            # translation_key needs format

                            new_desc = dataclasses.replace(
                                base_desc,
                                key=feature.name,
                                translation_key=base_desc.translation_key,  # Use generic key as is
                            )

                            entities.append(
                                ViClimateBinarySensor(
                                    coordinator,
                                    map_key,
                                    feature.name,
                                    new_desc,
                                    translation_placeholders={"index": index},
                                )
                            )
                            break

    async_add_entities(entities)


class ViClimateBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a generic Viessmann Climate Devices Binary Sensor."""

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: BinarySensorEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._attr_translation_placeholders = translation_placeholders or {}

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

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
    def feature_data(self):
        """Retrieve the specific feature from coordinator data."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return next(
            (f for f in device.features_flat if f.name == self._feature_name), None
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        feat = self.feature_data
        if feat and feat.value is not None:
            # Interpret value. Assuming "on" string or boolean true/1.
            if isinstance(feat.value, str):
                return feat.value.lower() in ("on", "active", "true", "1")
            return bool(feat.value)
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {"viessmann_feature_name": self._feature_name}

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        feat = self.feature_data
        return self.coordinator.last_update_success and feat and feat.is_enabled
