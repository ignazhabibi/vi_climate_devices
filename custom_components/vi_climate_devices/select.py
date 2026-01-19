"""Select platform for Viessmann Climate Devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
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


@dataclass
class ViClimateSelectEntityDescription(SelectEntityDescription):
    """Custom description for ViClimate select entities."""

    param_name: str | None = None
    command_name: str | None = None
    property_name: str | None = None


# Feature -> Description
SELECT_TYPES: dict[str, ViClimateSelectEntityDescription] = {
    "heating.dhw.operating.modes.active": ViClimateSelectEntityDescription(
        key="heating.dhw.operating.modes.active",
        translation_key="dhw_mode",
        icon="mdi:water-boiler-auto",
        param_name="mode",
        command_name="setMode",
        property_name="value",  # Usually 'value' for modes
        entity_category=EntityCategory.CONFIG,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices select based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                if feature.name in SELECT_TYPES:
                    desc = SELECT_TYPES[feature.name]
                    entities.append(ViClimateSelect(coordinator, map_key, feature, desc))

    async_add_entities(entities)


class ViClimateSelect(CoordinatorEntity, SelectEntity):
    """Representation of a Viessmann Climate Devices Select Entity."""

    entity_description: ViClimateSelectEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature: Feature,
        description: ViClimateSelectEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature.name
        self._param_name = description.param_name
        self._property_name = description.property_name or description.param_name
        self._command_name = description.command_name

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

        # Dynamic Option Discovery
        self._attr_options = []
        self._update_options(feature)

    def _update_options(self, feature: Feature):
        """Extract available options from constraints."""
        empty_options = []
        if not self._command_name:
            self._attr_options = empty_options
            return

        cmd = feature.commands.get(self._command_name)
        if not cmd:
            self._attr_options = empty_options
            return

        # Try to find the parameter
        param = cmd.params.get(self._param_name)

        # Simple dynamic fallback if param name mismatch
        if not param and len(cmd.params) == 1:
            inferred = list(cmd.params.keys())[0]
            param = cmd.params[inferred]
            # Update param name for execution later
            self._param_name = inferred

        if param and "constraints" in param and "enum" in param["constraints"]:
            self._attr_options = param["constraints"]["enum"]
        else:
            _LOGGER.warning(
                "No enum constraints found for select entity %s (param: %s)",
                self.entity_id,
                self._param_name,
            )
            self._attr_options = empty_options

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
    def current_option(self) -> str | None:
        """Return the current value."""
        feat = self.feature_data
        if not feat:
            return None

        if self._property_name in feat.properties:
            val = feat.properties[self._property_name].get("value")
            if val in self.options:
                return str(val)
            # If value is not in options (e.g. unknown state), return None or log?
            # For now return None to avoid UI errors
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # Optimistic update
        old_value = self.current_option
        if self._property_name in feat.properties:
            feat.properties[self._property_name]["value"] = option
        self.async_write_ha_state()

        try:
            client = self.coordinator.client
            _LOGGER.debug(
                "ViClimateSelect: Setting option %s for entity %s", option, self.entity_id
            )
            await client.execute_command(
                feat, self._command_name, {self._param_name: option}
            )
        except Exception as e:
            # Revert
            if old_value and self._property_name in feat.properties:
                feat.properties[self._property_name]["value"] = old_value
                self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set option {option}: {e}") from e
