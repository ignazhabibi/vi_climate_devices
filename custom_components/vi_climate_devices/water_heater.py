"""Water Heater platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_GAS,
    STATE_HEAT_PUMP,
    STATE_OFF,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
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

# Features to look for
FEATURE_TARGET_TEMP = "heating.dhw.temperature.main"
FEATURE_CURRENT_TEMP = "heating.dhw.sensors.temperature.hotWaterStorage"
FEATURE_MODE = "heating.dhw.operating.modes.active"

# Mapping from Viessmann API modes to Home Assistant standard states
# This ensures proper UI translation.
VIESSMANN_TO_HA_MODE = {
    "off": STATE_OFF,
    "standby": STATE_OFF,
    "eco": STATE_ECO,
    "efficient": STATE_ECO,
    "efficientWithMinComfort": STATE_PERFORMANCE,
    "comfort": STATE_PERFORMANCE,
    "balanced": STATE_HEAT_PUMP,
    "standard": STATE_GAS,
}

# Reverse mapping: HA state -> list of possible Viessmann modes (in preference order)
# We'll pick the first one that's actually available on the device
HA_TO_VIESSMANN_MODES = {
    STATE_OFF: ["off", "standby"],
    STATE_ECO: ["eco", "efficient"],
    STATE_PERFORMANCE: ["comfort", "efficientWithMinComfort"],
    STATE_HEAT_PUMP: ["balanced"],
    STATE_GAS: ["standard"],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices water heater."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            # Check if we have the main target temperature feature
            # We treat the generic DHW capability as dependent on having
            # a target temp control AND a mode control.
            # Let's verify essential features exist.

            # Find features by name in the device list
            target_feat = device.get_feature(FEATURE_TARGET_TEMP)

            if target_feat:
                entities.append(ViClimateWaterHeater(coordinator, map_key, target_feat))

    async_add_entities(entities)


class ViClimateWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a Viessmann Water Heater."""

    _attr_translation_key = "dhw_water_heater"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        target_feature: Feature,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._map_key = map_key
        # Primary feature is the Target Temperature control
        self._target_feature_name = target_feature.name

        device = coordinator.data.get(map_key)
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-water_heater"
        self._attr_has_entity_name = True

        # Initialize constraints based on target temp feature
        self._update_constraints(target_feature)

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
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(name)

    def _update_constraints(self, feature: Feature):
        """Extract min/max/step from target temp command."""
        # Use new FeatureControl object
        if feature.control:
            if feature.control.min is not None:
                self._attr_min_temp = feature.control.min
            if feature.control.max is not None:
                self._attr_max_temp = feature.control.max
            if feature.control.step is not None:
                self._attr_target_temperature_step = feature.control.step

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested number of decimal places."""
        step = getattr(self, "_attr_target_temperature_step", None)
        return get_suggested_precision(step)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {}
        # Use underlying attribute to avoid AttributeError if base class
        # doesn't provide the property in all HA versions.
        step = getattr(self, "_attr_target_temperature_step", None)
        if step is not None:
            attrs["target_temp_step"] = step
        return attrs

    # --- Properties ---

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        feat = self._get_feature(FEATURE_CURRENT_TEMP)
        if feat and isinstance(feat.value, (int, float)):
            return float(feat.value)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        # Return optimistic value if set
        if hasattr(self, "_optimistic_temp") and self._optimistic_temp is not None:
            return self._optimistic_temp
        feat = self._get_feature(self._target_feature_name)
        if feat and isinstance(feat.value, (int, float)):
            return float(feat.value)
        return None

    @property
    def current_operation(self) -> str | None:
        """Return current operation mode mapped to HA standard state."""
        # Return optimistic mode if set
        if hasattr(self, "_optimistic_mode") and self._optimistic_mode is not None:
            return self._optimistic_mode
        feat = self._get_feature(FEATURE_MODE)
        if feat and feat.value:
            # Map Viessmann mode to HA standard state
            val = str(feat.value)
            return VIESSMANN_TO_HA_MODE.get(val, val)
        return None

    @property
    def operation_list(self) -> list[str]:
        """Return available operation modes as HA standard states."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat or not feat.control or not feat.control.options:
            # Fallback
            return [STATE_OFF, STATE_ECO, STATE_PERFORMANCE]

        # Get API modes from constraints
        api_modes: list[str] = []
        options = feat.control.options
        if isinstance(options, list):
            api_modes = [str(opt) for opt in options]
        elif isinstance(options, dict):
            api_modes = list(options.keys())

        # Convert to HA standard states (deduplicated)
        ha_modes = set()
        for api_mode in api_modes:
            ha_mode = VIESSMANN_TO_HA_MODE.get(api_mode, api_mode)
            ha_modes.add(ha_mode)

        return list(ha_modes)

    # --- Actions ---

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return

        feat = self._get_feature(self._target_feature_name)
        if not feat:
            raise HomeAssistantError("Target temperature feature not found")

        device = self.coordinator.data.get(self._map_key)

        # 1. OPTIMISTIC UPDATE
        self._optimistic_temp = value
        self.async_write_ha_state()

        try:
            response = await self.coordinator.client.set_feature(device, feat, value)
            _LOGGER.debug(
                "Command response: success=%s, message=%s, reason=%s",
                response.success,
                response.message,
                response.reason,
            )

            if not response.success:
                raise HomeAssistantError(
                    f"Command rejected: {response.message or response.reason}"
                )
            # Clear optimistic value - let next poll pick up real value
            self._optimistic_temp = None
        except Exception as err:
            # ROLLBACK on error
            self._optimistic_temp = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set temperature: {err}") from err

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat:
            raise HomeAssistantError("Mode feature not found")

        device = self.coordinator.data.get(self._map_key)

        # Get available API modes from device
        available_api_modes = self._get_available_api_modes(feat)

        # Convert HA standard state to Viessmann API mode
        # Find first candidate that's actually available on device
        candidates = HA_TO_VIESSMANN_MODES.get(operation_mode, [operation_mode])
        viessmann_mode = None
        for candidate in candidates:
            if candidate in available_api_modes:
                viessmann_mode = candidate
                break

        if viessmann_mode is None:
            # Fallback: use first candidate even if not in list
            viessmann_mode = candidates[0] if candidates else operation_mode
            _LOGGER.warning(
                "Mode %s not in available modes %s, trying %s anyway",
                operation_mode,
                available_api_modes,
                viessmann_mode,
            )

        # 1. OPTIMISTIC UPDATE
        self._optimistic_mode = operation_mode
        self.async_write_ha_state()

        try:
            response = await self.coordinator.client.set_feature(
                device, feat, viessmann_mode
            )
            _LOGGER.debug(
                "Command response: success=%s, message=%s, reason=%s",
                response.success,
                response.message,
                response.reason,
            )

            if not response.success:
                raise HomeAssistantError(
                    f"Command rejected: {response.message or response.reason}"
                )
            # Clear optimistic mode - let next poll pick up real value
            self._optimistic_mode = None
        except Exception as err:
            # ROLLBACK on error
            self._optimistic_mode = None
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set mode: {err}") from err

    def _get_available_api_modes(self, feat: Feature) -> list[str]:
        """Get list of available API modes from feature constraints."""
        if feat.control and feat.control.options:
            return list(map(str, feat.control.options))
        return []
