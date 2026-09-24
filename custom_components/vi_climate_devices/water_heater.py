"""Water Heater platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    STATE_ECO,
    STATE_GAS,
    STATE_HEAT_PUMP,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
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
from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import ViClimateEntity, async_setup_dynamic_entities
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
    service_validation_error,
)
from .utils import (
    get_feature_number_value,
    get_feature_string_options,
    get_feature_string_value,
    get_suggested_precision,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Features to look for
FEATURE_TARGET_TEMP = "heating.dhw.temperature.main"
FEATURE_CURRENT_TEMP = "heating.dhw.sensors.temperature.hotWaterStorage"
FEATURE_MODE = "heating.dhw.operating.modes.active"

# Mapping from Viessmann API modes to Home Assistant standard states.
# The ``balanced`` API mode is device-family-specific and is handled separately.
VIESSMANN_TO_HA_MODE = {
    "off": STATE_OFF,
    "standby": STATE_OFF,
    "eco": STATE_ECO,
    "efficient": STATE_ECO,
    "efficientWithMinComfort": STATE_PERFORMANCE,
    "comfort": STATE_PERFORMANCE,
    "standard": STATE_GAS,
}

# Reverse mapping for device-independent modes. The first available mode wins.
HA_TO_VIESSMANN_MODES = {
    STATE_OFF: ["off", "standby"],
    STATE_ECO: ["eco", "efficient"],
    STATE_PERFORMANCE: ["comfort", "efficientWithMinComfort"],
    STATE_GAS: ["standard"],
}

DEVICE_FAMILY_MODE_MAPPINGS = {
    "vitocal": {"balanced": STATE_HEAT_PUMP},
    "vitodens": {"balanced": STATE_GAS},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices water heater."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_water_heaters(coordinator),
    )


def _discover_water_heaters(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[ViClimateWaterHeater]:
    """Discover water heater entities from the current coordinator data."""
    entities: list[ViClimateWaterHeater] = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            target_feat = device.get_feature(FEATURE_TARGET_TEMP)
            mode_feat = device.get_feature(FEATURE_MODE)

            if (
                target_feat
                and target_feat.is_writable
                and mode_feat
                and mode_feat.is_writable
            ):
                entities.append(ViClimateWaterHeater(coordinator, map_key, target_feat))
    return entities


# Home Assistant declares `available` as a cached_property while ViClimateEntity
# overrides it with a plain property; the MRO conflict is a false positive.
class ViClimateWaterHeater(ViClimateEntity, WaterHeaterEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
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
        self._availability_feature_names = (target_feature.name, FEATURE_MODE)

        device = coordinator.data.get(map_key)
        if not device:
            raise ValueError(f"Device {map_key} not found in coordinator data")

        self._attr_unique_id = f"{device.gateway_serial}-{device.id}-water_heater"
        self._attr_has_entity_name = True

        # Initialize constraints based on target temp feature
        self._update_constraints(target_feature)

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

    # --- Helpers to get latest features ---

    def _get_feature(self, name: str) -> Feature | None:
        device = self.coordinator.data.get(self._map_key)
        if not device:
            return None
        return device.get_feature(name)

    def _update_constraints(self, feature: Feature | None) -> None:
        """Extract min/max/step from target temp command."""
        # Use new FeatureControl object
        if feature and feature.control:
            if feature.control.min is not None:
                self._attr_min_temp = feature.control.min
            if feature.control.max is not None:
                self._attr_max_temp = feature.control.max
            if feature.control.step is not None:
                self._attr_target_temperature_step = feature.control.step

    def _get_device_family_mode_mapping(self) -> dict[str, str] | None:
        """Return the current device family's API-to-HA mode mapping."""
        device = self.coordinator.data.get(self._map_key)
        if device:
            model_id = device.model_id.lower()
            for family, family_modes in DEVICE_FAMILY_MODE_MAPPINGS.items():
                if model_id.startswith(family):
                    return family_modes
        return None

    def _map_api_mode_to_ha_mode(self, api_mode: str) -> str | None:
        """Map an API mode to the device family's HA operation mode."""
        if family_modes := self._get_device_family_mode_mapping():
            return family_modes.get(api_mode) or VIESSMANN_TO_HA_MODE.get(api_mode)
        return VIESSMANN_TO_HA_MODE.get(api_mode)

    def _get_api_mode_candidates(self, operation_mode: str) -> list[str]:
        """Return API modes that represent an HA operation on this device."""
        if family_modes := self._get_device_family_mode_mapping():
            family_candidates = [
                api_mode
                for api_mode, ha_mode in family_modes.items()
                if ha_mode == operation_mode
            ]
            return family_candidates + HA_TO_VIESSMANN_MODES.get(operation_mode, [])
        return HA_TO_VIESSMANN_MODES.get(operation_mode, [])

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested number of decimal places."""
        step = getattr(self, "_attr_target_temperature_step", None)
        return get_suggested_precision(step)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {}
        # Use underlying attribute to avoid AttributeError if base class
        # doesn't provide the property in all HA versions.
        step = getattr(self, "_attr_target_temperature_step", None)
        if step is not None:
            attrs["target_temp_step"] = step
        return attrs

    # --- Properties ---

    @property
    def current_temperature(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current temperature."""
        feat = self._get_feature(FEATURE_CURRENT_TEMP)
        if feat is None:
            return None
        number = get_feature_number_value(feat.value)
        return float(number) if number is not None else None

    @property
    def target_temperature(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the temperature we try to reach."""
        # Return optimistic value if set
        if hasattr(self, "_optimistic_temp") and self._optimistic_temp is not None:
            return self._optimistic_temp
        feat = self._get_feature(self._target_feature_name)
        if feat is None:
            return None
        number = get_feature_number_value(feat.value)
        return float(number) if number is not None else None

    @property
    def current_operation(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return current operation mode mapped to HA standard state."""
        # Return optimistic mode if set
        if hasattr(self, "_optimistic_mode") and self._optimistic_mode is not None:
            return self._optimistic_mode
        feat = self._get_feature(FEATURE_MODE)
        if feat is None:
            return None
        api_mode = get_feature_string_value(feat.value)
        if api_mode is None:
            return None
        return self._map_api_mode_to_ha_mode(api_mode)

    @property
    def operation_list(self) -> list[str]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return available operation modes as HA standard states."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat or not feat.control or not feat.control.options:
            # Fallback
            return [STATE_OFF, STATE_ECO, STATE_PERFORMANCE]

        # Get API modes from constraints
        api_modes = get_feature_string_options(feat.control.options)

        # Convert to HA standard states (deduplicated)
        ha_modes: set[str] = set()
        for api_mode in api_modes:
            ha_mode = self._map_api_mode_to_ha_mode(api_mode)
            if ha_mode:
                ha_modes.add(ha_mode)

        return sorted(ha_modes)

    # --- Actions ---

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return

        feat = self._get_feature(self._target_feature_name)
        if not feat:
            raise home_assistant_error(ExceptionTranslationKey.FEATURE_UNAVAILABLE)

        # 1. OPTIMISTIC UPDATE
        self._optimistic_temp = value
        self.async_write_ha_state()

        try:
            response = await self.coordinator.async_set_feature(
                self._map_key, feat.name, value
            )
            if not response.success:
                raise service_validation_error(ExceptionTranslationKey.COMMAND_REJECTED)

            # Clear optimistic value - let next poll pick up real value
            self._optimistic_temp = None
            self.async_write_ha_state()
        except ServiceValidationError:
            self._optimistic_temp = None
            self.async_write_ha_state()
            raise
        except ValueError as err:
            self._optimistic_temp = None
            self.async_write_ha_state()
            _LOGGER.debug("Viessmann rejected requested water temperature: %s", err)
            raise service_validation_error(
                ExceptionTranslationKey.COMMAND_REJECTED
            ) from err
        except ConfigEntryAuthFailed:
            raise
        except (HomeAssistantError, ViError) as err:
            # ROLLBACK on error
            self._optimistic_temp = None
            self.async_write_ha_state()
            _LOGGER.debug("Unable to change Viessmann water temperature: %s", err)
            raise home_assistant_error(
                ExceptionTranslationKey.TEMPERATURE_CHANGE_FAILED
            ) from err

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode."""
        feat = self._get_feature(FEATURE_MODE)
        if not feat:
            raise home_assistant_error(ExceptionTranslationKey.FEATURE_UNAVAILABLE)

        # Get available API modes from device
        available_api_modes = self._get_available_api_modes(feat)

        # Convert HA standard state to Viessmann API mode
        # Find first candidate that's actually available on device
        candidates = self._get_api_mode_candidates(operation_mode)
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
            response = await self.coordinator.async_set_feature(
                self._map_key, feat.name, viessmann_mode
            )
            if not response.success:
                raise service_validation_error(ExceptionTranslationKey.COMMAND_REJECTED)

            # Clear optimistic mode - let next poll pick up real value
            self._optimistic_mode = None
            self.async_write_ha_state()
        except ServiceValidationError:
            self._optimistic_mode = None
            self.async_write_ha_state()
            raise
        except ValueError as err:
            self._optimistic_mode = None
            self.async_write_ha_state()
            _LOGGER.debug("Viessmann rejected requested water-heater mode: %s", err)
            raise service_validation_error(
                ExceptionTranslationKey.COMMAND_REJECTED
            ) from err
        except ConfigEntryAuthFailed:
            raise
        except (HomeAssistantError, ViError) as err:
            # ROLLBACK on error
            self._optimistic_mode = None
            self.async_write_ha_state()
            _LOGGER.debug("Unable to change Viessmann water-heater mode: %s", err)
            raise home_assistant_error(
                ExceptionTranslationKey.MODE_CHANGE_FAILED
            ) from err

    def _get_available_api_modes(self, feat: Feature) -> list[str]:
        """Get list of available API modes from feature constraints."""
        if feat.control and feat.control.options:
            return get_feature_string_options(feat.control.options)
        return []
