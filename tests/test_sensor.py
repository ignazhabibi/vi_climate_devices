"""Tests for the Viessmann Heat sensor platform."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, Feature
from vi_api_client.mock_client import MockViClient

from custom_components.vi_climate_devices.const import DOMAIN, IGNORED_FEATURES
from custom_components.vi_climate_devices.sensor import SENSOR_TYPES
from custom_components.vi_climate_devices.utils import is_feature_ignored

FIXTURE_NAMES = MockViClient.get_available_mock_devices()

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
    # Fixture value is 12.2 -> State '12.2'.
    outside_temp = hass.states.get("sensor.vitocal250a_outside_temperature")
    assert outside_temp is not None
    assert outside_temp.state == "12.2"
    assert outside_temp.attributes["unit_of_measurement"] == "°C"

    # Assert: Verify a Template/Regex Sensor (Compressor Speed).
    # Checks if regex matches 'heating.compressors.0.speed.current' correctly.
    compressor_speed = hass.states.get("sensor.vitocal250a_compressor_0_speed")
    assert compressor_speed is not None
    assert compressor_speed.state == "0"
    assert (
        compressor_speed.attributes["friendly_name"] == "Vitocal250A Compressor 0 Speed"
    )

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
    # The template entity 'compressor_0_speed' should exist, but the generic fallback 'heating_compressors_...' should not.
    assert hass.states.get("sensor.vitocal250a_compressor_0_speed") is not None
    assert (
        hass.states.get("sensor.vitocal250a_heating_compressors_0_speed_current")
        is None
    )

    # Cleanup: Unload the integration to prevent thread leaks.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_removed_today_energy_sensors_are_not_created(
    hass: HomeAssistant, mock_client
):
    """Test removed today energy sensors are no longer created."""
    # Arrange: Set up the integration with the Vitocal250A fixture.
    await _setup_integration(hass, mock_client)

    # Assert: The removed today sensors are absent after setup.
    assert hass.states.get("sensor.vitocal250a_dhw_consumption_today") is None
    assert hass.states.get("sensor.vitocal250a_heating_consumption_today") is None
    assert hass.states.get("sensor.vitocal250a_total_consumption_today") is None
    assert hass.states.get("sensor.vitocal250a_dhw_production_today") is None
    assert hass.states.get("sensor.vitocal250a_heating_production_today") is None
    assert hass.states.get("sensor.vitocal250a_production_dhw_current_day") is None
    assert hass.states.get("sensor.vitocal250a_production_heating_current_day") is None

    # Cleanup: Unload the integration to prevent thread leaks.
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
        patch.object(mock_client, "update_device", return_value=mock_device),
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
            mock_client, "update_device", return_value=device
        ) as update_device,
    ):
        await _setup_integration(hass, mock_client)
        registry = er.async_get(hass)
        registry_entry = registry.async_get("sensor.mockdevice_test_unknown_energy")
        assert registry_entry is not None

        # Act: Refresh after the absolute energy value decreases.
        update_device.return_value = decreased_device
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
    mock_client = MockViClient(device_name=device_name, auth=None)
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
