"""Tests for the OAuth config flow wrapper."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import OAuth2TokenRequestError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry
from vi_api_client import (
    DEFAULT_SCOPES,
    FixtureViClient,
    JsonValue,
    ViAuthError,
    ViConnectionError,
    ViError,
    ViRateLimitError,
    ViServerInternalError,
)
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


def _make_token_error() -> OAuth2TokenRequestError:
    """Create a transient OAuth token error."""
    return OAuth2TokenRequestError(
        request_info=MagicMock(),
        history=(),
        status=500,
        message="Service Unavailable",
        headers=MagicMock(),
        domain=DOMAIN,
    )


@pytest.fixture(autouse=True)
def mock_api_validation_client(
    mock_client: FixtureViClient,
) -> Iterator[tuple[FixtureViClient, MagicMock]]:
    """Return an API client whose default validation finds an installation."""
    with patch(
        "custom_components.vi_climate_devices.config_flow.ViessmannClient",
        return_value=mock_client,
    ) as client_factory:
        yield mock_client, client_factory


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
async def test_oauth_entry_creation_delegates_for_new_user_flow(
    hass: HomeAssistant,
) -> None:
    """Create a new entry through Home Assistant's standard OAuth flow."""
    # Arrange: A non-reauthentication flow must retain the base handler behavior.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()
    expected_result = {"type": FlowResultType.CREATE_ENTRY}
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh"}}

    with patch.object(
        config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
        "async_oauth_create_entry",
        new=AsyncMock(return_value=expected_result),
    ) as create_entry:
        # Act: Complete OAuth authentication for a newly configured integration.
        result = await flow_handler.async_oauth_create_entry(data)

    # Assert: The base flow creates the new entry rather than updating a reauth entry.
    assert result == expected_result
    create_entry.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_oauth_entry_creation_validates_installation_access(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Create an entry only after the fresh token can list an installation."""
    # Arrange: OAuth has returned a fresh token and the API exposes one installation.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    expected_result = {"type": FlowResultType.CREATE_ENTRY}
    _, client_factory = mock_api_validation_client

    with patch.object(
        config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
        "async_oauth_create_entry",
        new=AsyncMock(return_value=expected_result),
    ) as create_entry:
        # Act: Complete OAuth for a new configuration.
        result = await flow_handler.async_oauth_create_entry(data)

    # Assert: The validated token is handed to Home Assistant's normal entry flow.
    assert result == expected_result
    client_factory.assert_called_once()
    create_entry.assert_awaited_once_with(data)
    validation_auth = client_factory.call_args.kwargs["auth"]
    assert await validation_auth.async_get_access_token() == "fresh-token"
    assert validation_auth.websession is async_get_clientsession(hass)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_error", "expected_error"),
    [
        (_make_token_error(), "invalid_auth"),
        (ViAuthError("rejected"), "invalid_auth"),
        (TimeoutError(), "cannot_connect"),
        (ViConnectionError("offline"), "cannot_connect"),
        (ViRateLimitError("limited"), "cannot_connect"),
        (ViServerInternalError("unavailable"), "cannot_connect"),
        (ViError("invalid response"), "unknown"),
    ],
)
async def test_oauth_entry_creation_shows_translated_validation_failure(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
    api_error: Exception,
    expected_error: str,
) -> None:
    """Keep an OAuth token out of entry data when API validation fails."""
    # Arrange: API validation fails after OAuth returns a fresh token.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    client, _ = mock_api_validation_client
    client.get_installations = AsyncMock(side_effect=api_error)

    # Act: Complete OAuth with an inaccessible API account.
    result = await flow_handler.async_oauth_create_entry(data)

    # Assert: The token stays only in the flow while translated feedback is shown.
    assert result.get("type") is FlowResultType.FORM
    assert result.get("step_id") == "validate"
    assert result.get("errors") == {"base": expected_error}
    assert flow_handler._validation_data == data


@pytest.mark.asyncio
async def test_oauth_entry_creation_requires_an_accessible_installation(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Reject a valid token that cannot access any Viessmann installation."""
    # Arrange: OAuth succeeds but the account has no accessible installations.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()
    client, _ = mock_api_validation_client
    client.get_installations = AsyncMock(return_value=[])

    # Act: Complete OAuth with the otherwise-valid token.
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    result = await flow_handler.async_oauth_create_entry(data)

    # Assert: The flow identifies the missing installation prerequisite.
    assert result.get("errors") == {"base": "no_installations"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"token": "fresh-token"},
        {"token": {"access_token": 123}},
        {"token": None},
    ],
)
async def test_oauth_entry_creation_rejects_malformed_token_shapes(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
    data: dict[str, JsonValue],
) -> None:
    """Reject OAuth data whose token does not carry a string access token."""
    # Arrange: OAuth returns a token payload with an invalid shape.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()

    # Act: Complete OAuth with the malformed token payload.
    result = await flow_handler.async_oauth_create_entry(data)

    # Assert: Validation fails before any client is constructed.
    assert result.get("type") is FlowResultType.FORM
    assert result.get("step_id") == "validate"
    assert result.get("errors") == {"base": "invalid_auth"}
    assert flow_handler._validation_data == data
    mock_api_validation_client[1].assert_not_called()


