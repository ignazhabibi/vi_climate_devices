"""Shared utility functions for the Viessmann Climate Devices integration."""

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
