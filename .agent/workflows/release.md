---
description: analyze changes, bump version, generate changelog, and tag release
---

# Release Workflow

This workflow guides the agent to create a semantic release for the Home Assistant integration.

## 1. Pre-Flight Checks
1.  **Branch Check**: Ensure `main` is fully up-to-date.
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

## 3. Message Hierarchy
Use different message styles for commits, pull requests, and releases.

- **Commit messages**: Atomic and technical. Follow the repository format
  `type: description`.
- **PR titles and bodies**: Summarize the full branch for reviewers.
- **Release notes**: Summarize multiple merged PRs for users. Favor user-facing
  outcomes over raw commit history.

## 4. Generate Changelog
Create a changelog snippet in the requested style.
**IMPORTANT:** Do summarize at the release level. Group related merged work into
user-facing entries instead of replaying raw commit subjects line by line.
Reference PRs or commits when useful, but do not depend on scopes being present.

```markdown
# Changelog

## Breaking Changes 🚨
<summary> (PR #xx, commit <hash>) (BC)

## New Features 💫
<summary> (PR #xx, commit <hash>)

## Bug Fixes 🐞
<summary> (PR #xx, commit <hash>)

## Other Changes ☀️
<summary> (PR #xx, commit <hash>)
```

## 5. Execution
1.  **Create Release Branch**:
    ```bash
    git checkout -b release/v<NEW_VERSION>
    ```
2.  **Bump Version**: Update `manifest.json` and `pyproject.toml` with the new version on the release branch.
    ```bash
    # Update both release version sources together.
    python3.14 -c "from pathlib import Path; import json; manifest = Path('custom_components/vi_climate_devices/manifest.json'); data = json.loads(manifest.read_text()); data['version'] = '<NEW_VERSION>'; manifest.write_text(json.dumps(data, indent=2) + '\n'); pyproject = Path('pyproject.toml'); pyproject.write_text(pyproject.read_text().replace('version = \"<OLD_VERSION>\"', 'version = \"<NEW_VERSION>\"', 1)); print('Updated manifest.json and pyproject.toml')"
    ```
3.  **Commit**:
    ```bash
    git add custom_components/vi_climate_devices/manifest.json pyproject.toml
    git commit -m "chore: bump version to <NEW_VERSION>"
    ```
4.  **Push Release Branch & PR**:
    ```bash
    git push -u origin release/v<NEW_VERSION>
    ```
5.  **Merge PR**:
    - Open a pull request from `release/v<NEW_VERSION>` into `main`.
    - Wait until the PR `quality-check` is green.
    - Merge the PR on GitHub.
6.  **Refresh Local Main**:
    ```bash
    git checkout main
    git pull origin main
    ```
7.  **Tag the Merged Main Commit**:
    ```bash
    git -c core.commentChar=";" tag -a v<NEW_VERSION> -m "Release v<NEW_VERSION>" -m "<PASTE_CHANGELOG_HERE>"
    git push origin v<NEW_VERSION>
    ```

## 6. Post-Release
- GitHub Actions (if configured) will automatically build and publish the release.
- Do not claim the release is live until:
  - the PR merge produced a green `main` push run, and
  - the tag run for `v<NEW_VERSION>` is green.
- Perform a final documentation drift check for release-related guidance:
  - `README.md`
  - `AGENTS.md`
  - `.agent/rules/tech-stack.md`
  - `.agent/rules/git-workflow.md`
  - `.agent/workflows/release.md`
  Update them in the same task if the release changed versioning policy,
  dependency/update policy, CI expectations, or release procedure assumptions.
- Confirm both runs explicitly:
  ```bash
  gh run list --workflow release.yml --limit 5
  ```
- The Agent should notify the user only after those checks pass.
