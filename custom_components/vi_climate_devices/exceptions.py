"""Translated exceptions exposed by the Viessmann integration."""

from __future__ import annotations

from enum import StrEnum

from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN


class ExceptionTranslationKey(StrEnum):
    """Translation keys for user-facing integration errors."""

    FEATURE_UNAVAILABLE = "feature_unavailable"
    UNSUPPORTED_MODE = "unsupported_mode"
    COMMAND_REJECTED = "command_rejected"
    TEMPERATURE_CHANGE_FAILED = "temperature_change_failed"
    MODE_CHANGE_FAILED = "mode_change_failed"
    SELECTION_FAILED = "selection_failed"
    SWITCH_OPERATION_FAILED = "switch_operation_failed"
    NUMBER_CHANGE_FAILED = "number_change_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    SETUP_NOT_READY = "setup_not_ready"


def home_assistant_error(key: ExceptionTranslationKey) -> HomeAssistantError:
    """Create a translated general integration error."""
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


def service_validation_error(
    key: ExceptionTranslationKey,
) -> ServiceValidationError:
    """Create a translated error caused by an invalid requested action."""
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def config_entry_auth_failed(
    key: ExceptionTranslationKey = ExceptionTranslationKey.AUTHENTICATION_FAILED,
) -> ConfigEntryAuthFailed:
    """Create a translated configuration authentication error."""
    return ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key=key)


def config_entry_not_ready(
    key: ExceptionTranslationKey = ExceptionTranslationKey.SETUP_NOT_READY,
) -> ConfigEntryNotReady:
    """Create a translated transient configuration setup error."""
    return ConfigEntryNotReady(translation_domain=DOMAIN, translation_key=key)


def update_failed(
    key: ExceptionTranslationKey = ExceptionTranslationKey.SETUP_NOT_READY,
) -> UpdateFailed:
    """Create a translated coordinator update error."""
    return UpdateFailed(translation_domain=DOMAIN, translation_key=key)
