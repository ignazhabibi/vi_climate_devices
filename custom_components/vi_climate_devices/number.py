"""Number platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from vi_api_client import Feature, ViError

from . import ViClimateDevicesConfigEntry
from .const import DOMAIN, IGNORED_FEATURES, TESTED_DEVICES
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import EntityTemplate, ViClimateEntity, async_setup_dynamic_entities
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
    service_validation_error,
)
from .utils import (
    beautify_name,
    get_feature_number_value,
    get_suggested_precision,
    is_feature_ignored,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


# Templates with regex patterns for dynamic feature names
NUMBER_TEMPLATES: tuple[EntityTemplate[NumberEntityDescription], ...] = (
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.heating\.curve\.slope$"),
        description=NumberEntityDescription(
            key="placeholder",
            translation_key="heating_curve_slope",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.heating\.curve\.shift$"),
        description=NumberEntityDescription(
            key="placeholder",
            translation_key="heating_curve_shift",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        ),
    ),
    EntityTemplate(
        # Matches: comfort, normal, reduced, eco, comfortCooling, comfortHeating, etc.
        # Flat name example: heating.circuits.0.operating.programs.comfort.temperature
        pattern=re.compile(
            r"^heating\.circuits\.(\d+)\.operating\.programs\."
            r"((?:comfort|normal|reduced|eco)(?:Cooling|Heating|))\.temperature$"
        ),
        description=NumberEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_program_temperature",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.temperature\.levels\.min$"),
        description=NumberEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_temperature_limit_min",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ),
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.temperature\.levels\.max$"),
        description=NumberEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_temperature_limit_max",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ),
)

NUMBER_TYPES: dict[str, NumberEntityDescription] = {
    "heating.dhw.temperature.hysteresis": NumberEntityDescription(
        key="heating.dhw.temperature.hysteresis",
        translation_key="dhw_hysteresis",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.KELVIN,
        device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        entity_registry_enabled_default=False,
    ),
    "heating.dhw.temperature.hysteresis.switchOnValue": (
        NumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.switchOnValue",
            translation_key="dhw_hysteresis_on",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        )
    ),
    "heating.dhw.temperature.hysteresis.switchOffValue": (
        NumberEntityDescription(
            key="heating.dhw.temperature.hysteresis.switchOffValue",
            translation_key="dhw_hysteresis_off",
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            device_class=NumberDeviceClass.TEMPERATURE_DELTA,
        )
    ),
    "heating.dhw.temperature.main": NumberEntityDescription(
        key="heating.dhw.temperature.main",
        translation_key="dhw_target_temperature",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    ),
}


def _get_number_entity_description(
    feature_name: str,
) -> tuple[NumberEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name."""
    for template in NUMBER_TEMPLATES:
        match = template.pattern.match(feature_name)
        if not match:
            continue
        groups = match.groups()
        index = groups[0]
        # If pattern has 2 groups, second is program
        program = groups[1] if len(groups) > 1 else None

        base_desc = template.description

        placeholders = {"index": index}
        new_key = feature_name  # We use the actual feature name
        new_trans_key = base_desc.translation_key

        # Program specific logic
        if program:
            program_snake = re.sub(r"(?<!^)(?=[A-Z])", "_", program).lower()
            new_trans_key = f"heating_circuit_program_{program_snake}_temperature"

        new_desc = replace(
            base_desc,
            key=new_key,
            translation_key=new_trans_key,
        )
        return new_desc, placeholders
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices number based on a config entry."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_numbers(coordinator),
    )


