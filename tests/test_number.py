"""Tests for the Viessmann Heat number platform."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import Feature

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.number import (
    NUMBER_TEMPLATES,
    NUMBER_TYPES,
    ViClimateNumber,
)


@pytest.mark.asyncio
async def test_number_entity_setup(hass: HomeAssistant):
    """Test that number entity setup extracts constraints correctly."""
    # Mock coordinator and device
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"
    device.model_id = "TestDevice"

    # Mock feature with commands/constraints
    mock_feature = MagicMock()
    mock_feature.name = (
        "heating.circuits.0.heating.curve.slope"  # Needs to match pattern
    )
    mock_feature.properties = {"slope": {"value": 1.4}, "shift": {"value": 0}}

    # Mock new Control API
    mock_control = MagicMock()
    mock_control.min = 0.2
    mock_control.max = 3.5
    mock_control.step = 0.1
    mock_control.type = "number"
    mock_feature.control = mock_control

    device.features = [mock_feature]
    # Important: Mock get_feature
    device.get_feature.return_value = mock_feature

    # Mock return data
    coordinator.data = {"serial_0": device}
    coordinator.last_update_success = True

    # Initialize Slope Entity via Template Lookup
    desc_slope = None
    # We test the direct template matching logic as done in setup_entry
    # But for unit test, just manually picking description is fine?
    # Let's reproduce logic from setup a bit
    for tmpl in NUMBER_TEMPLATES:
        m = tmpl["pattern"].match("heating.circuits.0.heating.curve.slope")
        if m:
            base = tmpl["description"]
            desc_slope = dataclasses.replace(
                base,
                key="heating.circuits.0.heating.curve.slope",
                translation_key=base.translation_key,
            )
            break

    assert desc_slope is not None
    entity_slope = ViClimateNumber(
        coordinator,
        "serial_0",
        mock_feature.name,
        desc_slope,
        translation_placeholders={"index": "0"},
    )

    # Verify Constraints
    assert entity_slope.native_min_value == 0.2
    assert entity_slope.native_max_value == 3.5
    assert entity_slope.native_step == 0.1

    # Verify Value - Mock feature.value
    mock_feature.value = 1.4
    assert entity_slope.native_value == 1.4


@pytest.mark.asyncio
async def test_number_dhw_target_temp(hass: HomeAssistant):
    """Test DHW Target Temperature entity."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.client.set_feature = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.temperature.main"
    feature.value = 50.0

    # Control
    control = MagicMock()
    control.min = 10
    control.max = 60
    control.step = 1
    feature.control = control

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    device.get_feature.return_value = feature

    coordinator.data = {"test_gw_0": device}

    desc = NUMBER_TYPES["heating.dhw.temperature.main"]

    entity = ViClimateNumber(coordinator, "test_gw_0", feature.name, desc)
    entity.hass = hass

    # Verify Config
    assert entity.translation_key == "dhw_target_temperature"
    assert entity.native_value == 50.0
    assert entity.native_min_value == 10.0
    assert entity.native_max_value == 60.0

    # Set Value
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_native_value(55.0)

    # Command uses client.set_feature
    coordinator.client.set_feature.assert_called_with(device, feature, 55.0)


@pytest.mark.asyncio
async def test_number_set_value(hass: HomeAssistant):
    """Test setting a value."""
    # Mock client
    mock_client = AsyncMock()

    # Mock coordinator
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    coordinator.client = mock_client
    coordinator.async_request_refresh = AsyncMock()

    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"

    # Mock feature
    mock_feature = MagicMock()
    mock_feature.name = "heating.circuits.0.heating.curve.slope"
    mock_feature.value = 1.4

    mock_control = MagicMock()
    mock_control.min = 0.2
    mock_control.max = 3.5
    mock_feature.control = mock_control

    device.features = [mock_feature]
    device.get_feature.return_value = mock_feature

    coordinator.data = {"serial_0": device}

    # Initialize Slope Entity
    desc_slope = None
    for tmpl in NUMBER_TEMPLATES:
        m = tmpl["pattern"].match("heating.circuits.0.heating.curve.slope")
        if m:
            base = tmpl["description"]
            desc_slope = dataclasses.replace(
                base, key="heating.circuits.0.heating.curve.slope"
            )
            break

    entity_slope = ViClimateNumber(
        coordinator,
        "serial_0",
        mock_feature.name,
        desc_slope,
        translation_placeholders={"index": "0"},
    )
    entity_slope.hass = hass
    entity_slope.async_write_ha_state = MagicMock()

    # ACT: Set Slope to 1.6
    await entity_slope.async_set_native_value(1.6)

    # ASSERT
    mock_client.set_feature.assert_called_once_with(device, mock_feature, 1.6)

    # Optimistic updates are less explicit in new code (library handles object, HA handles state),
    # but we DO call refresh
    coordinator.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_number_hysteresis_set(hass: HomeAssistant):
    """Test setting hysteresis value."""
    # Mock client and data
    mock_client = AsyncMock()
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    coordinator.client = mock_client
    coordinator.async_request_refresh = AsyncMock()

    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"

    # Mock feature
    mock_feature = MagicMock()
    mock_feature.name = "heating.dhw.temperature.hysteresis.switchOnValue"
    mock_feature.value = 2.5

    control = MagicMock()
    control.min = 1
    control.max = 10
    mock_feature.control = control

    device.features = [mock_feature]
    device.get_feature.return_value = mock_feature
    coordinator.data = {"serial_0": device}

    # Initialize Hysteresis ON Entity
    desc_on = NUMBER_TYPES["heating.dhw.temperature.hysteresis.switchOnValue"]
    entity_on = ViClimateNumber(coordinator, "serial_0", mock_feature.name, desc_on)
    entity_on.hass = hass
    entity_on.async_write_ha_state = MagicMock()

    # ACT: Set to 3.0
    await entity_on.async_set_native_value(3.0)

    # ASSERT
    mock_client.set_feature.assert_called_once_with(device, mock_feature, 3.0)
    coordinator.async_request_refresh.assert_called_once()
