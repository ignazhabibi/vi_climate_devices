"""Number platform for Viessmann Climate Devices."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from typing import Any
import re

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberDeviceClass,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
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
class ViClimateNumberEntityDescription(NumberEntityDescription):
    """Custom description for ViClimate number entities."""

    param_name: str | None = None
    command_name: str | None = None
    property_name: str | None = (
        None  # Optional: logic name to read from properties if different from param_name
    )


# Definition maps: feature_name -> List of descriptions
# Dynamic Templates
NUMBER_TEMPLATES = [
    {
        "pattern": r"^heating\.circuits\.(\d+)\.heating\.curve$",
        "descriptions": [
            ViClimateNumberEntityDescription(
                key="heating.circuits.{}.heating.curve.slope",  # Placeholder {} for format
                translation_key="heating_curve_slope",  # Generic key
                icon="mdi:slope-uphill",
                param_name="slope",
                command_name="setCurve",
                mode=NumberMode.BOX,
                entity_category=EntityCategory.CONFIG,
            ),
            ViClimateNumberEntityDescription(
                key="heating.circuits.{}.heating.curve.shift",
                translation_key="heating_curve_shift",  # Generic key
                icon="mdi:arrow-up-down",
                param_name="shift",
                command_name="setCurve",
                mode=NumberMode.BOX,
                entity_category=EntityCategory.CONFIG,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=NumberDeviceClass.TEMPERATURE,
            ),
        ],
    },
    {
        # Matches: comfort, normal, reduced, eco, comfortCooling, comfortHeating, etc.
        "pattern": r"^heating\.circuits\.(\d+)\.operating\.programs\.((?:comfort|normal|reduced|eco)(?:Cooling|Heating|))$",
        "descriptions": [
            ViClimateNumberEntityDescription(
                key="heating.circuits.{}.operating.programs.{}.temperature",
                translation_key="heating_circuit_program_temperature",
                icon="mdi:thermometer",
                param_name="temperature",
                property_name="temperature",  # Read from the 'temperature' property of the program feature
                command_name="setTemperature",
                mode=NumberMode.BOX,
                entity_category=EntityCategory.CONFIG,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=NumberDeviceClass.TEMPERATURE,
            )
        ],
    },
]

NUMBER_TYPES: dict[str, list[ViClimateNumberEntityDescription]] = {
    "heating.dhw.temperature.hysteresis": [
        ViClimateNumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.on",
            translation_key="dhw_hysteresis_on",
            icon="mdi:thermometer-plus",
            param_name="hysteresis",
            property_name="switchOnValue",  # Read from this property
            command_name="setHysteresisSwitchOnValue",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
        ViClimateNumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.off",
            translation_key="dhw_hysteresis_off",
            icon="mdi:thermometer-minus",
            param_name="hysteresis",
            property_name="switchOffValue",  # Read from this property
            command_name="setHysteresisSwitchOffValue",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ],
    "heating.dhw.temperature.main": [
        ViClimateNumberEntityDescription(
            key="heating.dhw.temperature.main",
            translation_key="dhw_target_temperature",
            icon="mdi:thermometer",
            param_name="temperature",
            property_name="value",  # The property is named 'value', not 'temperature'
            command_name="setTargetTemperature",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ],
    # Add other circuits if needed (1, 2, 3)
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices number based on a config entry."""
    coords = hass.data[DOMAIN][entry.entry_id]
    coordinator: ViClimateDataUpdateCoordinator = coords["data"]

    entities = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            # Iterate hierarchically over features (NOT flat) to access commands and complex properties
            for feature in device.features:
                if feature.name in NUMBER_TYPES:
                    descriptions = NUMBER_TYPES[feature.name]
                    for desc in descriptions:
                        entities.append(
                            ViClimateNumber(coordinator, map_key, feature, desc)
                        )
                else:
                    # Check templates
                    for template in NUMBER_TEMPLATES:
                        match = re.match(template["pattern"], feature.name)
                        if match:
                            # Handle multiple capture groups (up to 2 supported for now: index, program)
                            # Pattern 1: ^heating\.circuits\.(\d+)\.heating\.curve$ -> groups=(0,)
                            # Pattern 2: ^heating\.circuits\.(\d+)\.operating\.programs\.(\w+)\.temperature$ -> groups=(0, 'comfort')

                            groups = match.groups()
                            index = groups[0]
                            program = groups[1] if len(groups) > 1 else None

                            for base_desc in template["descriptions"]:
                                # Clone and Format
                                # key format: "heating.circuits.{}.heating.curve.slope" -> "heating.circuits.0.heating.curve.slope"
                                # key format: "heating.circuits.{}.operating.programs.{}.temperature" -> "heating.circuits.0.operating.programs.comfort.temperature"
                                if program:
                                    program_snake = re.sub(
                                        r"(?<!^)(?=[A-Z])", "_", program
                                    ).lower()
                                    specific_trans_key = f"heating_circuit_program_{program_snake}_temperature"

                                    new_trans_key = specific_trans_key
                                    new_key = base_desc.key.format(index, program)
                                    placeholders = {
                                        "index": index
                                    }  # Program removed from placeholder if we use specific key
                                else:
                                    new_key = base_desc.key.format(index)
                                    placeholders = {"index": index}
                                    new_trans_key = base_desc.translation_key

                                # translation_key generic is kept as is
                                # new_trans_key = base_desc.translation_key  <-- REMOVED because it overwrote the specific key logic

                                new_desc = replace(
                                    base_desc,
                                    key=new_key,
                                    translation_key=new_trans_key,
                                )

                                entities.append(
                                    ViClimateNumber(
                                        coordinator,
                                        map_key,
                                        feature,
                                        new_desc,
                                        translation_placeholders=placeholders,
                                    )
                                )
                            break  # Found match, stop templates loop

    async_add_entities(entities)


