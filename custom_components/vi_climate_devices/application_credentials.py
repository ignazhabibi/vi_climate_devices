"""Application credentials platform for Viessmann Climate Devices."""

from __future__ import annotations

from typing import override

from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
    LocalOAuth2ImplementationWithPkce,
)
from vi_api_client.const import ENDPOINT_AUTHORIZE, ENDPOINT_TOKEN


class _OAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Viessmann PKCE implementation with its application credential name."""

    def __init__(
        self,
        hass: HomeAssistant,
        auth_domain: str,
        credential: ClientCredential,
    ) -> None:
        """Initialize the OAuth implementation."""
        super().__init__(
            hass,
            auth_domain,
            credential.client_id,
            authorize_url=ENDPOINT_AUTHORIZE,
            token_url=ENDPOINT_TOKEN,
        )
        self._name = credential.name

    @property
    @override
    def name(self) -> str:
        """Return the application credential name."""
        return self._name or self.client_id


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    """Return authorization server."""
    return AuthorizationServer(
        authorize_url=ENDPOINT_AUTHORIZE,
        token_url=ENDPOINT_TOKEN,
    )


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> AbstractOAuth2Implementation:
    """Return auth implementation for a custom auth implementation."""
    return _OAuth2Implementation(
        hass,
        auth_domain,
        credential,
    )
