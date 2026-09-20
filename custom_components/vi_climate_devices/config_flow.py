"""Config flow for Viessmann Climate Devices integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import OAuth2TokenRequestError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from vi_api_client import (
    DEFAULT_SCOPES,
    AbstractAuth,
    JsonValue,
    ViAuthError,
    ViClient as ViessmannClient,
    ViConnectionError,
    ViError,
    ViRateLimitError,
    ViServerInternalError,
)

from .const import DOMAIN


class _OAuthValidationAuth(AbstractAuth):
    """Supply an unpersisted OAuth token to the Viessmann client."""

    def __init__(self, hass: HomeAssistant, access_token: str) -> None:
        """Initialize the bridge with Home Assistant's shared web session."""
        super().__init__(websession=async_get_clientsession(hass))
        self._access_token = access_token

    async def async_get_access_token(self) -> str:
        """Return the token issued in the current OAuth flow."""
        return self._access_token


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Config flow to handle Viessmann Climate Devices OAuth2 authentication."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the OAuth flow and its in-memory validation data."""
        super().__init__()
        self._validation_data: dict[str, JsonValue] | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict[str, str]:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": DEFAULT_SCOPES,
        }

    async def async_step_reauth(
        self, entry_data: Mapping[str, JsonValue]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the refresh token is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, JsonValue] | None = None,
    ) -> ConfigFlowResult:
        """Confirm re-authentication and restart the OAuth flow."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )

        auth_implementation = self._get_reauth_entry().data.get("auth_implementation")
        if not isinstance(auth_implementation, str):
            return self.async_abort(reason="unknown")
        # Home Assistant leaves this inherited method's input unparameterized.
        return await self.async_step_pick_implementation(  # pyright: ignore[reportUnknownMemberType]
            user_input={"implementation": auth_implementation},
        )

    async def async_oauth_create_entry(
        self,
        data: dict[str, JsonValue],
    ) -> ConfigFlowResult:
        """Create or update the config entry after OAuth authentication."""
        error = await self._async_validate_api_access(data)
        if error is not None:
            self._validation_data = data
            return self.async_show_form(
                step_id="validate",
                data_schema=vol.Schema({}),
                errors={"base": error},
            )

        return await self._async_finish_oauth(data)

    async def async_step_validate(
        self,
        user_input: dict[str, JsonValue] | None = None,
    ) -> ConfigFlowResult:
        """Retry API access validation without repeating OAuth."""
        if self._validation_data is None:
            return self.async_abort(reason="unknown")

        error = await self._async_validate_api_access(self._validation_data)
        if error is not None:
            return self.async_show_form(
                step_id="validate",
                data_schema=vol.Schema({}),
                errors={"base": error},
            )

        return await self._async_finish_oauth(self._validation_data)

    async def _async_finish_oauth(self, data: dict[str, JsonValue]) -> ConfigFlowResult:
        """Persist OAuth data only after API validation succeeds."""
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates=data,
            )
        # Home Assistant leaves this inherited method's input unparameterized.
        return await super().async_oauth_create_entry(  # pyright: ignore[reportUnknownMemberType]
            data
        )

    async def _async_validate_api_access(
        self, data: dict[str, JsonValue]
    ) -> str | None:
        """Verify that the fresh OAuth token can access an installation."""
        token = data.get("token")
        if not isinstance(token, dict):
            return "invalid_auth"
        access_token = token.get("access_token")
        if not isinstance(access_token, str):
            return "invalid_auth"
        client = ViessmannClient(auth=_OAuthValidationAuth(self.hass, access_token))

        try:
            error = "no_installations" if not await client.get_installations() else None
        except OAuth2TokenRequestError, ViAuthError:
            error = "invalid_auth"
        except (
            TimeoutError,
            ViConnectionError,
            ViRateLimitError,
            ViServerInternalError,
        ):
            error = "cannot_connect"
        except ViError:
            error = "unknown"

        return error
