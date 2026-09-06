"""Tests for Home Assistant platform request parallelism."""

from custom_components.vi_climate_devices import (
    binary_sensor,
    climate,
    number,
    select,
    sensor,
    switch,
    water_heater,
)


def test_platforms_declare_unlimited_parallel_updates() -> None:
    """Test every platform delegates request serialization to the coordinator."""
    platforms = (
        binary_sensor,
        climate,
        number,
        select,
        sensor,
        switch,
        water_heater,
    )

    assert all(platform.PARALLEL_UPDATES == 0 for platform in platforms)
