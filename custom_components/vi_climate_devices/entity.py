"""Shared entity behavior for Viessmann Climate Devices."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from vi_api_client import Feature, FeatureValue, ViError

from .const import DOMAIN
from .coordinator import ViClimateDataUpdateCoordinator
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
    service_validation_error,
)
from .utils import beautify_name

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityTemplate[EntityDescriptionT: EntityDescription]:
    """Pair a feature-name pattern with its concrete entity description type."""

    pattern: re.Pattern[str]
    description: EntityDescriptionT


class ViClimateEntity(CoordinatorEntity[ViClimateDataUpdateCoordinator]):
    """Base entity that reflects per-device refresh availability."""

    _attr_has_entity_name = True
    _availability_feature_names: tuple[str, ...] = ()

    def __init__(
        self, coordinator: ViClimateDataUpdateCoordinator, map_key: str
    ) -> None:
        """Bind the entity to one coordinator device.

        Home Assistant reads device info only when the entity is added, so it
        is captured once from the device present at creation.

        Raises:
            ValueError: If the device is absent from coordinator data.
        """
        super().__init__(coordinator)
        device = coordinator.data.get(map_key)
        if device is None:
            raise ValueError(f"Device {map_key} not found in coordinator data")
        self._map_key = map_key
        self._unique_id_prefix = f"{device.gateway_serial}-{device.id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._unique_id_prefix)},
            name=device.model_id,
            manufacturer="Viessmann",
            model=device.model_id,
            serial_number=device.gateway_serial,
        )

    @property
    def available(self) -> bool:
        """Return whether the coordinator has current data for this device."""
        if not super().available or not self.coordinator.is_device_available(
            self._map_key
        ):
            return False
        device = self.coordinator.data.get(self._map_key)
        if device is None:
            return False
        return all(
            device.get_feature(feature_name) is not None
            for feature_name in self._availability_feature_names
        )

    def _get_feature(self, name: str) -> Feature | None:
        """Return the latest feature by name, or None without a device."""
        device = self.coordinator.data.get(self._map_key)
        if device is None:
            return None
        return device.get_feature(name)

    async def _async_write_feature(
        self,
        feature_name: str,
        value: FeatureValue,
        failure_key: ExceptionTranslationKey,
        clear_optimistic_state: Callable[[], None],
    ) -> None:
        """Write a feature value and translate failures for the action caller.

        The optimistic state is cleared after every outcome, including a
        reauthentication failure, so an unconfirmed value never stays visible.

        Raises:
            ServiceValidationError: If Viessmann or the client rejects the value.
            ConfigEntryAuthFailed: If Viessmann rejects the credentials.
            HomeAssistantError: If the write fails for another reason.
        """
        try:
            response = await self.coordinator.async_set_feature(
                self._map_key, feature_name, value
            )
            if not response.success:
                raise service_validation_error(ExceptionTranslationKey.COMMAND_REJECTED)
        except ServiceValidationError, ConfigEntryAuthFailed:
            raise
        except ValueError as err:
            _LOGGER.debug("Viessmann rejected a feature command: %s", err)
            raise service_validation_error(
                ExceptionTranslationKey.COMMAND_REJECTED
            ) from err
        except (HomeAssistantError, ViError) as err:
            _LOGGER.debug("Unable to write a Viessmann feature: %s", err)
            raise home_assistant_error(failure_key) from err
        finally:
            clear_optimistic_state()
            self.async_write_ha_state()


class ViClimateFeatureEntity(ViClimateEntity):
    """Base entity backed by a single Viessmann feature."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: EntityDescription,
        translation_placeholders: dict[str, str] | None = None,
        enabled_default: bool | None = True,
    ) -> None:
        """Initialize identity, naming and availability for the feature.

        Raises:
            ValueError: If the device is absent from coordinator data.
        """
        super().__init__(coordinator, map_key)
        self._feature_name = feature_name
        self._availability_feature_names = (feature_name,)
        self._attr_translation_placeholders = translation_placeholders or {}
        if enabled_default is not None:
            self._attr_entity_registry_enabled_default = enabled_default
        self._attr_unique_id = f"{self._unique_id_prefix}-{description.key}"
        # Auto-discovered features have no translation key, so derive a name.
        if not description.translation_key:
            self._attr_name = (
                description.name
                if isinstance(description.name, str)
                else beautify_name(feature_name)
            )

    @property
    def feature_data(self) -> Feature | None:
        """Return the latest data for the entity's feature."""
        return self._get_feature(self._feature_name)


def async_setup_dynamic_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ViClimateDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
    discover_entities: Callable[[], Sequence[Entity]],
) -> None:
    """Add discovered entities initially and whenever coordinator data changes."""
    added_unique_ids: set[str] = set()

    def add_new_entities() -> None:
        """Add only entities that have not been created by this platform."""
        registry_unique_ids = {
            entity.unique_id
            for entity in er.async_get(hass).entities.values()
            if entity.config_entry_id == entry.entry_id
        }
        added_unique_ids.intersection_update(registry_unique_ids)
        entities = [
            entity
            for entity in discover_entities()
            if entity.unique_id is not None and entity.unique_id not in added_unique_ids
        ]
        added_unique_ids.update(
            entity.unique_id for entity in entities if entity.unique_id is not None
        )
        async_add_entities(entities)

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))
