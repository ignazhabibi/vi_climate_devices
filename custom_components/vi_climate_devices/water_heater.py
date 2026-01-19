"""Water Heater platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
    STATE_ECO,
    STATE_PERFORMANCE,
    STATE_OFF,
    STATE_HEAT_PUMP,
    STATE_GAS,
)
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from vi_api_client import Feature

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator

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
            # We treat the generic DHW capability as dependent on having a target temp control
            # AND a mode control, though mode might be optional?
            # Let's verify essential features exist.

            # Find features by name in the device list
            target_feat = next(
                (f for f in device.features if f.name == FEATURE_TARGET_TEMP), None
            )

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
        # Search flat list for efficiency if available, or normal list
        # features_flat is usually available on device object in this integration context
        if hasattr(device, "features_flat"):
            return next((f for f in device.features_flat if f.name == name), None)
        return next((f for f in device.features if f.name == name), None)

    def _update_constraints(self, feature: Feature):
        """Extract min/max/step from target temp command."""
        cmd_name = "setTargetTemperature"
        param_name = "temperature"

        cmd = feature.commands.get(cmd_name)
        if cmd and param_name in cmd.params:
            constraints = cmd.params[param_name].get("constraints", {})
            if "min" in constraints:
                self._attr_min_temp = float(constraints["min"])
            if "max" in constraints:
                self._attr_max_temp = float(constraints["max"])
            # Precision/Step is not a standard attribute of WaterHeaterEntity in base class,
            # but HA might respect 'precision' property or we handle it internally.

    # --- Properties ---

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        feat = self._get_feature(FEATURE_CURRENT_TEMP)
        if feat and "value" in feat.properties:
            val = feat.properties["value"].get("value")
            if val is not None:
                return float(val)
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        feat = self._get_feature(self._target_feature_name)
        if feat and "value" in feat.properties:
            val = feat.properties["value"].get("value")
            if val is not None:
                return float(val)
        return None

    @property
    def current_operation(self) -> str | None:
        """Return current operation mode mapped to HA standard state."""
        feat = self._get_feature(FEATURE_MODE)
        if feat and "value" in feat.properties:
            val = feat.properties["value"].get("value")
            if val is not None:
                # Map Viessmann mode to HA standard state
                return VIESSMANN_TO_HA_MODE.get(str(val), str(val))
        return None

    @property
    def operation_list(self) -> list[str] | None:
        """Return available operation modes as HA standard states."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat:
            return []

        # Try to find enum constraints in 'setMode' command
        cmd = feat.commands.get("setMode")
        if cmd:
            param = cmd.params.get("mode")
            if param and "constraints" in param and "enum" in param["constraints"]:
                viessmann_modes = param["constraints"]["enum"]
                # Map all Viessmann modes to HA states (unique values only)
                ha_modes = []
                seen = set()
                for mode in viessmann_modes:
                    ha_mode = VIESSMANN_TO_HA_MODE.get(mode, mode)
                    if ha_mode not in seen:
                        ha_modes.append(ha_mode)
                        seen.add(ha_mode)
                return ha_modes

        # Fallback if no command constraints found but value exists
        curr = self.current_operation
        if curr:
            return [curr]
        return []

    # --- Actions ---

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return

        feat = self._get_feature(self._target_feature_name)
        if not feat:
            raise HomeAssistantError("Target temperature feature not found")

        # Store old value for rollback
        old_value = (
            feat.properties.get("value", {}).get("value")
            if "value" in feat.properties
            else None
        )

        # Optimistic update
        if "value" in feat.properties:
            feat.properties["value"]["value"] = value
        self.async_write_ha_state()

        command_name = "setTargetTemperature"
        param_name = "temperature"

        try:
            await self.coordinator.client.execute_command(
                feat, command_name, {param_name: value}
            )
        except Exception as err:
            # Revert optimistic update on failure
            if old_value is not None and "value" in feat.properties:
                feat.properties["value"]["value"] = old_value
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set temperature: {err}") from err

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat:
            raise HomeAssistantError("Mode feature not found")

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

        # Store old value for rollback
        old_value = (
            feat.properties.get("value", {}).get("value")
            if "value" in feat.properties
            else None
        )

        # Optimistic update (store Viessmann mode, our property maps it back to HA state)
        if "value" in feat.properties:
            feat.properties["value"]["value"] = viessmann_mode
        self.async_write_ha_state()

        command_name = "setMode"
        param_name = "mode"

        try:
            await self.coordinator.client.execute_command(
                feat, command_name, {param_name: viessmann_mode}
            )
        except Exception as err:
            # Revert optimistic update on failure
            if old_value is not None and "value" in feat.properties:
                feat.properties["value"]["value"] = old_value
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set mode: {err}") from err

    def _get_available_api_modes(self, feat: Feature) -> list[str]:
        """Get list of available API modes from feature constraints."""
        cmd = feat.commands.get("setMode")
        if cmd:
            param = cmd.params.get("mode")
            if param and "constraints" in param and "enum" in param["constraints"]:
                return param["constraints"]["enum"]
        return []
