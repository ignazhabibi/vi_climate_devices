---
description: Ensure code quality, consistent style, and test coverage before committing.
---
# Quality Assurance & Refactoring Workflow

Follow this checklist to ensure every file meets the project's high standards for Architecture, Style, and Reliability.

## 1. Architectural Integrity (DRY / SRP / YAGNI)

- **DRY (Don't Repeat Yourself)**:
  - [ ] Are there duplicated code blocks (e.g., similar `Device()` construction in tests or CLI)?
  - [ ] *Action*: Extract logic into private helper methods or `utils.py`.

- **SRP (Single Responsibility Principle)**:
  - [ ] Do functions do one clear thing? (e.g., separating parameter validation from command execution).
  - [ ] *Action*: Split large functions. Use the Dispatcher pattern for complex conditional logic.

- **YAGNI (You Ain't Gonna Need It)**:
  - [ ] Are there unused helper methods or redundant properties (like convenience getters that duplicate data)?
  - [ ] *Action*: Delete dead code aggressively.

## 2. Documentation Standards (Google Style)

- **Docstrings**:
  - [ ] Does every public module, class, and method have a docstring?
  - [ ] Do they follow Google Style (Args/Returns/Raises)?
  - [ ] *Action*: update docstrings.

- **Type Hints**:
  - [ ] Are all arguments and return values typed?

## 3. Linting (Ruff)

- **Run Linter**:
  ```bash
  // turbo
  ruff check . --fix
  ```
  - [ ] Fix any remaining errors manually (complexity, line length, unused imports).

## 4. Testing & Verification

- **Updates**:
  - [ ] If logic changed, were tests updated?
  - [ ] Do tests use the new API patterns (e.g. `set_feature` instead of `execute_command`)?

- **Run Tests**:
  ```bash
  // turbo
  pytest
  ```
  - [ ] **ALL** tests must pass. No regressions allowed.

## 5. Documentation Sync

- **User Docs**:
  - [ ] Did the API signature change? Update `docs/`.
  - [ ] Update `README.md` if high-level usage examples changed.

## 6. Commit

- **Sign-off**: Only commit when all above checks are Green.
