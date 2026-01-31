"""Shared utility functions for the Viessmann Climate Devices integration."""

import re
from typing import Any


def beautify_name(name: str) -> str:
    """Convert a dot-separated name to a Title Cased string.

    Removes leading 'heating.' if present.
    Example: 'heating.outside.temperature' -> 'Outside Temperature'
    """
    if not name:
        return name

    # Strip specific cleaning prefixes (order matters)
    for prefix in (
        "heating.configuration.pressure.",
        "heating.heat.",
        "heating.",
        "Power.",
        "device.power.",
        "device.",
    ):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break

    # Collapse specific phrases
    name = name.replace("power.consumption", "consumption")

    # Robust segment cleaning: split, filter, join
    # This handles start, middle, and end occurrences cleanly.
    segments = name.split(".")
    filtered_segments = [
        s for s in segments if s not in ("summary", "Power", "configuration")
    ]
    name = ".".join(filtered_segments)

    # Replace dots with spaces
    name = name.replace(".", " ")

    # Split camelCase: insert space before uppercase letters
    # that follow lowercase letters
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)

    return name.title()


def is_feature_boolean_like(value: Any) -> bool:
    """Check if a value is effectively boolean (bool or 'on'/'off' string).

    Used to determine if a generic feature should be a Binary Sensor
    instead of a Sensor.
    """
    return get_feature_bool_value(value, strict=True) is not None


def get_feature_bool_value(value: Any, strict: bool = False) -> bool | None:
    """Interpret a feature value as a boolean if possible.

    If strict is True, only explicit boolean-like values (bool, specific strings)
    are returned. Numeric fallback is skipped.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    result = None
    if isinstance(value, str):
        val_lower = value.lower()
        if val_lower in {"on", "active", "true", "1", "enabled"}:
            result = True
        elif val_lower in {"off", "inactive", "false", "0", "disabled"}:
            result = False

    if result is not None:
        return result

    if not strict:
        # Fallback for truthiness for other types (e.g. numeric 1/0)
        try:
            if isinstance(value, (int, float)):
                return bool(value)
        except (ValueError, TypeError):
            pass

    return None


def is_feature_ignored(
    feature_name: str,
    ignored_features: list[str | re.Pattern],
) -> bool:
    """Check if a feature should be ignored based on list of patterns."""
    for pattern in ignored_features:
        if isinstance(pattern, str) and feature_name == pattern:
            return True
        if hasattr(pattern, "match") and pattern.match(feature_name):
            return True
    return False


def get_suggested_precision(step: float | None) -> int | None:
    """Determine decimal precision for display based on step size."""
    if step is None:
        return None

    # is_integer() returns True for floats that are whole numbers (e.g. 1.0, 2.0)
    if step.is_integer():
        return 0

    # Determine decimals based on float representation
    # Use fixed-point formatting to avoid scientific notation (1e-04)
    step_str = f"{step:f}".rstrip("0")
    if "." in step_str:
        return len(step_str.split(".")[1])

    return 0
