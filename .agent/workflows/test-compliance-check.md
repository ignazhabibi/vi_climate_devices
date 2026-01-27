---
description: Check and enforce compliance of a test file with testing.md rules (AAA, ViMockClient)
---

# Test Compliance Check

This workflow is designed to refactor a specific test file to meet the strict standards defined in `.agent/rules/testing.md`.

## 1. Preparation Phase

1.  **Read Rules**: Open and read `.agent/rules/testing.md` to load the latest standards into your context.
2.  **Read Target**: Open the target test file (e.g., `tests/test_something.py`).

## 2. Analysis Phase (Mental Check)

Analyze the target file against these critical criteria:

*   **Structure**: Does it use `def test_...():` functions (NO classes)?
*   **AAA Pattern**: Does *every* test function have explicit, specific `# Arrange`, `# Act`, `# Assert` comments?
    *   *Bad*: `# Arrange` (generic)
    *   *Good*: `# Arrange: Setup Vitocal250A mock and integration.`
*   **Mocking**:
    *   Does it use `respx`? (Forbidden -> Must Change)
    *   Does it use `AsyncMock` for data objects? (Discouraged -> Prefer `MockViClient`)
    *   Does it usage `MockViClient`? (Required/Preferred)
*   **Style (Ref: .agent/rules/python-style.md)**:
    *   **NO single-letter variables** (e.g., `k, v` in loops -> `key, value`).
    *   **Comments**: Full sentences with periods.
    *   **Logging**: No f-strings in `_LOGGER` calls.

## 3. Remediation Phase (Execution)

If the file violates any rules, **Rewrite the file** (or specific functions) to comply.

### Step 3.1: Convert to MockViClient
If the test manually constructs deep mock objects, replace them with `MockViClient`:
```python
# Old
mock_device = AsyncMock()
mock_device.features = [...]

# New
from vi_api_client.mock_client import MockViClient
mock_client = MockViClient(device_name="Vitocal250A")
with patch("custom_components.vi_climate_devices.ViessmannClient", return_value=mock_client):
    ...
```

### Step 3.2: Enforce AAA
Insert or update comments to be specific:
```python
# --- ARRANGE ---
# 1. Setup mock config entry...
# 2. Patch ViClient...

# --- ACT ---
await hass.config_entries.async_setup(entry.entry_id)

# --- ASSERT ---
state = hass.states.get("...")
assert state.state == "..."
```

## 4. Verification

1.  Run the specific test file: `pytest tests/test_target.py`
2.  Ensure it passes.
