"""Tests for application credentials helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
)
from vi_api_client.const import ENDPOINT_AUTHORIZE, ENDPOINT_TOKEN

from custom_components.vi_climate_devices.application_credentials import (
    async_get_auth_implementation,
    async_get_authorization_server,
)


@pytest.mark.asyncio
async def test_async_get_authorization_server_uses_viessmann_endpoints(
    hass: HomeAssistant,
) -> None:
    """Test the authorization server points to the Viessmann OAuth endpoints."""
    # Arrange: Use the Home Assistant test instance as-is.

    # Act: Build the advertised authorization server metadata.
    server = await async_get_authorization_server(hass)

    # Assert: The returned endpoints match the Viessmann library constants.
    assert str(server.authorize_url) == ENDPOINT_AUTHORIZE
    assert str(server.token_url) == ENDPOINT_TOKEN


@pytest.mark.asyncio
async def test_async_get_auth_implementation_returns_pkce_implementation(
    hass: HomeAssistant,
) -> None:
    """Test the credentials helper builds a PKCE-based local OAuth implementation."""
    # Arrange: Provide stored Home Assistant application credentials.
    credential = ClientCredential(
        client_id="client-id",
        client_secret="client-secret",
        name="Viessmann",
    )

    # Act: Create the OAuth implementation from the stored credentials.
    implementation = await async_get_auth_implementation(
        hass,
        "vi_climate_devices",
        credential,
    )

    # Assert: The integration uses a PKCE-capable local OAuth implementation.
    assert isinstance(implementation, LocalOAuth2ImplementationWithPkce)
    assert implementation.client_id == "client-id"
    assert implementation.client_secret == ""
    assert implementation.authorize_url == ENDPOINT_AUTHORIZE
    assert implementation.token_url == ENDPOINT_TOKEN


@pytest.mark.asyncio
async def test_async_get_auth_implementation_uses_fresh_pkce_verifier(
    hass: HomeAssistant,
) -> None:
    """Test each OAuth flow receives a fresh PKCE verifier."""
    # Arrange: Provide the same stored application credential for two flows.
    credential = ClientCredential(
        client_id="client-id",
        client_secret="ignored-placeholder",
        name="Viessmann",
    )

    # Act: Create two independent OAuth implementations.
    first_implementation = await async_get_auth_implementation(
        hass,
        "vi_climate_devices",
        credential,
    )
    second_implementation = await async_get_auth_implementation(
        hass,
        "vi_climate_devices",
        credential,
    )

    # Assert: Each flow uses its own implementation and PKCE verifier.
    assert first_implementation is not second_implementation
    assert first_implementation.code_verifier != second_implementation.code_verifier


@pytest.mark.asyncio
async def test_refresh_request_omits_application_credential_secret(
    hass: HomeAssistant,
) -> None:
    """Test a Viessmann refresh request never sends the HA placeholder secret."""
    # Arrange: Build the PKCE implementation and a successful token response.
    credential = ClientCredential(
        client_id="client-id",
        client_secret="ignored-placeholder",
        name="Viessmann",
    )
    implementation = await async_get_auth_implementation(
        hass,
        "vi_climate_devices",
        credential,
    )
    response = MagicMock(status=200)
    response.json = AsyncMock(
        return_value={
            "access_token": "fresh-access-token",
            "expires_in": 3600,
        }
    )
    session = MagicMock()
    session.post = AsyncMock(return_value=response)

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_clientsession",
        return_value=session,
    ):
        # Act: Refresh an expired access token through Home Assistant's helper.
        refreshed_token = await implementation.async_refresh_token(
            {
                "access_token": "expired-access-token",
                "expires_at": 0,
                "expires_in": 3600,
                "refresh_token": "refresh-token",
            }
        )

    # Assert: The request matches Viessmann's public-client refresh contract.
    session.post.assert_awaited_once_with(
        ENDPOINT_TOKEN,
        data={
            "client_id": "client-id",
            "grant_type": "refresh_token",
            "refresh_token": "refresh-token",
        },
    )
    assert refreshed_token["access_token"] == "fresh-access-token"
    assert refreshed_token["refresh_token"] == "refresh-token"
