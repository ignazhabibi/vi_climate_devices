---
description: Ensure code quality, consistent style, and test coverage before committing.
---
# Quality Assurance & Refactoring Workflow

Follow this checklist to ensure every file meets the project's high standards for Architecture, Style, and Reliability.

> **Principle**: *"Always leave the code cleaner than you found it."* — Robert C. Martin, Clean Code

This principle guides incremental quality improvements during implementation work. The goal is continuous, low-risk enhancement without introducing regressions.

## 1. Naming Conventions

- **Use clear, full names**: Always use descriptive variable, attribute, and method names.
  - ❌ Bad: `k`, `v`, `d`, `m`, `desc`
  - ✅ Good: `key`, `value`, `device`, `mode`, `description`
- **Refactor shortcuts**: If you encounter abbreviated names while working in an area, rename them to full descriptive names.

## 2. Implementation Choices

When making implementation decisions:

- **DO NOT** choose based on what's faster to implement
- **DO** consider long-term codebase health — refactoring that benefits maintainability is valid

**Balance improvement against regression risk. Consider:**
- Code complexity and brittleness
- Test coverage for the affected area
- Scope of your current work
- Impact of potential bugs

## 3. Architectural Integrity (DRY / SRP / YAGNI)

- **DRY (Don't Repeat Yourself)**:
  - [ ] Are there duplicated code blocks (e.g., similar `Device()` construction in tests or CLI)?
  - [ ] *Action*: Extract logic into private helper methods or `utils.py`.

- **SRP (Single Responsibility Principle)**:
  - [ ] Do functions do one clear thing? (e.g., separating parameter validation from command execution).
  - [ ] *Action*: Split large functions. Use the Dispatcher pattern for complex conditional logic.

- **YAGNI (You Ain't Gonna Need It)**:
  - [ ] Are there unused helper methods or redundant properties (like convenience getters that duplicate data)?
  - [ ] *Action*: Delete dead code aggressively.

## 4. Documentation Standards (Google Style)

- **Docstrings**:
  - [ ] Does every public module, class, and method have a docstring?
  - [ ] Do they follow **Strict** Google Style?
    - Must include `Args:`, `Returns:`, and `Raises:` sections where applicable.
    - One-line summaries only for very simple properties without arguments.
  - [ ] *Action*: Update docstrings to be comprehensive.

- **Type Hints**:
  - [ ] Are all arguments and return values typed?
  - [ ] **NO** `Any` types unless absolutely necessary (must have a comment explaining why).
  - [ ] Use `Optional`, `Union`, or specific protocols instead of loose typing.

- **Comment Standards**:
  - [ ] **NO** "thought process" comments (e.g. "I think we should do X", "Trying to fix Y").
  - [ ] **NO** redundant comments explaining obvious code (e.g. `i += 1 # increment i`).
  - [ ] **ONLY** Professional "Senior Dev" comments: Explain **WHY** something is done if it's non-obvious, or clarify complex constraints.
  - [ ] *Action*: Remove any internal monologue or trivial comments.

## 5. Linting (Ruff)

- **Run Linter**:
  ```bash
  // turbo
  ruff check . --fix
  ```
  - [ ] Fix any remaining errors manually (complexity, line length, unused imports).

## 6. Testing & Verification

### Testing Guidelines

| Scenario | Action |
|----------|--------|
| No tests exist for code you're touching | Add tests for the specific behavior you're implementing/fixing, without refactoring existing code |
| Tests exist but coverage is low | Add tests for gaps if you're already working in that area |
| Tests exist, quality is low | Improve test quality if it's straightforward (better assertions, clearer names, remove duplication) |

### Test Structure (AAA Pattern)

- **Arrange**: Set up the test state (mocks, config).
- **Act**: Execute the function under test.
- **Assert**: Verify the results strictly.
- *Action*: Ensure tests follow this structure with clear comments separating sections.

### Checklist

- **Updates**:
  - [ ] If logic changed, were tests updated?
  - [ ] Do tests use the new API patterns (e.g. `set_feature` instead of `execute_command`)?

- **Run Tests**:
  ```bash
  // turbo
  pytest
  ```
  - [ ] **ALL** tests must pass. No regressions allowed.

## 7. Documentation Sync

- **User Docs**:
  - [ ] Did the API signature change? Update `docs/`.
  - [ ] Update `README.md` if high-level usage examples changed.

## 8. Commit

- **Sign-off**: Only commit when all above checks are Green.
