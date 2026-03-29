---
description: Synchronize repository documentation with the current codebase, tooling, and workflow reality
---

# Documentation Update Workflow

This workflow ensures that repository-operational documentation stays
self-contained and synchronized with the current Home Assistant integration
implementation, tooling, and workflow reality.

## 1. Analysis Phase

Identify which parts of the repository changed and which documentation surfaces
must be updated together.

### Check `README.md`
- **Installation**: Are the HACS and manual installation steps still accurate?
- **Configuration**: Does the configuration flow description match `config_flow.py`?
- **Entities**: Are the examples in "Entities Overview" still representative of `sensor.py`, `binary_sensor.py`, etc.?
- **Troubleshooting**: Are the common issues still relevant?

### Check `AGENTS.md`
- **Bootstrap Guidance**: Does the agent entrypoint still describe the correct
  always-relevant files, workflows, and mandatory checks?
- **Operational Truths**: Do CI, release, setup, and governance notes match the
  current repository reality?

### Check `.agent/rules/`
- **`architecture-context.md`**: Do architecture assumptions still match the
  actual integration and library usage?
- **`tech-stack.md`**: Does the documented Python/tooling/dependency baseline
  still match the project?
- **Other Rules**: Do testing, git, and library protection rules still reflect
  how the repo is actually maintained?

### Check `.agent/workflows/`
- **Workflow Triggers**: Does each workflow still match how work is really
  performed in this repository?
- **Protected Branch Reality**: Do branch, PR, release, and commit steps match
  current GitHub governance?
- **Validation Steps**: Do local and CI checks in the workflows still match the
  actual commands used by the repo?

### Check Global Files
- **`manifest.json`**: Verify that requirements and version match any claims in documentation.
- **`strings.json` / `en.json`**: Ensure that any localized strings or configuration steps mentioned in the README match the actual translation keys.

### Check Platform Files
- **`sensor.py`**, **`binary_sensor.py`**, **`number.py`**, **`switch.py`**, **`select.py`**, **`water_heater.py`**:
    - If new platforms were added, ensure they are listed in the "Entities Overview".
    - If logic for auto-discovery changed, ensure the "Features" section reflects this.

## 2. Verification Steps (The "Meticulous Check")

For every documentation surface you update:
1.  **Open the source file** alongside the doc file.
2.  **Verify names:** Configuration keys, Entity IDs patterns, Service names.
3.  **Verify logic:** If the docs explain how something works (e.g. branch
    protection, release steps, "polled every 60s"), check the actual workflow,
    code, or GitHub setup evidence first.

> [!IMPORTANT]
> If there is *any* discrepancy, the code is the source of truth. Update the documentation to match the code.

## 3. Execution

1.  Update every affected documentation surface, not just `README.md`.
2.  If architecture, tech stack, testing strategy, CI, release flow, or GitHub
    governance changed, ensure the relevant rule/workflow files are updated in
    the same task.
3.  In the final handoff, explicitly state which documentation files were
    checked and whether any remained unchanged after review.
