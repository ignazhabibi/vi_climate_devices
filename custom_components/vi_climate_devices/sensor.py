"""Sensor platform for Viessmann Climate Devices."""

from __future__ import annotations

import dataclasses
import logging
import re
from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from vi_api_client import Device, Feature, JsonValue

from . import ViClimateDevicesConfigEntry
from .const import IGNORED_FEATURES, TESTED_DEVICES
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import (
    EntityTemplate,
    ViClimateFeatureEntity,
    async_setup_dynamic_entities,
    get_template_translation,
)
from .status_messages import (
    HEAT_PUMP_STATE_OPTIONS,
    HEATING_ROD_STAGE_OPTIONS,
    STATUS_MESSAGES_FEATURE,
    StatusMessage,
    get_active_heating_rod_stages,
    get_heat_pump_state,
    get_heating_rod_state,
    is_heat_pump,
    parse_status_messages,
)
from .utils import (
    api_value_to_option_key,
    beautify_name,
    get_feature_string_value,
    is_feature_boolean_like,
    is_feature_ignored,
    normalize_sensor_value,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Enum states are lowercase keys of the API values (see api_value_to_option_key).
# Sort the values alphabetically.
ACTIVE_PROGRAM_OPTIONS = [
    "comfort",
    "comfort_cooling",
    "comfort_cooling_energy_saving",
    "comfort_energy_saving",
    "comfort_heating",
    "eco",
    "fixed",
    "forced_last_from_schedule",
    "frostprotection",
    "holiday",
    "holiday_at_home",
    "normal",
    "normal_cooling",
    "normal_cooling_energy_saving",
    "normal_energy_saving",
    "normal_heating",
    "reduced",
    "reduced_cooling",
    "reduced_cooling_energy_saving",
    "reduced_energy_saving",
    "reduced_heating",
    "standby",
    "summer_eco",
]

# Sort the values alphabetically.
NOISE_REDUCTION_OPTIONS = [
    "max_reduced",
    "not_reduced",
    "slightly_reduced",
]

# The valve switches between heating/cooling, the integrated bypass/defrost
# buffer, and domestic hot water; "climatCircuitTwoDefrost" is the buffer port,
# not a second heating circuit. The API spells some positions "climat..."
# without the trailing "e".
# Sort the values alphabetically.
VALVE_POSITION_OPTIONS = [
    "climat_circuit_one_and_two",
    "climat_circuit_two_defrost",
    "climate_circuit_one",
    "domestic_hot_water",
]


@dataclasses.dataclass(frozen=True, kw_only=True)
class ViClimateStatusSensorEntityDescription(SensorEntityDescription):
    """Describe a sensor derived from the active status messages."""

    value_fn: Callable[[list[StatusMessage]], str | None]
    attributes_fn: Callable[[list[StatusMessage]], dict[str, JsonValue]]


def _active_codes_attributes(messages: list[StatusMessage]) -> dict[str, JsonValue]:
    """Return every active status message, including unmapped codes."""
    return {"active_codes": [message.as_attribute() for message in messages]}


def _active_stages_attributes(messages: list[StatusMessage]) -> dict[str, JsonValue]:
    """Return the running heating rod stages to expose non-cumulative switching."""
    active_stages: list[JsonValue] = [*get_active_heating_rod_stages(messages)]
    return {"active_stages": active_stages}


# Heat pump sensors derived from the active status messages. Their keys extend
# the feature name because several entities share one feature.
STATUS_SENSOR_TYPES: tuple[ViClimateStatusSensorEntityDescription, ...] = (
    ViClimateStatusSensorEntityDescription(
        key=f"{STATUS_MESSAGES_FEATURE}.heatPumpState",
        translation_key="heat_pump_state",
        device_class=SensorDeviceClass.ENUM,
        options=HEAT_PUMP_STATE_OPTIONS,
        value_fn=get_heat_pump_state,
        attributes_fn=_active_codes_attributes,
    ),
    ViClimateStatusSensorEntityDescription(
        key=f"{STATUS_MESSAGES_FEATURE}.heatingRodStage",
        translation_key="heating_rod_stage",
        device_class=SensorDeviceClass.ENUM,
        options=HEATING_ROD_STAGE_OPTIONS,
        value_fn=get_heating_rod_state,
        attributes_fn=_active_stages_attributes,
    ),
)

AUTO_DISCOVERED_TOTAL_INCREASING_ENERGY_FEATURES = frozenset(
    {
        "ess.transfer.charge.cumulated.currentDay",
        "ess.transfer.charge.cumulated.currentWeek",
        "ess.transfer.charge.cumulated.currentMonth",
        "ess.transfer.charge.cumulated.currentYear",
        "ess.transfer.charge.cumulated.lifeCycle",
        "ess.transfer.discharge.cumulated.currentDay",
        "ess.transfer.discharge.cumulated.currentWeek",
        "ess.transfer.discharge.cumulated.currentMonth",
        "ess.transfer.discharge.cumulated.currentYear",
        "ess.transfer.discharge.cumulated.lifeCycle",
        "photovoltaic.production.cumulated.currentDay",
        "photovoltaic.production.cumulated.currentWeek",
        "photovoltaic.production.cumulated.currentMonth",
        "photovoltaic.production.cumulated.currentYear",
        "photovoltaic.production.cumulated.lifeCycle",
        "pcc.transfer.consumption.total",
        "pcc.transfer.feedIn.total",
    }
)


# Templates with regex patterns for dynamic feature names
SENSOR_TEMPLATES: tuple[EntityTemplate[SensorEntityDescription], ...] = (
    # Heating Circuits Active Program
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.operating\.programs\.active$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_active_program",
            device_class=SensorDeviceClass.ENUM,
            options=ACTIVE_PROGRAM_OPTIONS,
        ),
    ),
    # Heating Circuits Supply Temperature
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.sensors\.temperature\.supply$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_supply_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ),
    # Burners Modulation
    EntityTemplate(
        pattern=re.compile(r"^heating\.burners\.(\d+)\.modulation$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="burner_modulation",
            native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ),
    # Burners Statistics
    EntityTemplate(
        pattern=re.compile(r"^heating\.burners\.(\d+)\.statistics\.starts$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="burner_starts",
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(r"^heating\.burners\.(\d+)\.statistics\.hours$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="burner_hours",
            native_unit_of_measurement="h",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressors Statistics
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.statistics\.hours$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_hours",  # Generic key
            native_unit_of_measurement="h",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.statistics\.starts$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_starts",  # Generic key
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Phase
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.phase$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_phase",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Pressure Inlet
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.sensors\.pressure\.inlet$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_inlet_pressure",
            native_unit_of_measurement=UnitOfPressure.BAR,
            device_class=SensorDeviceClass.PRESSURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Temperature - Inlet
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.inlet$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_inlet_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Temperature - Motor Chamber
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.motorChamber$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_motor_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Temperature - Oil
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.sensors\.temperature\.oil$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_oil_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Temperature - Outlet
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.compressors\.(\d+)\.sensors\.temperature\.outlet$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_outlet_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Speed - Current
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.speed\.current$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_speed_current",
            native_unit_of_measurement="rps",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Compressor Speed - Setpoint
    EntityTemplate(
        pattern=re.compile(r"^heating\.compressors\.(\d+)\.speed\.setpoint$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="compressor_speed_setpoint",
            native_unit_of_measurement="rps",
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Fans (primary circuit)
    EntityTemplate(
        pattern=re.compile(r"^heating\.primaryCircuit\.fans\.(\d+)\.current$"),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="fan_speed",
            native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Economizer Temperature
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.economizers\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="economizer_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Evaporator Temperatures
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.evaporators\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.evaporators\.(\d+)\.sensors\.temperature\.overheat$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="evaporator_overheat_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    # Condensor Liquid Temperature
    EntityTemplate(
        pattern=re.compile(
            r"^heating\.condensors\.(\d+)\.sensors\.temperature\.liquid$"
        ),
        description=SensorEntityDescription(
            key="placeholder",
            translation_key="condensor_liquid_temperature",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
)


SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    # Boiler Common Supply Temperature
    "heating.boiler.sensors.temperature.commonSupply": SensorEntityDescription(
        key="heating.boiler.sensors.temperature.commonSupply",
        translation_key="common_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Boiler Main Temperature
    "heating.boiler.sensors.temperature.main": SensorEntityDescription(
        key="heating.boiler.sensors.temperature.main",
        translation_key="boiler_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Temperature - Bottom
    "heating.bufferCylinder.sensors.temperature.bottom": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.bottom",
        translation_key="buffer_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Main Temperature
    "heating.bufferCylinder.sensors.temperature.main": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.main",
        translation_key="buffer_cylinder_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Temperature - Mid Bottom
    "heating.bufferCylinder.sensors.temperature.midBottom": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.midBottom",
        translation_key="buffer_mid_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Temperature - Middle
    "heating.bufferCylinder.sensors.temperature.middle": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.middle",
        translation_key="buffer_middle_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Temperature - Mid Top
    "heating.bufferCylinder.sensors.temperature.midTop": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.midTop",
        translation_key="buffer_mid_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Buffer Cylinder Temperature - Top
    "heating.bufferCylinder.sensors.temperature.top": SensorEntityDescription(
        key="heating.bufferCylinder.sensors.temperature.top",
        translation_key="buffer_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # DHW Charging (Today)
    "heating.dhw.sensors.temperature.hotWaterStorage": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorage",
        translation_key="dhw_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # DHW Storage Temperature - Bottom
    "heating.dhw.sensors.temperature.hotWaterStorageBottom": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorageBottom",
        translation_key="dhw_storage_bottom_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # DHW Storage Temperature - Top
    "heating.dhw.sensors.temperature.hotWaterStorageTop": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.hotWaterStorageTop",
        translation_key="dhw_storage_top_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # DHW Outlet Temperature
    "heating.dhw.sensors.temperature.outlet": SensorEntityDescription(
        key="heating.dhw.sensors.temperature.outlet",
        translation_key="dhw_outlet_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Current Heat Production
    "heating.heat.production.current": SensorEntityDescription(
        key="heating.heat.production.current",
        translation_key="heat_production_current",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Production Summary DHW (Current Day).
    "heating.heat.production.summary.dhw.currentDay": SensorEntityDescription(
        key="heating.heat.production.summary.dhw.currentDay",
        translation_key="production_dhw_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Production Summary DHW (Current Year).
    "heating.heat.production.summary.dhw.currentYear": SensorEntityDescription(
        key="heating.heat.production.summary.dhw.currentYear",
        translation_key="production_dhw_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Production Summary Heating (Current Day).
    "heating.heat.production.summary.heating.currentDay": SensorEntityDescription(
        key="heating.heat.production.summary.heating.currentDay",
        translation_key="production_heating_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Production Summary Heating (Current Year).
    "heating.heat.production.summary.heating.currentYear": SensorEntityDescription(
        key="heating.heat.production.summary.heating.currentYear",
        translation_key="production_heating_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Production Summary Cooling (Current Day).
    "heating.heat.production.summary.cooling.currentDay": SensorEntityDescription(
        key="heating.heat.production.summary.cooling.currentDay",
        translation_key="production_cooling_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Production Summary Cooling (Current Year).
    "heating.heat.production.summary.cooling.currentYear": SensorEntityDescription(
        key="heating.heat.production.summary.cooling.currentYear",
        translation_key="production_cooling_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Current Power Consumption
    "heating.power.consumption.current": SensorEntityDescription(
        key="heating.power.consumption.current",
        translation_key="power_consumption_current",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Realtime Consumption DHW (Current Day).
    "heating.power.consumption.dhw.currentDay": SensorEntityDescription(
        key="heating.power.consumption.dhw.currentDay",
        translation_key="consumption_dhw_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Realtime Consumption DHW (Current Year).
    "heating.power.consumption.dhw.currentYear": SensorEntityDescription(
        key="heating.power.consumption.dhw.currentYear",
        translation_key="consumption_dhw_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Realtime Consumption Heating (Current Day).
    "heating.power.consumption.heating.currentDay": SensorEntityDescription(
        key="heating.power.consumption.heating.currentDay",
        translation_key="consumption_heating_current_day",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Realtime Consumption Heating (Current Year).
    "heating.power.consumption.heating.currentYear": SensorEntityDescription(
        key="heating.power.consumption.heating.currentYear",
        translation_key="consumption_heating_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Realtime Consumption Total (Current Year).
    "heating.power.consumption.total.currentYear": SensorEntityDescription(
        key="heating.power.consumption.total.currentYear",
        translation_key="consumption_total_current_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Heating Rod Consumption DHW (Current Year).
    "heating.heatingRod.power.consumption.summary.dhw.currentYear": (
        SensorEntityDescription(
            key="heating.heatingRod.power.consumption.summary.dhw.currentYear",
            translation_key="heating_rod_consumption_dhw_current_year",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
    ),
    # Heating Rod Consumption Heating (Current Year).
    "heating.heatingRod.power.consumption.summary.heating.currentYear": (
        SensorEntityDescription(
            key="heating.heatingRod.power.consumption.summary.heating.currentYear",
            translation_key="heating_rod_consumption_heating_current_year",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
    ),
    # Heating Rod (Diagnostic) - Hours
    "heating.heatingRod.statistics.hours": SensorEntityDescription(
        key="heating.heatingRod.statistics.hours",
        translation_key="heating_rod_hours",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Heating Rod (Diagnostic) - Starts
    "heating.heatingRod.statistics.starts": SensorEntityDescription(
        key="heating.heatingRod.statistics.starts",
        translation_key="heating_rod_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Primary Circuit Return Temperature
    "heating.primaryCircuit.sensors.temperature.return": SensorEntityDescription(
        key="heating.primaryCircuit.sensors.temperature.return",
        translation_key="primary_return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Primary Circuit Supply Temperature
    "heating.primaryCircuit.sensors.temperature.supply": SensorEntityDescription(
        key="heating.primaryCircuit.sensors.temperature.supply",
        translation_key="primary_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # SCOP DHW
    "heating.scop.dhw": SensorEntityDescription(
        key="heating.scop.dhw",
        translation_key="scop_dhw",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # SCOP Heating
    "heating.scop.heating": SensorEntityDescription(
        key="heating.scop.heating",
        translation_key="scop_heating",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # SCOP Total
    "heating.scop.total": SensorEntityDescription(
        key="heating.scop.total",
        translation_key="scop_total",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Secondary Circuit Return Temperature
    "heating.secondaryCircuit.sensors.temperature.return": SensorEntityDescription(
        key="heating.secondaryCircuit.sensors.temperature.return",
        translation_key="secondary_return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Secondary Circuit Supply Temperature
    "heating.secondaryCircuit.sensors.temperature.supply": SensorEntityDescription(
        key="heating.secondaryCircuit.sensors.temperature.supply",
        translation_key="secondary_supply_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Outside Humidity
    "heating.sensors.humidity.outside": SensorEntityDescription(
        key="heating.sensors.humidity.outside",
        translation_key="outside_humidity",
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Supply Pressure
    "heating.sensors.pressure.supply": SensorEntityDescription(
        key="heating.sensors.pressure.supply",
        translation_key="supply_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Outside Temperature
    "heating.sensors.temperature.outside": SensorEntityDescription(
        key="heating.sensors.temperature.outside",
        translation_key="outside_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Return Temperature (Generic)
    "heating.sensors.temperature.return": SensorEntityDescription(
        key="heating.sensors.temperature.return",
        translation_key="return_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Volumetric Flow (Allengra)
    "heating.sensors.volumetricFlow.allengra": SensorEntityDescription(
        key="heating.sensors.volumetricFlow.allengra",
        translation_key="volumetric_flow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_HOUR,
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Solar Collector Temperature
    "heating.solar.sensors.temperature.collector": SensorEntityDescription(
        key="heating.solar.sensors.temperature.collector",
        translation_key="solar_collector_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Solar DHW Temperature
    "heating.solar.sensors.temperature.dhw": SensorEntityDescription(
        key="heating.solar.sensors.temperature.dhw",
        translation_key="solar_dhw_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Solar Power Production Today
    "heating.solar.power.production.day": SensorEntityDescription(
        key="heating.solar.power.production.day",
        translation_key="solar_production_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Internal Pump (current speed)
    "heating.boiler.pumps.internal.current": SensorEntityDescription(
        key="heating.boiler.pumps.internal.current",
        translation_key="internal_pump",
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Outside Temperature Damping Factor (time constant)
    "heating.configuration.temperature.outside.DampingFactor": (
        SensorEntityDescription(
            key="heating.configuration.temperature.outside.DampingFactor",
            translation_key="outside_temperature_damping_factor",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
    ),
    # Noise Reduction (active program)
    "heating.noise.reduction.operating.programs.active": SensorEntityDescription(
        key="heating.noise.reduction.operating.programs.active",
        translation_key="noise_reduction_program",
        device_class=SensorDeviceClass.ENUM,
        options=NOISE_REDUCTION_OPTIONS,
    ),
    # Valves
    "heating.valves.fourThreeWay.position": SensorEntityDescription(
        key="heating.valves.fourThreeWay.position",
        translation_key="valve_position",
        device_class=SensorDeviceClass.ENUM,
        options=VALVE_POSITION_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


def _get_sensor_entity_description(
    feature_name: str, device: Device
) -> tuple[SensorEntityDescription, dict[str, str]] | None:
    """Find a matching entity description for a dynamic feature name.

    Returns:
        tuple: (description, translation_placeholders) or None
    """
    for template in SENSOR_TEMPLATES:
        match = template.pattern.match(feature_name)
        if match:
            base_desc = template.description
            translation_key, placeholders = get_template_translation(
                match, str(base_desc.translation_key), device
            )
            new_desc = dataclasses.replace(
                base_desc,
                key=feature_name,
                translation_key=translation_key,
            )
            return new_desc, placeholders
    return None


def _get_auto_discovery_description(feature: Feature) -> SensorEntityDescription:
    """Create a sensor description based on feature unit/type."""
    unit = feature.unit

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
            native_unit = UnitOfRatio.PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
        case "kilowattHour":
            device_class = SensorDeviceClass.ENERGY
            native_unit = UnitOfEnergy.KILO_WATT_HOUR
        case "watt":
            device_class = SensorDeviceClass.POWER
            native_unit = UnitOfPower.WATT
            state_class = SensorStateClass.MEASUREMENT
        case "kilowatt":
            device_class = SensorDeviceClass.POWER
            native_unit = UnitOfPower.KILO_WATT
            state_class = SensorStateClass.MEASUREMENT
        case "wattHour":
            device_class = SensorDeviceClass.ENERGY
            native_unit = UnitOfEnergy.WATT_HOUR
        case "ampere":
            device_class = SensorDeviceClass.CURRENT
            native_unit = UnitOfElectricCurrent.AMPERE
            state_class = SensorStateClass.MEASUREMENT
        case "volumetricFlow" | "liter/hour":
            device_class = SensorDeviceClass.VOLUME_FLOW_RATE
            native_unit = UnitOfVolumeFlowRate.LITERS_PER_HOUR
            state_class = SensorStateClass.MEASUREMENT
        case _:
            pass

    if (
        device_class is SensorDeviceClass.ENERGY
        and feature.name in AUTO_DISCOVERED_TOTAL_INCREASING_ENERGY_FEATURES
    ):
        state_class = SensorStateClass.TOTAL_INCREASING

    # Fallback for generic numbers
    if (
        device_class is None
        and state_class is None
        and isinstance(feature.value, (int, float))
    ):
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
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices sensor based on a config entry."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_realtime_sensors(coordinator),
    )


def _discover_realtime_sensors(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[ViClimateSensor | ViClimateStatusSensor]:
    """Discover and return realtime sensor entities."""
    entities: list[ViClimateSensor | ViClimateStatusSensor] = []
    for map_key, device in coordinator.data.items():
        # Iterate over FLATTENED features
        for feature in device.features:
            # Skip ignored features early
            if is_feature_ignored(feature.name, IGNORED_FEATURES):
                continue

            if feature.name == STATUS_MESSAGES_FEATURE:
                if is_heat_pump(device):
                    entities.extend(
                        ViClimateStatusSensor(
                            coordinator, map_key, feature.name, description
                        )
                        for description in STATUS_SENSOR_TYPES
                    )
                continue

            # 1. Defined Entities (High Quality)
            if feature.name in SENSOR_TYPES:
                description = SENSOR_TYPES[feature.name]
                entities.append(
                    ViClimateSensor(coordinator, map_key, feature.name, description)
                )
                continue

            if match_result := _get_sensor_entity_description(feature.name, device):
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
                # Only disable entities by default for thoroughly tested devices
                is_tested = device.model_id in TESTED_DEVICES
                entities.append(
                    ViClimateSensor(
                        coordinator,
                        map_key,
                        feature.name,
                        description,
                        enabled_default=not is_tested,
                    )
                )
    return entities


class ViClimateSensor(ViClimateFeatureEntity, SensorEntity):
    """Representation of a generic Viessmann Climate Devices Sensor."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: SensorEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            map_key,
            feature_name,
            description,
            translation_placeholders,
            enabled_default,
        )
        self.entity_description = description
        self._unknown_enum_values: set[str] = set()

    @property
    def native_value(self) -> StateType:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state of the sensor."""
        feat = self.feature_data
        if not feat:
            return None
        if self.entity_description.device_class is SensorDeviceClass.ENUM:
            return self._get_enum_state(feat)
        return normalize_sensor_value(feat.value)

    def _get_enum_state(self, feature: Feature) -> str | None:
        """Return the option key for an enum feature, or None if it is unknown.

        Home Assistant rejects enum states outside the declared options, and
        the reported values differ between device generations and firmware.
        An unknown value therefore becomes an unknown state and is logged once
        so the options can be extended.
        """
        api_value = get_feature_string_value(feature.value)
        if api_value is None:
            return None
        option = api_value_to_option_key(api_value)
        if option in (self.entity_description.options or ()):
            return option
        if api_value not in self._unknown_enum_values:
            self._unknown_enum_values.add(api_value)
            _LOGGER.warning(
                "Unknown value %s for %s; reporting the state as unknown",
                api_value,
                feature.name,
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, JsonValue]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state attributes."""
        attrs: dict[str, JsonValue] = {"viessmann_feature_name": self._feature_name}
        feat = self.feature_data
        if feat and isinstance(feat.value, (dict, list)):
            attrs["raw_value"] = feat.value
        return attrs

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return True if entity is available."""
        feat = self.feature_data
        return super().available and feat is not None and feat.is_enabled


class ViClimateStatusSensor(ViClimateFeatureEntity, SensorEntity):
    """Sensor whose state is derived from the active status messages."""

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: ViClimateStatusSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, map_key, feature_name, description)
        self.entity_description = description
        self._status_description = description

    def _get_messages(self) -> list[StatusMessage] | None:
        """Return the active status messages, or None if they are unreadable."""
        feat = self.feature_data
        if not feat:
            return None
        return parse_status_messages(feat.value)

    @property
    def native_value(self) -> StateType:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state derived from the active status messages."""
        messages = self._get_messages()
        if messages is None:
            return None
        return self._status_description.value_fn(messages)

    @property
    def extra_state_attributes(self) -> dict[str, JsonValue]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the feature name and the status details behind the state."""
        attrs: dict[str, JsonValue] = {"viessmann_feature_name": self._feature_name}
        messages = self._get_messages()
        if messages is not None:
            attrs.update(self._status_description.attributes_fn(messages))
        return attrs

    @property
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return True if entity is available."""
        feat = self.feature_data
        return super().available and feat is not None and feat.is_enabled
