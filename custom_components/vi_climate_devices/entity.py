"""Shared entity behavior for Viessmann Climate Devices."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ViClimateDataUpdateCoordinator


class ViClimateEntity(CoordinatorEntity[ViClimateDataUpdateCoordinator]):
    """Base entity that reflects per-device refresh availability."""

    _map_key: str

    @property
    def available(self) -> bool:
        """Return whether the coordinator has current data for this device."""
        return super().available and self.coordinator.is_device_available(self._map_key)
