---
description: Synchronize documentation (README) with the integration codebase
---

# Documentation Update Workflow

This workflow ensures that `README.md` is strictly synchronized with the Home Assistant integration implementation.

## 1. Analysis Phase

Identify which components have changed and require documentation updates.

### Check `README.md`
- **Installation**: Are the HACS and manual installation steps still accurate?
- **Configuration**: Does the configuration flow description match `config_flow.py`?
- **Entities**: Are the examples in "Entities Overview" still representative of `sensor.py`, `binary_sensor.py`, etc.?
- **Troubleshooting**: Are the common issues still relevant?

### Check Global Files
- **`manifest.json`**: Verify that requirements and version match any claims in documentation.
- **`strings.json` / `en.json`**: Ensure that any localized strings or configuration steps mentioned in the README match the actual translation keys.

### Check Platform Files
- **`sensor.py`**, **`binary_sensor.py`**, **`number.py`**, **`switch.py`**, **`select.py`**, **`water_heater.py`**:
    - If new platforms were added, ensure they are listed in the "Entities Overview".
    - If logic for auto-discovery changed, ensure the "Features" section reflects this.

## 2. Verification Steps (The "Meticulous Check")

For *every* piece of code documentation you update:
1.  **Open the source file** alongside the doc file.
2.  **Verify names:** Configuration keys, Entity IDs patterns, Service names.
3.  **Verify logic:** If the docs explain *how* something works (e.g. "polled every 60s"), check `coordinator.py` or relevant constants to confirm.

> [!IMPORTANT]
> If there is *any* discrepancy, the code is the source of truth. Update the documentation to match the code.

## 3. Execution

1.  Make the necessary edits to `README.md`.
2.  **Notify User:** Inform the user that documentation is updated and ready for review/commit.
    > [!NOTE]
    > Do not commit changes automatically. Leave them staged or unstaged for the user.