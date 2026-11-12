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
from vi_api_client import (
    Device,
    Feature,
    FeatureValue,
    ViCommandRejectedError,
    ViError,
)

from .const import DOMAIN, FEATURE_SUCCESSORS
from .coordinator import ViClimateDataUpdateCoordinator
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
    service_validation_error,
)
from .utils import beautify_name, get_feature_string_options

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityTemplate[EntityDescriptionT: EntityDescription]:
    """Pair a feature-name pattern with its concrete entity description type."""

    pattern: re.Pattern[str]
    description: EntityDescriptionT


def count_device_instances(device: Device, prefix: str) -> int:
    """Return how many instances of a numbered component a device reports.

    The API lists enabled circuits, compressors, and burners in a
    `<prefix>enabled` feature. Other components (fans, evaporators, ...) are
    counted by the distinct indices of their features.
    """
    for feature in device.features:
        if feature.name == f"{prefix}enabled" and isinstance(feature.value, list):
            return len(get_feature_string_options(feature.value))
    return len(
        {
            index
            for feature in device.features
            if feature.name.startswith(prefix)
            and (index := feature.name[len(prefix) :].split(".", 1)[0]).isdigit()
        }
    )


def get_numbered_translation(
    translation_key: str, device: Device, prefix: str, index: str
) -> tuple[str, dict[str, str]]:
    """Return the translation key and placeholders for a numbered entity.

    Single-instance components keep the plain name. Devices with several
    heating circuits or components use the `<key>_numbered` variant with a
    1-based `{number}`, matching Viessmann's own circuit numbering.
    """
    if count_device_instances(device, prefix) > 1:
        return f"{translation_key}_numbered", {"number": str(int(index) + 1)}
    return translation_key, {}


def get_template_translation(
    match: re.Match[str], translation_key: str, device: Device
) -> tuple[str, dict[str, str]]:
    """Return the numbered translation for a feature matched by an entity template.

    The first capture group of every template is the component index; the
    feature name before it identifies the component type.
    """
    prefix = match.string[: match.start(1)]
    return get_numbered_translation(translation_key, device, prefix, match.group(1))


_DEPRECATED_FEATURES_BY_SUCCESSOR = {
    successor: deprecated for deprecated, successor in FEATURE_SUCCESSORS.items()
}


def get_feature_or_successor(device: Device, feature_name: str) -> Feature | None:
    """Return the successor of a deprecated feature, or the feature itself.

    Depending on the firmware, a device reports the successor, the deprecated
    feature, or both. The successor wins when the device reports it.
    """
    if (successor_name := FEATURE_SUCCESSORS.get(feature_name)) is not None and (
        successor := device.get_feature(successor_name)
    ) is not None:
        return successor
    return device.get_feature(feature_name)


def get_entity_feature_name(device: Device, feature_name: str) -> str | None:
    """Return the feature name that identifies the entity of a reported feature.

    A successor is identified by its deprecated feature, so the existing
    entity keeps its unique ID instead of being replaced. When the device also
    reports the deprecated feature, that feature creates the entity, and None
    is returned for the successor to avoid a duplicate.
    """
    deprecated_name = _DEPRECATED_FEATURES_BY_SUCCESSOR.get(feature_name)
    if deprecated_name is None:
        return feature_name
    if device.get_feature(deprecated_name) is not None:
        return None
    return deprecated_name


def async_remove_successor_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ViClimateDataUpdateCoordinator,
    domain: str,
) -> None:
    """Remove registry entries that were auto-discovered for a successor.

    Before a successor was mapped, auto-discovery created a separate entity
    for it next to the defined entity of the deprecated feature. The defined
    entity now reads the successor, so the duplicate would stay orphaned.
    """
    registry = er.async_get(hass)
    for device in coordinator.data.values():
        for successor_name in sorted(_DEPRECATED_FEATURES_BY_SUCCESSOR):
            unique_id = f"{device.gateway_serial}-{device.id}-{successor_name}"
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id is None:
                continue
            registry_entry = registry.async_get(entity_id)
            if registry_entry is None or registry_entry.config_entry_id != (
                entry.entry_id
            ):
                continue
            _LOGGER.debug("Removing duplicate successor entity %s", entity_id)
            registry.async_remove(entity_id)


def describe_write_rejection(err: ValueError | ViCommandRejectedError) -> str:
    """Return a log-safe description of a rejected write.

    A local validation error describes the requested value. The API's
    rejection message can carry installation details, so only its reason is
    logged.
    """
    if isinstance(err, ViCommandRejectedError):
        return f"reason={err.reason}"
    return str(err)


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
            get_feature_or_successor(device, feature_name) is not None
            for feature_name in self._availability_feature_names
        )

    def _get_feature(self, name: str) -> Feature | None:
        """Return the latest feature by name, or None without a device.

        A deprecated feature with a known successor resolves to the successor
        whenever the device reports it.
        """
        device = self.coordinator.data.get(self._map_key)
        if device is None:
            return None
        return get_feature_or_successor(device, name)

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
            await self.coordinator.async_set_feature(self._map_key, feature_name, value)
        except ServiceValidationError, ConfigEntryAuthFailed:
            raise
        except (ValueError, ViCommandRejectedError) as err:
            # Handled before ViError: a rejection is a user-facing validation
            # outcome, not a general write failure.
            _LOGGER.debug(
                "Viessmann rejected a feature command: %s",
                describe_write_rejection(err),
            )
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


def async_setup_dynamic_entities(  # noqa: PLR0913, PLR0917
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ViClimateDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
    discover_entities: Callable[[], Sequence[Entity]],
    superseded_domains: Sequence[str] = (),
) -> None:
    """Add discovered entities initially and whenever coordinator data changes.

    A feature keeps its unique ID when it moves to another platform, for
    example a read-only boolean that becomes writable and turns from a binary
    sensor into a switch. Entries with the same unique ID in a superseded
    domain are removed when the replacing entity is added, so no orphaned
    registry entry stays behind.
    """
    added_unique_ids: set[str] = set()

    def add_new_entities() -> None:
        """Add only entities that have not been created by this platform."""
        registry = er.async_get(hass)
        registry_unique_ids = {
            entity.unique_id
            for entity in registry.entities.values()
            if entity.config_entry_id == entry.entry_id
        }
        added_unique_ids.intersection_update(registry_unique_ids)
        entities = [
            entity
            for entity in discover_entities()
            if entity.unique_id is not None and entity.unique_id not in added_unique_ids
        ]
        new_unique_ids = sorted(
            entity.unique_id for entity in entities if entity.unique_id is not None
        )
        added_unique_ids.update(new_unique_ids)
        _remove_superseded_entries(registry, entry, new_unique_ids, superseded_domains)
        async_add_entities(entities)

    add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))


def _remove_superseded_entries(
    registry: er.EntityRegistry,
    entry: ConfigEntry,
    unique_ids: Sequence[str],
    superseded_domains: Sequence[str],
) -> None:
    """Remove this entry's registry entries that a new entity replaces."""
    for domain in superseded_domains:
        for unique_id in unique_ids:
            entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id is None:
                continue
            registry_entry = registry.async_get(entity_id)
            if registry_entry is None or registry_entry.config_entry_id != (
                entry.entry_id
            ):
                continue
            _LOGGER.debug("Removing superseded entity %s", entity_id)
            registry.async_remove(entity_id)