@pytest.mark.asyncio
async def test_validation_retry_reuses_the_oauth_token_after_a_transient_failure(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Retry API validation without running the OAuth flow again."""
    # Arrange: The first request is unavailable and the second finds an installation.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}
    flow_handler.flow_impl = FakeOAuthImplementation()
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    client, _ = mock_api_validation_client
    client.get_installations = AsyncMock(
        side_effect=[
            ViConnectionError("offline"),
            ViConnectionError("still offline"),
            [object()],
        ]
    )
    expected_result = {"type": FlowResultType.CREATE_ENTRY}

    with patch.object(
        config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
        "async_oauth_create_entry",
        new=AsyncMock(return_value=expected_result),
    ) as create_entry:
        # Act: Complete OAuth, retry while unavailable, then retry after recovery.
        first_result = await flow_handler.async_oauth_create_entry(data)
        second_result = await flow_handler.async_step_validate({})
        retry_result = await flow_handler.async_step_validate({})

    # Assert: The retry completes using the retained fresh token.
    assert first_result.get("errors") == {"base": "cannot_connect"}
    assert second_result.get("errors") == {"base": "cannot_connect"}
    assert retry_result == expected_result
    create_entry.assert_awaited_once_with(data)


@pytest.mark.asyncio
async def test_validation_retry_aborts_when_no_token_is_available(
    hass: HomeAssistant,
) -> None:
    """Abort an invalid retry that has no OAuth token to validate."""
    # Arrange: A flow is resumed without a prior validation failure.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_USER}

    # Act: Attempt to validate without retained OAuth data.
    result = await flow_handler.async_step_validate({})

    # Assert: The invalid flow state is translated rather than persisting anything.
    assert result.get("type") is FlowResultType.ABORT
    assert result.get("reason") == "unknown"


@pytest.mark.asyncio
async def test_reauth_updates_entry_only_after_api_validation(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Update reauthentication data only after the fresh token is validated."""
    # Arrange: A reauth flow has a valid token and an existing entry to update.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_REAUTH}
    entry = MagicMock()
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    expected_result = {"type": FlowResultType.ABORT}

    with (
        patch.object(flow_handler, "_get_reauth_entry", return_value=entry),
        patch.object(
            flow_handler,
            "async_update_reload_and_abort",
            return_value=expected_result,
        ) as update_entry,
    ):
        # Act: Complete reauthentication.
        result = await flow_handler.async_oauth_create_entry(data)

    # Assert: Reauth persists only data that has passed API validation.
    assert result == expected_result
    mock_api_validation_client[1].assert_called_once()
    update_entry.assert_called_once_with(entry, data_updates=data)


@pytest.mark.asyncio
async def test_reauth_keeps_existing_entry_data_when_validation_fails(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Do not update a reauth entry when its fresh token cannot access the API."""
    # Arrange: Reauthentication gets a fresh token but Viessmann rejects it.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_REAUTH}
    data: dict[str, JsonValue] = {"token": {"access_token": "fresh-token"}}
    client, _ = mock_api_validation_client
    client.get_installations = AsyncMock(side_effect=ViAuthError("rejected"))

    with patch.object(flow_handler, "async_update_reload_and_abort") as update_entry:
        # Act: Complete reauthentication with an inaccessible API account.
        result = await flow_handler.async_oauth_create_entry(data)

    # Assert: The existing entry update is skipped until validation succeeds.
    assert result.get("errors") == {"base": "invalid_auth"}
    update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_confirm_aborts_without_a_string_auth_implementation(
    hass: HomeAssistant,
) -> None:
    """Abort the reauth confirm step when the entry lacks an implementation name."""
    # Arrange: A reauth entry whose data has no usable auth implementation.
    flow_handler = OAuth2FlowHandler()
    flow_handler.hass = hass
    flow_handler.context = {"source": config_entries.SOURCE_REAUTH}
    entry = MagicMock()
    entry.data = {}

    with patch.object(flow_handler, "_get_reauth_entry", return_value=entry):
        # Act: Confirm reauthentication for the malformed entry.
        result = await flow_handler.async_step_reauth_confirm({})

    # Assert: The flow aborts instead of picking an undefined implementation.
    assert result.get("type") is FlowResultType.ABORT
    assert result.get("reason") == "unknown"


@pytest.mark.asyncio
async def test_first_user_flow_creates_config_entry(
    hass: HomeAssistant,
) -> None:
    """Test the first user flow creates a config entry after OAuth authentication."""
    # Arrange: Register one fake implementation through the OAuth helper layer.
    implementation = FakeOAuthImplementation()

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_implementations",
        return_value={implementation.domain: implementation},
    ):
        # Act: Start the flow.
        start_result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        # Act: Select the OAuth implementation.
        auth_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            {"implementation": implementation.domain},
        )

        # Act: Complete the OAuth callback.
        callback_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            user_input={"code": "fresh-code"},
        )

        # Act: Resolve the authorization code and create the config entry.
        creation_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
        )

    # Assert: The flow starts OAuth authentication and creates the first entry.
    assert start_result.get("type") is FlowResultType.FORM
    assert start_result.get("step_id") == "pick_implementation"
    assert auth_result.get("type") is FlowResultType.EXTERNAL_STEP
    assert auth_result.get("step_id") == "auth"
    url = auth_result.get("url")
    assert url is not None
    authorize_url = URL(url)
    assert authorize_url.query["existing"] == "1"
    assert authorize_url.query["scope"] == DEFAULT_SCOPES
    assert callback_result.get("type") is FlowResultType.EXTERNAL_STEP_DONE
    assert creation_result.get("type") is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.asyncio
async def test_user_flow_retries_api_validation_without_repeating_oauth(
    hass: HomeAssistant,
    mock_api_validation_client: tuple[FixtureViClient, MagicMock],
) -> None:
    """Complete configuration after a transient API validation failure recovers."""
    # Arrange: OAuth succeeds once while the first API validation request is offline.
    implementation = FakeOAuthImplementation()
    implementation.async_resolve_external_data = AsyncMock(
        return_value={"access_token": "token", "expires_in": 3600}
    )
    client, _ = mock_api_validation_client
    client.get_installations = AsyncMock(
        side_effect=[ViConnectionError("offline"), [object()]]
    )

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_implementations",
        return_value={implementation.domain: implementation},
    ):
        # Act: Complete OAuth and receive the transient validation failure form.
        start_result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            {"implementation": implementation.domain},
        )
        await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            user_input={"code": "fresh-code"},
        )
        validation_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
        )

        # Act: Retry validation after Viessmann becomes reachable.
        creation_result = await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            user_input={},
        )

    # Assert: Home Assistant creates the entry without exchanging OAuth again.
    assert validation_result.get("type") is FlowResultType.FORM
    assert validation_result.get("step_id") == "validate"
    assert validation_result.get("errors") == {"base": "cannot_connect"}
    assert creation_result.get("type") is FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    implementation.async_resolve_external_data.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_flow_aborts_when_an_entry_already_exists(
    hass: HomeAssistant,
) -> None:
    """Test a second user-initiated setup is rejected before OAuth begins."""
    # Arrange: Register the integration's existing account configuration.
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    # Act: Attempt to start another user setup flow.
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    # Assert: Home Assistant uses its standard single-entry abort.
    assert result.get("type") is FlowResultType.ABORT
    assert result.get("reason") == "single_instance_allowed"
    assert result.get("translation_domain") == "homeassistant"


@pytest.mark.asyncio
async def test_user_flow_aborts_if_an_entry_is_created_during_oauth(
    hass: HomeAssistant,
) -> None:
    """Test an OAuth flow does not create a second entry after a concurrent setup."""
    # Arrange: Start OAuth setup while no entry exists.
    implementation = FakeOAuthImplementation()

    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.async_get_implementations",
        return_value={implementation.domain: implementation},
    ):
        start_result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            {"implementation": implementation.domain},
        )
        await hass.config_entries.flow.async_configure(
            start_result["flow_id"],
            user_input={"code": "fresh-code"},
        )
        MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

        # Act: Complete OAuth after another flow has already added an entry.
        result = await hass.config_entries.flow.async_configure(start_result["flow_id"])

    # Assert: The late guard prevents a duplicate entry with HA's standard abort.
    assert result.get("type") is FlowResultType.ABORT
    assert result.get("reason") == "single_instance_allowed"
    assert result.get("translation_domain") == "homeassistant"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


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
        assert reauth_result.get("type") is FlowResultType.FORM
        assert reauth_result.get("step_id") == "reauth_confirm"

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
    assert confirm_result.get("type") is FlowResultType.EXTERNAL_STEP
    assert confirm_result.get("step_id") == "auth"
    assert callback_result.get("type") is FlowResultType.EXTERNAL_STEP_DONE
    assert creation_result.get("type") is FlowResultType.ABORT
    assert creation_result.get("reason") == "reauth_successful"
    assert entry.data["auth_implementation"] == "fake-provider"
    assert entry.data["retained_setting"] == "keep-me"
    assert entry.data["token"]["access_token"] == "token"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
