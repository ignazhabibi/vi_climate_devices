import re

import pytest
from homeassistant.core import HomeAssistant
from vi_api_client import MockViClient

from custom_components.vi_climate_devices.binary_sensor import (
    BINARY_SENSOR_TEMPLATES,
    BINARY_SENSOR_TYPES,
)
from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.number import (
    NUMBER_TEMPLATES,
    NUMBER_TYPES,
)
from custom_components.vi_climate_devices.select import SELECT_TYPES
from custom_components.vi_climate_devices.sensor import (
    SENSOR_TEMPLATES,
    SENSOR_TYPES,
)
from custom_components.vi_climate_devices.switch import SWITCH_TYPES

# List of available mock devices provided by the user/library
MOCK_DEVICES = [
    "Vitocal151A",
    "Vitocal200",
    "Vitocal252",
    "Vitocal300G",
    "Vitodens050W",
    "Vitodens200W",
    "Vitodens300W",
    "VitolaUniferral",
    "Vitopure350",
]


REPORT_FILE = "MOCK_COVERAGE.md"


@pytest.fixture(scope="session")
def coverage_data():
    """Accumulate coverage data across tests."""
    data = []
    yield data

    # TEARDOWN: Write the full report
    with open(REPORT_FILE, "w") as f:
        f.write("# ViClimate Integration Coverage Report\n\n")
        f.write("Generated automatically during `test_mock_fixtures.py`.\n\n")

        # --- Summary Table ---
        f.write("## Overview\n\n")
        f.write("| Device | Coverage | Mapped / Total | Missing Count |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")

        # Sort by device name
        sorted_data = sorted(data, key=lambda x: x["device_name"])

        for entry in sorted_data:
            name = entry["device_name"]
            total = entry["total"]
            mapped = entry["mapped"]
            missing = total - mapped
            percent = (mapped / total * 100) if total > 0 else 0
            f.write(
                f"| [{name}](#{name.lower()}) | **{percent:.1f}%** | {mapped} / {total} | {missing} |\n"
            )

        f.write("\n## Detailed Breakdown\n\n")

        # --- Details ---
        for entry in sorted_data:
            name = entry["device_name"]
            f.write(f"### {name}\n\n")

            # Entities
            for cat, items in [
                ("Sensors", entry["sensors"]),
                ("Binary Sensors", entry["binary"]),
                ("Number Entities", entry["numbers"]),
                ("Switch Entities", entry["switches"]),
                ("Select Entities", entry["selects"]),
            ]:
                f.write(f"#### ✅ Created {cat} ({len(items)})\n")
                if items:
                    for k, v in sorted(items.items()):
                        f.write(f"- `{k}`: {v}\n")
                else:
                    f.write("- *None*\n")
                f.write("\n")

            # Missing
            missing_map = entry["missing"]
            f.write(f"#### ⚠️ Enabled Features WITHOUT Entity ({len(missing_map)})\n")
            if missing_map:
                f.write(
                    "> These features are enabled on the device but have no mapped entity.\n\n"
                )
                for k, v in sorted(missing_map.items()):
                    f.write(f"- `{k}`: {v}\n")
            else:
                f.write("- *All enabled features covered!*\n")

            f.write("\n---\n\n")


@pytest.mark.asyncio
@pytest.mark.parametrize("device_name", MOCK_DEVICES)
async def test_mock_device_features(
    hass: HomeAssistant, device_name: str, coverage_data
):
    """Test compatibility and generate coverage report."""

    # Initialize Mock Client
    try:
        client = MockViClient(device_name=device_name)
    except FileNotFoundError:
        pytest.skip(f"Fixture for {device_name} not found.")

    # Setup Coordinator
    coordinator = ViClimateDataUpdateCoordinator(hass, client)

    # Refresh Data
    try:
        data = await coordinator._async_update_data()
        coordinator.data = data
    except Exception as e:
        pytest.fail(f"Update failed: {e}")

    # Analyze Devices
    for device in coordinator.data.values():
        coverage_entry = _analyze_device_coverage(device, device_name)
        coverage_data.append(coverage_entry)

        # Basic assertions to ensure test still fails on regression
        if "Vitopure" not in device_name:
            total_entities = (
                len(coverage_entry["sensors"])
                + len(coverage_entry["binary"])
                + len(coverage_entry["numbers"])
                + len(coverage_entry["switches"])
                + len(coverage_entry["selects"])
            )
            assert total_entities > 0, "No entities created!"