class ViClimateNumber(CoordinatorEntity, NumberEntity):
    """Representation of a Viessmann Climate Devices Number Entity."""

    entity_description: ViClimateNumberEntityDescription

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature: Feature,
        description: ViClimateNumberEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature.name  # The parent feature name
        self._param_name = description.param_name
        self._property_name = description.property_name or description.param_name
        self._command_name = description.command_name
        self._attr_translation_placeholders = translation_placeholders or {}

        device = coordinator.data.get(map_key)

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

        # Initial Setup of Constraints from Feature Metadata
        self._resolve_command_param(feature)
        self._update_constraints(feature)

    def _resolve_command_param(self, feature: Feature):
        """Resolve the actual parameter name expected by the command."""
        self._command_param_name = self._param_name  # Default to configured name

        if not self._command_name or self._command_name not in feature.commands:
            return

        cmd = feature.commands[self._command_name]

        # 1. Exact match?
        if self._param_name in cmd.params:
            return

        # 2. Dynamic Resolution: If command has only 1 parameter, assume that is the one we want to control.
        # This handles cases like 'setTemperature' needing 'targetTemperature' when we identified it as 'temperature'
        if len(cmd.params) == 1:
            inferred = list(cmd.params.keys())[0]
            _LOGGER.debug(
                "Inferred command parameter '%s' for entity %s (configured '%s') on command %s",
                inferred,
                self._feature_name,  # entity_id is None at init
                self._param_name,
                self._command_name,
            )
            self._command_param_name = inferred
        else:
            _LOGGER.warning(
                "Could not resolve command parameter for %s. Configured: '%s', Command '%s' has params: %s",
                self._feature_name,  # entity_id is None at init
                self._param_name,
                self._command_name,
                list(cmd.params.keys()),
            )

    def _to_smart_number(self, value: float) -> float | int:
        """Convert to int if no decimal part, else float."""
        f_val = float(value)
        if f_val.is_integer():
            return int(f_val)
        return f_val

    def _update_constraints(self, feature: Feature):
        """Extract min/max/step from feature commands."""
        if not self._command_name or not self._command_param_name:
            return

        cmd = feature.commands.get(self._command_name)
        if cmd and self._command_param_name in cmd.params:
            constraints = cmd.params[self._command_param_name].get("constraints", {})

            if "min" in constraints:
                self._attr_native_min_value = self._to_smart_number(constraints["min"])
            if "max" in constraints:
                self._attr_native_max_value = self._to_smart_number(constraints["max"])
            if "stepping" in constraints:
                self._attr_native_step = self._to_smart_number(constraints["stepping"])
            elif "step" in constraints:
                self._attr_native_step = self._to_smart_number(constraints["step"])

    @property
    def feature_data(self) -> Feature | None:
        """Get latest feature data from coordinator."""
        # We need to re-fetch the feature object from the coordinator to get updated values
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        # Searching in .features list.
        # Since we stored top-level feature name, we can find it.
        # But wait, device.features is a list. We need to find by name.
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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "viessmann_feature_name": self._feature_name,
            "viessmann_param_name": self._param_name,
            "viessmann_property_name": self._property_name,
            "viessmann_command_param": getattr(self, "_command_param_name", None),
        }

    @property
    def mode(self) -> NumberMode:
        """Return the mode of the entity."""
        return self.entity_description.mode

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        feat = self.feature_data
        if not feat:
            return None

        # Read from properties: e.g. feat.properties["slope"]["value"]
        # Use property_name logic which defaults to param_name
        if self._property_name in feat.properties:
            val = feat.properties[self._property_name].get("value")
            if val is not None:
                return self._to_smart_number(val)

        return None

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        feat = self.feature_data
        if not feat:
            raise HomeAssistantError("Feature not available")

        # Prepare payload
        payload = {}

        cmd_def = feat.commands.get(self._command_name)
        if not cmd_def:
            raise HomeAssistantError(f"Command {self._command_name} not found")

        # 1. OPTIMISTIC UPDATE (Immediate UI Feedback)
        old_value = None
        if self._property_name in feat.properties:
            old_value = feat.properties[self._property_name].get("value")
            feat.properties[self._property_name]["value"] = value

        self.async_write_ha_state()

        # 2. PREPARE PAYLOAD
        # Target parameter gets the new value.
        # Other parameters are backfilled from properties (if present).

        target_param = getattr(self, "_command_param_name", self._param_name)

        for param in cmd_def.params:
            if param == target_param:
                payload[param] = value
            else:
                if param in feat.properties:
                    payload[param] = feat.properties[param].get("value")
                else:
                    _LOGGER.warning(
                        "Parameter %s required for command %s but not found in properties.",
                        param,
                        self._command_name,
                    )

        _LOGGER.debug(
            "ViClimateNumber: Executing command '%s' for entity '%s' with payload: %s",
            self._command_name,
            self.entity_id,
            payload,
        )

        # 3. EXECUTE COMMAND
        try:
            client = self.coordinator.client
            await client.execute_command(feat, self._command_name, payload)
        except Exception as e:
            # REVERT on failure
            if old_value is not None:
                feat.properties[self._property_name]["value"] = old_value
                self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set value: {e}") from e
