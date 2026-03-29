# AGENTS.md

This repository keeps its detailed agent guidance in `.agent/`.

Use this file as the bootstrap entry point. The detailed files in `.agent/` are
the canonical source for project-specific rules and workflows.

## Priority and Structure

When working in this repository, use this order:

1. System / developer / tool instructions from the runtime
2. This `AGENTS.md`
3. `.agent/rules/`
4. `.agent/workflows/`

If repository guidance conflicts internally:

- Rules in `.agent/rules/` override workflow convenience steps.
- Newer repository reality overrides stale examples.
- Do not hardcode dependency versions into guidance files unless the exact
  version is genuinely required.

## Always-Relevant Files

Read these first for most non-trivial tasks:

- `.agent/rules/architecture-context.md`
- `.agent/rules/tech-stack.md`
- `.agent/rules/python-style.md`
- `.agent/rules/testing.md`
- `.agent/rules/git-workflow.md`
- `.agent/rules/library-protection.md`

## Workflow Selection

Pick the matching workflow before making substantial changes:

- Feature work: `.agent/workflows/feature-develop.md`
- Releases and tags: `.agent/workflows/release.md`
- PR submission flow: `.agent/workflows/pr-submit.md`
- Test review / test updates: `.agent/workflows/test-compliance-check.md`
- Rules review / agent guidance cleanup: `.agent/workflows/rules-compliance-check.md`
- Documentation-only work: `.agent/workflows/doc-update.md`

## Project Context

- This is a Home Assistant custom integration for Viessmann climate devices.
- Main integration code lives in `custom_components/vi_climate_devices/`.
- Tests live in `tests/`.
- The integration depends on `vi_api_client`, which uses a flat feature model.
- Treat `vi_api_client` as a separate codebase. Do not edit files in
  `/Users/michael/Projekte/vi_api_client/` from this repo workflow.
- `MockViClient` with the `Vitocal250A` fixture is the preferred test client.
- Snapshot coverage is centered on discovery behavior in
  `tests/test_discovery_snapshot.py`.
- Treat `pytest-homeassistant-custom-component` as the authoritative Home
  Assistant test stack. Avoid separately pinning `pytest` ecosystem packages
  unless there is a concrete repo-specific reason.

## Development Baseline

Use the same local install path as CI whenever possible:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install '.[dev]'
```

Primary local quality gates:

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

If a change touches snapshots, test dependencies, CI config, or packaging,
validate once in a fresh environment installed with `.[dev]`.

## CI and Release Notes

- CI currently runs via `.github/workflows/release.yml`.
- `main` is protected by a GitHub ruleset. Assume pull requests are required for
  all changes, including `.agent/` guidance and documentation updates, unless
  the user explicitly asks for a confirmed emergency bypass.
- Python support baseline is 3.14+ across packaging, CI, and repository guidance.
- Prefer matching the current CI Python version locally for verification.
- Home Assistant release versioning is driven by
  `custom_components/vi_climate_devices/manifest.json`.
- Keep `pyproject.toml` package metadata version aligned with
  `custom_components/vi_climate_devices/manifest.json` during releases unless a
  task explicitly requires them to diverge.
- A release is not considered live until both the `main` push run and the tag
  run are green.
- Snapshot and Home Assistant test stack changes must be validated against the
  Linux CI run, not only against local macOS runs. A local green snapshot test
  does not guarantee the same result on GitHub Actions.

## Practical Agent Notes

- Prefer `rg` / `rg --files` for repo search.
- Use `apply_patch` for manual file edits.
- Keep changes minimal and consistent with existing patterns.
- For snapshot updates, inspect the `.ambr` diff instead of blindly accepting it.
- If rules or workflows look stale, update them as part of the task instead of
  working around them silently.
- If important new insights emerge during the work, and those insights should
  be preserved in `AGENTS.md`, a workflow, or a rule file, the agent must
  explicitly propose that documentation update instead of keeping the knowledge
  implicit.
