"""Tests for the defined entities of ventilation units with heat recovery."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import Device, FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    _discover_binary_sensors,
)
from custom_components.vi_climate_devices.number import _discover_numbers
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors
from custom_components.vi_climate_devices.switch import _discover_switches

# Feature, translation key, unit, device class, and value of the air streams,
# heat recovery, bypass, and volume flows.
AIR_READINGS = (
    (
        "ventilation.sensors.temperature.outside",
        "outdoor_air_temperature",
        "°C",
        "temperature",
        2.1,
    ),
    (
        "ventilation.sensors.temperature.extract",
        "extract_air_temperature",
        "°C",
        "temperature",
        20.5,
    ),
    (
        "ventilation.sensors.temperature.exhaust",
        "exhaust_air_temperature",
        "°C",
        "temperature",
        7.5,
    ),
    (
        "ventilation.sensors.humidity.outdoor",
        "outdoor_air_humidity",
        "%",
        "humidity",
        64,
    ),
    (
        "ventilation.sensors.humidity.extract",
        "extract_air_humidity",
        "%",
        "humidity",
        57,
    ),
    (
        "ventilation.sensors.humidity.exhaust",
        "exhaust_air_humidity",
        "%",
        "humidity",
        80,
    ),
    ("ventilation.heating.recovery", "heat_recovery", "%", None, 77),
    ("ventilation.bypass.position", "bypass_position", "%", None, 0),
    (
        "ventilation.volumeFlow.current.input",
        "supply_air_volume_flow",
        "m³/h",
        "volume_flow_rate",
        200,
    ),
    (
        "ventilation.volumeFlow.current.output",
        "extract_air_volume_flow",
        "m³/h",
        "volume_flow_rate",
        192,
    ),
)

# Feature, translation key, and value of the diagnostic exhaust fan sensors.
EXHAUST_FAN_READINGS = (
    ("ventilation.fan.exhaust.current", "exhaust_fan_speed", 1796),
    ("ventilation.fan.exhaust.target", "exhaust_fan_target_speed", 0),
    ("ventilation.fan.exhaust.runtime", "exhaust_fan_runtime", 13897),
)

# Installation details, duplicates of the bypass mode, and external locks.
HIDDEN_FEATURES = frozenset(
    {
        "device.commissioning.information.date",
        "device.commissioning.information.status",
        "ventilation.air.balance.offset.input",
        "ventilation.bypass.configuration.temperature.perceived",
        "ventilation.bypass.configuration.temperature.supply.dynamicRegulation",
        "ventilation.bypass.operating.modes.active.level",
        "ventilation.bypass.operating.modes.active.state",
        "ventilation.bypass.operating.modes.automatic.active",
        "ventilation.bypass.operating.modes.open.active",
        "ventilation.external.lock.active",
        "ventilation.fan.assignmentSwitch.active",
        "ventilation.features.co2.active",
        "ventilation.filter.information.filterOneEan",
        "ventilation.filter.information.filterRuntimeResetValue",
        "ventilation.levels.levelOne.volumeFlow",
        "ventilation.lockExternal.fireProtectionFlap",
        "ventilation.sensors.actuator.selftest.enabled",
        "ventilation.sensors.actuator.selftest.status",
    }
)


async def _vitoair() -> Device:
    """Return the Vitoair FS 300E fixture device."""
    return (
        await FixtureViClient("VitoairFs300E").get_full_installation_status("99999")
    )[0]


@pytest.mark.asyncio
async def test_vitoair_defines_air_streams_heat_recovery_and_bypass() -> None:
    """Name the four air streams, the heat recovery, the bypass, and the fans."""
    # Arrange: Load the Vitoair FS 300E ventilation unit fixture.
    coordinator = MagicMock(data={"device": await _vitoair()})

    # Act: Discover the fixture's sensors and binary sensors.
    entities = {
        entity.entity_description.key: entity
        for entity in [
            *_discover_realtime_sensors(coordinator),
            *_discover_binary_sensors(coordinator),
        ]
    }

    # Assert: The air readings carry their units and device classes.
    for feature_name, translation_key, unit, device_class, value in AIR_READINGS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.native_unit_of_measurement == unit
        assert entity.entity_description.device_class == device_class
        assert entity.entity_description.entity_category is None
        assert entity.native_value == value

    # Assert: The exhaust fan details are diagnostic sensors.
    for feature_name, translation_key, value in EXHAUST_FAN_READINGS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.entity_category == "diagnostic"
        assert entity.native_value == value

    # Assert: The bypass mode is a translated enum state.
    bypass_mode = entities["ventilation.bypass.operating.modes.active"]
    assert bypass_mode.entity_description.translation_key == "bypass_mode"
    assert bypass_mode.native_value == "automatic"

    # Assert: The heat exchanger frost protection is a running binary sensor.
    frost = entities["ventilation.heatExchanger.frostprotection.status"]
    assert frost.entity_description.translation_key == "heat_exchanger_frost_protection"
    assert frost.entity_description.device_class == "running"
    assert frost.is_on is False

    # Assert: Installation details, bypass duplicates, and locks create no entity.
    assert not HIDDEN_FEATURES & set(entities)


@pytest.mark.asyncio
async def test_vitoair_temporary_shutdown_is_an_enabled_quick_mode() -> None:
    """Offer the temporary shutdown and its runtime like the other quick modes."""
    # Arrange: Load the Vitoair FS 300E ventilation unit fixture.
    coordinator = MagicMock(data={"device": await _vitoair()})
    feature_prefix = "ventilation.quickmodes.temporaryShutdown"

    # Act: Discover the fixture's switches and numbers.
    switches = {
        entity.entity_description.key: entity
        for entity in _discover_switches(coordinator)
    }
    numbers = {
        entity.entity_description.key: entity
        for entity in _discover_numbers(coordinator)
    }

    # Assert: The quick mode switch is enabled and off.
    shutdown = switches[f"{feature_prefix}.active"]
    assert (
        shutdown.entity_description.translation_key
        == "ventilation_quick_mode_temporary_shutdown"
    )
    assert shutdown.entity_registry_enabled_default is True
    assert shutdown.is_on is False

    # Assert: The runtime is an enabled minute control within its limits.
    runtime = numbers[f"{feature_prefix}.defaultRuntime"]
    assert (
        runtime.entity_description.translation_key
        == "ventilation_quick_mode_temporary_shutdown_runtime"
    )
    assert runtime.entity_registry_enabled_default is True
    assert (runtime.native_min_value, runtime.native_max_value) == (1, 1440)
    assert runtime.native_value == 720
