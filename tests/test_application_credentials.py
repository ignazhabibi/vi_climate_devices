"""Tests for application credentials helpers."""

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
    assert implementation.client_secret == "client-secret"
    assert implementation.authorize_url == ENDPOINT_AUTHORIZE
    assert implementation.token_url == ENDPOINT_TOKEN
