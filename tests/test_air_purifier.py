"""Tests for the defined entities of air purifiers."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    _discover_binary_sensors,
)
from custom_components.vi_climate_devices.number import _discover_numbers
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors
from custom_components.vi_climate_devices.switch import _discover_switches

# Feature, translation key, device class, and value of the air readings.
AIR_READINGS = (
    ("ventilation.sensors.airBorneDust.pm1", "pm1", "pm1", 0.3),
    ("ventilation.sensors.airBorneDust.pm2d5", "pm25", "pm25", 0.3),
    ("ventilation.sensors.airBorneDust.pm4", "pm4", "pm4", 0.3),
    ("ventilation.sensors.airBorneDust.pm10", "pm10", "pm10", 0.3),
    ("ventilation.sensors.airQuality", "air_quality_index", None, 22),
    ("ventilation.sensors.volatileOrganicCompounds", "voc_index", None, 68),
    ("ventilation.sensors.humidity.supply", "supply_air_humidity", "humidity", 43),
    (
        "ventilation.sensors.temperature.supply",
        "supply_air_temperature",
        "temperature",
        20.7,
    ),
)

# Feature, translation key, and value of the diagnostic fan and filter sensors.
MAINTENANCE_READINGS = (
    ("ventilation.fan.supply.current", "supply_fan_speed", 1181),
    ("ventilation.fan.supply.target", "supply_fan_target_speed", 1181),
    ("ventilation.fan.supply.runtime", "supply_fan_runtime", 1171),
    ("ventilation.filter.pollution.blocked", "filter_pollution", 5),
    ("ventilation.filter.runtime.operatingHours", "filter_operating_hours", 6994),
    ("ventilation.filter.runtime.overdueHours", "filter_overdue_hours", 0),
    ("ventilation.filter.runtime.remainingHours", "filter_remaining_hours", 1766),
    ("ventilation.operating.state.reason", "ventilation_reason", "standby"),
)

# Feature and translation key of the quick mode runtimes.
QUICK_MODE_RUNTIMES = (
    (
        "ventilation.quickmodes.forcedLevelFour.defaultRuntime",
        "ventilation_quick_mode_forced_level_four_runtime",
    ),
    (
        "ventilation.quickmodes.silent.defaultRuntime",
        "ventilation_quick_mode_silent_runtime",
    ),
)

# Features the fan entity covers, or command availability flags.
HIDDEN_FEATURES = frozenset(
    {
        "ventilation.operating.modes.filterChange.active",
        "ventilation.operating.modes.permanent.active",
        "ventilation.operating.modes.sensorDriven.active",
        "ventilation.operating.modes.ventilation.active",
        "ventilation.operating.programs.active",
        "ventilation.operating.state.demand",
        "ventilation.quickmodes.forcedLevelFour.isCommandExecutable",
        "ventilation.quickmodes.silent.isCommandExecutable",
        "ventilation.quickmodes.standby.active",
    }
)


@pytest.mark.asyncio
async def test_vitopure_350_defines_air_fan_and_filter_entities() -> None:
    """Name the air, fan, and filter readings and the quick mode controls."""
    # Arrange: Load the Vitopure 350 air purifier fixture.
    device = (
        await FixtureViClient("Vitopure350").get_full_installation_status("99999")
    )[0]
    coordinator = MagicMock(data={"device": device})

    # Act: Discover the fixture's sensors, binary sensors, switches, and numbers.
    entities = {
        entity.entity_description.key: entity
        for entity in [
            *_discover_realtime_sensors(coordinator),
            *_discover_binary_sensors(coordinator),
            *_discover_switches(coordinator),
        ]
    }
    numbers = {
        entity.entity_description.key: entity
        for entity in _discover_numbers(coordinator)
    }

    # Assert: The air readings are measurements with their device classes.
    for feature_name, translation_key, device_class, value in AIR_READINGS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.device_class == device_class
        assert entity.entity_description.state_class == SensorStateClass.MEASUREMENT
        assert entity.entity_description.entity_category is None
        assert entity.native_value == value

    # Assert: The fan and filter details are diagnostic sensors.
    for feature_name, translation_key, value in MAINTENANCE_READINGS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.entity_category == "diagnostic"
        assert entity.native_value == value

    # Assert: The filter change is a problem binary sensor.
    filter_change = entities["ventilation.control.filterChange.active"]
    assert filter_change.entity_description.translation_key == "filter_change"
    assert filter_change.entity_description.device_class == "problem"
    assert filter_change.is_on is False

    # Assert: The quick mode runtimes are enabled minute controls within the
    # constraints the API reports.
    for feature_name, translation_key in QUICK_MODE_RUNTIMES:
        runtime = numbers[feature_name]
        assert runtime.entity_description.translation_key == translation_key
        assert runtime.entity_description.native_unit_of_measurement == "min"
        assert runtime.entity_description.device_class == "duration"
        assert runtime.entity_description.entity_category == "config"
        assert runtime.entity_registry_enabled_default is True
        assert (runtime.native_min_value, runtime.native_max_value) == (1, 1440)
        assert runtime.native_step == 1
        assert runtime.native_value == 30

    # Assert: The quick mode switches are enabled.
    for feature_name, translation_key in (
        (
            "ventilation.quickmodes.forcedLevelFour.active",
            "ventilation_quick_mode_forced_level_four",
        ),
        ("ventilation.quickmodes.silent.active", "ventilation_quick_mode_silent"),
    ):
        quick_mode = entities[feature_name]
        assert quick_mode.entity_description.translation_key == translation_key
        assert quick_mode.entity_registry_enabled_default is True
        assert quick_mode.is_on is False

    # Assert: Fan duplicates and command availability flags create no entity.
    assert not HIDDEN_FEATURES & set(entities)


@pytest.mark.parametrize(
    ("device_name", "reason"),
    [
        pytest.param("Vitopure350", "standby", id="standby"),
        pytest.param("VitoairFs300E", "sensor_override", id="camel-case"),
    ],
)
@pytest.mark.asyncio
async def test_ventilation_reason_is_a_translated_enum(
    device_name: str, reason: str
) -> None:
    """Report the ventilation reason as an option key of its API value."""
    # Arrange: Load a ventilation fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's ventilation reason sensor.
    entity = next(
        entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
        if entity.entity_description.key == "ventilation.operating.state.reason"
    )

    # Assert: The reason is a translated enum state.
    assert entity.entity_description.device_class == "enum"
    assert entity.native_value == reason
