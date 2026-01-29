"""Shared utility functions for the Viessmann Climate Devices integration."""

import re
from typing import Any


def beautify_name(name: str) -> str:
    """Convert a dot-separated name to a Title Cased string.

    Example: 'heating.outside.temperature' -> 'Heating Outside Temperature'
    """
    if not name:
        return name
    return name.replace(".", " ").title()


def is_feature_boolean_like(value: Any) -> bool:
    """Check if a value is effectively boolean (bool or 'on'/'off' string).

    Used to determine if a generic feature should be a Binary Sensor
    instead of a Sensor.
    """
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.lower() in ("on", "off", "active", "true", "false")
    return False


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
