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
from custom_components.vi_climate_devices.exceptions import ExceptionTranslationKey
from custom_components.vi_climate_devices.number import NUMBER_TEMPLATES, NUMBER_TYPES
from custom_components.vi_climate_devices.select import SELECT_TEMPLATES, SELECT_TYPES
from custom_components.vi_climate_devices.sensor import (
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
)
from custom_components.vi_climate_devices.switch import SWITCH_TYPES
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
        # Static sensor definitions.
        descriptions.extend(SENSOR_TYPES.values())
        # Templates.
        for t in SENSOR_TEMPLATES:
            descriptions.append(t.description)

    elif platform == "binary_sensor":
        descriptions.extend(BINARY_SENSOR_TYPES.values())
        for t in BINARY_SENSOR_TEMPLATES:
            descriptions.append(t.description)

    elif platform == "number":
        descriptions.extend(NUMBER_TYPES.values())
        for t in NUMBER_TEMPLATES:
            descriptions.append(t.description)

    elif platform == "select":
        descriptions.extend(SELECT_TYPES.values())
        for template in SELECT_TEMPLATES:
            descriptions.append(template.description)

    elif platform == "switch":
        descriptions.extend(SWITCH_TYPES.values())

    elif platform == "water_heater":
        # Arrange: Instantiate entity with mocks to read the REAL translation_key property
        mock_coordinator = MagicMock()
        mock_coordinator.data = {"test_key": MagicMock()}  # Device mock
        mock_feature = MagicMock(name="heating.dhw.temperature.main")

        entity = ViClimateWaterHeater(mock_coordinator, "test_key", mock_feature)

        # Now we get the actual key defined in the code ("dhw_water_heater")
        descriptions.append(SimpleNamespace(translation_key=entity.translation_key))

    return descriptions


MIGRATED_ENTITY_ICONS = {
    "number": {
        "dhw_hysteresis": "mdi:thermometer-lines",
        "dhw_hysteresis_on": "mdi:thermometer-plus",
        "dhw_hysteresis_off": "mdi:thermometer-minus",
        "dhw_target_temperature": "mdi:thermometer",
        "heating_curve_slope": "mdi:slope-uphill",
        "heating_curve_shift": "mdi:arrow-up-down",
        "heating_circuit_program_temperature": "mdi:thermometer",
        "heating_circuit_temperature_limit_min": "mdi:thermometer-low",
        "heating_circuit_temperature_limit_max": "mdi:thermometer-high",
    },
    "select": {
        "dhw_mode": "mdi:water-boiler-auto",
        "heating_circuit_operation_mode": "mdi:home-thermometer",
    },
    "sensor": {
        "heating_rod_hours": "mdi:counter",
        "heating_rod_starts": "mdi:counter",
        "scop_dhw": "mdi:chart-line",
        "scop_heating": "mdi:chart-line",
        "scop_total": "mdi:chart-line",
        "supply_pressure": "mdi:gauge",
        "volumetric_flow": "mdi:gauge",
        "valve_position": "mdi:valve",
        "burner_modulation": "mdi:fire",
        "burner_starts": "mdi:counter",
        "burner_hours": "mdi:counter",
        "compressor_hours": "mdi:counter",
        "compressor_starts": "mdi:counter",
        "compressor_phase": "mdi:state-machine",
        "compressor_inlet_pressure": "mdi:gauge",
        "compressor_speed_current": "mdi:fan",
        "compressor_speed_setpoint": "mdi:fan",
        "fan_speed": "mdi:fan",
        "evaporator_overheat_temperature": "mdi:thermometer",
        "condensor_liquid_temperature": "mdi:thermometer",
    },
    "switch": {
        "dhw_one_time_charge": "mdi:water-boiler",
        "dhw_hygiene": "mdi:shield-check",
    },
}


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
    "platform",
    ["sensor", "binary_sensor", "number", "select", "switch", "water_heater"],
)
def test_entity_has_translation_key(platform):
    """Verify that every entity description has a translation_key set."""
    # Arrange: Load definitions for the specific platform.
    descriptions = get_entity_definitions(platform)

    # Act & Assert: Iterate through all descriptions and verify existence of translation_key.
    for i, desc in enumerate(descriptions):
        key_name = getattr(desc, "key", "UNKNOWN")
        translation_key = getattr(desc, "translation_key", None)
        assert translation_key, (
            f"EntityDescription at index {i} in {platform} is missing a translation_key. Key: {key_name}"
        )


@pytest.mark.parametrize(
    "platform",
    ["sensor", "binary_sensor", "number", "select", "switch", "water_heater"],
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


def test_migrated_entity_icons_are_translated_without_direct_descriptions(
    translations,
) -> None:
    """Keep curated icons translated and out of Python entity metadata."""
    # Arrange: The migration contract preserves the exact former icon values.
    for platform, expected_icons in MIGRATED_ENTITY_ICONS.items():
        descriptions = get_entity_definitions(platform)
        descriptions_by_key = {
            description.translation_key: description for description in descriptions
        }

        # Act and assert: Every locale defines the translated icon with an entity name.
        for source_name, source in translations.items():
            translated_entities = source["entity"][platform]
            for translation_key, expected_icon in expected_icons.items():
                translation = translated_entities[translation_key]
                assert translation["icon"] == expected_icon, (
                    f"{source_name} {platform}.{translation_key} changed its icon"
                )
                assert "name" in translation, (
                    f"{source_name} {platform}.{translation_key} has an orphaned icon"
                )

        # Assert: Entity descriptions defer icon selection to translations.
        for translation_key in expected_icons:
            assert descriptions_by_key[translation_key].icon is None


def test_dhw_mode_translations_match_api_modes(translations):
    """Keep the English DHW mode labels aligned with their API semantics."""
    for translation in (translations["strings"], translations["en"]):
        for platform in ("select", "water_heater"):
            states = translation["entity"][platform][
                "dhw_mode" if platform == "select" else "dhw_water_heater"
            ]["state"]
            assert states["efficient"] == "Eco"
            assert states["efficientWithMinComfort"] == "Comfort"


def test_exception_translation_keys_exist_in_all_maintained_translations(
    translations,
) -> None:
    """Keep every user-facing integration exception translatable."""
    # Arrange: The semantic exception taxonomy is the source of every raised key.
    exception_keys = {key.value for key in ExceptionTranslationKey}

    # Act and assert: Each maintained source must define every exception message.
    for source_name, source in translations.items():
        translated_keys = set(source.get("exceptions", {}))
        assert exception_keys <= translated_keys, (
            f"Missing exception translations in {source_name}: "
            f"{sorted(exception_keys - translated_keys)}"
        )
