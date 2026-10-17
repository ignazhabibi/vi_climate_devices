"""Tests for the Viessmann Heat sensor platform."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, Feature, FixtureViClient, GatewayDeviceRefreshResult

from custom_components.vi_climate_devices.const import DOMAIN, IGNORED_FEATURES
from custom_components.vi_climate_devices.sensor import (
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
    ViClimateSensor,
)
from custom_components.vi_climate_devices.utils import is_feature_ignored

FIXTURE_NAMES = FixtureViClient.get_available_fixture_devices()

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

AUTO_DISCOVERED_NON_CUMULATIVE_ENERGY_FEATURES = frozenset(
    {
        "ess.battery.usedAverage.averageUsableSystemEnergy",
        "ess.battery.usedAverage.usableEnergyModuleOne",
        "ess.battery.usedAverage.usableEnergyModuleTwo",
        "ess.battery.usedAverage.usableEnergyModuleThree",
        "ess.battery.usedAverage.usableEnergyModuleFour",
        "ess.battery.usedAverage.usableEnergyModuleFive",
        "ess.battery.usedAverage.usableEnergyModuleSix",
        "heating.compressors.0.heat.production.cooling.week",
        "heating.compressors.0.heat.production.dhw.week",
        "heating.compressors.0.heat.production.heating.week",
        "heating.compressors.0.power.consumption.dhw.week",
        "heating.compressors.0.power.consumption.heating.week",
    }
)

EXPECTED_AUTO_DISCOVERED_ENERGY_FEATURES = {
    "Vitocal200S": frozenset(),
    "Vitocal222S": frozenset(),
    "Vitocal250A": frozenset(),
    "Vitocal333G-with-Vitovent300F": frozenset(
        feature_name
        for feature_name in AUTO_DISCOVERED_NON_CUMULATIVE_ENERGY_FEATURES
        if feature_name.startswith("heating.")
    ),
    "Vitocharge03": (
        AUTO_DISCOVERED_TOTAL_INCREASING_ENERGY_FEATURES
        | frozenset(
            feature_name
            for feature_name in AUTO_DISCOVERED_NON_CUMULATIVE_ENERGY_FEATURES
            if feature_name.startswith("ess.")
        )
    ),
    "Vitodens200W": frozenset(),
    "Vitopure350": frozenset(),
}


async def _setup_integration(hass: HomeAssistant, mock_client):
    """Helper to setup the integration with the provided mock client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "client_id": "123",
            "token": {
                "access_token": "mock_access_token",
                "refresh_token": "mock_refresh_token",
                "expires_at": 3800000000,
                "token_type": "Bearer",
            },
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=mock_client,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            return_value=None,
        ),
        patch("custom_components.vi_climate_devices.HAAuth"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_sensor_values(hass: HomeAssistant, mock_client):
    """Test that sensors are created correctly from the fixture data."""
    # Act: Setup the integration with the global mock_client (Vitocal250A).
    await _setup_integration(hass, mock_client)

    # Assert: Verify a Standard Sensor (Outside Temperature).
    # Fixture value is 11.1 -> State '11.1'.
    outside_temp = hass.states.get("sensor.vitocal250a_outside_temperature")
    assert outside_temp is not None
    assert outside_temp.state == "11.1"
    assert outside_temp.attributes["unit_of_measurement"] == "°C"

    # Assert: Verify a Template/Regex Sensor (Compressor Speed).
    # Checks if regex matches 'heating.compressors.0.speed.current' correctly.
    compressor_speed = hass.states.get("sensor.vitocal250a_compressor_speed")
    assert compressor_speed is not None
    assert compressor_speed.state == "0"
    assert (
        compressor_speed.attributes["friendly_name"] == "Vitocal250A Compressor Speed"
    )

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_current_power_and_heat_sensors(hass: HomeAssistant, mock_client):
    """Expose current power consumption and heat production as kW power sensors."""
    # Act: Set up the integration with the Vitocal250A fixture.
    await _setup_integration(hass, mock_client)

    # Assert: Both features are defined power sensors with a kW unit.
    for entity_id, friendly_name in (
        (
            "sensor.vitocal250a_current_power_consumption",
            "Vitocal250A Current Power Consumption",
        ),
        (
            "sensor.vitocal250a_current_heat_production",
            "Vitocal250A Current Heat Production",
        ),
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "0"
        assert state.attributes["friendly_name"] == friendly_name
        assert state.attributes["unit_of_measurement"] == "kW"
        assert state.attributes["device_class"] == "power"
        assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT

    # Assert: Their status sub-features do not create diagnostic sensors.
    sensor_feature_names = {
        state.attributes.get("viessmann_feature_name")
        for state in hass.states.async_all("sensor")
    }
    assert "heating.power.consumption.current.status" not in sensor_feature_names
    assert "heating.heat.production.current.status" not in sensor_feature_names

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_no_duplicate_entity_creation(hass: HomeAssistant, mock_client):
    """Ensure entities defined in SENSOR_TYPES or SENSOR_TEMPLATES are not also created as generic fallback sensors."""
    await _setup_integration(hass, mock_client)

    # Assert: Verify duplicate prevention for Defined Features.
    # The specific entity 'outside_temperature' should exist, but the generic fallback 'heating_sensors_...' should not.
    assert hass.states.get("sensor.vitocal250a_outside_temperature") is not None
    assert hass.states.get("sensor.vitocal250a_sensors_temperature_outside") is None

    # Assert: Verify duplicate prevention for Template Features.
    # The template entity 'compressor_speed' should exist, but the generic fallback 'heating_compressors_...' should not.
    assert hass.states.get("sensor.vitocal250a_compressor_speed") is not None
    assert (
        hass.states.get("sensor.vitocal250a_heating_compressors_0_speed_current")
        is None
    )

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_sensor_feature_discovered_after_setup_is_added_once(
    hass: HomeAssistant, mock_client
) -> None:
    """Test a new sensor feature is added dynamically without duplicates."""
    # Arrange: Set up the integration with the original fixture feature set.
    await _setup_integration(hass, mock_client)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data
    device_key, device = next(iter(coordinator.data.items()))
    feature = Feature(
        name="custom.dynamic.temperature",
        value=18.5,
        unit="celsius",
        is_enabled=True,
        is_ready=True,
    )
    coordinator.data = {
        device_key: dataclasses.replace(device, features=[*device.features, feature])
    }

    # Act: Publish the updated device twice through the coordinator seam.
    coordinator.async_update_listeners()
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    # Assert: One fallback sensor appears for the newly exposed feature.
    registry = er.async_get(hass)
    unique_id = f"{device.gateway_serial}-{device.id}-{feature.name}"
    entries = [
        item
        for item in registry.entities.values()
        if item.platform == DOMAIN and item.unique_id == unique_id
    ]
    assert len(entries) == 1
    state = hass.states.get(entries[0].entity_id)
    assert state is not None
    assert state.state == "18.5"

    # Cleanup: Unload the integration to stop the coordinator listener.
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


DAILY_ENERGY_FEATURES = (
    "heating.heat.production.summary.cooling.currentDay",
    "heating.heat.production.summary.dhw.currentDay",
    "heating.heat.production.summary.heating.currentDay",
    "heating.power.consumption.dhw.currentDay",
    "heating.power.consumption.heating.currentDay",
)


@pytest.mark.parametrize(
    ("device_name", "expected_values"),
    [
        pytest.param(
            "Vitocal250A",
            {
                "heating.heat.production.summary.cooling.currentDay": 0.0,
                "heating.heat.production.summary.dhw.currentDay": 6.3,
                "heating.heat.production.summary.heating.currentDay": 25.7,
                "heating.power.consumption.dhw.currentDay": 1.8,
                "heating.power.consumption.heating.currentDay": 4.5,
            },
            id="e3-heat-pump",
        ),
        pytest.param(
            "Vitocal222S",
            {
                "heating.heat.production.summary.cooling.currentDay": 0.0,
                "heating.heat.production.summary.dhw.currentDay": 6.8,
                "heating.heat.production.summary.heating.currentDay": 13.1,
                "heating.power.consumption.dhw.currentDay": 0.0,
                "heating.power.consumption.heating.currentDay": 0.0,
            },
            id="e3-split-heat-pump",
        ),
        pytest.param(
            "Vitodens200W",
            {
                "heating.heat.production.summary.dhw.currentDay": 1.0,
                "heating.heat.production.summary.heating.currentDay": 26.0,
                "heating.power.consumption.dhw.currentDay": 0.0,
                "heating.power.consumption.heating.currentDay": 0.4,
            },
            id="gas-boiler",
        ),
    ],
)
@pytest.mark.asyncio
async def test_daily_energy_sensors(
    hass: HomeAssistant, device_name: str, expected_values: dict[str, float]
):
    """Expose daily energy counters next to the yearly counters."""
    # Arrange: Load the real device fixture.
    mock_client = FixtureViClient(device_name)
    installations = await mock_client.get_installations()
    device = (await mock_client.get_full_installation_status(installations[0].id))[0]

    # Act: Discover the fixture through the Home Assistant integration.
    await _setup_integration(hass, mock_client)
    registry = er.async_get(hass)

    # Assert: Every daily feature the device reports is a resetting kWh counter.
    for feature_name in DAILY_ENERGY_FEATURES:
        unique_id = f"{device.gateway_serial}-{device.id}-{feature_name}"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if feature_name not in expected_values:
            assert entity_id is None
            continue
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert float(state.state) == expected_values[feature_name]
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["device_class"] == "energy"
        assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING

    # Assert: Lagging daily values stay hidden.
    sensor_feature_names = {
        state.attributes.get("viessmann_feature_name")
        for state in hass.states.async_all("sensor")
    }
    assert "heating.power.consumption.total.currentDay" not in sensor_feature_names
    assert not {
        name
        for name in sensor_feature_names
        if name and name.startswith("heating.power.consumption.summary.")
    }

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_auto_discovery_unit_mapping(hass: HomeAssistant, mock_client):
    """Test that auto-discovered sensors get correct unit mapping based on feature.unit."""
    # Arrange: Create a mock device with features that have specific units but are NOT in SENSOR_TYPES.

    # Create Features with various units
    feat_celsius = Feature(
        name="test.unknown.temp",
        value=20.5,
        is_enabled=True,
        is_ready=True,
        unit="celsius",
    )

    feat_bar = Feature(
        name="test.unknown.pressure",
        value=1.5,
        is_enabled=True,
        is_ready=True,
        unit="bar",
    )

    feat_energy = Feature(
        name="test.unknown.energy",
        value=100.0,
        is_enabled=True,
        is_ready=True,
        unit="kilowattHour",
    )

    feat_watthour = Feature(
        name="test.unknown.watthour",
        value=500.0,
        is_enabled=True,
        is_ready=True,
        unit="wattHour",
    )

    feat_ampere = Feature(
        name="test.unknown.ampere",
        value=5.0,
        is_enabled=True,
        is_ready=True,
        unit="ampere",
    )

    feat_flow = Feature(
        name="test.unknown.flow",
        value=500,
        is_enabled=True,
        is_ready=True,
        unit="liter/hour",
    )

    # Create Device
    mock_device = Device(
        id="0",
        gateway_serial="mock_gateway",
        installation_id="123",
        features=[
            feat_celsius,
            feat_bar,
            feat_energy,
            feat_watthour,
            feat_ampere,
            feat_flow,
        ],
        model_id="MockDevice",
        device_type="heating",
        status="online",
    )

    # Arrange: Patch the mock client to return our custom device.

    with (
        patch.object(
            mock_client, "get_full_installation_status", return_value=[mock_device]
        ),
        patch.object(
            mock_client,
            "refresh_gateway_devices",
            return_value=GatewayDeviceRefreshResult([mock_device], {}),
        ),
    ):
        # Act
        await _setup_integration(hass, mock_client)

        registry = er.async_get(hass)

        # Assert: Check Celsius Mapping via Registry
        entry_temp = registry.async_get("sensor.mockdevice_test_unknown_temp")
        assert entry_temp is not None
        # MockDevice is not in TESTED_DEVICES, so entities are enabled by default
        assert entry_temp.disabled_by is None
        assert entry_temp.original_device_class == "temperature"

        # Assert: Check Bar Mapping
        entry_pressure = registry.async_get("sensor.mockdevice_test_unknown_pressure")
        assert entry_pressure is not None
        assert entry_pressure.disabled_by is None
        assert entry_pressure.original_device_class == "pressure"

        # Assert: Check Energy Mapping
        entry_energy = registry.async_get("sensor.mockdevice_test_unknown_energy")
        assert entry_energy is not None
        assert entry_energy.disabled_by is None
        assert entry_energy.original_device_class == "energy"
        energy_state = hass.states.get(entry_energy.entity_id)
        assert energy_state is not None
        assert "state_class" not in energy_state.attributes

        # Assert: Check WattHour Mapping
        entry_wh = registry.async_get("sensor.mockdevice_test_unknown_watthour")
        assert entry_wh is not None
        assert entry_wh.original_device_class == "energy"
        assert entry_wh.unit_of_measurement == "Wh"
        watt_hour_state = hass.states.get(entry_wh.entity_id)
        assert watt_hour_state is not None
        assert "state_class" not in watt_hour_state.attributes

        # Assert: Check Ampere Mapping
        entry_amp = registry.async_get("sensor.mockdevice_test_unknown_ampere")
        assert entry_amp is not None
        assert entry_amp.original_device_class == "current"
        assert entry_amp.unit_of_measurement == "A"

        # Assert: Check Flow Mapping
        entry_flow = registry.async_get("sensor.mockdevice_test_unknown_flow")
        assert entry_flow is not None
        assert entry_flow.disabled_by is None
        # Flow doesn't have a default device class in our auto-discovery yet

        # Cleanup: Unload the integration to prevent thread leaks.
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_decreasing_unknown_energy_is_not_a_counter(
    hass: HomeAssistant, mock_client
):
    """Test a decreasing unknown energy value stays non-cumulative."""
    # Arrange: Build two snapshots whose unknown energy value decreases.
    feature = Feature(
        name="test.unknown.energy",
        value=100.0,
        is_enabled=True,
        is_ready=True,
        unit="kilowattHour",
    )
    device = Device(
        id="0",
        gateway_serial="mock_gateway",
        installation_id="123",
        features=[feature],
        model_id="MockDevice",
        device_type="heating",
        status="online",
    )
    decreased_device = dataclasses.replace(
        device, features=[dataclasses.replace(feature, value=90.0)]
    )

    with (
        patch.object(
            mock_client, "get_full_installation_status", return_value=[device]
        ),
        patch.object(
            mock_client,
            "refresh_gateway_devices",
            return_value=GatewayDeviceRefreshResult([device], {}),
        ) as refresh_gateway_devices,
    ):
        await _setup_integration(hass, mock_client)
        registry = er.async_get(hass)
        registry_entry = registry.async_get("sensor.mockdevice_test_unknown_energy")
        assert registry_entry is not None

        # Act: Refresh after the absolute energy value decreases.
        refresh_gateway_devices.return_value = GatewayDeviceRefreshResult(
            [decreased_device], {}
        )
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        await entry.runtime_data.async_request_refresh()
        await hass.async_block_till_done()

        # Assert: The new value is exposed without resettable-counter semantics.
        state = hass.states.get(registry_entry.entity_id)
        assert state is not None
        assert state.state == "90.0"
        assert "state_class" not in state.attributes

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize("device_name", FIXTURE_NAMES)
@pytest.mark.asyncio
async def test_fixture_auto_discovered_energy_state_classes(
    hass: HomeAssistant, device_name: str
):
    """Test every fixture's auto-discovered energy sensor classification."""
    # Arrange: Load every feature from the selected real device fixture.
    mock_client = FixtureViClient(device_name)
    installations = await mock_client.get_installations()
    devices = await mock_client.get_full_installation_status(
        installations[0].id, only_enabled=False
    )
    expected_feature_names = EXPECTED_AUTO_DISCOVERED_ENERGY_FEATURES[device_name]
    fixture_features = {
        feature.name: (device, feature)
        for device in devices
        for feature in device.features
        if feature.unit in {"kilowattHour", "wattHour"}
        and feature.name not in SENSOR_TYPES
        and not is_feature_ignored(feature.name, IGNORED_FEATURES)
    }

    # Act: Discover the fixture through the Home Assistant integration.
    await _setup_integration(hass, mock_client)
    registry = er.async_get(hass)

    # Assert: The audit stays exhaustive as fixtures gain energy properties.
    assert fixture_features.keys() == expected_feature_names
    for feature_name, (device, feature) in fixture_features.items():
        unique_id = f"{device.gateway_serial}-{device.id}-{feature_name}"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.attributes["device_class"] == "energy"
        assert state.attributes["unit_of_measurement"] == (
            "kWh" if feature.unit == "kilowattHour" else "Wh"
        )
        expected_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if feature_name in AUTO_DISCOVERED_TOTAL_INCREASING_ENERGY_FEATURES
            else None
        )
        assert state.attributes.get("state_class") == expected_state_class

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("device_name", "feature_name"),
    [
        ("Vitocal200S", "heating.compressors.0.power"),
        (
            "Vitocal333G-with-Vitovent300F",
            "heating.compressors.0.power.consumption.current",
        ),
        ("Vitocharge03", "photovoltaic.production.current"),
    ],
)
@pytest.mark.asyncio
async def test_fixture_auto_discovered_kilowatt_sensors(
    hass: HomeAssistant, device_name: str, feature_name: str
):
    """Map auto-discovered kilowatt features to kW power measurements."""
    # Arrange: Locate the undefined kilowatt feature in the real device fixture.
    mock_client = FixtureViClient(device_name)
    installations = await mock_client.get_installations()
    devices = await mock_client.get_full_installation_status(installations[0].id)
    device = next(
        device for device in devices if device.get_feature(feature_name) is not None
    )
    assert feature_name not in SENSOR_TYPES

    # Act: Discover the fixture through the Home Assistant integration.
    await _setup_integration(hass, mock_client)

    # Assert: The feature becomes a kW power sensor with a measurement state class.
    unique_id = f"{device.gateway_serial}-{device.id}-{feature_name}"
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["device_class"] == "power"
    assert state.attributes["unit_of_measurement"] == "kW"
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_sensor_ignores_generic_on_off_string(hass: HomeAssistant, mock_client):
    """Test that a feature with 'on'/'off' string value is NOT created as a sensor.

    Using real fixture key: heating.dhw.status (value: "on")
    """
    # Arrange: Configure the integration with the mock client fixture.
    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=mock_client,
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.async_get_config_entry_implementation",
            return_value=MagicMock(),
        ),
        patch(
            "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session.async_ensure_token_valid",
            return_value=None,
        ),
        patch("custom_components.vi_climate_devices.HAAuth"),
    ):
        entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "1", "token": "x"})
        entry.add_to_hass(hass)

        # Act: Initialize the integration to trigger discovery.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Sensor should NOT exist for 'heating.dhw.status'.
        # The feature returns "on", so it should be picked up by binary_sensor, NOT sensor.
        sensor_entity = hass.states.get("sensor.vitocal250a_heating_dhw_status")
        assert sensor_entity is None

        # Cleanup: Unload the integration to prevent thread leaks.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("device_name", "expected_states"),
    [
        pytest.param(
            "Vitocal250A",
            {
                "heating.circuits.0.operating.programs.active": "normal_heating",
                "heating.noise.reduction.operating.programs.active": (
                    "slightly_reduced"
                ),
                "heating.valves.fourThreeWay.position": "climat_circuit_two_defrost",
            },
            id="e3-heat-pump",
        ),
        pytest.param(
            "Vitodens200W",
            {"heating.circuits.0.operating.programs.active": "normal"},
            id="legacy-gas-boiler",
        ),
    ],
)
@pytest.mark.asyncio
async def test_enum_sensors_report_translated_option_keys(
    hass: HomeAssistant, device_name: str, expected_states: dict[str, str]
):
    """Report program and valve values as lowercase enum option keys."""
    # Arrange: Load the real device fixture.
    mock_client = FixtureViClient(device_name)
    installations = await mock_client.get_installations()
    device = (await mock_client.get_full_installation_status(installations[0].id))[0]

    # Act: Discover the fixture through the Home Assistant integration.
    await _setup_integration(hass, mock_client)
    registry = er.async_get(hass)

    # Assert: The feature-based unique ID is kept and the state is an option key.
    for feature_name, expected_state in expected_states.items():
        unique_id = f"{device.gateway_serial}-{device.id}-{feature_name}"
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == expected_state
        assert state.attributes["device_class"] == "enum"
        assert expected_state in state.attributes["options"]

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_unknown_enum_value_is_unknown_and_logged_once(
    hass: HomeAssistant, mock_client, caplog: pytest.LogCaptureFixture
):
    """Keep the entity working when the API reports an unlisted value."""
    # Arrange: Set up the integration, then report an unlisted program twice.
    await _setup_integration(hass, mock_client)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = entry.runtime_data
    device_key, device = next(iter(coordinator.data.items()))
    feature_name = "heating.circuits.0.operating.programs.active"
    coordinator.data = {
        device_key: dataclasses.replace(
            device,
            features=[
                dataclasses.replace(feature, value="futureProgram")
                if feature.name == feature_name
                else feature
                for feature in device.features
            ],
        )
    }

    # Act: Publish the unknown value in two updates.
    coordinator.async_update_listeners()
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    # Assert: The state is unknown and the raw value is logged once.
    registry = er.async_get(hass)
    unique_id = f"{device.gateway_serial}-{device.id}-{feature_name}"
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"
    warnings = [
        record
        for record in caplog.records
        if "Unknown value futureProgram" in record.getMessage()
    ]
    assert len(warnings) == 1

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_enum_sensor_without_string_value_is_unknown(
    caplog: pytest.LogCaptureFixture,
):
    """Report unknown for a malformed or missing enum feature without logging."""
    # Arrange: Build the program sensor from the fixture, with a malformed value.
    device = (
        await FixtureViClient("Vitocal250A").get_full_installation_status("99999")
    )[0]
    feature_name = "heating.circuits.0.operating.programs.active"
    device = dataclasses.replace(
        device,
        features=[
            dataclasses.replace(feature, value=5)
            if feature.name == feature_name
            else feature
            for feature in device.features
        ],
    )
    map_key = f"{device.gateway_serial}_{device.id}"
    coordinator = MagicMock(data={map_key: device})
    description = next(
        template.description
        for template in SENSOR_TEMPLATES
        if template.pattern.match(feature_name)
    )
    sensor = ViClimateSensor(coordinator, map_key, feature_name, description)

    # Act and assert: A non-string value is unknown and not logged.
    assert sensor.native_value is None
    assert "Unknown value" not in caplog.text

    # Act and assert: A device missing after refresh is unknown as well.
    coordinator.data = {}
    assert sensor.native_value is None


