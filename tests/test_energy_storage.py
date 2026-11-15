"""Tests for the defined entities of energy storage systems."""

import dataclasses
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from vi_api_client import Feature, FixtureViClient

from custom_components.vi_climate_devices.select import _discover_selects
from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors

ENERGY_STORAGE_SENSORS = {
    "ess.power": ("battery_power", "W", "power", SensorStateClass.MEASUREMENT),
    "ess.sensors.temperature.ambient": (
        "battery_ambient_temperature",
        "°C",
        "temperature",
        SensorStateClass.MEASUREMENT,
    ),
    "ess.stateOfCharge": (
        "battery_state_of_charge",
        "%",
        "battery",
        SensorStateClass.MEASUREMENT,
    ),
    "ess.transfer.charge.cumulated.lifeCycle": (
        "battery_charge_total",
        "Wh",
        "energy",
        SensorStateClass.TOTAL_INCREASING,
    ),
    "ess.transfer.discharge.cumulated.lifeCycle": (
        "battery_discharge_total",
        "Wh",
        "energy",
        SensorStateClass.TOTAL_INCREASING,
    ),
    "pcc.transfer.consumption.total": (
        "grid_import_total",
        "Wh",
        "energy",
        SensorStateClass.TOTAL_INCREASING,
    ),
    "pcc.transfer.feedIn.total": (
        "grid_export_total",
        "Wh",
        "energy",
        SensorStateClass.TOTAL_INCREASING,
    ),
    "pcc.transfer.power.exchange": (
        "grid_power",
        "W",
        "power",
        SensorStateClass.MEASUREMENT,
    ),
    "photovoltaic.production.cumulated.lifeCycle": (
        "pv_production_total",
        "Wh",
        "energy",
        SensorStateClass.TOTAL_INCREASING,
    ),
    "photovoltaic.production.current": (
        "pv_power",
        "kW",
        "power",
        SensorStateClass.MEASUREMENT,
    ),
}


@pytest.mark.parametrize("device_name", ["Vitocharge03", "VitochargeEvolution08"])
@pytest.mark.asyncio
async def test_energy_storage_systems_define_battery_grid_and_pv(
    device_name: str,
) -> None:
    """Name the battery, grid, and PV values the energy dashboard needs."""
    # Arrange: Load the real energy storage system fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    descriptions = {
        entity.entity_description.key: entity.entity_description
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: Each value is a defined sensor with unit and classes.
    for feature_name, (
        translation_key,
        unit,
        device_class,
        state_class,
    ) in ENERGY_STORAGE_SENSORS.items():
        description = descriptions[feature_name]
        assert description.translation_key == translation_key
        assert description.native_unit_of_measurement == unit
        assert description.device_class == device_class
        assert description.state_class == state_class
        assert description.entity_category is None


# Feature, translation key, unit, device class, and value of the Evolution 08
# battery, inverter, grid, and PV readings.
EVOLUTION_08_SENSORS = (
    (
        "ess.battery.usedAverage.averageUsableSystemEnergy",
        "battery_usable_energy",
        "Wh",
        "energy_storage",
        15000,
    ),
    ("ess.inverter.ac.power.activePower", "ess_inverter_power", "W", "power", 1526),
    (
        "ess.inverter.ac.power.reactivePower",
        "ess_inverter_reactive_power",
        "var",
        "reactive_power",
        -616,
    ),
    (
        "ess.transfer.charge.cumulated.currentDay",
        "battery_charge_current_day",
        "Wh",
        "energy",
        11690,
    ),
    (
        "ess.transfer.discharge.cumulated.currentYear",
        "battery_discharge_current_year",
        "Wh",
        "energy",
        672957,
    ),
    (
        "photovoltaic.production.cumulated.currentDay",
        "pv_production_current_day",
        "Wh",
        "energy",
        14607,
    ),
    ("pcc.ac.active.current.total", "grid_current", "A", "current", 4),
    ("pcc.ac.active.power.phaseOne", "grid_power_phase_1", "W", "power", -165),
    (
        "pcc.ac.reactive.power.phaseThree",
        "grid_reactive_power_phase_3",
        "var",
        "reactive_power",
        11,
    ),
)

# Identifiers, static details, and periods the lifetime totals cover.
EVOLUTION_08_HIDDEN_FEATURES = frozenset(
    {
        "device.serial.internalComponents.vinList",
        "ess.battery.usedAverage.usableEnergyModuleOne",
        "ess.configuration.systemType",
        "ess.power.nominal.inverter",
        "ess.transfer.charge.cumulated.currentWeek",
        "ess.version.hardware.family",
        "pcc.state.gridCode",
        "photovoltaic.installedPeakPower",
        "photovoltaic.production.cumulated.currentMonth",
        "photovoltaic.string.0.name",
        "photovoltaic.string.enabled",
        "tcu.ethernet.0.config.mode",
    }
)


