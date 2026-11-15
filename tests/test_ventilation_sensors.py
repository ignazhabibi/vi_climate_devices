"""Tests for the defined ventilation state sensors."""

from unittest.mock import MagicMock

import pytest
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors


@pytest.mark.parametrize(
    ("device_name", "reason"),
    [
        pytest.param("Vitopure350", "standby", id="standby"),
        pytest.param("VitoairFs300E", "sensor_override", id="camel-case"),
    ],
)
@pytest.mark.asyncio
async def test_ventilation_reason_is_a_translated_enum(
    device_name: str, reason: str
) -> None:
    """Report the ventilation reason as an option key of its API value."""
    # Arrange: Load a ventilation fixture.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's ventilation reason sensor.
    entity = next(
        entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
        if entity.entity_description.key == "ventilation.operating.state.reason"
    )

    # Assert: The reason is a translated enum state.
    assert entity.entity_description.device_class == "enum"
    assert entity.native_value == reason


@pytest.mark.parametrize(
    ("device_name", "level"),
    [
        pytest.param("Vitocal200S", "level_one", id="vitocal-200s"),
        pytest.param("Vitocal300G-CU401B", "level_one", id="vitocal-300g"),
        pytest.param("Vitopure350", None, id="placeholder"),
    ],
)
@pytest.mark.asyncio
async def test_ventilation_level_is_a_translated_enum(
    device_name: str, level: str | None
) -> None:
    """Report the ventilation level also on devices without a fan entity."""
    # Arrange: Load a fixture that reports the ventilation state.
    device = (await FixtureViClient(device_name).get_full_installation_status("99999"))[
        0
    ]

    # Act: Discover the fixture's sensors.
    entities = {
        entity.entity_description.key: entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
    }

    # Assert: The level is a diagnostic enum; a placeholder is unknown.
    sensor = entities["ventilation.operating.state.level"]
    assert sensor.entity_description.translation_key == "ventilation_level"
    assert sensor.entity_description.entity_category == "diagnostic"
    assert sensor.native_value == level