REFRIGERANT_CIRCUIT_SENSORS = {
    "heating.sensors.valve.0.expansion.target": (
        "Vitocal250A Expansion Valve 1 Opening",
        "50",
        "%",
    ),
    "heating.sensors.valve.1.expansion.target": (
        "Vitocal250A Expansion Valve 2 Opening",
        "0",
        "%",
    ),
    "heating.inverters.0.sensors.power.output": (
        "Vitocal250A Inverter Power",
        "0",
        "W",
    ),
    "heating.inverters.0.sensors.power.current": (
        "Vitocal250A Inverter Current",
        "0",
        "A",
    ),
    "heating.inverters.0.sensors.temperature.powerModule": (
        "Vitocal250A Inverter Temperature",
        "25.7",
        "°C",
    ),
}


@pytest.mark.asyncio
async def test_refrigerant_circuit_sensors_are_defined_on_tested_devices(
    hass: HomeAssistant, mock_client
):
    """Keep valve and inverter sensors enabled and named on tested devices."""
    # Arrange: Treat the fixture as a tested device and keep a renamed entity ID.
    device = (await mock_client.get_full_installation_status("99999"))[0]
    unique_id_prefix = f"{device.gateway_serial}-{device.id}"
    registry = er.async_get(hass)
    renamed = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{unique_id_prefix}-heating.inverters.0.sensors.power.output",
        suggested_object_id="vitocal250a_aktueller_stromverbrauch_0",
    )

    # Act: Set up the integration.
    with patch(
        "custom_components.vi_climate_devices.sensor.TESTED_DEVICES",
        [device.model_id],
    ):
        await _setup_integration(hass, mock_client)

    # Assert: Each sensor keeps its feature-based unique ID and is enabled.
    for feature_name, (name, value, unit) in REFRIGERANT_CIRCUIT_SENSORS.items():
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{unique_id_prefix}-{feature_name}"
        )
        assert entity_id is not None
        registry_entry = registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.disabled_by is None
        assert registry_entry.entity_category == "diagnostic"
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.attributes["friendly_name"] == name
        assert state.state == value
        assert state.attributes["unit_of_measurement"] == unit

    # Assert: An existing entity ID survives the new name.
    assert renamed.entity_id == "sensor.vitocal250a_aktueller_stromverbrauch_0"
    assert hass.states.get(renamed.entity_id) is not None
