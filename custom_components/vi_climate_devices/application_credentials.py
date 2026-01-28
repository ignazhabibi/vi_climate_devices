"""Application credentials platform for Viessmann Climate Devices."""

from __future__ import annotations

import logging

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

_LOGGER = logging.getLogger(__name__)


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
    return LocalOAuth2ImplementationWithPkce(
        hass,
        auth_domain,
        credential.client_id,
        authorize_url=ENDPOINT_AUTHORIZE,
        token_url=ENDPOINT_TOKEN,
        client_secret=credential.client_secret,
    )
