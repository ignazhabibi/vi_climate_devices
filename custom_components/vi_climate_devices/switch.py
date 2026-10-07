"""Switch platform for Viessmann Climate Devices."""

from __future__ import annotations

from typing import Any

# TODO(HA 2026.10): Import SwitchDeviceClass from
# homeassistant.components.switch.const and drop the pyright ignore.
from homeassistant.components.switch import (
    SwitchDeviceClass,  # pyright: ignore[reportPrivateImportUsage]
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViClimateDevicesConfigEntry
from .const import IGNORED_FEATURES, TESTED_DEVICES
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import ViClimateFeatureEntity, async_setup_dynamic_entities
from .exceptions import ExceptionTranslationKey, home_assistant_error
from .utils import (
    beautify_name,
    get_feature_bool_value,
    is_feature_boolean_like,
    is_feature_ignored,
)

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
class ViClimateSwitch(ViClimateFeatureEntity, SwitchEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
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
        super().__init__(
            coordinator,
            map_key,
            feature_name,
            description,
            enabled_default=enabled_default,
        )
        self.entity_description = description
        self._optimistic_state: bool | None = None

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

        self._optimistic_state = target_state
        self.async_write_ha_state()
        await self._async_write_feature(
            feat.name,
            target_state,
            ExceptionTranslationKey.SWITCH_OPERATION_FAILED,
            self._clear_optimistic_state,
        )

    def _clear_optimistic_state(self) -> None:
        """Forget the unconfirmed switch state."""
        self._optimistic_state = None
