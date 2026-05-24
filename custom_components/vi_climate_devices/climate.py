"""Climate platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client import Feature

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator
from .utils import get_suggested_precision

_LOGGER = logging.getLogger(__name__)

# Mapping from Viessmann API operation modes to Home Assistant HVACMode.
# Sort the keys alphabetically.
API_TO_HA_HVAC_MODE = {
    "cooling": HVACMode.COOL,
    "dhwAndHeating": HVACMode.HEAT,
    "dhwAndHeatingCooling": HVACMode.HEAT_COOL,
    "heating": HVACMode.HEAT,
    "off": HVACMode.OFF,
    "standby": HVACMode.OFF,
}

# Mapping from Home Assistant HVACMode to prioritized candidate API operating modes.
# We will select the first candidate from the list that is actually supported
# by the device.
# Sort the keys alphabetically.
HA_TO_API_HVAC_MODE: dict[HVACMode, list[str]] = {
    HVACMode.COOL: ["cooling", "dhwAndHeatingCooling"],
    HVACMode.HEAT: ["heating", "dhwAndHeating"],
    HVACMode.HEAT_COOL: ["dhwAndHeatingCooling"],
    HVACMode.OFF: ["standby", "off"],
}

# Mapping from Viessmann active programs (operating programs) to Home Assistant
# preset modes.
# Sort the keys alphabetically.
API_TO_HA_PRESET = {
    "comfort": PRESET_COMFORT,
    "comfortCooling": PRESET_COMFORT,
    "comfortCoolingEnergySaving": PRESET_COMFORT,
    "comfortEnergySaving": PRESET_COMFORT,
    "comfortHeating": PRESET_COMFORT,
    "eco": PRESET_ECO,
    "frostprotection": PRESET_ECO,
    "holiday": PRESET_AWAY,
    "holidayAtHome": PRESET_AWAY,
    "normal": PRESET_HOME,
    "normalCooling": PRESET_HOME,
    "normalCoolingEnergySaving": PRESET_HOME,
    "normalEnergySaving": PRESET_HOME,
    "normalHeating": PRESET_HOME,
    "reduced": PRESET_SLEEP,
    "reducedCooling": PRESET_SLEEP,
    "reducedCoolingEnergySaving": PRESET_SLEEP,
    "reducedEnergySaving": PRESET_SLEEP,
    "reducedHeating": PRESET_SLEEP,
    "summerEco": PRESET_ECO,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices climate entities based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            # Scan for all active operating mode features to find heating circuits.
            # Example feature name: heating.circuits.0.operating.modes.active
            for feature in device.features:
                if feature.name.startswith(
                    "heating.circuits."
                ) and feature.name.endswith(".operating.modes.active"):
                    # Extract the circuit index (e.g. "0" or "1").
                    parts = feature.name.split(".")
                    if len(parts) >= 3:
                        circuit_index = parts[2]
                        entities.append(ViClimate(coordinator, map_key, circuit_index))

    async_add_entities(entities)


class ViClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Viessmann climate circuit."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "heating_circuit"
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        circuit_index: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._map_key = map_key
        self._circuit_index = circuit_index

        device = coordinator.data.get(map_key)
        self._attr_unique_id = (
            f"{device.gateway_serial}-{device.id}-heating_circuit_{circuit_index}"
        )
        self._attr_has_entity_name = True
        self._attr_translation_placeholders = {"index": circuit_index}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, f"{device.gateway_serial}-{device.id}")},
            name=device.model_id,
            manufacturer="Viessmann",
            model=device.model_id,
            serial_number=device.gateway_serial,
        )

    # --- Helpers to get latest features ---

    def _get_feature(self, name: str) -> Feature | None:
        """Get the latest feature object by name from the coordinator."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(name)

    def _get_program_base_name(self, program_name: str) -> str:
        """Get the base prefix of a program name (e.g., 'normalHeating' -> 'normal')."""
        program_lower = program_name.lower()
        known_bases = [
            "comfort",
            "normal",
            "reduced",
            "eco",
            "holiday",
            "frostprotection",
        ]
        for base in known_bases:
            if program_lower.startswith(base):
                return base
        return program_lower

    def _get_program_temperature_feature(self, program_name: str) -> Feature | None:
        """Get the temperature feature for a program with prefix fallback matching."""
        # 1. Try exact name match.
        feature_name = (
            f"heating.circuits.{self._circuit_index}."
            f"operating.programs.{program_name}.temperature"
        )
        feature = self._get_feature(feature_name)
        if feature:
            return feature

        # 2. Match based on normalized base names.
        target_base = self._get_program_base_name(program_name)
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None

        prefix = f"heating.circuits.{self._circuit_index}.operating.programs."
        for feat in device.features:
            if feat.name.startswith(prefix) and feat.name.endswith(".temperature"):
                # Extract program name part:
                # e.g., '...normalHeating.temperature' -> 'normalHeating'
                prog_part = feat.name[len(prefix) : -len(".temperature")]
                if self._get_program_base_name(prog_part) == target_base:
                    return feat

        return None

    def _get_active_temp_feature(self) -> Feature | None:
        """Get the temperature feature corresponding to the active operating program."""
        active_program_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.programs.active"
        )
        if not active_program_feature or not active_program_feature.value:
            return None

        return self._get_program_temperature_feature(str(active_program_feature.value))

    # --- Properties ---

    @property
    def current_temperature(self) -> float | None:
        """Return the current room temperature."""
        room_temp_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.sensors.temperature.room"
        )
        if room_temp_feature and isinstance(room_temp_feature.value, (int, float)):
            return float(room_temp_feature.value)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        if hasattr(self, "_optimistic_temp") and self._optimistic_temp is not None:
            return self._optimistic_temp

        temp_feature = self._get_active_temp_feature()
        if temp_feature and isinstance(temp_feature.value, (int, float)):
            return float(temp_feature.value)
        return None

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature limit."""
        temp_feature = self._get_active_temp_feature()
        if (
            temp_feature
            and temp_feature.control
            and temp_feature.control.min is not None
        ):
            return float(temp_feature.control.min)
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature limit."""
        temp_feature = self._get_active_temp_feature()
        if (
            temp_feature
            and temp_feature.control
            and temp_feature.control.max is not None
        ):
            return float(temp_feature.control.max)
        return super().max_temp

    @property
    def target_temperature_step(self) -> float | None:
        """Return the target temperature step size."""
        temp_feature = self._get_active_temp_feature()
        if (
            temp_feature
            and temp_feature.control
            and temp_feature.control.step is not None
        ):
            return float(temp_feature.control.step)
        return super().target_temperature_step

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested number of decimal places."""
        step = self.target_temperature_step
        return get_suggested_precision(step)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current HVAC mode."""
        if hasattr(self, "_optimistic_mode") and self._optimistic_mode is not None:
            return self._optimistic_mode

        mode_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.modes.active"
        )
        if mode_feature and mode_feature.value:
            return API_TO_HA_HVAC_MODE.get(str(mode_feature.value))
        return None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available HVAC modes."""
        mode_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.modes.active"
        )
        if (
            not mode_feature
            or not mode_feature.control
            or not mode_feature.control.options
        ):
            return [HVACMode.HEAT, HVACMode.OFF]

        modes = set()
        options = mode_feature.control.options
        api_options = []
        if isinstance(options, list):
            api_options = [str(opt) for opt in options]
        elif isinstance(options, dict):
            api_options = list(options.keys())

        for option in api_options:
            if option in API_TO_HA_HVAC_MODE:
                modes.add(API_TO_HA_HVAC_MODE[option])

        return sorted(list(modes))

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode."""
        active_program_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.programs.active"
        )
        if active_program_feature and active_program_feature.value:
            program_name = str(active_program_feature.value)
            return API_TO_HA_PRESET.get(program_name)
        return None

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        presets = set()
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return []

        prefix = f"heating.circuits.{self._circuit_index}.operating.programs."
        for feature in device.features:
            if feature.name.startswith(prefix):
                parts = feature.name[len(prefix) :].split(".")
                if parts:
                    program_name = parts[0]
                    if program_name in API_TO_HA_PRESET:
                        presets.add(API_TO_HA_PRESET[program_name])

        return sorted(list(presets))

    # --- Actions ---

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return

        active_program_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.programs.active"
        )
        if not active_program_feature or not active_program_feature.value:
            raise HomeAssistantError("Could not determine the active program")

        program_name = str(active_program_feature.value)
        temp_feature = self._get_program_temperature_feature(program_name)
        if not temp_feature:
            raise HomeAssistantError(
                "No temperature control feature found for the active program: "
                f"{program_name}"
            )

        device = self.coordinator.data.get(self._map_key)

        # 1. OPTIMISTIC UPDATE
        self._optimistic_temp = value
        self.async_write_ha_state()

        try:
            response, updated_device = await self.coordinator.client.set_feature(
                device, temp_feature, value
            )
            _LOGGER.debug(
                "Command response for setting temperature: success=%s, "
                "message=%s, reason=%s",
                response.success,
                response.message,
                response.reason,
            )

            if not response.success:
                raise HomeAssistantError(
                    f"Command rejected: {response.message or response.reason}"
                )

            # Store updated device in coordinator.
            self.coordinator.data[self._map_key] = updated_device

            # Clear optimistic value.
            self._optimistic_temp = None
        except Exception as err:
            # ROLLBACK on error.
            self._optimistic_temp = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set temperature: {err}") from err

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        mode_feature = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.modes.active"
        )
        if not mode_feature:
            raise HomeAssistantError("Operating mode feature not found")

        available_options = []
        if mode_feature.control and mode_feature.control.options:
            if isinstance(mode_feature.control.options, list):
                available_options = [
                    str(option) for option in mode_feature.control.options
                ]
            elif isinstance(mode_feature.control.options, dict):
                available_options = list(mode_feature.control.options.keys())

        candidates = HA_TO_API_HVAC_MODE.get(hvac_mode, [])
        target_api_mode = None
        for candidate in candidates:
            if candidate in available_options:
                target_api_mode = candidate
                break

        if target_api_mode is None:
            if candidates:
                target_api_mode = candidates[0]
            else:
                raise HomeAssistantError(f"Unsupported HVAC mode: {hvac_mode}")

        device = self.coordinator.data.get(self._map_key)

        # 1. OPTIMISTIC UPDATE
        self._optimistic_mode = hvac_mode
        self.async_write_ha_state()

        try:
            response, updated_device = await self.coordinator.client.set_feature(
                device, mode_feature, target_api_mode
            )
            _LOGGER.debug(
                "Command response for setting HVAC mode: success=%s, "
                "message=%s, reason=%s",
                response.success,
                response.message,
                response.reason,
            )

            if not response.success:
                raise HomeAssistantError(
                    f"Command rejected: {response.message or response.reason}"
                )

            # Store updated device in coordinator.
            self.coordinator.data[self._map_key] = updated_device

            # Clear optimistic mode.
            self._optimistic_mode = None
        except Exception as err:
            # ROLLBACK on error.
            self._optimistic_mode = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set HVAC mode: {err}") from err

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        raise HomeAssistantError(
            "Preset modes are read-only on this device and follow the "
            "configured schedule"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attributes = {}

        # Current active program.
        active_prog_feat = self._get_feature(
            f"heating.circuits.{self._circuit_index}.operating.programs.active"
        )
        if active_prog_feat and active_prog_feat.value:
            attributes["active_program"] = str(active_prog_feat.value)

        # Curve Slope.
        slope_feat = self._get_feature(
            f"heating.circuits.{self._circuit_index}.heating.curve.slope"
        )
        if slope_feat and slope_feat.value is not None:
            attributes["heating_curve_slope"] = float(slope_feat.value)

        # Curve Shift.
        shift_feat = self._get_feature(
            f"heating.circuits.{self._circuit_index}.heating.curve.shift"
        )
        if shift_feat and shift_feat.value is not None:
            attributes["heating_curve_shift"] = float(shift_feat.value)

        return attributes
