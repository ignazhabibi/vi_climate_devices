---
trigger: always_on
---

# Tech Stack & Patterns

## 1. Python Version
- Runtime target is Python 3.14+.
- Prefer matching the current CI interpreter for local verification when possible.

## 2. Typing (Strict)
- **No Any:** Avoid `Any` at all costs. Use strict typing (`TypeVar`, `Protocol`).
- **Generics:** Use built-in generics (e.g., `list[str]` instead of `List[str]`).
- **Self:** Do not annotate `self` in methods.

## 3. Static Type Checking
- Use Pyright with the shared configuration in `pyproject.toml`.
- Run `python scripts/quality_check.py` locally. The runner passes its active
  interpreter to Pyright.
- Keep the Pylance type-checking mode aligned with Pyright's configured mode.
- New utility scripts are checked in Pyright strict mode. Expand strict typing
  to integration modules incrementally once they are clean.

## 4. Quality Gate
- Run `python scripts/quality_check.py` for the complete local gate.
- Install the versioned pre-commit hook after the development dependencies.
- The hook and CI both use the same quality-check script.

## 5. Error Handling & Logic
- **Specific Exceptions:** NEVER catch a bare `Exception`. Catch specific errors (e.g., `ValueError`, `FileNotFoundError`).
- **EAFP:** Prefer "Easier to Ask for Forgiveness than Permission" (try/except) over extensive `if` checks where Pythonic.
- **Custom Exceptions:** Define custom exceptions in `exceptions.py`.
- **No Leaking:** Do not raise HTTP-specific exceptions (like `HTTPException`) in the service/library layer. Keep the core logic clean.

## 6. Filesystem
- **Pathlib:** Always use `pathlib.Path`.
    - ❌ Wrong: `os.path.join(a, b)`
    - ✅ Right: `pathlib.Path(a) / b`

## 6. Data Validation
- Use `pydantic` (v2) for internal data models.