def _discover_numbers(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[ViClimateNumber]:
    """Discover number entities from the current coordinator data."""
    entities: list[ViClimateNumber] = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                # Numbers need a writable feature and bounded control.
                if (
                    not feature.is_writable
                    or not feature.control
                    or (feature.control.min is None and feature.control.max is None)
                ):
                    continue

                # 1. Defined Entities
                if feature.name in NUMBER_TYPES:
                    desc = NUMBER_TYPES[feature.name]
                    entities.append(
                        ViClimateNumber(coordinator, map_key, feature.name, desc)
                    )
                    continue

                # 2. Configured Templates
                if match_result := _get_number_entity_description(feature.name):
                    desc, placeholders = match_result
                    entities.append(
                        ViClimateNumber(
                            coordinator,
                            map_key,
                            feature.name,
                            desc,
                            translation_placeholders=placeholders,
                        )
                    )
                    continue

                # Automatic Discovery (Fallback)
                # Control must exist and have min/max constraints
                description = NumberEntityDescription(
                    key=feature.name,
                    name=beautify_name(feature.name),
                    entity_category=EntityCategory.CONFIG,
                )
                # Only disable entities by default for thoroughly tested devices
                is_tested = device.model_id in TESTED_DEVICES
                entities.append(
                    ViClimateNumber(
                        coordinator,
                        map_key,
                        feature.name,
                        description,
                        enabled_default=not is_tested,
                    )
                )
    return entities


# Home Assistant declares `available` as a cached_property while ViClimateEntity
# overrides it with a plain property; the MRO conflict is a false positive.
class ViClimateNumber(ViClimateEntity, NumberEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Representation of a Viessmann Climate Devices Number Entity."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: NumberEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
        enabled_default: bool | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._availability_feature_names = (feature_name,)
        self._attr_translation_placeholders = translation_placeholders or {}
        if enabled_default is not None:
            self._attr_entity_registry_enabled_default = enabled_default
        self._optimistic_value: float | None = None

        device = coordinator.data.get(map_key)
        if not device:
            raise ValueError(f"Device {map_key} not found in coordinator data")

        # Unique ID: gateway-device-key
        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-{description.key}"
        self._attr_has_entity_name = True

        # Improve name for auto-discovered entities
        if (
            not hasattr(description, "translation_key")
            or not description.translation_key
        ):
            if isinstance(description.name, str):
                self._attr_name = description.name
            else:
                self._attr_name = beautify_name(feature_name)

        # Initial Setup of Constraints from Feature Control
        feature = device.get_feature(feature_name)
        self._update_constraints(feature)

    def _update_constraints(self, feature: Feature | None) -> None:
        """Extract min/max/step from feature control."""
        if feature and feature.control:
            if feature.control.min is not None:
                self._attr_native_min_value = float(feature.control.min)
            if feature.control.max is not None:
                self._attr_native_max_value = float(feature.control.max)
            if feature.control.step is not None:
                self._attr_native_step = float(feature.control.step)

    @property
    def feature_data(self) -> Feature | None:
        """Get latest feature data from coordinator."""
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(self._feature_name)

    @property
    def device_info(self) -> DeviceInfo | None:  # pyright: ignore[reportIncompatibleVariableOverride]
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
    def extra_state_attributes(self) -> dict[str, str]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return entity specific state attributes."""
        return {
            "viessmann_feature_name": self._feature_name,
        }

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested number of decimal places."""
        return get_suggested_precision(self._attr_native_step)

    @property
    def native_value(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current value."""
        # Return optimistic value if set, otherwise from coordinator
        if self._optimistic_value is not None:
            return self._optimistic_value
        feat = self.feature_data
        if not feat:
            return None
        return get_feature_number_value(feat.value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        feat = self.feature_data
        if not feat:
            raise home_assistant_error(ExceptionTranslationKey.FEATURE_UNAVAILABLE)

        # 1. OPTIMISTIC UPDATE - Store locally and update UI immediately
        self._optimistic_value = value
        self.async_write_ha_state()

        # 2. EXECUTE COMMAND
        try:
            # Round value based on step to avoid floating point precision issues.
            precision = get_suggested_precision(self._attr_native_step)
            if precision is not None:
                value = round(value, precision)

            response = await self.coordinator.async_set_feature(
                self._map_key, feat.name, value
            )
            if not response.success:
                raise service_validation_error(ExceptionTranslationKey.COMMAND_REJECTED)

            # 3. Clear optimistic value - let next poll pick up real value
            self._optimistic_value = None
            self.async_write_ha_state()
        except ServiceValidationError:
            self._optimistic_value = None
            self.async_write_ha_state()
            raise
        except ValueError as err:
            self._optimistic_value = None
            self.async_write_ha_state()
            _LOGGER.debug("Viessmann rejected number value: %s", err)
            raise service_validation_error(
                ExceptionTranslationKey.COMMAND_REJECTED
            ) from err
        except ConfigEntryAuthFailed:
            raise
        except (HomeAssistantError, ViError) as err:
            # 5. ROLLBACK on error
            self._optimistic_value = None
            self.async_write_ha_state()
            _LOGGER.debug("Unable to change Viessmann number value: %s", err)
            raise home_assistant_error(
                ExceptionTranslationKey.NUMBER_CHANGE_FAILED
            ) from err
