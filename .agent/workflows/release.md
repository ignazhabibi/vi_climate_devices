---
description: Run tests, lint, bump version, and publish a new release.
---

1. Run the full test suite to ensure stability.
   `pytest tests/`

2. Run linting to ensure code quality.
   `ruff check custom_components/vi_climate_devices tests`

3. Determine the next version number automatically based on Semantic Versioning principles:
   - **Major** (x.0.0): Breaking changes.
   - **Minor** (0.x.0): New features (backwards compatible).
   - **Patch** (0.0.x): Bug fixes.
   Check `pyproject.toml` for the current version.

4. Update the version in `pyproject.toml`.
   - Read `pyproject.toml`.
   - Update `version = "..."`.

5. Update the version in `custom_components/vi_climate_devices/manifest.json`.
   - Read `manifest.json`.
   - Update `"version": "..."`.

6. Commit the changes.
   `git add pyproject.toml custom_components/vi_climate_devices/manifest.json`
   `git commit -m "Bump version to v<VERSION>"`

7. Tag the release.
   `git tag v<VERSION>`

8. Push changes and tags to remote.
   `git push origin main --tags`
