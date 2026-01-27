---
trigger: always_on
---

# Testing Standards (HA Integration Context)

These rules apply strictly to the `tests/` directory of the `vi_climate_devices` integration.

## 1. Structure & Organization
- **Mirror Source:** The test structure must mirror the integration structure.
    - `custom_components/vi_climate_devices/sensor.py` -> `tests/test_sensor.py`
    - `custom_components/vi_climate_devices/config_flow.py` -> `tests/test_config_flow.py`
- **Fixtures:**
    - Usage of `pytest-homeassistant-custom-component` snapshots is encouraged for verifying large state dictionaries or diagnostics.
    - Integration-specific JSON fixtures (if any) go in `tests/fixtures/`.

## 2. Framework & Style
- **Framework:** Use `pytest` exclusively.
- **No Classes:** Use simple functions (`def test_...():`), NEVER use `unittest.TestCase` classes.
- **Naming:** Test files start with `test_`. Test functions start with `test_`.
- **Code Style:** Tests MUST follow all rules from `.agent/rules/python-style.md`:
  - **CRITICAL:** No single-letter variables (`f`, `v`, `d`, `i`, `k`) - use `features`, `value`, `data`, `index`, `key`.
  - Comments must be full sentences (capital letter, period)
  - Use f-strings (except in logger calls)
  - Descriptive boolean names (`is_`, `has_`, `should_`)

## 3. The "Arrange-Act-Assert" Pattern (MANDATORY)
Every test function must follow the **Arrange-Act-Assert** structure.

**CRITICAL: AAA comments must be test-specific, NOT generic.**

❌ **Wrong (Generic):**
```python
# Arrange: Prepare test data and fixtures.
# Act: Execute the function being tested.
# Assert: Verify the results match expectations.
```

✅ **Right (Specific):**
```python
# Arrange: Setup mock heat pump, initialize integration.
# Act: Fire a time change event to trigger update.
# Assert: Sensor 'sensor.heat_pump_outdoor_temperature' should be '12.5'.
```

Visually separate these sections with comments if the test is longer than 5 lines.

1.  **Arrange:** Prepare `MockConfigEntry`, configure `ViClient` mocks, and setup the integration in HA.
2.  **Act:** Execute the specific action (setup entry, call service, fire event).
3.  **Assert:** Verify the results using `hass.states.get()` or mock assertions.

## 4. Data & Mocking
- **Mocking Strategy:** Do **NOT** mock HTTP calls (`respx`) directly.
    - **Why?** This is an integration, not the API library. We assume the library (`vi_api_client`) works.
    - **What to Mock:** Mock the `vi_api_client.ViClient` class or use `vi_api_client.ViMockClient`.
- **Integration Setup:** Always use `MockConfigEntry` from `pytest_homeassistant_custom_component.common`.
- **Async:** Mark async tests explicitly with `@pytest.mark.asyncio`.

## 5. One-Shot Example
Follow this exact style for writing entity tests, PREFERRING `ViMockClient` over manual mocks:

```python
import pytest
from unittest.mock import patch
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant
from custom_components.vi_climate_devices.const import DOMAIN
from vi_api_client.mock_client import MockViClient

@pytest.mark.asyncio
async def test_sensor_creation_manual_discovery(hass: HomeAssistant):
    # Arrange: Setup Viessmann integration with MockConfigEntry and MockViClient.
    entry = MockConfigEntry(domain=DOMAIN, data={"client_id": "123", "token": "abc"})
    entry.add_to_hass(hass)

    # Initialize MockViClient with a real fixture (e.g. Vitocal250A)
    # This ensures we test against REAL data structures, not made-up ones.
    mock_client = MockViClient(device_name="Vitocal250A")

    # Patch the internal client creation or the api methods.
    # Since the integration instantiates ViClient (aliased), we can patch the class itself
    # to return our mock_client instance.
    with patch(
        "custom_components.vi_climate_devices.ViessmannClient",
        return_value=mock_client
    ):
        # Act: Initialize the integration (setup entry)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Assert: Verify the 'outside value' sensor has the correct state from the fixture.
        state = hass.states.get("sensor.viessmann_outside_temperature")
        assert state is not None
        assert state.state == "5.5" # Example value from fixture
        assert state.attributes["unit_of_measurement"] == "°C"
```

## 6. Snapshot Testing (Hybird Strategy)

We use a **Hybrid Strategy** combining manual assertions and snapshots.

### 6.1 When to use what?
*   **Manual Assertions (`assert state == "12.2"`):**
    *   Use for **Unit Tests** of specific entities (Sensors, Switches, Numbers).
    *   **Goal:** Verify the **Business Logic** (Value Parsing, Unit Conversion).
    *   **Reason:** Explicit assertions document the expected behavior and make it easy to debug *why* a logic change failed.
*   **Snapshot Testing (`syrupy`):**
    *   Use for **Discovery Tests** (`test_init_snapshot.py`) and **Diagnostics**.
    *   **Goal:** Verify the **Mass Creation** of entities (Registry consistency).
    *   **Reason:** Ensures we don't accidentally lose entities or change IDs/Attributes across the entire portfolio (Regression Safety).

### 6.2 Snapshot Workflow
1.  **Create:** Run `pytest ... --snapshot-update` to generate/update the `.ambr` file.
2.  **Verify:** Manually inspect the `.ambr` file. **This is the critical step.**
3.  **Commit:** Check the `.ambr` file into Git.

## 7. Mock Data Integrity
- **Authenticity:** When mocking response data for `ViClient`, try to use data structures that match reality.
- **Use MockViClient:** Whenever possible, use the `MockViClient` from the library to provide realistic, comprehensive device data trees instead of manually constructing partial mocks.
- **Deterministic:** Tests must be deterministic. Reliance on `MockViClient` fixtures ensures consistent values (e.g., Temperature is always "12.2") regardless of real-world interactions.