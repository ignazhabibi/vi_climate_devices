# AGENTS.md

## Scope and Priorities

Follow runtime instructions first, then this file, then the repository's
configured tooling. Treat the implementation and configuration as newer than
examples or assumptions in documentation.

Keep changes small and directly related to the request. Do not refactor or
clean up unrelated code. State assumptions and tradeoffs when they materially
affect the solution.

## Project Context

- This is a Home Assistant custom integration for Viessmann climate devices.
- Integration code is in `custom_components/vi_climate_devices/`; tests are in
  `tests/`.
- `vi_api_client` is a separate codebase. Never edit its files from this
  repository. Explain the required library change, its rationale, and the
  expected version bump instead.
- The client has a flat feature model: look up dot-named `Feature` objects with
  `device.get_feature(...)`; do not navigate nested API properties.
- A refreshed device returned by `update_device` replaces the old object. Use
  `set_feature` for writes; do not construct raw API payloads.
- Preserve explicitly defined entities. Automatic discovery is a fallback for
  unmapped features.
- Keep the single-coordinator model. Do not poll individual features or add a
  separate analytics coordinator without an explicit product decision.

## Python and Tests

For Python implementation, test, or review work, read
[CONTRIBUTING.md](CONTRIBUTING.md) before starting.

## Local Quality Gate

Before proposing a commit or push, run the complete quality gate. For
development setup and commands, read the [Development](README.md#development)
section in `README.md`.

## Git, Pull Requests, and Releases

- `main` is protected. Use short-lived branches and pull requests; never
  commit or merge directly to `main` without an explicitly confirmed emergency
  bypass.
- Stage only requested files. Before committing, show the files, summary, and
  proposed Conventional Commit message; no additional confirmation is needed.
- Wait for the GitHub `quality-check` job before treating a PR as merge-ready.
  Use GitHub squash merge only with explicit authorization.
- After a merge, fast-forward local `main` and delete the confirmed merged
  local branch.
- Releases must keep `pyproject.toml` and `manifest.json` versions aligned.
  Propose the version change and changelog before committing. Tag only the
  merged `main` commit: stable releases use `vX.Y.Z`, prereleases use
  `vX.Y.Z-alpha.N`, `-beta.N`, or `-rc.N`. A release is live only after both
  its `main` and tag workflows pass.

## Documentation Drift

After changes to architecture, dependencies, setup, tests, CI, GitHub policy,
or releases, check `README.md`, `CONTRIBUTING.md`, `AGENTS.md`,
`pyproject.toml`, and relevant `.github/workflows/` files. Update affected
documentation in the same change, or explicitly state that no update was
needed.

## Agent skills

### Issue tracker

Issues and specs live in this repository's GitHub Issues. See
`docs/agents/issue-tracker.md`.

Write GitHub issues, tickets, and specifications in English, even when the
surrounding conversation is in another language.

### Triage labels

Use the canonical triage-label vocabulary. See
`docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-document layout. See
`docs/agents/domain.md`.
