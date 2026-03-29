---
description: analyze changes, bump version, generate changelog, and tag release
---

# Release Workflow

This workflow guides the agent to create a semantic release for the Home Assistant integration.

## 1. Pre-Flight Checks
1.  **Branch Check**: Ensure we are on `main` and fully up-to-date.
    ```bash
    git checkout main && git pull
    ```
2.  **Clean State**: `git status` must show no modified files.
3.  **Local Validation**: Run the same quality gates as CI before tagging.
    ```bash
    ruff check .
    ruff format --check .
    python -m pytest -q
    ```
4.  **Fresh Env Check (when relevant)**: If the change touches test dependencies,
    CI config, snapshots, or packaging metadata, validate once in a fresh
    environment installed via `.[dev]` to catch resolver drift early.
    ```bash
    python3.14 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install '.[dev]'
    python -m pytest -q
    ```

## 2. Analysis & Versioning
1.  **Get Current Version**: Read `version` from `custom_components/vi_climate_devices/manifest.json` and `version` from `pyproject.toml`.
    - These versions should normally match.
    - If they do not match, the agent must call that out explicitly and include the alignment in the release work.
2.  **Analyze Commits**:
    ```bash
    git log --pretty=format:"%h %s" $(git describe --tags --abbrev=0)..HEAD
    ```
    *Note: If no tags exist, just use `git log`.*
3.  **Determine Bump**:
    -   **MAJOR**: Breaking changes (look for `BREAKING CHANGE`, `!:` or explicit notes).
    -   **MINOR**: New features (`feat:`).
    -   **PATCH**: Bug fixes (`fix:`), docs, chores.
4.  **Propose**:
    -   Tell the user the Current Version.
    -   Tell the user whether `manifest.json` and `pyproject.toml` are aligned.
    -   List the changes grouped by type.
    -   Propose the New Version.
    -   **WAIT for Confirmation**.

## 3. Generate Changelog
Create a changelog snippet in the requested style.
**IMPORTANT:** Do NOT summarize. Use the exact commit scope and message from `git log`. Include the commit hash.

```markdown
# Changelog

## Breaking Changes 🚨
<commit_hash> <scope>: <message> (BC)

## New Features 💫
<commit_hash> <scope>: <message>

## Bug Fixes 🐞
<commit_hash> <scope>: <message>

## Other Changes ☀️
<commit_hash> <scope>: <message>
```

## 4. Execution
1.  **Bump Version**: Update `manifest.json` and `pyproject.toml` with the new version.
    ```bash
    # Update both release version sources together.
    python3.14 -c "from pathlib import Path; import json; manifest = Path('custom_components/vi_climate_devices/manifest.json'); data = json.loads(manifest.read_text()); data['version'] = '<NEW_VERSION>'; manifest.write_text(json.dumps(data, indent=2) + '\n'); pyproject = Path('pyproject.toml'); pyproject.write_text(pyproject.read_text().replace('version = \"<OLD_VERSION>\"', 'version = \"<NEW_VERSION>\"', 1)); print('Updated manifest.json and pyproject.toml')"
    ```
2.  **Commit**:
    ```bash
    git add custom_components/vi_climate_devices/manifest.json pyproject.toml
    git commit -m "chore(release): bump version to <NEW_VERSION>"
    ```
3.  **Tag**:
    ```bash
    git -c core.commentChar=";" tag -a v<NEW_VERSION> -m "Release v<NEW_VERSION>" -m "<PASTE_CHANGELOG_HERE>"
    ```
4.  **Push**:
    ```bash
    git push origin main
    git push origin v<NEW_VERSION>
    ```

## 5. Post-Release
- GitHub Actions (if configured) will automatically build and publish the release.
- Do not claim the release is live until:
  - the `main` push run is green, and
  - the tag run for `v<NEW_VERSION>` is green.
- Confirm both runs explicitly:
  ```bash
  gh run list --workflow release.yml --limit 5
  ```
- The Agent should notify the user only after those checks pass.
