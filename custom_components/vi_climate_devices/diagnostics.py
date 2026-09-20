"""Privacy-safe diagnostics built from the coordinator cache."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import TypeGuard
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from vi_api_client import Feature, FeatureControl

from .coordinator import ViClimateDataUpdateCoordinator

_REDACTED_VALUE = "<redacted>"
_SENSITIVE_FEATURE_MARKERS = ("location", "serial", "raw")
_SENSITIVE_VALUE_MARKERS = (
    "address",
    "alias",
    "credential",
    "coordinate",
    "description",
    "identification",
    "identifier",
    "latitude",
    "location",
    "longitude",
    "raw",
    "resource",
    "serial",
    "secret",
    "token",
    "uri",
    "url",
)
type JsonValue = (
    bool | float | int | str | list[JsonValue] | dict[str, JsonValue] | None
)
type JsonObject = dict[str, JsonValue]


def _is_sensitive_value_key(key: object) -> bool:
    """Return whether a nested value key can identify a user or resource."""
    key_text = str(key).casefold()
    return (
        key_text == "id"
        or key_text.endswith("id")
        or any(marker in key_text for marker in _SENSITIVE_VALUE_MARKERS)
    )


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    """Return whether a value is a mapping of walkable entries."""
    return isinstance(value, Mapping)


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    """Return whether a value is a non-string sequence of walkable entries."""
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _serialize_mapping(value: Mapping[object, object]) -> dict[str, JsonValue]:
    """Return a redacted, sorted serialization of a mapping value."""
    return {
        str(key): (
            _REDACTED_VALUE if _is_sensitive_value_key(key) else _serialize_value(item)
        )
        for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
    }


def _serialize_sequence(value: Sequence[object]) -> list[JsonValue]:
    """Return an element-wise serialization of a sequence value."""
    return [_serialize_value(item) for item in value]


def _serialize_value(value: object) -> JsonValue:
    """Return a JSON-safe representation of a feature value."""
    if value is None or isinstance(value, bool):
        serialized: JsonValue = value
    elif isinstance(value, str):
        serialized = _REDACTED_VALUE if urlparse(value).scheme else value
    elif isinstance(value, int):
        serialized = value
    elif isinstance(value, float):
        serialized = value if isfinite(value) else None
    elif _is_mapping(value):
        serialized = _serialize_mapping(value)
    elif _is_sequence(value):
        serialized = _serialize_sequence(value)
    else:
        serialized = None
    return serialized


def _serialize_constraints(control: FeatureControl | None) -> JsonObject:
    """Return the safe, applicable constraints for a writable feature."""
    if control is None:
        return {}

    constraints: JsonObject = {}
    for name in ("min", "max", "step", "value_type", "options"):
        value = getattr(control, name)
        if value is not None:
            constraints[name] = _serialize_value(value)
    return constraints


def _serialize_feature(feature: Feature) -> JsonObject:
    """Return a safe diagnostics projection for one cached feature."""
    is_sensitive = any(
        marker in feature.name.casefold() for marker in _SENSITIVE_FEATURE_MARKERS
    )
    return {
        "name": feature.name,
        "value": _REDACTED_VALUE if is_sensitive else _serialize_value(feature.value),
        "unit": feature.unit,
        "is_enabled": feature.is_enabled,
        "is_ready": feature.is_ready,
        "is_writable": feature.is_writable,
        "constraints": _serialize_constraints(feature.control),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry[ViClimateDataUpdateCoordinator],
) -> dict[str, list[JsonObject]]:
    """Return privacy-safe diagnostics from the current coordinator snapshot."""
    del hass
    devices = sorted(
        entry.runtime_data.data.values(),
        key=lambda device: (device.installation_id, device.gateway_serial, device.id),
    )
    installation_labels = {
        installation_id: f"installation_{index}"
        for index, installation_id in enumerate(
            sorted({device.installation_id for device in devices}), start=1
        )
    }
    gateway_labels = {
        (installation_id, gateway_serial): f"gateway_{index}"
        for index, (installation_id, gateway_serial) in enumerate(
            sorted(
                {(device.installation_id, device.gateway_serial) for device in devices}
            ),
            start=1,
        )
    }

    return {
        "devices": [
            {
                "installation": installation_labels[device.installation_id],
                "gateway": gateway_labels[
                    (device.installation_id, device.gateway_serial)
                ],
                "device": f"device_{index}",
                "model": device.model_id,
                "type": device.device_type,
                "status": device.status,
                "features": [
                    _serialize_feature(feature)
                    for feature in sorted(
                        device.features, key=lambda feature: feature.name
                    )
                ],
            }
            for index, device in enumerate(devices, start=1)
        ]
    }
