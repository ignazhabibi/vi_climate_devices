---
trigger: always_on
---

# Git & Development Workflow

Strict guidelines for version control and feature development.

## 1. Core Principle: The "Main is Sacred" Rule
- **NEVER** commit directly to `main`.
- `main` is protected by a GitHub ruleset. Treat pull requests as required for
  all changes, including documentation and `.agent/` guidance updates, unless
  the user explicitly asks for an emergency bypass and confirms the tradeoff.
- `main` must always be green (passing CI).
- All work happens in short-lived feature branches.

## 2. Feature Branch Lifecycle ("The Daily Loop")

### A. Start (Clean Slate)
1. `git checkout main`
2. `git pull` (Synch with upstream)
3. `git checkout -b feature/<descriptive-name>`

### B. Develop (The Loop)
1. Write code (`src/` and `tests/`).
2. **Local Tests**: Run `python -m pytest -q` frequently.
3. **Local Lint**: Run `ruff check .` and `ruff format --check .` before every commit.
4. **Commit**: `git commit -m "type: description"` (Conventional Commits).
   - Preferred format in this repository is `type: description`.
   - Use `feat`, `fix`, `refactor`, `docs`, `test`, or `chore`.
   - Do not require a scope by default.

### C. Submit (The Gatekeeper)
1. `git push -u origin feature/<name>`
2. **User Action**: Create Pull Request (PR) on GitHub.
3. **CI Check**: Wait for "Quality Check" pipeline to pass.
4. **Merge**: User performs "Squash and merge" on GitHub.
5. **Cleanup**: User deletes branch on GitHub.

### D. Re-Sync (Local Cleanup)
1. `git checkout main`
2. `git pull` (Get the squashed merge).
3. `git branch -d feature/<name>` (Verify delete).

## 3. Release Process (Only when ready)
1. **Version Bump**: Update `version` in `custom_components/vi_climate_devices/manifest.json`.
2. **Commit**: `chore: bump version to X.Y.Z`
3. **Tag**: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. **Push Tag**: `git push origin vX.Y.Z`
   - *This triggers the Release Workflow on GitHub.*
5. **Optional Pre-release Tags**: For Home Assistant validation before a stable
   release, use semver prerelease tags such as `vX.Y.Z-alpha.N`,
   `vX.Y.Z-beta.N`, or `vX.Y.Z-rc.N`.
   - *These trigger the dedicated Pre-release Workflow and create a GitHub
     prerelease instead of a stable release.*

## 4. Agent Role & Permissions
- **Allowed**: `git checkout -b`, `git add`, `git commit`, `git push`.
- **Forbidden**: `git merge` (User does this via UI), committing to `main`
  outside an explicitly approved emergency bypass.
- **Validation**: The Agent must run `ruff check .`, `ruff format --check .`, and `python -m pytest -q` before proposing a push.
