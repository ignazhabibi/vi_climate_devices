"""Tests for shared Viessmann entity behavior."""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import Device, Feature, FeatureValue, FixtureViClient

from custom_components.vi_climate_devices.const import DOMAIN
from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.sensor import ViClimateSensor
from custom_components.vi_climate_devices.water_heater import (
    FEATURE_MODE,
    FEATURE_TARGET_TEMP,
    ViClimateWaterHeater,
)


def _build_device() -> Device:
    """Create a minimal device with one enabled sensor feature."""
    return Device(
        id="device-0",
        gateway_serial="gw-main",
        installation_id="installation-1",
        model_id="Vitocal250A",
        device_type="heating",
        status="online",
        features=[
            Feature(
                name="heating.sensors.temperature.outside",
                value=12.2,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
            )
        ],
    )


def test_entity_is_unavailable_when_its_device_refresh_fails(
    hass: HomeAssistant, mock_client
) -> None:
    """Test sensor availability follows the coordinator's per-device status."""
    # Arrange: Create an enabled sensor for a successfully refreshed device.
    device = _build_device()
    device_key = "gw-main_device-0"
    coordinator = ViClimateDataUpdateCoordinator(hass, MockConfigEntry(), mock_client)
    coordinator.data = {device_key: device}
    entity = ViClimateSensor(
        coordinator,
        device_key,
        "heating.sensors.temperature.outside",
        SensorEntityDescription(key="outside_temperature"),
    )

    # Act: Mark only this device as failed during a partial coordinator refresh.
    coordinator._failed_device_keys.add(device_key)

    # Assert: The entity is unavailable despite the coordinator having partial data.
    assert not entity.available


def test_entity_is_unavailable_when_its_feature_disappears(
    hass: HomeAssistant, mock_client
) -> None:
    """Test an entity remains registered but unavailable without its feature."""
    # Arrange: Create an entity for an initially present sensor feature.
    device = _build_device()
    device_key = "gw-main_device-0"
    coordinator = ViClimateDataUpdateCoordinator(hass, MockConfigEntry(), mock_client)
    coordinator.data = {device_key: device}
    entity = ViClimateSensor(
        coordinator,
        device_key,
        "heating.sensors.temperature.outside",
        SensorEntityDescription(key="outside_temperature"),
    )

    # Act: Publish the refreshed device with the feature absent.
    coordinator.data = {device_key: replace(device, features=[])}

    # Assert: The existing entity is unavailable rather than deleted.
    assert not entity.available


@pytest.mark.parametrize(
    ("value", "expected_state", "expected_raw_value"),
    [
        (True, None, None),
        ("Not Connected", None, None),
        (["heating", "cooling"], None, ["heating", "cooling"]),
        ({"program": "heating"}, None, {"program": "heating"}),
    ],
)
def test_sensor_normalizes_feature_values_without_affecting_availability(
    hass: HomeAssistant,
    mock_client,
    value: FeatureValue,
    expected_state: str | int | float | None,
    expected_raw_value: list[str] | dict[str, str] | None,
) -> None:
    """Test a malformed sensor state remains local to that entity."""
    # Arrange: Publish a feature value that is not necessarily a scalar state.
    device = _build_device()
    device_key = "gw-main_device-0"
    feature = replace(device.features[0], value=value)
    coordinator = ViClimateDataUpdateCoordinator(hass, MockConfigEntry(), mock_client)
    coordinator.data = {device_key: replace(device, features=[feature])}
    entity = ViClimateSensor(
        coordinator,
        device_key,
        feature.name,
        SensorEntityDescription(key="outside_temperature"),
    )

    # Act: Resolve the entity's state and attributes from the feature value.
    native_value = entity.native_value
    attributes = entity.extra_state_attributes

    # Assert: The entity is available while only its invalid state becomes unknown.
    assert entity.available
    assert native_value == expected_state
    if expected_raw_value is None:
        assert "raw_value" not in attributes
    else:
        assert attributes["raw_value"] == expected_raw_value


def test_water_heater_is_unavailable_when_its_mode_feature_disappears(
    hass: HomeAssistant, mock_client
) -> None:
    """Test the water heater requires both discovery features to remain available."""
    # Arrange: Create a water heater with its target-temperature and mode features.
    target_feature = Feature(
        name=FEATURE_TARGET_TEMP,
        value=50.0,
        unit="celsius",
        is_enabled=True,
        is_ready=True,
    )
    mode_feature = Feature(
        name=FEATURE_MODE,
        value="dhw",
        unit="",
        is_enabled=True,
        is_ready=True,
    )
    device_key = "gw-main_device-0"
    device = replace(_build_device(), features=[target_feature, mode_feature])
    coordinator = ViClimateDataUpdateCoordinator(hass, MockConfigEntry(), mock_client)
    coordinator.data = {device_key: device}
    entity = ViClimateWaterHeater(coordinator, device_key, target_feature)

    # Act: Publish a refreshed device without the required mode feature.
    coordinator.data = {device_key: replace(device, features=[target_feature])}

    # Assert: The existing water-heater entity becomes unavailable.
    assert not entity.available


@pytest.mark.parametrize(
    ("device_name", "expected_names"),
    [
        pytest.param(
            "Vitocal250A",
            {
                ("climate", "heating_circuit_0"): "Vitocal250A Heating Circuit",
                (
                    "number",
                    "heating.circuits.0.heating.curve.slope",
                ): "Vitocal250A Heating Curve Slope",
                (
                    "sensor",
                    "heating.compressors.0.statistics.starts",
                ): "Vitocal250A Compressor Starts",
                (
                    "sensor",
                    "heating.primaryCircuit.fans.0.current",
                ): "Vitocal250A Fan 1 Speed",
                (
                    "sensor",
                    "heating.primaryCircuit.fans.1.current",
                ): "Vitocal250A Fan 2 Speed",
            },
            id="single-circuit-two-fans",
        ),
        pytest.param(
            "Vitocal200S",
            {
                ("climate", "heating_circuit_0"): "Vitocal200S Heating Circuit 1",
                ("climate", "heating_circuit_1"): "Vitocal200S Heating Circuit 2",
                (
                    "number",
                    "heating.circuits.1.heating.curve.slope",
                ): "Vitocal200S Heating Circuit 2 Curve Slope",
                (
                    "sensor",
                    "heating.compressors.0.statistics.starts",
                ): "Vitocal200S Compressor Starts",
            },
            id="two-circuits",
        ),
    ],
)
@pytest.mark.asyncio
async def test_entity_names_number_only_repeated_components(
    hass: HomeAssistant,
    device_name: str,
    expected_names: dict[tuple[str, str], str],
) -> None:
    """Number circuits and components 1-based, and only when there are several."""
    # Arrange: Load the real device fixture.
    client = FixtureViClient(device_name)
    device = (await client.get_full_installation_status("99999"))[0]
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)

    # Act: Discover the fixture through the Home Assistant integration.
    with (
        patch(
            "custom_components.vi_climate_devices.ViessmannClient",
            return_value=client,
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

        # Assert: Each entity has the expected default name.
        registry = er.async_get(hass)
        for (domain, unique_suffix), expected_name in expected_names.items():
            unique_id = f"{device.gateway_serial}-{device.id}-{unique_suffix}"
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            assert entity_id is not None, unique_suffix
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.attributes["friendly_name"] == expected_name

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
