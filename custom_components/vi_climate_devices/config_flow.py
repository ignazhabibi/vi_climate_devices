"""Config flow for Viessmann Climate Devices integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from vi_api_client.const import DEFAULT_SCOPES

from .const import DOMAIN


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Config flow to handle Viessmann Climate Devices OAuth2 authentication."""

    DOMAIN = DOMAIN

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
        self, entry_data: Mapping[str, object]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the refresh token is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, object] | None = None,
    ) -> ConfigFlowResult:
        """Confirm re-authentication and restart the OAuth flow."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )

        return await self.async_step_pick_implementation(
            user_input={
                "implementation": self._get_reauth_entry().data["auth_implementation"],
            },
        )

    async def async_oauth_create_entry(
        self,
        data: dict[str, object],
    ) -> ConfigFlowResult:
        """Create or update the config entry after OAuth authentication."""
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates=data,
            )
        return await super().async_oauth_create_entry(data)
