"""Tests for ViClimate water heater entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.water_heater import (
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from vi_api_client import Feature, MockViClient
from vi_api_client.models import FeatureControl

from custom_components.vi_climate_devices import water_heater
from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.water_heater import (
    STATE_ECO,
    STATE_GAS,
    STATE_OFF,
    STATE_PERFORMANCE,
)


@pytest.fixture
def mock_water_heater_client():
    """Return a mocked client with water heater features."""
    client = MockViClient("Vitocal252")

    # 1. Target Temp Feature
    f_target = MagicMock(spec=Feature)
    f_target.name = "heating.dhw.temperature.main"
    f_target.is_enabled = True
    f_target.value = 50.0
    f_target.control = MagicMock(spec=FeatureControl)
    f_target.control.min = 10
    f_target.control.max = 60
    f_target.control.step = 1.0
    f_target.control.options = None

    # 2. Current Temp Feature
    f_current = MagicMock(spec=Feature)
    f_current.name = "heating.dhw.sensors.temperature.hotWaterStorage"
    f_current.is_enabled = True
    f_current.value = 48.5
    f_current.control = None

    # 3. Mode Feature
    f_mode = MagicMock(spec=Feature)
    f_mode.name = "heating.dhw.operating.modes.active"
    f_mode.is_enabled = True
    f_mode.value = "eco"
    f_mode.control = MagicMock(spec=FeatureControl)
    f_mode.control.options = ["off", "eco", "comfort", "standard"]
    # MockViClient validation checks 'options' for enums
    # We must ensure options are set correctly if we want validation to pass
    # However, since we mock set_feature, validation might be bypassed if we mock the client.

    client.features = [f_target, f_current, f_mode]
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
    mock_device.features_flat = mock_water_heater_client.features
    mock_device.get_feature.side_effect = lambda name: next(
        (f for f in mock_device.features if f.name == name), None
    )

    coordinator.data = {"0": mock_device}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator}

    # Manually load the platform

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
    # Mapping check: eco->eco, comfort->performance, standard->gas, off->off
    assert sorted(entity.operation_list) == sorted(
        [STATE_OFF, STATE_ECO, STATE_PERFORMANCE, STATE_GAS]
    )

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
    mock_device.features_flat = mock_water_heater_client.features
    mock_device.get_feature.side_effect = lambda name: next(
        (f for f in mock_device.features if f.name == name), None
    )

    coordinator.data = {"0": mock_device}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator}

    async_add_entities = MagicMock()
    await water_heater.async_setup_entry(hass, entry, async_add_entities)
    entity = async_add_entities.call_args[0][0][0]

    # Mock set_feature on coordinator client
    coordinator.client.set_feature = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    # Entity is not fully registered, so mock async_write_ha_state
    entity.async_write_ha_state = MagicMock()

    # Test Set Temperature
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 55.0})

    coordinator.client.set_feature.assert_called_with(
        mock_device,
        entity._get_feature("heating.dhw.temperature.main"),
        55.0,
    )

    # Test Set Mode (now uses HA states)
    await entity.async_set_operation_mode(STATE_PERFORMANCE)

    # Should send Viessmann mode "comfort" to API
    coordinator.client.set_feature.assert_called_with(
        mock_device,
        entity._get_feature("heating.dhw.operating.modes.active"),
        "comfort",
    )
