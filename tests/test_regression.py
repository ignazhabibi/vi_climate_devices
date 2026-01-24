"""Regression tests for specific bugs found during deployment."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.sensor import (
    ANALYTICS_Types,
    SENSOR_TYPES,
)
from custom_components.vi_climate_devices import sensor
from vi_api_client import Feature


def test_no_duplicate_sensor_definitions():
    """Ensure no feature key is defined in both SENSOR_TYPES and ANALYTICS_Types."""
    sensor_keys = set(SENSOR_TYPES.keys())
    analytics_keys = set(ANALYTICS_Types.keys())

    duplicates = sensor_keys.intersection(analytics_keys)
    assert not duplicates, f"Duplicate keys found in definition tables: {duplicates}"


@pytest.mark.asyncio
async def test_complex_sensor_state_handling(hass: HomeAssistant):
    """Test that complex values (dict/list) are handled gracefully by sensors."""
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # Mock Client
    client = MagicMock()

    # Create Features with complex values
    f_dict = MagicMock(spec=Feature)
    f_dict.name = "test.complex.dict"
    f_dict.value = {"error": "code", "msg": "test"}
    f_dict.is_writable = False
    f_dict.is_enabled = True

    f_list = MagicMock(spec=Feature)
    f_list.name = "test.complex.list"
    f_list.value = [1, 2, 3, 4]
    f_list.is_writable = False
    f_list.is_enabled = True

    f_normal = MagicMock(spec=Feature)
    f_normal.name = "test.simple"
    f_normal.value = 10.5
    f_normal.is_writable = False
    f_normal.is_enabled = True

    # Setup Device
    mock_device = MagicMock()
    mock_device.gateway_serial = "12345"
    mock_device.id = "0"
    mock_device.model_id = "TestModel"
    mock_device.features = [f_dict, f_list, f_normal]
    mock_device.features_flat = mock_device.features
    # Simple get_feature mock
    mock_device.get_feature.side_effect = lambda name: next(
        (f for f in mock_device.features if f.name == name), None
    )

    # Setup Coordinator
    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    coordinator.data = {"0": mock_device}
    coordinator.last_update_success = True

    hass.data.setdefault(DOMAIN, {})
    # Note: sensor setup needs 'analytics' key even if None
    hass.data[DOMAIN][entry.entry_id] = {"data": coordinator, "analytics": None}

    # Setup Platform
    async_add_entities = MagicMock()
    await sensor.async_setup_entry(hass, entry, async_add_entities)

    # Verify Entities
    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]

    # Find our entities
    ent_dict = next(e for e in entities if e.name == "test.complex.dict")
    ent_list = next(e for e in entities if e.name == "test.complex.list")
    ent_normal = next(e for e in entities if e.name == "test.simple")

    # Check Dict Sensor
    assert ent_dict.native_value == "Complex Data"
    assert ent_dict.extra_state_attributes["raw_value"] == {
        "error": "code",
        "msg": "test",
    }

    # Check List Sensor
    assert ent_dict.native_value == "Complex Data"  # Wait, logic returns str?
    # Logic in code:
    # if isinstance(val, list): return len(val)
    # return "Complex Data"
    assert ent_list.native_value == 4  # Length of list
    assert ent_list.extra_state_attributes["raw_value"] == [1, 2, 3, 4]

    # Check Normal Sensor
    assert ent_normal.native_value == 10.5
