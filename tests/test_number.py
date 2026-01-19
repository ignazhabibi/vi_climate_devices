"""Tests for the Viessmann Heat number platform."""

from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from homeassistant.core import HomeAssistant

from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator
from custom_components.vi_climate_devices.number import (
    ViClimateNumber,
    NUMBER_TYPES,
    NUMBER_TEMPLATES,
)
import re
import dataclasses
from vi_api_client import Feature


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
    mock_feature.name = "heating.circuits.0.heating.curve"
    mock_feature.properties = {"slope": {"value": 1.4}, "shift": {"value": 0}}

    # Mock Command Definition
    cmd_def = MagicMock()
    cmd_def.params = {
        "slope": {
            "type": "number",
            "constraints": {"min": 0.2, "max": 3.5, "stepping": 0.1},
        },
        "shift": {
            "type": "number",
            "constraints": {"min": -13, "max": 40, "stepping": 1},
        },
    }
    mock_feature.commands = {"setCurve": cmd_def}

    device.features = [mock_feature]

    # Mock return data
    coordinator.data = {"serial_0": device}
    coordinator.last_update_success = True

    # Initialize Slope Entity
    # Initialize Slope Entity via Template Lookup
    desc_slope = None
    for tmpl in NUMBER_TEMPLATES:
        m = re.match(tmpl["pattern"], "heating.circuits.0.heating.curve")
        if m:
            # Slope is index 0 in descriptions list for this template
            base = tmpl["descriptions"][0]
            # Format
            desc_slope = dataclasses.replace(
                base,
                key=base.key.format("0"),
                translation_key=base.translation_key,  # Generic key
            )
            break
    assert desc_slope is not None
    entity_slope = ViClimateNumber(
        coordinator,
        "serial_0",
        mock_feature,
        desc_slope,
        translation_placeholders={"index": "0"},
    )

    # Verify Constraints
    assert entity_slope.native_min_value == 0.2
    assert entity_slope.native_max_value == 3.5
    assert entity_slope.native_step == 0.1
    # Verify Value
    assert entity_slope.native_value == 1.4

    # Verify Attributes
    attrs = entity_slope.extra_state_attributes
    assert attrs["viessmann_feature_name"] == "heating.circuits.0.heating.curve"
    assert attrs["viessmann_param_name"] == "slope"


@pytest.mark.asyncio
async def test_number_dhw_target_temp(hass: HomeAssistant):
    """Test DHW Target Temperature entity."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.temperature.main"
    # Configured to read from "value" property in NUMBER_TYPES
    feature.properties = {"value": {"value": 50.0}}

    cmd_def = MagicMock()
    cmd_def.params = {"temperature": {"constraints": {"min": 10, "max": 60, "step": 1}}}
    feature.commands = {"setTargetTemperature": cmd_def}

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    coordinator.data = {"test_gw_0": device}

    desc = NUMBER_TYPES["heating.dhw.temperature.main"][0]

    entity = ViClimateNumber(coordinator, "test_gw_0", feature, desc)
    entity.hass = hass

    # Verify Config
    assert entity.translation_key == "dhw_target_temperature"
    assert entity.native_value == 50.0
    assert entity.native_min_value == 10.0
    assert entity.native_max_value == 60.0

    # Set Value
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_native_value(55.0)

    # Command expects "temperature" param (as configured or dynamically resolved)
    coordinator.client.execute_command.assert_called_with(
        feature, "setTargetTemperature", {"temperature": 55.0}
    )
    # Optimistic update should target the 'value' property (as configured)
    assert feature.properties["value"]["value"] == 55.0


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
    mock_feature.name = "heating.circuits.0.heating.curve"
    mock_feature.properties = {"slope": {"value": 1.4}, "shift": {"value": 0}}

    cmd_def = MagicMock()
    cmd_def.params = {
        "slope": {},
        "shift": {},  # simplify params for set test
    }
    mock_feature.commands = {"setCurve": cmd_def}

    device.features = [mock_feature]  # <--- ADDED THIS LINE
    coordinator.data = {"serial_0": device}

    # Initialize Slope Entity
    # Initialize Slope Entity via Template Lookup
    desc_slope = None
    for tmpl in NUMBER_TEMPLATES:
        m = re.match(tmpl["pattern"], "heating.circuits.0.heating.curve")
        if m:
            base = tmpl["descriptions"][0]
            desc_slope = dataclasses.replace(
                base,
                key=base.key.format("0"),
                translation_key=base.translation_key,  # Generic key
            )
            break
    entity_slope = ViClimateNumber(
        coordinator,
        "serial_0",
        mock_feature,
        desc_slope,
        translation_placeholders={"index": "0"},
    )
    entity_slope.hass = hass
    entity_slope.async_write_ha_state = (
        MagicMock()
    )  # <--- Mock this to avoid platform setup issues

    # ACT: Set Slope to 1.6
    await entity_slope.async_set_native_value(1.6)

    # ASSERT
    # Expect payload to contain BOTH slope (new) and shift (old)
    expected_payload = {"slope": 1.6, "shift": 0}
    mock_client.execute_command.assert_called_once_with(
        mock_feature, "setCurve", expected_payload
    )

    # We deliberately removed the immediate refresh to rely on optimistic updates
    coordinator.async_request_refresh.assert_not_called()

    # Verify Optimistic Update: The local feature property should be updated
    assert mock_feature.properties["slope"]["value"] == 1.6


@pytest.mark.asyncio
async def test_number_hysteresis_set(hass: HomeAssistant):
    """Test setting hysteresis value (single parameter command)."""
    # Mock client and data
    mock_client = AsyncMock()
    coordinator = MagicMock(spec=ViClimateDataUpdateCoordinator)
    coordinator.client = mock_client
    coordinator.async_request_refresh = AsyncMock()

    device = MagicMock()
    device.gateway_serial = "serial"
    device.id = "0"

    # Mock feature with ON command
    mock_feature = MagicMock()
    mock_feature.name = "heating.dhw.temperature.hysteresis"
    mock_feature.properties = {
        "switchOnValue": {"value": 2.5}  # Correct Property Name
    }

    cmd_def = MagicMock()
    cmd_def.params = {"hysteresis": {}}
    mock_feature.commands = {"setHysteresisSwitchOnValue": cmd_def}

    device.features = [mock_feature]
    coordinator.data = {"serial_0": device}

    # Initialize Hysteresis ON Entity
    desc_on = NUMBER_TYPES["heating.dhw.temperature.hysteresis"][0]  # On
    entity_on = ViClimateNumber(coordinator, "serial_0", mock_feature, desc_on)
    entity_on.hass = hass
    entity_on.async_write_ha_state = MagicMock()

    # ACT: Set to 3.0
    await entity_on.async_set_native_value(3.0)

    # ASSERT
    # Expect payload to contain ONLY "hysteresis" (Parameter name)
    expected_payload = {"hysteresis": 3.0}
    mock_client.execute_command.assert_called_once_with(
        mock_feature, "setHysteresisSwitchOnValue", expected_payload
    )

    # Verify optimistic update on the PROPERTY
    assert mock_feature.properties["switchOnValue"]["value"] == 3.0
    entity_on.async_write_ha_state.assert_called_once()
