---
description: Review and update agent guidance so rules, workflows, and bootstrap docs remain aligned with repository reality
---

# Rules and Workflow Compliance Check

**Goal:** Keep `AGENTS.md`, `.agent/rules/`, and `.agent/workflows/`
self-contained, current, and internally consistent with the real repository
behavior.

## Instructions

Act as a strict repository guidance reviewer. Audit the guidance files against
the actual codebase, CI, release process, and GitHub governance, then update
them directly where needed.

### Phase 1: Repository Reality Check
1.  **Bootstrap Alignment:**
    *   Verify `AGENTS.md` still points to the right always-relevant files and workflows.
    *   Ensure it reflects current branch protection, CI, release, setup, and test-stack reality.
2.  **Rules Alignment:**
    *   Check `.agent/rules/` for stale assumptions about architecture, tech stack, testing, Git workflow, and library boundaries.
    *   Pay special attention to `architecture-context.md` and `tech-stack.md` whenever architecture or tooling changed.
3.  **Workflow Alignment:**
    *   Check `.agent/workflows/` for stale steps, especially around branches, PRs, release flow, validation commands, and documentation duties.

### Phase 2: Self-Contained Documentation Check
1.  **Coverage:** Ensure repository-operational documentation is treated as one
    system:
    *   `README.md`
    *   `AGENTS.md`
    *   `.agent/rules/`
    *   `.agent/workflows/`
2.  **Durable Knowledge:** If a new insight changed how the repo is actually
    maintained, verify that the insight is captured in the right doc file and
    not left implicit in conversation only.
3.  **No Silent Drift:** If a file is stale, update it as part of the task
    instead of merely noting the discrepancy.

### Phase 3: Required Triggers
Treat guidance updates as mandatory when the task changed any of the following:

- architecture or discovery assumptions
- tech stack, Python baseline, or dependency strategy
- test strategy, snapshot handling, or CI authority
- local setup commands
- release versioning or tagging flow
- GitHub governance such as branch protection or PR requirements

## Output
Apply the necessary guidance updates directly. Afterwards:

- summarize what guidance was updated
- state which files were reviewed for drift
- explicitly note if any checked files needed no change
