---
trigger: always_on
---

# Python Style Guidelines (HA Compatible)

These rules apply strictly to all Python files.

## 1. String Formatting & Logging (CRITICAL)
- **General:** Use **f-strings** for all string interpolation.
- **EXCEPTION - Logging:** Ruff enforces that `_LOGGER` calls do not use eager
  formatting such as f-strings.
- **Log Content:** Log messages must NOT end with a period `.`.

## 2. Ordering & Sorting
- **Imports and identifiers:** Ruff enforces sorted imports and PEP 8 naming.
- **Data Structures:** Constants, content of Lists, and Dictionary Keys must be sorted **alphabetically**.
    - If you create a list of supported features, sort them A-Z.

## 3. Naming Conventions
- **Descriptive Names:** Avoid single-letter variables like `k`, `v`, `d`, `i`.
    - ❌ Wrong: `for k, v in data.items():`
    - ✅ Right: `for key, value in data.items():`
    - ✅ Right: `for index, device in enumerate(devices):`
- **Variables/Functions:** Use `snake_case`.
- **Constants:** Use `UPPER_CASE`.
- **Booleans:** Must start with `is_`, `has_`, or `should_`.
- **Privates:** Use `_leading_underscore` for internal methods.

## 4. Comments
- Must be full sentences.
- Must start with a capital letter.
- Must end with a period `.`.
