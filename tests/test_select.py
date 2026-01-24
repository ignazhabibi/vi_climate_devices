from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import Feature

from custom_components.vi_climate_devices.select import SELECT_TYPES, ViClimateSelect


@pytest.mark.asyncio
async def test_select_dhw_mode(hass: HomeAssistant):
    """Test DHW Mode Select entity."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    coordinator.client.set_feature = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.operating.modes.active"
    feature.value = "eco"  # Current value

    # Mock Control Options
    mock_control = MagicMock()
    mock_control.options = ["off", "eco", "comfort"]
    feature.control = mock_control

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "TestDevice"
    device.features = [feature]
    device.get_feature.return_value = feature  # Mock lookup

    coordinator.data = {"test_gw_0": device}

    desc = SELECT_TYPES["heating.dhw.operating.modes.active"]

    entity = ViClimateSelect(coordinator, "test_gw_0", feature.name, desc)
    entity.hass = hass

    # Verify Config
    assert entity.translation_key == "dhw_mode"
    assert entity.unique_id == "test_gw-0-heating.dhw.operating.modes.active"
    assert entity.current_option == "eco"
    assert entity.options == ["off", "eco", "comfort"]

    # Select Option
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_select_option("comfort")

    coordinator.client.set_feature.assert_called_with(device, feature, "comfort")


@pytest.mark.asyncio
async def test_select_dhw_mode_gas_variant(hass: HomeAssistant):
    """Test DHW Mode Select for Gas (efficientWithMinComfort)."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()

    feature = MagicMock(spec=Feature)
    feature.name = "heating.dhw.operating.modes.active"
    feature.value = "efficient"

    mock_control = MagicMock()
    mock_control.options = ["off", "efficient", "efficientWithMinComfort"]
    feature.control = mock_control

    device = MagicMock()
    device.gateway_serial = "test_gw"
    device.id = "0"
    device.model_id = "GasBoiler"
    device.features = [feature]
    device.get_feature.return_value = feature

    coordinator.data = {"test_gw_0": device}

    desc = SELECT_TYPES["heating.dhw.operating.modes.active"]
    entity = ViClimateSelect(coordinator, "test_gw_0", feature.name, desc)
    entity.hass = hass

    assert entity.options == ["off", "efficient", "efficientWithMinComfort"]
    assert entity.current_option == "efficient"
