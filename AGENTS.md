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

- Python 3.14+ is the project baseline. Follow the Ruff and Pyright
  configuration in `pyproject.toml`; do not duplicate their mechanically
  enforceable rules here.
- Prefer precise types and built-in generics. Avoid expanding `Any` usage;
  tighten existing typing incrementally.
- Use specific exceptions and EAFP where appropriate. Do not catch bare
  `Exception` or leak HTTP-layer exceptions into integration logic.
- Use descriptive identifiers. Avoid single-letter local variables except for
  conventional, short-lived uses; name booleans with `is_`, `has_`, or
  `should_`. Sort collections when their order has no semantic meaning.
- Use `pathlib.Path` for filesystem paths. Keep log messages free of trailing
  periods.
- Start every Python file, including test files, with a concise module docstring
  describing its purpose.
- Use Google-style docstrings for public classes, functions, and methods.
  Describe their purpose and externally observable behavior. Explain design
  rationale or constraints when they are not apparent from the code. Do not
  repeat parameter or return types already present in annotations.
- Include a `Raises:` section for exceptions that are intentionally raised,
  translated, or form a relevant part of the callable's public contract. Do
  not list incidental implementation exceptions that callers cannot reasonably
  handle. Test functions do not require docstrings when their name and
  Arrange-Act-Assert structure describe the scenario clearly.
- Keep comments meaningful and scenario-specific. Explain non-obvious reasons
  and constraints; omit code paraphrases, agent reasoning notes, and abandoned
  implementation plans.
- Use pytest functions and the Home Assistant test stack. Prefer
  `MockViClient` with the `Vitocal250A` fixture; do not mock HTTP requests in
  this integration. Use `MockConfigEntry` when setting up an integration.
- Structure every test according to Arrange-Act-Assert. Add explicit,
  test-specific `# Arrange:`, `# Act:`, and `# Assert:` comments when the test
  is long enough that its phases are not immediately apparent, or when it has
  multiple phases, state transitions, concurrent operations, or substantial
  fixture and mock setup. Do not add comments that merely restate obvious code.
  Use native `assert` statements for values and state, mock assertion helpers
  for interactions, and `pytest.raises` for expected exceptions.
  Exception-focused tests may use `# Act and assert: ...` when separating the
  phases would be artificial. In multi-step scenarios, label each additional
  phase explicitly; do not place new mock setup or actions under an Assert
  comment.
- Use snapshots for discovery and diagnostics coverage; inspect every `.ambr`
  diff rather than accepting it blindly.
- When snapshots or `pytest-homeassistant-custom-component` change, a green
  Linux CI run is required in addition to local validation.

## Local Quality Gate

Set up a development environment with:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install '.[dev]'
pre-commit install --install-hooks
```

Run the complete gate before proposing a commit or push:

```bash
python scripts/quality_check.py
```

The installed pre-commit hook and GitHub CI run the same gate. If dependencies,
snapshots, packaging, or CI configuration change, also validate once in a fresh
`.[dev]` environment.

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
or releases, check `README.md`, this file, `pyproject.toml`, and relevant
`.github/workflows/` files. Update affected documentation in the same change,
or explicitly state that no update was needed.

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
