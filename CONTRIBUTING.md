# Contributing

## Python

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
## Documentation and Comments

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
## Tests

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
## Snapshots and CI

- Use snapshots for discovery and diagnostics coverage; inspect every `.ambr`
  diff rather than accepting it blindly.
- When snapshots or `pytest-homeassistant-custom-component` change, a green
  Linux CI run is required in addition to local validation.
