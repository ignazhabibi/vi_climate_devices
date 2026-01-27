---
description: lint, test, commit and push, then create Pull Request
---

# Feature Branch PR Workflow

This workflow enforces the "Main is Sacred" rule. It checks your current branch, commits changes, and helps you create a PR.

## 1. Safety Checks (Agent)

The agent must first verify:
1.  **Branch Check**: Ensure we are NOT on `main`.
    ```bash
    git branch --show-current
    ```
    > [!WARNING]
    > If output is `main`, the Agent must **STOP** and ask the user to start a feature branch.

2.  **Lint & Test**:
    ```bash
    // turbo
    ruff format .
    // turbo
    ruff check --fix custom_components/vi_climate_devices tests
    // turbo
    pytest tests/
    ```
    > [!IMPORTANT]
    > If tests fail, **ABORT**.

3.  **Manifest Check**:
    Verify that `manifest.json` is valid JSON.
    ```bash
    // turbo
    cat custom_components/vi_climate_devices/manifest.json | python3 -c "import sys, json; print('Manifest is valid JSON') if json.load(sys.stdin) else sys.exit(1)"
    ```

## 2. Commit (Agent)

1.  **Stage**: `git add .`
2.  **Commit**: Generate a comprehensive commit message `type(scope): description`.
    - `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
    - Message should be under 50 chars ideally.

## 3. Push & PR (Agent)

1.  **Push**:
    ```bash
    git push -u origin HEAD
    ```

2.  **Create PR**:
    *   **Option A (Best)**: If `gh` CLI is installed:
        ```bash
        gh pr create --fill --web
        ```
    *   **Option B (Fallback)**: If `gh` fails or is missing, **construct and display the URL** for the user:
        `https://github.com/ignazhabibi/vi_climate_devices/pull/new/<BRANCH_NAME>`

    > [!TIP]
    > Always check if `gh` is available with `gh --version` before trying Option A.

## X. Releases

For creating a release (tagging & version bump), please refer to the dedicated workflow:
`release` (see `.agent/workflows/release.md`).