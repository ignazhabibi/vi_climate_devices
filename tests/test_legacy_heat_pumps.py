"""Tests for the defined entities of legacy CU401B heat pumps."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    _discover_binary_sensors,
)
from custom_components.vi_climate_devices.number import _discover_numbers
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors

LEGACY_HEAT_PUMPS = [
    "Vitocal200S",
    "Vitocal300G-CU401B",
    "Vitocal333G-with-Vitovent300F",
]

DUPLICATE_REFRIGERANT_FEATURES = {
    "heating.sensors.pressure.suctionGas": "heating.compressors.0.sensors.pressure.inlet",
    "heating.sensors.temperature.hotGas": "heating.compressors.0.sensors.temperature.outlet",
    "heating.sensors.temperature.liquidGas": "heating.evaporators.0.sensors.temperature.liquid",
    "heating.sensors.temperature.suctionGas": "heating.compressors.0.sensors.temperature.inlet",
}


@pytest.mark.parametrize("device_name", LEGACY_HEAT_PUMPS)
@pytest.mark.asyncio
async def test_legacy_heat_pumps_define_cop_and_discharge_pressure(
    device_name: str,
) -> None:
    """Name the coefficients of performance and the discharge pressure."""
    # Arrange: Load the real legacy heat pump fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: The values are defined diagnostic sensors.
    for circuit in ("cooling", "dhw", "heating", "total"):
        cop = descriptions[f"heating.cop.{circuit}"]
        assert cop.translation_key == f"cop_{circuit}"
        assert cop.entity_category == "diagnostic"
    pressure = descriptions["heating.sensors.pressure.hotGas"]
    assert pressure.translation_key == "compressor_outlet_pressure"
    assert pressure.native_unit_of_measurement == "bar"


@pytest.mark.parametrize("device_name", LEGACY_HEAT_PUMPS)
@pytest.mark.asyncio
async def test_duplicate_refrigerant_values_create_no_sensors(device_name: str) -> None:
    """Skip refrigerant values that a defined sensor already reports."""
    # Arrange: Load the real legacy heat pump fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    keys = {
        entity.entity_description.key
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: Each skipped value matches the reading of a defined sensor.
    for duplicate, defined in DUPLICATE_REFRIGERANT_FEATURES.items():
        assert duplicate not in keys
        assert defined in keys
        duplicate_feature = device.get_feature(duplicate)
        defined_feature = device.get_feature(defined)
        assert duplicate_feature is not None
        assert defined_feature is not None
        assert duplicate_feature.value == defined_feature.value


# Feature, translation key, and value of the CU401B diagnostic sensors.
CU401B_DIAGNOSTIC_SENSORS = (
    ("heating.compressors.0.sensors.power", "compressor_load", 100),
    (
        "heating.compressors.0.sensors.temperature.overheat",
        "compressor_overheat_temperature",
        4,
    ),
    (
        "heating.compressors.0.statistics.load.hoursLoadClassOne",
        "compressor_hours_load_class_1",
        5,
    ),
    (
        "heating.compressors.0.statistics.load.hoursLoadClassTwo",
        "compressor_hours_load_class_2",
        233,
    ),
    (
        "heating.compressors.0.statistics.load.hoursLoadClassThree",
        "compressor_hours_load_class_3",
        448,
    ),
    (
        "heating.compressors.0.statistics.load.hoursLoadClassFour",
        "compressor_hours_load_class_4",
        249,
    ),
    (
        "heating.compressors.0.statistics.load.hoursLoadClassFive",
        "compressor_hours_load_class_5",
        3,
    ),
    ("heating.device.mainECU.runtime", "main_ecu_runtime", 7768472),
    ("heating.heatingRod.runtime.levelOne", "heating_rod_runtime_level_1", 886682),
    ("heating.heatingRod.runtime.levelTwo", "heating_rod_runtime_level_2", 287877),
    ("heating.primaryCircuit.sensors.rotation", "primary_pump_speed", 80),
    (
        "heating.dhw.temperature.hysteresis.switchOffValue",
        "dhw_hysteresis_off",
        5,
    ),
)

# Identifiers, raw histories, static details, and duplicates.
CU401B_HIDDEN_FEATURES = frozenset(
    {
        "device.messages.logbook",
        "heating.buffer.sensors.temperature.main",
        "heating.buffer.sensors.temperature.top",
        "heating.circuits.1.operating.programs.eco.temperature",
        "heating.circuits.1.operating.programs.screedDrying.heatpump.useApproved",
        "heating.compressors.0.power",
        "heating.configuration.buffer.temperature.max",
        "heating.configuration.dhwHeater.useApproved",
        "heating.controller.serial",
        "heating.coolingCircuits.0.type",
    }
)


@pytest.mark.asyncio
async def test_vitocal_300g_defines_compressor_runtime_and_dhw_entities() -> None:
    """Name the CU401B readings and controls and hide its duplicates."""
    # Arrange: Load the Vitocal 300-G fixture with the CU401B controller.
    device = (
        await FixtureViClient("Vitocal300G-CU401B").get_full_installation_status(
            "99999"
        )
    )[0]
    coordinator = MagicMock(data={"device": device})

    # Act: Discover the fixture's sensors, binary sensors, and numbers.
    entities = {
        entity.entity_description.key: entity
        for entity in [
            *_discover_realtime_sensors(coordinator),
            *_discover_binary_sensors(coordinator),
        ]
    }
    numbers = {
        entity.entity_description.key: entity
        for entity in _discover_numbers(coordinator)
    }

    # Assert: The compressor, runtime, pump, and hysteresis readings are
    # diagnostic sensors.
    for feature_name, translation_key, value in CU401B_DIAGNOSTIC_SENSORS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.entity_category == "diagnostic"
        assert entity.native_value == value

    # Assert: Runtimes in seconds are durations shown in hours.
    runtime = entities["heating.device.mainECU.runtime"].entity_description
    assert runtime.device_class == "duration"
    assert runtime.suggested_unit_of_measurement == "h"

    # Assert: DHW charging and active cooling are running binary sensors.
    for feature_name, translation_key, is_on in (
        ("heating.dhw.charging.active", "dhw_charging", False),
        ("heating.coolingCircuits.0.reverse.active", "active_cooling", False),
    ):
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.device_class == "running"
        assert entity.is_on is is_on

    # Assert: The second DHW setpoint is an enabled number within its limits.
    setpoint = numbers["heating.dhw.temperature.temp2"]
    assert setpoint.entity_description.translation_key == "dhw_target_temperature_2"
    assert setpoint.entity_registry_enabled_default is True
    assert (setpoint.native_min_value, setpoint.native_max_value) == (10, 60)
    assert setpoint.native_value == 60

    # Assert: Identifiers, static details, and duplicates create no entity.
    assert not CU401B_HIDDEN_FEATURES & set(entities)


@pytest.mark.parametrize("device_name", ["Vitocal250A", "Vitocal252A"])
@pytest.mark.asyncio
async def test_writable_hysteresis_switch_off_creates_no_sensor(
    device_name: str,
) -> None:
    """Keep a writable switch-off hysteresis a number only."""
    # Arrange: Load a fixture that reports the hysteresis as writable.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]
    coordinator = MagicMock(data={"device": device})
    feature_name = "heating.dhw.temperature.hysteresis.switchOffValue"

    # Act: Discover the fixture's sensors and numbers.
    sensor_keys = {
        entity.entity_description.key
        for entity in _discover_realtime_sensors(coordinator)
    }
    number_keys = {
        entity.entity_description.key for entity in _discover_numbers(coordinator)
    }

    # Assert: Only the number exposes the hysteresis.
    assert feature_name in number_keys
    assert feature_name not in sensor_keys
