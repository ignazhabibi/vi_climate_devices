"""Switch platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client import Feature

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class ViClimateSwitchEntityDescription(SwitchEntityDescription):
    """Custom description for ViClimate switch entities."""

    # Optional override for logic mapping
    property_name: str | None = None


SWITCH_TYPES: dict[str, ViClimateSwitchEntityDescription] = {
    "heating.dhw.oneTimeCharge": ViClimateSwitchEntityDescription(
        key="heating.dhw.oneTimeCharge",
        translation_key="dhw_one_time_charge",
        icon="mdi:water-boiler",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    "heating.dhw.hygiene": ViClimateSwitchEntityDescription(
        key="heating.dhw.hygiene",
        translation_key="dhw_hygiene",
        icon="mdi:shield-check",
        property_name="enabled",
        device_class=SwitchDeviceClass.SWITCH,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices switch based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            # Iterate hierarchically over features (NOT flat)
            # Switches often have commands on the parent feature
            for feature in device.features:
                if feature.name in SWITCH_TYPES:
                    desc = SWITCH_TYPES[feature.name]
                    entities.append(
                        ViClimateSwitch(coordinator, map_key, feature, desc)
                    )

    async_add_entities(entities)


class ViClimateSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Viessmann Climate Devices Switch Entity."""

    entity_description: ViClimateSwitchEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature: Feature,
        description: ViClimateSwitchEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature.name
        self._property_name = description.property_name

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

    @property
    def feature_data(self) -> Feature | None:
        """Get latest feature data from coordinator."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return next((f for f in device.features if f.name == self._feature_name), None)

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

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        feat = self.feature_data
        if not feat:
            return None

        # Determine value key
        key = self._property_name or "active"

        # Check properties
        if key in feat.properties:
            val = feat.properties[key].get("value")
            return bool(val)

        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_set_state(False)

    async def _async_set_state(self, target_state: bool) -> None:
        """Execute the command."""
        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # 1. Optimistic Update
        key = self._property_name or "active"
        old_value = None
        if key in feat.properties:
            old_value = feat.properties[key].get("value")
            feat.properties[key]["value"] = target_state

        self.async_write_ha_state()

        try:
            await self._execute_command(feat, target_state)
        except Exception as e:
            # Revert optimistic update
            if old_value is not None:
                feat.properties[key]["value"] = old_value
                self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to switch {target_state}: {e}") from e

    async def _execute_command(self, feat: Feature, target_state: bool) -> None:
        """Determine and execute the correct command for the feature."""
        client = self.coordinator.client
        _LOGGER.debug(
            "ViClimateSwitch: Setting state to %s for entity '%s' (Feature: %s)",
            target_state,
            self.entity_id,
            self._feature_name,
        )

        # Logic: Prefer explicit boolean setters (setActive, setEnabled)
        # Then fallback to action commands (activate/deactivate, enable/disable)

        # --- PATH A: setEnabled (e.g. hygiene) ---
        if "setEnabled" in feat.commands:
            cmd_def = feat.commands["setEnabled"]
            await self._execute_param_command(
                feat, "setEnabled", "enabled", cmd_def, target_state
            )
            return

        # --- PATH B: setActive (e.g. oneTimeCharge) ---
        if "setActive" in feat.commands:
            cmd_def = feat.commands["setActive"]
            await self._execute_param_command(
                feat, "setActive", "active", cmd_def, target_state
            )
            return

        # --- PATH C: Action Commands (True) ---
        if target_state:
            if "enable" in feat.commands:
                await client.execute_command(feat, "enable", {})
            elif "activate" in feat.commands:
                await client.execute_command(feat, "activate", {})
            else:
                available = list(feat.commands.keys())
                raise HomeAssistantError(
                    f"No suitable command found to TURN ON. Available: {available}"
                )
            return

        # --- PATH D: Action Commands (False) ---
        if "disable" in feat.commands:
            await client.execute_command(feat, "disable", {})
        elif "deactivate" in feat.commands:
            await client.execute_command(feat, "deactivate", {})
        else:
            available = list(feat.commands.keys())
            raise HomeAssistantError(
                f"No suitable command found to TURN OFF. Available: {available}"
            )

    async def _execute_param_command(
        self,
        feat: Feature,
        command_name: str,
        default_param: str,
        cmd_def,
        value: bool,
    ) -> None:
        """Helper to execute simple boolean property commands."""
        client = self.coordinator.client
        target_param = default_param
        # Dynamic Param Resolution
        if target_param not in cmd_def.params and len(cmd_def.params) == 1:
            target_param = next(iter(cmd_def.params.keys()))

        await client.execute_command(feat, command_name, {target_param: value})
