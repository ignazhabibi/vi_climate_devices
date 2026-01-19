import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from custom_components.vi_climate_devices.select import ViClimateSelect, SELECT_TYPES
from homeassistant.core import HomeAssistant
from vi_api_client import Feature


@pytest.mark.asyncio
async def test_select_dhw_mode(hass: HomeAssistant):
    """Test DHW Mode Select entity."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.operating.modes.active"
    feature.properties = {"value": {"value": "eco"}}

    # Command with Enum constraints
    msg_constraints = {"enum": ["off", "eco", "comfort"]}
    cmd_def = MagicMock()
    cmd_def.params = {"mode": {"constraints": msg_constraints}}
    feature.commands = {"setMode": cmd_def}

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    coordinator.data = {"test_gw_0": device}

    desc = SELECT_TYPES["heating.dhw.operating.modes.active"]

    entity = ViClimateSelect(coordinator, "test_gw_0", feature, desc)
    entity.hass = hass

    # Verify Config
    assert entity.translation_key == "dhw_mode"
    assert entity.unique_id == "test_gw-0-heating.dhw.operating.modes.active"
    assert entity.current_option == "eco"
    assert entity.options == ["off", "eco", "comfort"]

    # Select Option
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_select_option("comfort")

    coordinator.client.execute_command.assert_called_with(
        feature, "setMode", {"mode": "comfort"}
    )
    # Optimistic update
    assert feature.properties["value"]["value"] == "comfort"


@pytest.mark.asyncio
async def test_select_dhw_mode_gas_variant(hass: HomeAssistant):
    """Test DHW Mode Select for Gas (efficientWithMinComfort)."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.operating.modes.active"
    feature.properties = {"value": {"value": "efficient"}}

    # Gas style enums
    msg_constraints = {"enum": ["off", "efficient", "efficientWithMinComfort"]}
    cmd_def = MagicMock()
    cmd_def.params = {"mode": {"constraints": msg_constraints}}
    feature.commands = {"setMode": cmd_def}

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "GasBoiler"
    device.features = [feature]
    coordinator.data = {"test_gw_0": device}

    desc = SELECT_TYPES["heating.dhw.operating.modes.active"]
    entity = ViClimateSelect(coordinator, "test_gw_0", feature, desc)
    entity.hass = hass

    assert entity.options == ["off", "efficient", "efficientWithMinComfort"]
    assert entity.current_option == "efficient"