@pytest.mark.asyncio
async def test_vitocharge_evolution_08_defines_inverter_grid_and_pv_strings() -> None:
    """Name the inverter, phase, period, and PV string readings."""
    # Arrange: Load the Vitocharge Evolution 08 fixture.
    device = (
        await FixtureViClient("VitochargeEvolution08").get_full_installation_status(
            "99999"
        )
    )[0]
    coordinator = MagicMock(data={"device": device})

    # Act: Discover the fixture's sensors.
    entities = {
        entity.entity_description.key: entity
        for entity in _discover_realtime_sensors(coordinator)
    }

    # Assert: The readings carry their units and device classes.
    for (
        feature_name,
        translation_key,
        unit,
        device_class,
        value,
    ) in EVOLUTION_08_SENSORS:
        entity = entities[feature_name]
        assert entity.entity_description.translation_key == translation_key
        assert entity.entity_description.native_unit_of_measurement == unit
        assert entity.entity_description.device_class == device_class
        assert entity.native_value == value

    # Assert: The battery and PV states are translated enum states.
    assert entities["ess.operationState"].native_value == "discharge"
    assert entities["photovoltaic.status.status"].native_value == "ready"

    # Assert: The PV strings are named after the string names of the device.
    for feature_name, name, unit in (
        ("photovoltaic.string.0.power", "B", "kW"),
        ("photovoltaic.string.2.voltage", "A", "V"),
    ):
        entity = entities[feature_name]
        assert entity.translation_placeholders == {"name": name}
        assert entity.entity_description.native_unit_of_measurement == unit

    # Assert: Identifiers, static details, and covered periods create no sensor.
    assert not EVOLUTION_08_HIDDEN_FEATURES & set(entities)


def test_pv_string_without_a_name_is_named_by_its_index() -> None:
    """Fall back to the 1-based index when the device names no string."""
    # Arrange: Build a device whose PV string reports no name.
    feature = Feature(
        name="photovoltaic.string.1.voltage",
        value=200,
        unit="volt",
        is_enabled=True,
        is_ready=True,
    )
    device = MagicMock(features=[feature])
    device.get_feature.side_effect = lambda name: (
        feature if name == feature.name else None
    )

    # Act: Discover the device's sensors.
    entities = _discover_realtime_sensors(MagicMock(data={"device": device}))

    # Assert: The string is named after its index.
    assert [entity.translation_placeholders for entity in entities] == [{"name": "2"}]


@pytest.mark.parametrize(
    ("api_value", "state"),
    [
        pytest.param("safetyCheck", "safety_check", id="camel-case"),
        pytest.param("nothing", None, id="placeholder"),
    ],
)
@pytest.mark.asyncio
async def test_battery_operation_state_maps_api_values(
    api_value: str, state: str | None
) -> None:
    """Translate camelCase battery states and hide placeholders."""
    # Arrange: Report a battery state on the Evolution 08 fixture.
    device = (
        await FixtureViClient("VitochargeEvolution08").get_full_installation_status(
            "99999"
        )
    )[0]
    features = [
        dataclasses.replace(feature, value=api_value)
        if feature.name == "ess.operationState"
        else feature
        for feature in device.features
    ]
    device = dataclasses.replace(device, features=features)

    # Act: Discover the fixture's battery state sensor.
    entity = next(
        entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
        if entity.entity_description.key == "ess.operationState"
    )

    # Assert: The state is the option key, or unknown for a placeholder.
    assert entity.native_value == state


@pytest.mark.asyncio
async def test_battery_control_mode_is_a_translated_select() -> None:
    """Offer the battery control mode with translated options, enabled."""
    # Arrange: Load the Vitocharge Evolution 08 fixture.
    device = (
        await FixtureViClient("VitochargeEvolution08").get_full_installation_status(
            "99999"
        )
    )[0]

    # Act: Discover the fixture's selects.
    selects = {
        entity.entity_description.key: entity
        for entity in _discover_selects(MagicMock(data={"device": device}))
    }

    # Assert: The defined select is enabled with option keys of the API values.
    control_mode = selects["ess.battery.control.mode.active"]
    assert control_mode.entity_description.translation_key == "battery_control_mode"
    assert control_mode.entity_description.entity_category == "config"
    assert control_mode.entity_registry_enabled_default is True
    assert control_mode.options == ["power_control_mode", "nothing", "pcc_control_mode"]
    assert control_mode.current_option == "nothing"
