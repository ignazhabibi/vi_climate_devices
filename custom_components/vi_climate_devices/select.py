"""Select platform for Viessmann Climate Devices."""

from __future__ import annotations

import dataclasses
import re

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from vi_api_client import Feature

from . import ViClimateDevicesConfigEntry
from .const import IGNORED_FEATURES, TESTED_DEVICES
from .coordinator import ViClimateDataUpdateCoordinator
from .entity import (
    EntityTemplate,
    ViClimateFeatureEntity,
    async_setup_dynamic_entities,
)
from .exceptions import (
    ExceptionTranslationKey,
    home_assistant_error,
)
from .utils import beautify_name, is_feature_ignored

PARALLEL_UPDATES = 0


SELECT_TYPES: dict[str, SelectEntityDescription] = {
    "heating.dhw.operating.modes.active": SelectEntityDescription(
        key="heating.dhw.operating.modes.active",
        translation_key="dhw_mode",
        entity_category=EntityCategory.CONFIG,
    ),
}


# Templates with regex patterns for dynamic feature names
SELECT_TEMPLATES: tuple[EntityTemplate[SelectEntityDescription], ...] = (
    # Heating Circuit Operating Modes (heating.circuits.N.operating.modes.active)
    EntityTemplate(
        pattern=re.compile(r"^heating\.circuits\.(\d+)\.operating\.modes\.active$"),
        description=SelectEntityDescription(
            key="placeholder",
            translation_key="heating_circuit_operation_mode",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
)


def _get_select_entity_description(
    feature_name: str,
) -> tuple[SelectEntityDescription, dict[str, str] | None] | None:
    """Find a matching entity description for a dynamic feature name.

    Returns:
        tuple: (description, translation_placeholders) or None
    """
    for template in SELECT_TEMPLATES:
        match = template.pattern.match(feature_name)
        if match:
            index = match.group(1)
            base_desc = template.description

            new_desc = dataclasses.replace(
                base_desc,
                key=feature_name,
                translation_key=base_desc.translation_key,
            )
            return new_desc, {"index": index}
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViClimateDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Viessmann Climate Devices select based on a config entry."""
    coordinator = entry.runtime_data
    async_setup_dynamic_entities(
        hass,
        entry,
        coordinator,
        async_add_entities,
        lambda: _discover_selects(coordinator),
    )


def _discover_selects(
    coordinator: ViClimateDataUpdateCoordinator,
) -> list[ViClimateSelect]:
    """Discover select entities from the current coordinator data."""
    entities: list[ViClimateSelect] = []

    if coordinator.data:
        for map_key, device in coordinator.data.items():
            for feature in device.features:
                # Skip ignored features early
                if is_feature_ignored(feature.name, IGNORED_FEATURES):
                    continue

                if not feature.is_writable:
                    continue

                # 1. Defined Entities
                if feature.name in SELECT_TYPES:
                    desc = SELECT_TYPES[feature.name]
                    entities.append(
                        ViClimateSelect(coordinator, map_key, feature.name, desc)
                    )
                    continue

                # 2. Dynamic Templates
                if match_result := _get_select_entity_description(feature.name):
                    description, placeholders = match_result
                    entities.append(
                        ViClimateSelect(
                            coordinator,
                            map_key,
                            feature.name,
                            description,
                            translation_placeholders=placeholders,
                        )
                    )
                    continue

                # Automatic Discovery (Fallback)
                # Control must exist and have enum options
                if feature.control and feature.control.options is not None:
                    description = SelectEntityDescription(
                        key=feature.name,
                        name=beautify_name(feature.name),
                        entity_category=EntityCategory.CONFIG,
                    )
                    # Only disable entities by default for thoroughly tested devices
                    is_tested = device.model_id in TESTED_DEVICES
                    entities.append(
                        ViClimateSelect(
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
class ViClimateSelect(ViClimateFeatureEntity, SelectEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Representation of a Viessmann Climate Devices Select Entity."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        coordinator: ViClimateDataUpdateCoordinator,
        map_key: str,
        feature_name: str,
        description: SelectEntityDescription,
        translation_placeholders: dict[str, str] | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the entity."""
        super().__init__(
            coordinator,
            map_key,
            feature_name,
            description,
            translation_placeholders,
            enabled_default,
        )
        self.entity_description = description
        self._optimistic_option: str | None = None
        self._update_options(self.feature_data)

    def _update_options(self, feature: Feature | None) -> None:
        """Extract available options from feature control."""
        self._attr_options = []
        if feature and feature.control and feature.control.options:
            # Options can be Dict[value, label] or List[value]
            # We normalize to list of strings
            normalized_opts: list[str] = []
            for opt in feature.control.options:
                if isinstance(opt, dict):
                    option_value = opt.get("value")
                    if isinstance(option_value, str):
                        # Case B: Dict with value/(label)
                        normalized_opts.append(option_value)
                elif isinstance(opt, str):
                    # Case A: String value
                    normalized_opts.append(opt)
            self._attr_options = normalized_opts

    @property
    def current_option(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current value."""
        # Return optimistic option if set
        if self._optimistic_option is not None:
            return self._optimistic_option

        feat = self.feature_data
        if not feat:
            return None

        # Check if value is valid option
        if isinstance(feat.value, str) and feat.value in self.options:
            return feat.value

        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        feat = self.feature_data
        if not feat:
            raise home_assistant_error(ExceptionTranslationKey.FEATURE_UNAVAILABLE)

        self._optimistic_option = option
        self.async_write_ha_state()
        await self._async_write_feature(
            feat.name,
            option,
            ExceptionTranslationKey.SELECTION_FAILED,
            self._clear_optimistic_option,
        )

    def _clear_optimistic_option(self) -> None:
        """Forget the unconfirmed option."""
        self._optimistic_option = None
