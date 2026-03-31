"""Tests for the OAuth config flow wrapper."""

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
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
