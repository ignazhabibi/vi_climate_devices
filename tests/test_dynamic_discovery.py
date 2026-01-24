"""Test dynamic discovery for different device types."""

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import MockViClient

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)


@pytest.mark.asyncio
async def test_gas_boiler_entities(hass: HomeAssistant):
    """Test that gas boiler (Vitodens) creates boiler sensors."""
    # Use real MockViClient now that it is fixed
    client = MockViClient("Vitodens200W")

    # We need to properly initialize the mock client if needed,
    # but MockViClient("Vitodens200W") should be enough to load fixtures.

    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_refresh()

    if not coordinator.data:
        pytest.fail("Coordinator data empty.")

    device = next(iter(coordinator.data.values()))

    # 1. Check for Boiler specific feature
    # heating.burners.0.modulation should exist and be used for a sensor
    burner_mod = next(
        (f for f in device.features if f.name == "heating.burners.0.modulation"),
        None,
    )
    assert burner_mod is not None

    # 2. Check that it does NOT have Heat Pump specific feature
    hp_compressor = next(
        (
            f
            for f in device.features
            if f.name == "heating.compressors.0.statistics.hours"
        ),
        None,
    )
    assert hp_compressor is None


@pytest.mark.asyncio
async def test_heat_pump_entities(hass: HomeAssistant):
    """Test that heat pump (Vitocal) creates heat pump sensors."""
    client = MockViClient("Vitocal252")

    coordinator = ViClimateDataUpdateCoordinator(hass, client)
    await coordinator.async_refresh()

    if not coordinator.data:
        pytest.fail("Coordinator data empty.")

    device = next(iter(coordinator.data.values()))

    # 1. Check for Heat Pump specific feature
    # heating.compressors.0.statistics.hours should exist
    hp_compressor = next(
        (
            f
            for f in device.features
            if f.name == "heating.compressors.0.statistics.hours"
        ),
        None,
    )
    assert hp_compressor is not None

    # 2. Check that it does NOT have Boiler specific feature
    burner_mod = next(
        (f for f in device.features if f.name == "heating.burners.0.modulation"),
        None,
    )
    assert burner_mod is None
