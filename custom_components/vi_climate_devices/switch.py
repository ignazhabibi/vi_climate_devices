"""Switch platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
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
from .entity import ViClimateEntity, async_setup_dynamic_entities
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
    service_validation_error,
)
from .utils import (
    beautify_name,
    get_feature_bool_value,
    is_feature_boolean_like,
    is_feature_ignored,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


SWITCH_TYPES: dict[str, SwitchEntityDescription] = {
    # Updated keys for Flat Architecture
    "heating.dhw.oneTimeCharge.active": SwitchEntityDescription(
        key="heating.dhw.oneTimeCharge.active",
        translation_key="dhw_one_time_charge",
        device_class=SwitchDeviceClass.SWITCH,
    ),
    "heating.dhw.hygiene.enabled": SwitchEntityDescription(
        key="heating.dhw.hygiene.enabled",
        translation_key="dhw_hygiene",
        device_class=SwitchDeviceClass.SWITCH,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices switch based on a config entry."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_switches(coordinator),
    )


def _discover_switches(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[ViClimateSwitch]:
    """Discover switch entities from the current coordinator data."""
    entities: list[ViClimateSwitch] = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                # 1. Defined Entities
                if feature.name in SWITCH_TYPES:
                    if feature.is_enabled and feature.is_writable:
                        desc = SWITCH_TYPES[feature.name]
                        entities.append(
                            ViClimateSwitch(coordinator, map_key, feature.name, desc)
                        )
                    continue

                # 2. Automatic Discovery (Must be writable)
                if not feature.is_writable:
                    continue

                # Automatic Discovery (Fallback)
                # Writable boolean-like feature
                if feature.is_writable and is_feature_boolean_like(feature.value):
                    description = SwitchEntityDescription(
                        key=feature.name,
                        name=beautify_name(feature.name),
                        entity_category=EntityCategory.CONFIG,
                    )
                    # Only disable entities by default for thoroughly tested devices
                    is_tested = device.model_id in TESTED_DEVICES
                    entities.append(
                        ViClimateSwitch(
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
class ViClimateSwitch(ViClimateEntity, SwitchEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Representation of a Viessmann Climate Devices Switch Entity."""

    def __init__(
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: SwitchEntityDescription,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._map_key = map_key
        self._feature_name = feature_name
        self._availability_feature_names = (feature_name,)
        self._attr_entity_registry_enabled_default = enabled_default
        self._optimistic_state: bool | None = None

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
    def is_on(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return true if the switch is on."""
        # Return optimistic state if set
        if self._optimistic_state is not None:
            return self._optimistic_state

        feat = self.feature_data
        if not feat:
            return None

        return get_feature_bool_value(feat.value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._async_set_state(False)

    async def _async_set_state(self, target_state: bool) -> None:
        """Internal method to set the switch state."""
        feat = self.feature_data
        if not feat:
            raise home_assistant_error(ExceptionTranslationKey.FEATURE_UNAVAILABLE)

        # 1. OPTIMISTIC UPDATE
        self._optimistic_state = target_state
        self.async_write_ha_state()

        # 2. EXECUTE COMMAND
        try:
            response = await self.coordinator.async_set_feature(
                self._map_key, feat.name, target_state
            )
            _LOGGER.debug(
                "Command response: success=%s, message=%s, reason=%s",
                response.success,
                response.message,
                response.reason,
            )

            if not response.success:
                raise service_validation_error(ExceptionTranslationKey.COMMAND_REJECTED)

            # 3. Clear optimistic state
            self._optimistic_state = None
            self.async_write_ha_state()
        except ServiceValidationError:
            self._optimistic_state = None
            self.async_write_ha_state()
            raise
        except ValueError as err:
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.debug("Viessmann rejected switch state: %s", err)
            raise service_validation_error(
                ExceptionTranslationKey.COMMAND_REJECTED
            ) from err
        except ConfigEntryAuthFailed:
            raise
        except (HomeAssistantError, ViError) as err:
            # 5. ROLLBACK on error
            self._optimistic_state = None
            self.async_write_ha_state()
            _LOGGER.debug("Unable to change Viessmann switch state: %s", err)
            raise home_assistant_error(
                ExceptionTranslationKey.SWITCH_OPERATION_FAILED
            ) from err
