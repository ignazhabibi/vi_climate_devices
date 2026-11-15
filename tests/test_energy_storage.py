"""Tests for the defined entities of energy storage systems."""

import dataclasses
from unittest.mock import MagicMock

import pytest
from vi_api_client import Feature, FixtureViClient

from custom_components.vi_climate_devices.sensor import _discover_realtime_sensors


def test_pv_string_without_a_name_is_named_by_its_index() -> None:
    """Fall back to the 1-based index when the device names no string."""
    # Arrange: Build a device whose PV string reports no name.
    feature = Feature(
        name="photovoltaic.string.1.voltage",
        value=200,
        unit="volt",
        is_enabled=True,
        is_ready=True,
    )
    device = MagicMock(features=[feature])
    device.get_feature.side_effect = lambda name: (
        feature if name == feature.name else None
    )

    # Act: Discover the device's sensors.
    entities = _discover_realtime_sensors(MagicMock(data={"device": device}))

    # Assert: The string is named after its index.
    assert [entity.translation_placeholders for entity in entities] == [{"name": "2"}]


@pytest.mark.parametrize(
    ("api_value", "state"),
    [
        pytest.param("safetyCheck", "safety_check", id="camel-case"),
        pytest.param("nothing", None, id="placeholder"),
    ],
)
@pytest.mark.asyncio
async def test_battery_operation_state_maps_api_values(
    api_value: str, state: str | None
) -> None:
    """Translate camelCase battery states and hide placeholders."""
    # Arrange: Report a battery state on the Evolution 08 fixture.
    device = (
        await FixtureViClient("VitochargeEvolution08").get_full_installation_status(
            "99999"
        )
    )[0]
    features = [
        dataclasses.replace(feature, value=api_value)
        if feature.name == "ess.operationState"
        else feature
        for feature in device.features
    ]
    device = dataclasses.replace(device, features=features)

    # Act: Discover the fixture's battery state sensor.
    entity = next(
        entity
        for entity in _discover_realtime_sensors(MagicMock(data={"device": device}))
        if entity.entity_description.key == "ess.operationState"
    )

    # Assert: The state is the option key, or unknown for a placeholder.
    assert entity.native_value == state
