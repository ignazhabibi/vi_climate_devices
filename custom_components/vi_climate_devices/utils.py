"""Shared utility functions for the Viessmann Climate Devices integration."""


def beautify_name(name: str) -> str:
    """Convert a dot-separated name to a Title Cased string.

    Example: 'heating.outside.temperature' -> 'Heating Outside Temperature'
    """
    if not name:
        return name
    return name.replace(".", " ").title()
