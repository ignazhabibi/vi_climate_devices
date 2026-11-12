"""Tests that defined entities follow Viessmann's feature deprecations."""

import re
from collections.abc import Iterable

import pytest
from vi_api_client import FixtureViClient

from custom_components.vi_climate_devices.binary_sensor import (
    BINARY_SENSOR_TEMPLATES,
    BINARY_SENSOR_TYPES,
)
from custom_components.vi_climate_devices.const import (
    FEATURE_SUCCESSORS,
    IGNORED_FEATURES,
)
from custom_components.vi_climate_devices.number import NUMBER_TEMPLATES, NUMBER_TYPES
from custom_components.vi_climate_devices.sensor import (
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
)
from custom_components.vi_climate_devices.switch import SWITCH_TEMPLATES, SWITCH_TYPES
from custom_components.vi_climate_devices.utils import is_feature_ignored
from custom_components.vi_climate_devices.water_heater import (
    FEATURE_CURRENT_TEMP,
    FEATURE_MODE,
    FEATURE_TARGET_TEMP,
)

FIXTURE_NAMES = FixtureViClient.get_available_fixture_devices()

# Deprecated features behind defined entities that stay on the deprecated
# feature for now, with the reason the successor is not mapped yet (#220).
# Sort the keys alphabetically.
DEPRECATED_WITHOUT_MAPPED_SUCCESSOR = {
    "heating.heatingRod.statistics.hours": (
        "The successor heatingRods.heatGeneration.N.statistics has no verified "
        "feature name."
    ),
    "heating.heatingRod.statistics.starts": (
        "The successor heatingRods.heatGeneration.N.statistics has no verified "
        "feature name."
    ),
    "heating.noise.reduction.operating.programs.active": (
        "The values of the successor heating.noise.reduction.operating.state "
        "are not verified against the enum options."
    ),
    "heating.sensors.volumetricFlow.allengra": (
        "The successor heating.heatGeneration.0.secondaryCircuit.sensors."
        "volumetricFlow has no verified feature name or unit."
    ),
}

DEFINED_FEATURE_NAMES = frozenset(
    {
        *SENSOR_TYPES,
        *BINARY_SENSOR_TYPES,
        *NUMBER_TYPES,
        *SWITCH_TYPES,
        FEATURE_CURRENT_TEMP,
        FEATURE_MODE,
        FEATURE_TARGET_TEMP,
    }
)

TEMPLATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    template.pattern
    for templates in (
        SENSOR_TEMPLATES,
        BINARY_SENSOR_TEMPLATES,
        NUMBER_TEMPLATES,
        SWITCH_TEMPLATES,
    )
    for template in templates
)


def _is_defined(feature_name: str) -> bool:
    """Return whether a feature backs a defined entity instead of discovery."""
    if is_feature_ignored(feature_name, IGNORED_FEATURES):
        return False
    return feature_name in DEFINED_FEATURE_NAMES or any(
        pattern.match(feature_name) for pattern in TEMPLATE_PATTERNS
    )


async def _deprecated_feature_names(fixture_names: Iterable[str]) -> set[str]:
    """Return the deprecated features the fixtures report, also unavailable ones."""
    names: set[str] = set()
    for fixture_name in fixture_names:
        devices = await FixtureViClient(fixture_name).get_full_installation_status(
            "99999", only_available=False
        )
        names.update(
            feature.name
            for device in devices
            for feature in device.features
            if feature.deprecation is not None
        )
    return names


@pytest.mark.asyncio
async def test_deprecated_defined_features_have_a_decision() -> None:
    """Fail when a fixture deprecates a defined feature nobody has decided on.

    A new deprecation then surfaces when the fixtures are updated: either map
    the successor in FEATURE_SUCCESSORS or record why it stays unmapped.
    """
    # Arrange: Collect the deprecated features of every fixture.
    deprecated_names = await _deprecated_feature_names(FIXTURE_NAMES)

    # Act: Keep the deprecated features that back defined entities.
    undecided = sorted(
        name
        for name in deprecated_names
        if _is_defined(name)
        and name not in FEATURE_SUCCESSORS
        and name not in DEPRECATED_WITHOUT_MAPPED_SUCCESSOR
    )

    # Assert: Every deprecated defined feature has a decision.
    assert undecided == []


@pytest.mark.asyncio
async def test_recorded_deprecation_decisions_are_current() -> None:
    """Keep the mapping and the unmapped list limited to real deprecations."""
    # Arrange: Collect the deprecated features of every fixture.
    deprecated_names = await _deprecated_feature_names(FIXTURE_NAMES)

    # Act: Find recorded decisions that no longer match a deprecation.
    stale = sorted(
        name
        for name in (*FEATURE_SUCCESSORS, *DEPRECATED_WITHOUT_MAPPED_SUCCESSOR)
        if name not in deprecated_names or not _is_defined(name)
    )

    # Assert: Each recorded feature is a deprecated feature of a defined entity.
    assert stale == []
    assert not set(FEATURE_SUCCESSORS) & set(DEPRECATED_WITHOUT_MAPPED_SUCCESSOR)


def test_successors_belong_to_sensor_entities() -> None:
    """Limit successors to sensors, the only platform that resolves them.

    Sensor discovery skips the successor and removes its auto-discovered
    duplicate; the other platforms would create a second entity for it.
    """
    # Act and assert: Every mapped deprecated feature is a defined sensor.
    assert set(FEATURE_SUCCESSORS) <= set(SENSOR_TYPES)
