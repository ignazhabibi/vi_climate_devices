"""Tests for the OAuth config flow wrapper."""

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client.const import DEFAULT_SCOPES
from yarl import URL

from custom_components.vi_climate_devices.config_flow import OAuth2FlowHandler
from custom_components.vi_climate_devices.const import DOMAIN


class FakeOAuthImplementation(config_entry_oauth2_flow.AbstractOAuth2Implementation):
    """Minimal OAuth implementation for config flow tests."""

    @property
    def name(self) -> str:
        """Return a friendly implementation name."""
        return "Fake OAuth"

    @property
    def domain(self) -> str:
        """Return the provider domain."""
        return "fake-provider"

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Return a deterministic authorize URL for the flow."""
        return f"https://example.com/authorize?existing=1&flow_id={flow_id}"

    async def async_resolve_external_data(self, external_data: Any) -> dict[str, Any]:
        """Resolve external OAuth data."""
        return {"access_token": "token", "expires_in": 3600}

    async def _async_refresh_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """Return the unmodified token payload."""
        return token


@pytest.mark.asyncio
async def test_flow_handler_exposes_viessmann_scope() -> None:
    """Test the flow handler appends the Viessmann OAuth scopes to the authorize URL."""
    # Arrange: Instantiate the lightweight OAuth flow wrapper.
    flow_handler = OAuth2FlowHandler()

    # Act: Read the extra authorize data from the flow.
    authorize_data = flow_handler.extra_authorize_data

    # Assert: The flow publishes the library-defined Viessmann scope string.
    assert authorize_data == {"scope": DEFAULT_SCOPES}


@pytest.mark.asyncio
async def test_user_flow_shows_picker_and_starts_external_step(
    hass: HomeAssistant,
) -> None:
    """Test the user flow offers the implementation picker and starts OAuth auth."""
    # Arrange: Register one fake implementation through the OAuth helper layer.
    implementation = FakeOAuthImplementation()

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_implementations",
        return_value={implementation.domain: implementation},
    ):
        # Act: Start the flow and choose the fake implementation.
        start_result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        auth_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            {"implementation": implementation.domain},
        )

    # Assert: The flow shows the picker first and then redirects to OAuth auth.
    assert start_result["type"] is FlowResultType.FORM
    assert start_result["step_id"] == "pick_implementation"
    assert auth_result["type"] is FlowResultType.EXTERNAL_STEP
    assert auth_result["step_id"] == "auth"
    authorize_url = URL(auth_result["url"])
    assert authorize_url.query["existing"] == "1"
    assert authorize_url.query["scope"] == DEFAULT_SCOPES


@pytest.mark.asyncio
async def test_reauth_flow_shows_confirm_form_and_redirects_to_oauth(
    hass: HomeAssistant,
) -> None:
    """Test the reauth flow shows a confirmation form then starts the OAuth flow."""
    # Arrange: Create a config entry with expired token data and register it.
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "auth_implementation": "fake-provider",
            "retained_setting": "keep-me",
            "token": {
                "access_token": "expired-token",
                "expires_at": 0,
                "refresh_token": "dead-refresh",
                "token_type": "Bearer",
            },
        },
    )
    entry.add_to_hass(hass)

    implementation = FakeOAuthImplementation()

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_implementations",
        return_value={implementation.domain: implementation},
    ):
        # Act: Start the reauth flow (triggered by ConfigEntryAuthFailed).
        reauth_result = await entry.start_reauth_flow(hass)

        # Assert: The first step shows the reauth confirmation form.
        assert reauth_result["type"] is FlowResultType.FORM
        assert reauth_result["step_id"] == "reauth_confirm"

        # Act: User confirms the reauth form.
        confirm_result = await hass.config_entries.flow.async_configure(
            reauth_result["flow_id"],
            user_input={},
        )

        # Act: Complete the external callback with a fresh authorization code.
        callback_result = await hass.config_entries.flow.async_configure(
            reauth_result["flow_id"],
            user_input={"code": "fresh-code"},
        )

        # Act: Resolve the authorization code and persist the returned token.
        creation_result = await hass.config_entries.flow.async_configure(
            reauth_result["flow_id"],
        )

    # Assert: The flow redirects, updates the existing entry, and completes reauth.
    assert confirm_result["type"] is FlowResultType.EXTERNAL_STEP
    assert confirm_result["step_id"] == "auth"
    assert callback_result["type"] is FlowResultType.EXTERNAL_STEP_DONE
    assert creation_result["type"] is FlowResultType.ABORT
    assert creation_result["reason"] == "reauth_successful"
    assert entry.data["auth_implementation"] == "fake-provider"
    assert entry.data["retained_setting"] == "keep-me"
    assert entry.data["token"]["access_token"] == "token"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