def _analyze_device_coverage(device, device_name):
    """Analyze a single device for feature coverage."""
    # Helper map for value lookup
    flat_map = {f.name: f.value for f in device.features_flat}

    # State tracking
    context = {
        "flat_map": flat_map,
        "created": {
            "sensors": {},
            "binary": {},
            "numbers": {},
            "switches": {},
            "selects": {},
        },
        "covered_flat_keys": set(),
    }

    # 1. Simulate Number/Switch/Select Creation
    _simulate_config_entities(device, context)

    # 2. Simulate Sensor & Binary Creation
    _simulate_sensor_entities(device, context)

    # 3. Determine Missing Features
    missing_features = _find_missing_features(device, context)

    return {
        "device_name": device_name,
        "total": len([f for f in device.features_flat if f.is_enabled]),
        "mapped": len([f for f in device.features_flat if f.is_enabled])
        - len(missing_features),
        "sensors": context["created"]["sensors"],
        "binary": context["created"]["binary"],
        "numbers": context["created"]["numbers"],
        "switches": context["created"]["switches"],
        "selects": context["created"]["selects"],
        "missing": missing_features,
    }


def _get_simple_value(context, feature_name, desc, default_prop="value"):
    flat_map = context["flat_map"]
    prop = (
        getattr(desc, "property_name", None)
        or getattr(desc, "param_name", None)
        or default_prop
    )
    prop_key = f"{feature_name}.{prop}"
    if prop_key in flat_map:
        return flat_map[prop_key]
    if feature_name in flat_map:
        return flat_map[feature_name]  # Fallback
    return "N/A"


def _simulate_config_entities(device, context):
    """Simulate creation of configuration entities (Numbers, Switches, Selects)."""
    created = context["created"]
    covered = context["covered_flat_keys"]

    for feature in device.features:
        if feature.name in NUMBER_TYPES:
            for desc in NUMBER_TYPES[feature.name]:
                val = _get_simple_value(context, feature.name, desc)
                created["numbers"][desc.key] = val
                _mark_covered(covered, feature.name, desc)

        elif feature.name in SWITCH_TYPES:
            desc = SWITCH_TYPES[feature.name]
            val = _get_simple_value(context, feature.name, desc, default_prop="active")
            created["switches"][desc.key] = val
            prop = getattr(desc, "property_name", None) or "active"
            covered.add(f"{feature.name}.{prop}")

        elif feature.name in SELECT_TYPES:
            desc = SELECT_TYPES[feature.name]
            val = _get_simple_value(context, feature.name, desc)
            created["selects"][desc.key] = val
            _mark_covered(covered, feature.name, desc)

        else:
            # Number Templates
            for template in NUMBER_TEMPLATES:
                match = re.match(template["pattern"], feature.name)
                if match:
                    groups = match.groups()
                    index = groups[0]
                    program = groups[1] if len(groups) > 1 else None

                    for desc in template["descriptions"]:
                        if program:
                            new_key = desc.key.format(index, program)
                        else:
                            new_key = desc.key.format(index)

                        val = _get_simple_value(context, feature.name, desc)
                        created["numbers"][new_key] = val
                        _mark_covered(covered, feature.name, desc)
                    break


def _mark_covered(covered_set, feature_name, desc):
    prop = getattr(desc, "property_name", None) or getattr(desc, "param_name", None)
    if prop:
        covered_set.add(f"{feature_name}.{prop}")


def _simulate_sensor_entities(device, context):
    """Simulate creation of Sensor and BinarySensor entities."""
    created = context["created"]
    covered = context["covered_flat_keys"]

    for feature in device.features_flat:
        if not feature.is_enabled:
            continue

        # Sensors
        if feature.name in SENSOR_TYPES:
            created["sensors"][feature.name] = feature.value
            covered.add(feature.name)
        else:
            for template in SENSOR_TEMPLATES:
                if re.match(template["pattern"], feature.name):
                    created["sensors"][feature.name] = feature.value
                    covered.add(feature.name)
                    break

        # Binary Sensors
        if feature.name in BINARY_SENSOR_TYPES:
            created["binary"][feature.name] = feature.value
            covered.add(feature.name)
        else:
            for template in BINARY_SENSOR_TEMPLATES:
                if re.match(template["pattern"], feature.name):
                    created["binary"][feature.name] = feature.value
                    covered.add(feature.name)
                    break


def _find_missing_features(device, context):
    """Identify enabled features that were not mapped."""
    missing = {}
    created = context["created"]
    covered = context["covered_flat_keys"]

    for feature in device.features_flat:
        if not feature.is_enabled:
            continue

        name = feature.name
        if (
            name in created["sensors"]
            or name in created["binary"]
            or name in created["numbers"]
            or name in created["switches"]
            or name in created["selects"]
            or name in covered
        ):
            continue

        missing[name] = feature.value
    return missing
