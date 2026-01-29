"""Sensor platform for Viessmann Climate Devices."""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, IGNORED_FEATURES
from .coordinator import ViClimateAnalyticsCoordinator, ViClimateDataUpdateCoordinator
from .utils import beautify_name, is_feature_boolean_like, is_feature_ignored

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateSensorEntityDescription(SensorEntityDescription):
    """Custom description for ViClimate sensors."""


# --- Sensor Definitions ---

# Dynamic Templates for repeated features (index N)
# Pattern is a regex. Description translation_key expects {} for the index.
# Pre-compiled regex patterns for better performance
SENSOR_TEMPLATES = [
    # Heating Circuits Supply Temperature
    {
        "pattern": re.compile(
            r"^heating\.circuits\.(\d+)\.sensors\.temperature\.supply$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_supply_temperature",  # Generic key
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
    },
    # Burners Modulation
    {
        "pattern": re.compile(r"^heating\.burners\.(\d+)\.modulation$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="burner_modulation",  # Generic key
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:fire",
            state_class=SensorStateClass.MEASUREMENT,
        ),
    },
    # Burners Statistics
    {
        "pattern": re.compile(r"^heating\.burners\.(\d+)\.statistics\.starts$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="burner_starts",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    {
        "pattern": re.compile(r"^heating\.burners\.(\d+)\.statistics\.hours$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="burner_hours",
            native_unit_of_measurement="h",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressors Statistics
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.statistics\.hours$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_hours",  # Generic key
            native_unit_of_measurement="h",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.statistics\.starts$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_starts",  # Generic key
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Phase (text sensor)
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.phase$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_phase",
            icon="mdi:state-machine",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Pressure Inlet
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.pressure\.inlet$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_inlet_pressure",
            native_unit_of_measurement=UnitOfPressure.BAR,
            device_class=SensorDeviceClass.PRESSURE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:gauge",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Temperature - Inlet
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.inlet$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_inlet_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Temperature - Motor Chamber
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.motorChamber$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_motor_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Temperature - Oil
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.oil$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_oil_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Temperature - Outlet
    {
        "pattern": re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.outlet$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_outlet_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Speed - Current
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.speed\.current$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_speed_current",
            native_unit_of_measurement="rps",
            icon="mdi:fan",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Compressor Speed - Setpoint
    {
        "pattern": re.compile(r"^heating\.compressors\.(\d+)\.speed\.setpoint$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_speed_setpoint",
            native_unit_of_measurement="rps",
            icon="mdi:fan",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Inverters Power
    {
        "pattern": re.compile(r"^heating\.inverters\.(\d+)\.sensors\.power\.output$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="inverter_power_output",  # Generic key
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        ),
    },
    # Fans (primary circuit)
    {
        "pattern": re.compile(r"^heating\.primaryCircuit\.fans\.(\d+)\.current$"),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="fan_speed",
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:fan",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Economizer Temperature
    {
        "pattern": re.compile(
            r"^heating\.economizers\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="economizer_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Evaporator Temperatures
    {
        "pattern": re.compile(
            r"^heating\.evaporators\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    {
        "pattern": re.compile(
            r"^heating\.evaporators\.(\d+)\.sensors\.temperature\.overheat$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_overheat_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
    # Condensor Liquid Temperature
    {
        "pattern": re.compile(
            r"^heating\.condensors\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        "description": SensorEntityDescription(
            key="placeholder",
            translation_key="condensor_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    },
]

# Map feature names to SensorEntityDescription
SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    "heating.sensors.temperature.outside": SensorEntityDescription(
        key="heating.sensors.temperature.outside",
        translation_key="outside_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.sensors.temperature.return": SensorEntityDescription(
        key="heating.sensors.temperature.return",
        translation_key="return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.boiler.sensors.temperature.commonSupply": SensorEntityDescription(
        key="heating.boiler.sensors.temperature.commonSupply",
        translation_key="common_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.primaryCircuit.sensors.temperature.supply": SensorEntityDescription(
        key="heating.primaryCircuit.sensors.temperature.supply",
        translation_key="primary_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.secondaryCircuit.sensors.temperature.supply": SensorEntityDescription(
        key="heating.secondaryCircuit.sensors.temperature.supply",
        translation_key="secondary_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.bufferCylinder.sensors.temperature.main": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.main",
        translation_key="buffer_cylinder_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.dhw.sensors.temperature.hotWaterStorage": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorage",
        translation_key="dhw_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Heating Rod (Diagnostic)
    "heating.heatingRod.statistics.starts": SensorEntityDescription(
        key="heating.heatingRod.statistics.starts",
        translation_key="heating_rod_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "heating.heatingRod.statistics.hours": SensorEntityDescription(
        key="heating.heatingRod.statistics.hours",
        translation_key="heating_rod_hours",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # SCOP
    "heating.scop.dhw": SensorEntityDescription(
        key="heating.scop.dhw",
        translation_key="scop_dhw",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "heating.scop.heating": SensorEntityDescription(
        key="heating.scop.heating",
        translation_key="scop_heating",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "heating.scop.total": SensorEntityDescription(
        key="heating.scop.total",
        translation_key="scop_total",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Additional Diagnostic
    "heating.sensors.pressure.supply": SensorEntityDescription(
        key="heating.sensors.pressure.supply",
        translation_key="supply_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "heating.sensors.volumetricFlow.allengra": SensorEntityDescription(
        key="heating.sensors.volumetricFlow.allengra",
        translation_key="volumetric_flow",
        native_unit_of_measurement="L/h",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Production / Power
    "heating.heat.production.summary.dhw.currentDay": SensorEntityDescription(
        key="heating.heat.production.summary.dhw.currentDay",
        translation_key="production_dhw_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "heating.heat.production.summary.heating.currentDay": SensorEntityDescription(
        key="heating.heat.production.summary.heating.currentDay",
        translation_key="production_heating_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # --- New Sensors ---
    # Environment
    "heating.sensors.humidity.outside": SensorEntityDescription(
        key="heating.sensors.humidity.outside",
        translation_key="outside_humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Boiler (Gas)
    "heating.boiler.sensors.temperature.main": SensorEntityDescription(
        key="heating.boiler.sensors.temperature.main",
        translation_key="boiler_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Circuits Return
    "heating.primaryCircuit.sensors.temperature.return": SensorEntityDescription(
        key="heating.primaryCircuit.sensors.temperature.return",
        translation_key="primary_return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.secondaryCircuit.sensors.temperature.return": SensorEntityDescription(
        key="heating.secondaryCircuit.sensors.temperature.return",
        translation_key="secondary_return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # DHW Details
    "heating.dhw.sensors.temperature.outlet": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.outlet",
        translation_key="dhw_outlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.dhw.sensors.temperature.hotWaterStorageTop": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorageTop",
        translation_key="dhw_storage_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.dhw.sensors.temperature.hotWaterStorageBottom": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorageBottom",
        translation_key="dhw_storage_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Details
    "heating.bufferCylinder.sensors.temperature.top": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.top",
        translation_key="buffer_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.bufferCylinder.sensors.temperature.midTop": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.midTop",
        translation_key="buffer_mid_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.bufferCylinder.sensors.temperature.middle": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.middle",
        translation_key="buffer_middle_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.bufferCylinder.sensors.temperature.midBottom": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.midBottom",
        translation_key="buffer_mid_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.bufferCylinder.sensors.temperature.bottom": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.bottom",
        translation_key="buffer_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Solar
    "heating.solar.sensors.temperature.collector": SensorEntityDescription(
        key="heating.solar.sensors.temperature.collector",
        translation_key="solar_collector_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.solar.sensors.temperature.dhw": SensorEntityDescription(
        key="heating.solar.sensors.temperature.dhw",
        translation_key="solar_dhw_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "heating.solar.power.production.day": SensorEntityDescription(
        key="heating.solar.power.production.day",
        translation_key="solar_production_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Valves
    "heating.valves.fourThreeWay.position": SensorEntityDescription(
        key="heating.valves.fourThreeWay.position",
        translation_key="valve_position",
        icon="mdi:valve",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

# Analytics Features (from handover)
ANALYTICS_TYPES: dict[str, SensorEntityDescription] = {
    "analytics.heating.power.consumption.total": SensorEntityDescription(
        key="analytics.heating.power.consumption.total",
        translation_key="consumption_total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "analytics.heating.power.consumption.heating": SensorEntityDescription(
        key="analytics.heating.power.consumption.heating",
        translation_key="consumption_heating",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "analytics.heating.power.consumption.dhw": SensorEntityDescription(
        key="analytics.heating.power.consumption.dhw",
        translation_key="consumption_dhw",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
}


def _get_sensor_entity_description(
    feature_name: str,
) -> tuple[SensorEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name.

    Returns:
        tuple: (description, translation_placeholders) or None
    """
    for template in SENSOR_TEMPLATES:
        match = template["pattern"].match(feature_name)
        if match:
            index = match.group(1)
            base_desc: SensorEntityDescription = template["description"]

            # Clone and Format
            new_desc = dataclasses.replace(
                base_desc,
                key=feature_name,
                translation_key=base_desc.translation_key,
            )
            return new_desc, {"index": index}
    return None


def _get_auto_discovery_description(feature) -> SensorEntityDescription:
    """Create a sensor description based on feature unit/type."""
    unit = getattr(feature, "unit", None)

    # Defaults
    device_class = None
    state_class = None
    native_unit = None

    match unit:
        case "celsius":
            device_class = SensorDeviceClass.TEMPERATURE
            native_unit = UnitOfTemperature.CELSIUS
            state_class = SensorStateClass.MEASUREMENT
        case "bar":
            device_class = SensorDeviceClass.PRESSURE
            native_unit = UnitOfPressure.BAR
            state_class = SensorStateClass.MEASUREMENT
        case "percent":
            native_unit = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
        case "kilowattHour":
            device_class = SensorDeviceClass.ENERGY
            native_unit = UnitOfEnergy.KILO_WATT_HOUR
            state_class = SensorStateClass.TOTAL_INCREASING
        case "watt":
            device_class = SensorDeviceClass.POWER
            native_unit = UnitOfPower.WATT
            state_class = SensorStateClass.MEASUREMENT
        case "volumetricFlow" | "liter/hour":
            # API gives 'volumetricFlow' or 'liter/hour' -> L/h
            device_class = SensorDeviceClass.VOLUME_FLOW_RATE
            native_unit = "L/h"
            state_class = SensorStateClass.MEASUREMENT

    # Fallback for generic numbers
    if state_class is None and isinstance(feature.value, (int, float)):
        state_class = SensorStateClass.MEASUREMENT

    return SensorEntityDescription(
        key=feature.name,
        name=beautify_name(feature.name),
        native_unit_of_measurement=native_unit,
        device_class=device_class,
        state_class=state_class,
        entity_category=EntityCategory.DIAGNOSTIC if not device_class else None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices sensor based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]
    analytics_coordinator: ViClimateAnalyticsCoordinator = coords["analytics"]

    entities = []

    # --- 1. Viessmann IoT API ---
    if coordinator.data:
        entities.extend(_discover_realtime_sensors(coordinator))

    # --- 2. Viessmann Analytics API ---
    if coordinator.data and analytics_coordinator:
        entities.extend(_discover_analytics_sensors(coordinator, analytics_coordinator))

    async_add_entities(entities)


def _discover_realtime_sensors(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[SensorEntity]:
    """Discover and return realtime sensor entities."""
    entities = []
    for map_key, device in coordinator.data.items():
        # Iterate over FLATTENED features
        for feature in device.features:
            # Skip ignored features early
            if is_feature_ignored(feature.name, IGNORED_FEATURES):
                continue

            # 1. Defined Entities (High Quality)
            if feature.name in SENSOR_TYPES:
                description = SENSOR_TYPES[feature.name]
                entities.append(
                    ViClimateSensor(coordinator, map_key, feature.name, description)
                )
                continue

            if match_result := _get_sensor_entity_description(feature.name):
                description, placeholders = match_result
                entities.append(
                    ViClimateSensor(
                        coordinator,
                        map_key,
                        feature.name,
                        description,
                        translation_placeholders=placeholders,
                    )
                )
                continue

            # 2. Automatic Discovery (Fallback)
            # If not writable (Sensors) and not boolean-like
            # (Binary Sensor platform handles all boolean-like values)
            if not feature.is_writable and not is_feature_boolean_like(feature.value):
                description = _get_auto_discovery_description(feature)
                entities.append(
                    ViClimateSensor(coordinator, map_key, feature.name, description)
                )
    return entities


def _discover_analytics_sensors(
    coordinator: ViClimateDataUpdateCoordinator,
    analytics_coordinator: ViClimateAnalyticsCoordinator,
) -> list[SensorEntity]:
    """Discover and return analytics sensor entities."""
    entities = []
    # 1. Identify heating devices (Mirroring coordinator logic)
    heating_devices = [
        device
        for device in coordinator.data.values()
        if getattr(device, "device_type", "unknown") == "heating"
    ]

    # Fallback
    if not heating_devices and len(coordinator.data) == 1:
        heating_devices.append(next(iter(coordinator.data.values())))

    if heating_devices:
        for heating_device in heating_devices:
            _LOGGER.debug(
                "Analytics attached to device: %s (Serial: %s)",
                heating_device.id,
                heating_device.gateway_serial,
            )
            for feature_name, description in ANALYTICS_TYPES.items():
                # Skip ignored features
                if is_feature_ignored(feature_name, IGNORED_FEATURES):
                    continue

                entities.append(
                    ViClimateConsumptionSensor(
                        analytics_coordinator, heating_device, description
                    )
                )
    else:
        _LOGGER.warning("No heating device found for Analytics Setup.")

    return entities


class ViClimateSensor(CoordinatorEntity, SensorEntity):
    """Representation of a generic Viessmann Climate Devices Sensor."""

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: SensorEntityDescription,
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

        # Improve name for auto-discovered entities
        if (
            not hasattr(description, "translation_key")
            or not description.translation_key
        ):
            if hasattr(description, "name") and description.name:
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
    def feature_data(self):
        """Retrieve the specific feature from coordinator data."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        # Use efficient lookup
        return device.get_feature(self._feature_name)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        feat = self.feature_data
        if feat:
            val = feat.value
            # Handle "NotConnected" case
            if hasattr(val, "lower") and "notconnected" in str(val).lower().replace(
                " ", ""
            ):
                return None

            # Handle Complex types (Dict/List) that exceed HA state limit
            if isinstance(val, (dict, list)):
                # We cannot return complex types as state.
                # If it's a list, return len. If dict, return "Complex".
                # The full data is available in extra_state_attributes fallback.
                if isinstance(val, list):
                    return len(val)
                return "Complex Data"

            return val
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {"viessmann_feature_name": self._feature_name}
        feat = self.feature_data
        if feat and isinstance(feat.value, (dict, list)):
            attrs["raw_value"] = feat.value
        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        feat = self.feature_data
        return self.coordinator.last_update_success and feat and feat.is_enabled


class ViClimateConsumptionSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Viessmann Consumption Sensor (Analytics)."""

    def __init__(
        self,
        coordinator: ViClimateAnalyticsCoordinator,
        device,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self.device = device
        self._feature_name = description.key

        self._attr_unique_id = (
            f"{device.gateway_serial}-{device.id}-{self._feature_name}"
        )
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information (linked to the main device)."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.device.gateway_serial}-{self.device.id}")},
            name=self.device.model_id,
            manufacturer="Viessmann",
            model=self.device.model_id,
            serial_number=self.device.gateway_serial,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Check if coordinator has data for THIS device
        if not self.coordinator.last_update_success:
            return False

        device_key = f"{self.device.gateway_serial}_{self.device.id}"
        device_data = self.coordinator.data.get(device_key)

        if not device_data:
            return False

        # Check if feature exists
        return self._feature_name in device_data

    @property
    def native_value(self) -> float | None:
        """Return the consumption value."""
        # coordinator.data is a Dict[device_key, Dict[feature_name, Feature]]
        data = self.coordinator.data
        if not data:
            return None

        device_key = f"{self.device.gateway_serial}_{self.device.id}"
        device_features = data.get(device_key)

        if not device_features:
            return None

        feature = device_features.get(self._feature_name)
        if feature:
            val = feature.value
            if isinstance(val, (dict, list)):
                # Return primitive summary for state
                if isinstance(val, list):
                    return len(val)
                return "Complex Data"
            return val

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {}
        data = self.coordinator.data
        if data:
            device_key = f"{self.device.gateway_serial}_{self.device.id}"
            device_features = data.get(device_key)
            if device_features:
                feature = device_features.get(self._feature_name)
                if feature and isinstance(feature.value, (dict, list)):
                    attrs["raw_value"] = feature.value
        return attrs
