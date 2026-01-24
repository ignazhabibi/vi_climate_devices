import json
import os

import pytest

from custom_components.vi_climate_devices.binary_sensor import (
    BINARY_SENSOR_TEMPLATES,
    BINARY_SENSOR_TYPES,
)
from custom_components.vi_climate_devices.number import NUMBER_TEMPLATES, NUMBER_TYPES
from custom_components.vi_climate_devices.sensor import (
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
    ANALYTICS_Types,
)


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_entity_definitions(platform):
    """Returns a list of EntityDescription objects for the platform."""
    descriptions = []

    if platform == "sensor":
        # Static
        descriptions.extend(SENSOR_TYPES.values())
        # Templates
        for t in SENSOR_TEMPLATES:
            descriptions.append(t["description"])
        # Analytics
        descriptions.extend(ANALYTICS_Types.values())

    elif platform == "binary_sensor":
        descriptions.extend(BINARY_SENSOR_TYPES.values())
        for t in BINARY_SENSOR_TEMPLATES:
            descriptions.append(t["description"])

    elif platform == "number":
        # NUMBER_TYPES is dict[feature_name, Description] (Flat)
        descriptions.extend(NUMBER_TYPES.values())
        # Templates
        for t in NUMBER_TEMPLATES:
            # NUMBER_TEMPLATES[i]["description"] is a single Description object now
            descriptions.append(t["description"])

    return descriptions


@pytest.fixture
def translations():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    component_dir = os.path.join(base_dir, "custom_components", "vi_climate_devices")

    return {
        "strings": load_json(os.path.join(component_dir, "strings.json")),
        "en": load_json(os.path.join(component_dir, "translations", "en.json")),
        "de": load_json(os.path.join(component_dir, "translations", "de.json")),
    }


@pytest.mark.parametrize("platform", ["sensor", "binary_sensor", "number"])
def test_entity_has_translation_key(platform):
    """Verify that every entity description has a translation_key set."""
    descriptions = get_entity_definitions(platform)

    for i, desc in enumerate(descriptions):
        assert hasattr(desc, "translation_key") and desc.translation_key, (
            f"EntityDescription at index {i} in {platform} is missing a translation_key. Key: {getattr(desc, 'key', 'UNKNOWN')}"
        )


@pytest.mark.parametrize("platform", ["sensor", "binary_sensor", "number"])
def test_translation_keys_exist(platform, translations):
    """Verify that all used translation keys exist in translation files."""
    descriptions = get_entity_definitions(platform)

    used_keys = set()
    for desc in descriptions:
        used_keys.add(desc.translation_key)

    missing_strings = []
    missing_en = []
    missing_de = []

    for key in used_keys:
        # Check strings.json
        if key not in translations["strings"].get("entity", {}).get(platform, {}):
            missing_strings.append(key)

        # Check en.json
        if key not in translations["en"].get("entity", {}).get(platform, {}):
            missing_en.append(key)

        # Check de.json
        if key not in translations["de"].get("entity", {}).get(platform, {}):
            missing_de.append(key)

    error_msg = []
    if missing_strings:
        error_msg.append(
            f"Missing in strings.json for {platform}: {sorted(missing_strings)}"
        )
    if missing_en:
        error_msg.append(f"Missing in en.json for {platform}: {sorted(missing_en)}")
    if missing_de:
        error_msg.append(f"Missing in de.json for {platform}: {sorted(missing_de)}")

    assert not error_msg, "\n".join(error_msg)
