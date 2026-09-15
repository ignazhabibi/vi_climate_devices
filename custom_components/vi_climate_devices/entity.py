"""Shared entity behavior for Viessmann Climate Devices."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ViClimateDataUpdateCoordinator


class ViClimateEntity(CoordinatorEntity[ViClimateDataUpdateCoordinator]):
    """Base entity that reflects per-device refresh availability."""

    _map_key: str
    _availability_feature_names: tuple[str, ...] = ()

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
            if entity.config_entry_id == entry.entry_id and entity.unique_id is not None
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
