"""Run the repository's complete local quality gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_PATH = Path("custom_components/vi_climate_devices")
COVERAGE_REPORT = PROJECT_ROOT / ".coverage-report.json"
MODULE_LINE_COVERAGE_THRESHOLD = 95.0
CONFIG_FLOW_LINE_COVERAGE_THRESHOLD = 100.0

COMMANDS = (
    (sys.executable, "-m", "ruff", "check", "."),
    (sys.executable, "-m", "ruff", "format", "--check", "."),
    (sys.executable, "-m", "pyright", "--pythonpath", sys.executable),
    (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--cov={INTEGRATION_PATH}",
        "--cov-report=term-missing",
        f"--cov-report=json:{COVERAGE_REPORT}",
    ),
)


def _relative_coverage_path(filename: str) -> Path:
    """Return a report filename relative to the project when possible."""
    path = Path(filename)
    try:
        return path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def _validate_coverage() -> list[str]:
    """Return line-coverage threshold failures from the pytest coverage report."""
    raw_report = json.loads(COVERAGE_REPORT.read_text())
    if not isinstance(raw_report, dict):
        return ["Coverage report has an invalid top-level structure"]
    report = cast(dict[str, object], raw_report)
    files = report.get("files")
    if not isinstance(files, dict):
        return ["Coverage report does not contain per-file results"]

    failures: list[str] = []
    for filename, raw_file_report in cast(dict[str, object], files).items():
        file_report = (
            cast(dict[str, object], raw_file_report)
            if isinstance(raw_file_report, dict)
            else None
        )
        if not isinstance(file_report, dict):
            continue

        relative_path = _relative_coverage_path(filename)
        if relative_path.parent != INTEGRATION_PATH:
            continue

        summary = file_report.get("summary")
        missing_lines = file_report.get("missing_lines")
        if not isinstance(summary, dict) or not isinstance(missing_lines, list):
            failures.append(f"{relative_path}: invalid coverage data")
            continue

        statements = cast(dict[str, object], summary).get("num_statements")
        if not isinstance(statements, int) or statements == 0:
            failures.append(f"{relative_path}: invalid statement count")
            continue

        line_coverage = (
            100 * (statements - len(cast(list[object], missing_lines))) / statements
        )
        threshold = (
            CONFIG_FLOW_LINE_COVERAGE_THRESHOLD
            if relative_path.name == "config_flow.py"
            else MODULE_LINE_COVERAGE_THRESHOLD
        )
        is_config_flow = relative_path.name == "config_flow.py"
        is_requirement_met = (
            line_coverage >= threshold if is_config_flow else line_coverage > threshold
        )
        if not is_requirement_met:
            requirement = "be 100%" if is_config_flow else "be greater than 95%"
            failures.append(
                f"{relative_path}: {line_coverage:.2f}% line coverage "
                f"must {requirement}"
            )
    return failures


def main() -> int:
    """Run every quality command and stop at the first failure."""
    for command in COMMANDS:
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if result.returncode:
            return result.returncode

    failures = _validate_coverage()
    if failures:
        print("Coverage requirements failed:", *failures, sep="\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
