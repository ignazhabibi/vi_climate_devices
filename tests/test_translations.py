"""Tests for translation keys in the Viessmann Climate Devices integration."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.vi_climate_devices.binary_sensor import (
    BINARY_SENSOR_TEMPLATES,
    BINARY_SENSOR_TYPES,
)
from custom_components.vi_climate_devices.number import NUMBER_TEMPLATES, NUMBER_TYPES
from custom_components.vi_climate_devices.select import SELECT_TYPES
from custom_components.vi_climate_devices.sensor import (
    ANALYTICS_TYPES,
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
)
from custom_components.vi_climate_devices.water_heater import ViClimateWaterHeater


def load_json(path: Path):
    """Load JSON data from a file."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def get_entity_definitions(platform):
    """Returns a list of EntityDescription objects for the platform."""
    descriptions = []

    if platform == "sensor":
        # Static and Analytics
        descriptions.extend(SENSOR_TYPES.values())
        descriptions.extend(ANALYTICS_TYPES.values())
        # Templates
        for t in SENSOR_TEMPLATES:
            descriptions.append(t["description"])

    elif platform == "binary_sensor":
        descriptions.extend(BINARY_SENSOR_TYPES.values())
        for t in BINARY_SENSOR_TEMPLATES:
            descriptions.append(t["description"])

    elif platform == "number":
        descriptions.extend(NUMBER_TYPES.values())
        for t in NUMBER_TEMPLATES:
            descriptions.append(t["description"])

    elif platform == "select":
        descriptions.extend(SELECT_TYPES.values())

    elif platform == "water_heater":
        # Arrange: Instantiate entity with mocks to read the REAL translation_key property
        mock_coordinator = MagicMock()
        mock_coordinator.data = {"test_key": MagicMock()}  # Device mock
        mock_feature = MagicMock(name="heating.dhw.temperature.main")

        entity = ViClimateWaterHeater(mock_coordinator, "test_key", mock_feature)

        # Now we get the actual key defined in the code ("dhw_water_heater")
        descriptions.append(SimpleNamespace(translation_key=entity.translation_key))

    return descriptions


@pytest.fixture
def translations():
    """Load all translation files."""
    base_dir = Path(__file__).resolve().parent.parent
    component_dir = base_dir / "custom_components" / "vi_climate_devices"

    return {
        "strings": load_json(component_dir / "strings.json"),
        "en": load_json(component_dir / "translations" / "en.json"),
        "de": load_json(component_dir / "translations" / "de.json"),
    }


@pytest.mark.parametrize(
    "platform", ["sensor", "binary_sensor", "number", "select", "water_heater"]
)
def test_entity_has_translation_key(platform):
    """Verify that every entity description has a translation_key set."""
    # Arrange: Load definitions for the specific platform.
    descriptions = get_entity_definitions(platform)

    # Act & Assert: Iterate through all descriptions and verify existence of translation_key.
    for i, desc in enumerate(descriptions):
        key_name = getattr(desc, "key", "UNKNOWN")
        assert hasattr(desc, "translation_key") and desc.translation_key, (
            f"EntityDescription at index {i} in {platform} is missing a translation_key. Key: {key_name}"
        )


@pytest.mark.parametrize(
    "platform", ["sensor", "binary_sensor", "number", "select", "water_heater"]
)
def test_translation_keys_exist(platform, translations):
    """Verify that all used translation keys exist in translation files."""
    # Arrange: Get unique translation keys used by the platform.
    descriptions = get_entity_definitions(platform)
    used_keys = {desc.translation_key for desc in descriptions}

    # Act: Check against loaded translation files.
    missing_strings = []
    missing_en = []
    missing_de = []

    for key in used_keys:
        # Check strings.json (Developer Strings)
        if key not in translations["strings"].get("entity", {}).get(platform, {}):
            missing_strings.append(key)

        # Check en.json (English)
        if key not in translations["en"].get("entity", {}).get(platform, {}):
            missing_en.append(key)

        # Check de.json (German)
        if key not in translations["de"].get("entity", {}).get(platform, {}):
            missing_de.append(key)

    # Assert: Report any missing keys.
    error_msg = []
    if missing_strings:
        error_msg.append(f"Missing in strings.json: {missing_strings}")
    if missing_en:
        error_msg.append(f"Missing in en.json: {missing_en}")
    if missing_de:
        error_msg.append(f"Missing in de.json: {missing_de}")

    assert not error_msg, (
        f"Missing translations for platform '{platform}':\n" + "\n".join(error_msg)
    )
