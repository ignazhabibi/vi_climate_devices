"""Heat pump states derived from the active Viessmann status messages.

`device.messages.status.raw` lists the status messages that are currently
active, each with the local time it became active. The code meanings come from
the Viessmann service manual "Vitocal 1/25x-A - Systemkonfiguration und
Diagnose", document 6200041, table "Statusmeldungen":
https://climate-solutions.com/documents/6200041
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, tzinfo

from vi_api_client import Device, FeatureValue, JsonValue

from .utils import get_feature_status_entries, get_feature_string_value

STATUS_MESSAGES_FEATURE = "device.messages.status.raw"

# Heat pump operating states. S.125 also covers domestic hot water heating.
HEAT_PUMP_STATE_CODES: dict[str, str] = {
    "S.123": "off",
    "S.124": "pre_run",
    "S.125": "heating",
    "S.126": "cooling",
    "S.127": "defrost_preparation",
    "S.128": "defrosting",
    "S.129": "post_run",
}

# Active stages of the heating water instantaneous heater (heating rod).
# S.130 (switched off) and S.217 to S.219 (stage inactive) need no mapping:
# a stage counts as running only while its activation code is present.
HEATING_ROD_STAGE_CODES: dict[str, int] = {
    "S.131": 1,
    "S.132": 2,
    "S.133": 3,
}

DHW_HEATING_CODES = frozenset({"S.141"})
UTILITY_LOCK_CODES = frozenset({"S.195", "S.196"})
GRID_POWER_LIMITATION_CODES = frozenset({"S.427"})

# Sort the values in operating order.
HEAT_PUMP_STATE_OPTIONS = list(HEAT_PUMP_STATE_CODES.values())
HEATING_ROD_STAGE_OPTIONS = ["off", "stage_1", "stage_2", "stage_3"]


@dataclass(frozen=True)
class StatusMessage:
    """One active status message as reported by a single bus participant."""

    code: str
    bus_address: str | None
    since: datetime | None

    def as_attribute(self, time_zone: tzinfo) -> dict[str, JsonValue]:
        """Return the message as a state attribute entry.

        The activation time is local time of the installation, so the time zone
        is attached without converting the wall-clock time.
        """
        return {
            "code": self.code,
            "bus_address": self.bus_address,
            "since": (
                self.since.replace(tzinfo=time_zone).isoformat() if self.since else None
            ),
        }


def is_heat_pump(device: Device) -> bool:
    """Return whether the device has a compressor.

    The status message codes are defined for Vitocal heat pumps only, so other
    devices with status messages get no heat pump entities.
    """
    return any(
        feature.name.startswith("heating.compressors.") for feature in device.features
    )


def _parse_local_timestamp(value: JsonValue) -> datetime | None:
    """Return the activation time as a naive local time.

    Viessmann suffixes the local activation time with `Z`, so the suffix and
    any offset are dropped instead of converting from UTC.
    """
    timestamp = get_feature_string_value(value)
    if timestamp is None:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None, microsecond=0)


def parse_status_messages(value: FeatureValue) -> list[StatusMessage] | None:
    """Return the active status messages, or None for an unexpected shape.

    Entries without a code are skipped. Entries are not de-duplicated by code
    because several bus participants can report the same message.
    """
    entries = get_feature_status_entries(value)
    if entries is None:
        return None
    messages: list[StatusMessage] = []
    for entry in entries:
        code = get_feature_string_value(entry.get("errorCode"))
        if code is None:
            continue
        messages.append(
            StatusMessage(
                code=code,
                bus_address=get_feature_string_value(entry.get("busAddress")),
                since=_parse_local_timestamp(entry.get("timestamp")),
            )
        )
    return messages


def get_heat_pump_state_message(
    messages: Iterable[StatusMessage],
) -> StatusMessage | None:
    """Return the most recently activated heat pump state message, if any.

    Messages without an activation time rank behind every timed message.
    """
    state_messages = [
        message for message in messages if message.code in HEAT_PUMP_STATE_CODES
    ]
    if not state_messages:
        return None
    return max(state_messages, key=lambda message: message.since or datetime.min)


def get_heat_pump_state(messages: Iterable[StatusMessage]) -> str | None:
    """Return the most recently activated heat pump state, if any is active."""
    state_message = get_heat_pump_state_message(messages)
    if state_message is None:
        return None
    return HEAT_PUMP_STATE_CODES[state_message.code]


def get_active_heating_rod_stages(messages: Iterable[StatusMessage]) -> list[int]:
    """Return the sorted numbers of the running heating rod stages."""
    return sorted(
        {
            HEATING_ROD_STAGE_CODES[message.code]
            for message in messages
            if message.code in HEATING_ROD_STAGE_CODES
        }
    )


def get_heating_rod_state(messages: Iterable[StatusMessage]) -> str:
    """Return the heating rod state from the number of running stages.

    The count is used instead of the highest stage number so the state still
    reflects the running elements if a higher stage ever runs alone.
    """
    stage_count = len(get_active_heating_rod_stages(messages))
    return HEATING_ROD_STAGE_OPTIONS[stage_count]


def has_active_code(messages: Iterable[StatusMessage], codes: frozenset[str]) -> bool:
    """Return whether any of the given status codes is active."""
    return any(message.code in codes for message in messages)
