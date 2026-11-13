"""Tests for the defined entities of energy storage systems."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from vi_api_client import FixtureViClient

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
