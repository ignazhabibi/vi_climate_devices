"""Tests for ViClimate water heater entities."""

from unittest.mock import MagicMock, AsyncMock

import pytest
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature,
    ATTR_OPERATION_MODE,
)
from homeassistant.core import HomeAssistant

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator
from custom_components.vi_climate_devices.water_heater import (
    STATE_ECO,
    STATE_OFF,
    STATE_PERFORMANCE,
    STATE_GAS,
)
from vi_api_client import Feature, MockViClient


@pytest.fixture
def mock_water_heater_client():
    """Return a mocked client with water heater features."""
    client = MockViClient("Vitocal252")

    # 1. Target Temp Feature
    f_target = MagicMock()
    f_target.name = "heating.dhw.temperature.main"
    f_target.is_enabled = True
    f_target.properties = {"value": {"value": 50.0}}
    f_target.commands = {
        "setTargetTemperature": MagicMock(
            name="setTargetTemperature",
            is_executable=True,
            params={
                "temperature": {
                    "required": True,
                    "constraints": {"min": 10, "max": 60, "step": 1.0},
                }
            },
        )
    }

    # 2. Current Temp Feature
    f_current = MagicMock()
    f_current.name = "heating.dhw.sensors.temperature.hotWaterStorage"
    f_current.is_enabled = True
    f_current.properties = {"value": {"value": 48.5}}

    # 3. Mode Feature
    f_mode = MagicMock()
    f_mode.name = "heating.dhw.operating.modes.active"
    f_mode.is_enabled = True
    f_mode.properties = {"value": {"value": "eco"}}
    f_mode.commands = {
        "setMode": MagicMock(
            name="setMode",
            is_executable=True,
            params={
                "mode": {
                    "required": True,
                    "constraints": {"enum": ["off", "eco", "comfort", "standard"]},
                }
            },
        )
    }

    client.features = [f_target, f_current, f_mode]
    client.features_flat = [f_target, f_current, f_mode]
    return client


@pytest.mark.asyncio
async def test_water_heater_creation(hass: HomeAssistant, mock_water_heater_client):
    """Test water heater entity is created and has correct attributes."""
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # We need to manually simulate the coordinator setup
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_water_heater_client)

    # Mock successful update by just setting data directly
    mock_device = MagicMock()
    mock_device.gateway_serial = "1234567890"
    mock_device.id = "0"
    mock_device.model_id = "Vitocal252"
    mock_device.features = mock_water_heater_client.features
    mock_device.features_flat = mock_water_heater_client.features_flat

    coordinator.data = {"0": mock_device}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator}

    # Manually load the platform
    from custom_components.vi_climate_devices import water_heater

    async_add_entities = MagicMock()
    await water_heater.async_setup_entry(hass, entry, async_add_entities)

    # Check if entity was added
    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 1
    entity = entities[0]

    # Verify State Attributes
    assert entity.current_temperature == 48.5
    assert entity.target_temperature == 50.0
    assert entity.current_operation == STATE_ECO
    assert entity.min_temp == 10
    assert entity.max_temp == 60
    assert entity.operation_list == [STATE_OFF, STATE_ECO, STATE_PERFORMANCE, STATE_GAS]

    # Verify supported features
    assert entity.supported_features & WaterHeaterEntityFeature.TARGET_TEMPERATURE
    assert entity.supported_features & WaterHeaterEntityFeature.OPERATION_MODE


@pytest.mark.asyncio
async def test_water_heater_commands(hass: HomeAssistant, mock_water_heater_client):
    """Test setting temperature and mode."""
    entry = MagicMock()
    entry.entry_id = "test_entry"

    coordinator = ViClimateDataUpdateCoordinator(hass, mock_water_heater_client)

    # Mock successful update by just setting data directly
    mock_device = MagicMock()
    mock_device.gateway_serial = "1234567890"
    mock_device.id = "0"
    mock_device.model_id = "Vitocal252"
    mock_device.features = mock_water_heater_client.features
    mock_device.features_flat = mock_water_heater_client.features_flat

    coordinator.data = {"0": mock_device}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator}

    from custom_components.vi_climate_devices import water_heater

    async_add_entities = MagicMock()
    await water_heater.async_setup_entry(hass, entry, async_add_entities)
    entity = async_add_entities.call_args[0][0][0]

    # Mock execute_command on coordinator client
    coordinator.client.execute_command = AsyncMock()

    # Entity is not fully registered, so mock async_write_ha_state
    entity.async_write_ha_state = MagicMock()

    # Test Set Temperature
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 55.0})

    coordinator.client.execute_command.assert_called_with(
        entity._get_feature("heating.dhw.temperature.main"),
        "setTargetTemperature",
        {"temperature": 55.0},
    )
    # Optimistic State Check
    assert entity.target_temperature == 55.0

    # Test Set Mode (now uses HA states)
    await entity.async_set_operation_mode(STATE_PERFORMANCE)

    # Should send Viessmann mode "comfort" to API
    coordinator.client.execute_command.assert_called_with(
        entity._get_feature("heating.dhw.operating.modes.active"),
        "setMode",
        {"mode": "comfort"},
    )
    assert entity.current_operation == STATE_PERFORMANCE
