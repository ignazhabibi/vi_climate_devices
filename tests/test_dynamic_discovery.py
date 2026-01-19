"""Test dynamic discovery for different device types."""
import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import MockViClient
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator

@pytest.mark.asyncio
async def test_gas_boiler_entities(hass: HomeAssistant):
    """Test that gas boiler (Vitodens) creates boiler sensors."""
    client = MockViClient("Vitodens200W")
    
    # MockViClient natively supports the V2 flow (get_installations -> devices -> update)
    # No patching needed if the library is up to date.

    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_refresh()
    
    # Coordinator data is populated
    if not coordinator.data:
        # Fallback debug or failure
        assert False, f"Coordinator data empty. Client installations: {await client.get_installations()}"

    device = list(coordinator.data.values())[0]
    
    # 1. Check for Boiler specific feature
    # heating.burners.0.modulation should exist and be used for a sensor
    burner_mod = next((f for f in device.features_flat if f.name == "heating.burners.0.modulation"), None)
    assert burner_mod is not None

    # 2. Check that it does NOT have Heat Pump specific feature
    hp_compressor = next((f for f in device.features_flat if f.name == "heating.compressors.0.statistics.hours"), None)
    assert hp_compressor is None
    
@pytest.mark.asyncio
async def test_heat_pump_entities(hass: HomeAssistant):
    """Test that heat pump (Vitocal) creates heat pump sensors."""
    client = MockViClient("Vitocal252") 
    
    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_refresh()
    
    device = list(coordinator.data.values())[0]
    
    # 1. Check for Heat Pump specific feature
    # heating.compressors.0.statistics.hours should exist
    hp_compressor = next((f for f in device.features_flat if f.name == "heating.compressors.0.statistics.hours"), None)
    assert hp_compressor is not None
    
    # 2. Check that it does NOT have Boiler specific feature
    burner_mod = next((f for f in device.features_flat if f.name == "heating.burners.0.modulation"), None)
    assert burner_mod is None
