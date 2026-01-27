---
trigger: always_on
---

# Home Assistant Integration Context & Rules (Viessmann)

**Target Agent**: HA Integration Developer Agent
**Library Version**: 0.3.3 (Flat Architecture)
**GitHub**: [https://github.com/ignazhabibi/vi_api_client](https://github.com/ignazhabibi/vi_api_client)

## 1. High-Level Context
You are building a Home Assistant integration for **Viessmann Climate Solutions** devices (Heat Pumps, Gas Boilers, etc.).
The integration utilizes the asynchronous Python library `vi_api_client`.

> [!IMPORTANT]
> **Primary Directive**: The library uses a **FLAT ARCHITECTURE**. Do not look for nested properties. All data points are flattened into a simple list of `Feature` objects with dot-notation names (e.g., `heating.sensors.temperature.outside`).

> [!TIP]
> **Source Code**: When in doubt, strictly inspect the library source code! The library is installed from GitHub, so you have full access to the implementation details which act as the source of truth.

## 2. Library Architecture

### 2.1 Core Classes
*   **`ViClient`** (`vi_api_client.api.ViClient`): The main entry point.
    *   `get_full_installation_status(installation_id, only_enabled=True)`: Initial discovery.
    *   `update_device(device, only_enabled=True)`: Refreshes a device's features. Returns a **NEW** `Device` object.
    *   `set_feature(device, feature, value)`: Sends a command. Returns `CommandResponse`.
*   **`Device`**: Represents a physical device (Boiler, Heat Pump).
    *   `features`: A list of `Feature` objects.
    *   **Immutable**: You cannot update a device object in-place. You must replace it with the result of `update_device`.
*   **`Feature`**: A single data point.
    *   `name` (str): Unique ID (e.g., `heating.circuits.0.heating.curve.slope`).
    *   `value` (Any): Current state (float, string, bool).
    *   `is_ready` (bool): Whether the feature is ready for interaction.
    *   `is_enabled` (bool): Whether the feature is enabled.
    *   `control` (`FeatureControl`, optional): Metadata for writing.
    *   **Property**: `is_writable` (bool) -> returns `True` if `control` is not None.

### 2.2 The "Flat" Model
Instead of navigating deep JSON trees, you search for features by name in the flat list.
*   **Method**: `device.get_feature("heating.circuits.0.heating.curve.slope").value`

## 3. Mocking & Verification Strategy (MANDATORY)
To ensure robustness without requiring a live device, you **MUST** use the Mocking capabilities during development and testing.

*   **`ViMockClient`**: A drop-in replacement for `ViClient` that loads data from local JSON fixtures.
*   **Preferred Fixture**: `Vitocal250A` (Heat Pump). It is the most modern and feature-rich device reference.
*   **Usage**:
    ```python
    from vi_api_client.mock_client import ViMockClient
    # Argument is 'device_name' which must match a filename in fixtures/ (e.g., Vitocal250A.json)
    client = ViMockClient(device_name="Vitocal250A")
    # ... usage is identical to ViClient ...
    device = await client.get_devices(...)
    # Now you can test entity creation against real data structures
    ```

## 4. Integration PRD (Product Requirements)

### 4.1 Hybrid Discovery Strategy
The integration must use a **Hybrid Discovery** approach to balance quality and coverage.

#### Priority A: "Defined" Entities (Gold Standard)
*   **Goal**: Perfect names, icons, and translation keys for core features.
*   **Mechanism**: A manual mapping of specific Feature Names to Entity Definitions.
> [!IMPORTANT]
> **Preservation Rule**: Existing "beautiful" entities defined in previous versions MUST NOT be deleted or replaced by auto-discovery.

*   **Scope (Exemplary, NOT Exhaustive)**:
    *   Climate control (Room Temp, Modes).
    *   Heating Curve (Slope, Shift).
    *   Water Heater (DHW Temperature).
    *   Primary Sensors (Outside Temp, Power Consumption, COP).

#### Priority B: "Automatic" Discovery (Fallback)
*   **Goal**: Support *any* feature exposed by the API, even if not manually mapped.
*   **Mechanism**: Iterate through `device.features`. If a feature is NOT in the "Defined" map:
    1.  **Read-Only**: Create `Sensor` (or `BinarySensor` if bool).
    2.  **Writable + Number control**: Create `Number` entity.
    3.  **Writable + Enum options**: Create `Select` entity.
    4.  **Writable + Boolean**: Create `Switch` entity.
    5.  **Writable + Action**: Create `Button` entity.

    **Unit Mapping (Automatic Sensors)**
    When creating entities automatically, map `feature.unit` to HA constants as follows:

    | feature.unit | Device Class | State Class | Unit Const |
    | :--- | :--- | :--- | :--- |
    | `celsius` | `TEMPERATURE` | `MEASUREMENT` | `UnitOfTemperature.CELSIUS` |
    | `bar` | `PRESSURE` | `MEASUREMENT` | `UnitOfPressure.BAR` |
    | `percent` | `POWER_FACTOR` (if applicable) or None | `MEASUREMENT` | `PERCENTAGE` |
    | `kilowattHour` | `ENERGY` | `TOTAL_INCREASING` | `UnitOfEnergy.KILO_WATT_HOUR` |
    | `watt` | `POWER` | `MEASUREMENT` | `UnitOfPower.WATT` |
    | `volumetricFlow` | `VOLUME_FLOW_RATE` | `MEASUREMENT` | (e.g. `m³/h` - verify API unit) |

### 4.2 Coordinator & Updates
*   **Efficient Polling**: Do NOT poll individual features.
*   **Atomic Update**: use `client.update_device(device)`. This fetches only enabled features in a single call.
*   **State Management**: The `Coordinator.data` should store the **Device Objects** keyed by their unique ID (GatewaySerial + DeviceID).

### 4.3 Entity Implementation Rules
1.  **Value Access**: Always access `feature.value`.
    *   Handle `NotConnected` string in sensors (return `None`/Unavailable).
2.  **Writing Values**: Use `client.set_feature`.
    *   The library automatically handles dependency resolution (e.g., finding the correct command name and sibling parameters).
    *   **Do not** construct raw JSON payloads manually.
3.  **Constraints**: Initialize `min_value`, `max_value`, `step`, and `options` from `feature.control` during entity setup.

## 5. Development Checklist
1.  Implement Coordinator with `update_device`.
2.  Implement "Defined" entities (refer to `HA_INTEGRATION_HANDOVER.md` for specific mappings).
3.  Implement "Auto" discovery logic.
4.  **VERIFY** all entities using `ViMockClient` with `Vitocal250A`. Ensure no crashes on missing fields.
