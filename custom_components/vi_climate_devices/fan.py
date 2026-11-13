"""Fan platform for Viessmann ventilation devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity
from homeassistant.components.fan.const import FanEntityFeature
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)
from vi_api_client import Device

from . import ViClimateDevicesConfigEntry
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import ViClimateEntity, async_setup_dynamic_entities
from .exceptions import ExceptionTranslationKey, home_assistant_error
from .utils import (
    api_value_to_option_key,
    get_feature_bool_value,
    get_feature_string_options,
    get_feature_string_value,
)

PARALLEL_UPDATES = 0

FEATURE_MODE = "ventilation.operating.modes.active"
FEATURE_STANDBY_QUICK_MODE = "ventilation.quickmodes.standby.active"
FEATURE_ACTIVE_LEVEL = "ventilation.operating.programs.active"
FEATURE_STATE_LEVEL = "ventilation.operating.state.level"

# The fixed level is set with a command of the permanent mode; no writable
# feature represents it.
LEVEL_API_FEATURE = "ventilation.operating.modes.permanent"
LEVEL_COMMAND = "setLevel"
LEVEL_PARAMETER = "level"

MODE_PERMANENT = "permanent"
MODE_STANDBY = "standby"
MODE_VENTILATION = "ventilation"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann ventilation fans based on a config entry."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_fans(coordinator),
        superseded_domains=(Platform.SELECT,),
    )


def _discover_fans(coordinator: ViClimateDataUpdateCoordinator) -> list[ViClimateFan]:
    """Discover one fan per device with a writable ventilation mode."""
    entities: list[ViClimateFan] = []
    for map_key, device in coordinator.data.items():
        mode_feature = device.get_feature(FEATURE_MODE)
        if (
            mode_feature is not None
            and mode_feature.is_writable
            and mode_feature.constraints is not None
            and get_feature_string_options(mode_feature.constraints.options)
        ):
            entities.append(ViClimateFan(coordinator, map_key))
    return entities


def _level_options(device: Device) -> list[str]:
    """Return the fixed levels the device accepts, slowest first."""
    parameters = device.get_command_parameters(LEVEL_API_FEATURE, LEVEL_COMMAND)
    for parameter in parameters or ():
        if parameter.name == LEVEL_PARAMETER and parameter.constraints is not None:
            return get_feature_string_options(parameter.constraints.options)
    return []


# Home Assistant declares `available` as a cached_property while ViClimateEntity
# overrides it with a plain property; the MRO conflict is a false positive.
class ViClimateFan(ViClimateEntity, FanEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """A ventilation device with its operating mode and fixed level."""

    _attr_translation_key = "ventilation"

    def __init__(
        self, coordinator: ViClimateDataUpdateCoordinator, map_key: str
    ) -> None:
        """Initialize the fan from the device's ventilation features."""
        super().__init__(coordinator, map_key)
        self._availability_feature_names = (FEATURE_MODE,)
        # The former auto-discovered mode select used this unique ID.
        self._attr_unique_id = f"{self._unique_id_prefix}-{FEATURE_MODE}"

    def _device(self) -> Device | None:
        """Return the latest device data."""
        return self.coordinator.data.get(self._map_key)

    def _api_modes(self) -> list[str]:
        """Return the operating modes the device accepts."""
        feature = self._get_feature(FEATURE_MODE)
        if feature is None or feature.constraints is None:
            return []
        return get_feature_string_options(feature.constraints.options)

    def _api_mode(self) -> str | None:
        """Return the current operating mode."""
        feature = self._get_feature(FEATURE_MODE)
        return get_feature_string_value(feature.value) if feature else None

    def _has_standby_quick_mode(self) -> bool:
        """Return whether the device switches off through a standby quick mode."""
        feature = self._get_feature(FEATURE_STANDBY_QUICK_MODE)
        return feature is not None and feature.is_writable

    def _levels(self) -> list[str]:
        """Return the fixed levels, or none without the level command."""
        device = self._device()
        return _level_options(device) if device else []

    @property
    def supported_features(self) -> FanEntityFeature:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the controls the device reports."""
        features = FanEntityFeature.PRESET_MODE
        if MODE_STANDBY in self._api_modes() or self._has_standby_quick_mode():
            features |= FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self._levels():
            features |= FanEntityFeature.SET_SPEED
        return features

    @property
    def is_on(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return whether the device ventilates."""
        if self._has_standby_quick_mode():
            standby = self._get_feature(FEATURE_STANDBY_QUICK_MODE)
            is_standby = get_feature_bool_value(standby.value) if standby else None
            if is_standby is None:
                return None
            if is_standby:
                return False
        mode = self._api_mode()
        if mode is None:
            return None
        return mode != MODE_STANDBY

    @property
    def preset_modes(self) -> list[str]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the operating modes as translatable presets."""
        return [
            api_value_to_option_key(mode)
            for mode in self._api_modes()
            if mode != MODE_STANDBY
        ]

    @property
    def preset_mode(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current operating mode as a preset."""
        mode = self._api_mode()
        if mode is None or mode == MODE_STANDBY:
            return None
        return api_value_to_option_key(mode)

    @property
    def speed_count(self) -> int:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the number of fixed levels."""
        return len(self._levels())

    @property
    def percentage(self) -> int | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current level as a percentage."""
        levels = self._levels()
        if not levels:
            return None
        if self.is_on is False:
            return 0
        for feature_name in (FEATURE_ACTIVE_LEVEL, FEATURE_STATE_LEVEL):
            feature = self._get_feature(feature_name)
            level = get_feature_string_value(feature.value) if feature else None
            if level in levels:
                return ordered_list_item_to_percentage(levels, level)
        return None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch to the operating mode of the preset."""
        modes = {api_value_to_option_key(mode): mode for mode in self._api_modes()}
        mode = modes.get(preset_mode)
        if mode is None or mode == MODE_STANDBY:
            raise home_assistant_error(ExceptionTranslationKey.UNSUPPORTED_MODE)
        await self._async_set_mode(mode)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Leave standby, optionally with a level or preset."""
        if self._has_standby_quick_mode():
            await self._async_write_feature(
                FEATURE_STANDBY_QUICK_MODE,
                False,
                ExceptionTranslationKey.MODE_CHANGE_FAILED,
                lambda: None,
            )
        elif self._api_mode() == MODE_STANDBY and preset_mode is None:
            modes = [mode for mode in self._api_modes() if mode != MODE_STANDBY]
            if not modes:
                raise home_assistant_error(ExceptionTranslationKey.UNSUPPORTED_MODE)
            await self._async_set_mode(
                MODE_VENTILATION if MODE_VENTILATION in modes else modes[0]
            )
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        if percentage is not None:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the device to standby."""
        if self._has_standby_quick_mode():
            await self._async_write_feature(
                FEATURE_STANDBY_QUICK_MODE,
                True,
                ExceptionTranslationKey.MODE_CHANGE_FAILED,
                lambda: None,
            )
            return
        if MODE_STANDBY not in self._api_modes():
            raise home_assistant_error(ExceptionTranslationKey.UNSUPPORTED_MODE)
        await self._async_set_mode(MODE_STANDBY)

    async def async_set_percentage(self, percentage: int) -> None:
        """Run the device permanently at the level of the percentage."""
        if percentage == 0:
            await self.async_turn_off()
            return
        levels = self._levels()
        if not levels:
            raise home_assistant_error(ExceptionTranslationKey.UNSUPPORTED_MODE)
        if self._api_mode() != MODE_PERMANENT and MODE_PERMANENT in self._api_modes():
            await self._async_set_mode(MODE_PERMANENT)
        await self._async_run_command(
            LEVEL_API_FEATURE,
            LEVEL_COMMAND,
            {LEVEL_PARAMETER: percentage_to_ordered_list_item(levels, percentage)},
            ExceptionTranslationKey.MODE_CHANGE_FAILED,
        )

    async def _async_set_mode(self, mode: str) -> None:
        """Write the operating mode."""
        await self._async_write_feature(
            FEATURE_MODE, mode, ExceptionTranslationKey.MODE_CHANGE_FAILED, lambda: None
        )
