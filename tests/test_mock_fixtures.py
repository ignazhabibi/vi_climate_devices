import pytest
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.coordinator import ViClimateDataUpdateCoordinator
from vi_api_client import MockViClient
import re

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

    from custom_components.vi_climate_devices.sensor import SENSOR_TYPES, SENSOR_TEMPLATES
    from custom_components.vi_climate_devices.binary_sensor import (
        BINARY_SENSOR_TYPES,
        BINARY_SENSOR_TEMPLATES,
    )
    from custom_components.vi_climate_devices.number import NUMBER_TYPES, NUMBER_TEMPLATES
    from custom_components.vi_climate_devices.switch import SWITCH_TYPES
    from custom_components.vi_climate_devices.select import SELECT_TYPES

    # Analyze Devices
    for device in coordinator.data.values():
        # Helper map for value lookup
        flat_map = {f.name: f.value for f in device.features_flat}

        # Track results
        created_sensors = {}
        created_binary = {}
        created_numbers = {}
        created_switches = {}
        created_selects = {}

        # Track explicitly covered flat keys (e.g. including properties)
        covered_flat_keys = set()

        # Helper to get value
        def get_simple_value(feature_name, desc, default_prop="value"):
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

        # --- 1. Simulate Number Creation (Hierarchical) ---
        for feature in device.features:
            # BUG FIX: Do NOT unconditionally add feature.name to covered_flat_keys here.
            # It was causing inflated coverage numbers.
            # if feature.name in flat_map:
            #    covered_flat_keys.add(feature.name)

            if feature.name in NUMBER_TYPES:
                for desc in NUMBER_TYPES[feature.name]:
                    val = get_simple_value(feature.name, desc)
                    created_numbers[desc.key] = val

                    prop = getattr(desc, "property_name", None) or getattr(
                        desc, "param_name", None
                    )
                    if prop:
                        covered_flat_keys.add(f"{feature.name}.{prop}")

            elif feature.name in SWITCH_TYPES:
                desc = SWITCH_TYPES[feature.name]
                val = get_simple_value(feature.name, desc, default_prop="active")
                created_switches[desc.key] = val
                prop = getattr(desc, "property_name", None) or "active"
                covered_flat_keys.add(f"{feature.name}.{prop}")

            elif feature.name in SELECT_TYPES:
                desc = SELECT_TYPES[feature.name]
                val = get_simple_value(feature.name, desc)
                created_selects[desc.key] = val
                prop = getattr(desc, "property_name", None) or getattr(
                    desc, "param_name", None
                )
                if prop:
                    covered_flat_keys.add(f"{feature.name}.{prop}")

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

                            val = get_simple_value(feature.name, desc)
                            created_numbers[new_key] = val

                            prop = getattr(desc, "property_name", None) or getattr(
                                desc, "param_name", None
                            )
                            if prop:
                                covered_flat_keys.add(f"{feature.name}.{prop}")
                        break

        # --- 2. Simulate Sensor & Binary Creation (Flat) ---
        for feature in device.features_flat:
            if not feature.is_enabled:
                continue

            # Sensors
            if feature.name in SENSOR_TYPES:
                created_sensors[feature.name] = feature.value
                covered_flat_keys.add(feature.name)
            else:
                for template in SENSOR_TEMPLATES:
                    if re.match(template["pattern"], feature.name):
                        created_sensors[feature.name] = feature.value
                        covered_flat_keys.add(feature.name)
                        break

            # Binary Sensors
            if feature.name in BINARY_SENSOR_TYPES:
                created_binary[feature.name] = feature.value
                covered_flat_keys.add(feature.name)
            else:
                for template in BINARY_SENSOR_TEMPLATES:
                    if re.match(template["pattern"], feature.name):
                        created_binary[feature.name] = feature.value
                        covered_flat_keys.add(feature.name)
                        break

        # --- 3. Determine Missing Features ---
        missing_features = {}
        total_features = 0
        mapped_features = 0

        for feature in device.features_flat:
            if not feature.is_enabled:
                continue

            total_features += 1
            name = feature.name
            if (
                name in created_sensors
                or name in created_binary
                or name in created_numbers
                or name in created_switches
                or name in created_selects
                or name in covered_flat_keys
            ):
                mapped_features += 1
                continue

            missing_features[name] = feature.value

        # Store data for report
        coverage_data.append(
            {
                "device_name": device_name,
                "total": total_features,
                "mapped": mapped_features,
                "sensors": created_sensors,
                "binary": created_binary,
                "numbers": created_numbers,
                "switches": created_switches,
                "selects": created_selects,
                "missing": missing_features,
            }
        )

    # Basic assertions to ensure test still fails on regression
    if "Vitopure" not in device_name:
        assert (
            len(created_sensors)
            + len(created_binary)
            + len(created_numbers)
            + len(created_switches)
            + len(created_selects)
            > 0
        ), "No entities created!"
