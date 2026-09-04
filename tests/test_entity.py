"""Tests for shared Viessmann entity behavior."""

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.core import HomeAssistant
from vi_api_client import Device, Feature

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.sensor import ViClimateSensor


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
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
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
