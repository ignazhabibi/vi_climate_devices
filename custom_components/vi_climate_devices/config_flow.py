"""Config flow for Viessmann Climate Devices integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from vi_api_client.const import API_BASE_URL, DEFAULT_SCOPES

from .const import DOMAIN

USER_PROFILE_URL = f"{API_BASE_URL}/users/v1/users/me?sections=identity"


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
        try:
            account_id = await self._async_get_account_id(data)
        except ClientError, ValueError:
            return self.async_abort(reason="account_lookup_failed")

        existing_entry = await self.async_set_unique_id(account_id)

        if self.source == SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            if reauth_entry.unique_id is None:
                if existing_entry and existing_entry.entry_id != reauth_entry.entry_id:
                    return self.async_abort(reason="already_configured")
                self.hass.config_entries.async_update_entry(
                    reauth_entry, unique_id=account_id
                )
            else:
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                reauth_entry,
                data_updates=data,
            )

        self._abort_if_unique_id_configured()
        return await super().async_oauth_create_entry(data)

    async def _async_get_account_id(self, data: dict[str, object]) -> str:
        """Return the authenticated Viessmann account identifier."""
        token = data.get("token")
        if not isinstance(token, dict) or not isinstance(
            token.get("access_token"), str
        ):
            raise ValueError("OAuth response did not include an access token")

        response = await config_entry_oauth2_flow.async_oauth2_request(
            self.hass, token, "GET", USER_PROFILE_URL
        )
        try:
            response.raise_for_status()
            profile = await response.json()
        finally:
            response.release()

        if not isinstance(profile, Mapping):
            raise ValueError("User profile response was not an object")

        account = profile.get("data", profile)
        if not isinstance(account, Mapping):
            raise ValueError("User profile data was not an object")

        identity = account.get("identity", account)
        if not isinstance(identity, Mapping):
            identity = account

        for source in (identity, account):
            for key in ("id", "userId"):
                account_id = source.get(key)
                if isinstance(account_id, str) and account_id:
                    return account_id

        raise ValueError("User profile did not include an account identifier")
