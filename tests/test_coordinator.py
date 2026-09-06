"""Tests for coordinator discovery, refresh, and writes."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.number import NumberEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from vi_api_client import Device, Feature, ViAuthError, ViConnectionError
from vi_api_client.models import CommandResponse

from custom_components.vi_climate_devices.coordinator import (
    ViClimateDataUpdateCoordinator,
)
from custom_components.vi_climate_devices.number import ViClimateNumber


def _build_device(
    *,
    device_id: str,
    gateway_serial: str,
    model_id: str = "Vitocal250A",
) -> Device:
    """Create a minimal Viessmann device for coordinator tests."""
    return Device(
        id=device_id,
        gateway_serial=gateway_serial,
        installation_id="installation-1",
        model_id=model_id,
        device_type="heating",
        status="online",
        features=[
            Feature(
                name="heating.sensors.temperature.outside",
                value=12.2,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
            )
        ],
    )


def _make_reauth_error() -> OAuth2TokenRequestReauthError:
    """Create a reauth-class OAuth token error."""
    return OAuth2TokenRequestReauthError(
        request_info=MagicMock(),
        history=(),
        status=400,
        message="Bad Request",
        headers=MagicMock(),
        domain="vi_climate_devices",
    )


def _make_token_error() -> OAuth2TokenRequestError:
    """Create a transient OAuth token error."""
    return OAuth2TokenRequestError(
        request_info=MagicMock(),
        history=(),
        status=500,
        message="Internal Server Error",
        headers=MagicMock(),
        domain="vi_climate_devices",
    )


def _build_curve_device(slope: float, shift: float) -> Device:
    """Create a device exposing both heating-curve command parameters."""
    return Device(
        id="device-0",
        gateway_serial="gw-main",
        installation_id="installation-1",
        model_id="Vitocal250A",
        device_type="heating",
        status="online",
        features=[
            Feature(
                name="heating.circuits.0.heating.curve.shift",
                value=shift,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
            ),
            Feature(
                name="heating.circuits.0.heating.curve.slope",
                value=slope,
                unit="celsius",
                is_enabled=True,
                is_ready=True,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_data_coordinator_raises_when_no_installations_exist(
    hass: HomeAssistant, mock_client
) -> None:
    """Test discovery raises UpdateFailed when the account has no installations."""
    # Arrange: Return an empty installation list from the Viessmann client.
    mock_client.get_installations = AsyncMock(return_value=[])
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)

    # Act and Assert: The first refresh aborts with a clear update failure.
    with pytest.raises(UpdateFailed, match="No installations found"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_raises_reauth_when_installation_lookup_loses_auth(
    hass: HomeAssistant, mock_client
) -> None:
    """Test discovery triggers reauth when listing installations loses auth."""
    # Arrange: Reject the initial installation lookup with an auth failure.
    mock_client.get_installations = AsyncMock(side_effect=ViAuthError("token expired"))
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)

    # Act and Assert: Convert the discovery auth failure into a reauth trigger.
    with pytest.raises(ConfigEntryAuthFailed, match="token expired"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_discovers_devices_and_filters_ignored_ids(
    hass: HomeAssistant, mock_client
) -> None:
    """Test discovery keeps regular devices and drops configured ignored device ids."""
    # Arrange: Return one real device and one ignored gateway pseudo-device.
    active_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    ignored_device = _build_device(
        device_id="gateway",
        gateway_serial="gw-ignored",
        model_id="Gateway",
    )
    mock_client.get_installations = AsyncMock(
        return_value=[SimpleNamespace(id="installation-1")]
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[active_device, ignored_device]
    )
    mock_client.update_device = AsyncMock(return_value=active_device)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)

    # Act: Run the first coordinator refresh with discovery enabled.
    result = await coordinator._async_update_data()

    # Assert: Only the real device survives discovery and is tracked for updates.
    assert result == {"gw-main_device-0": active_device}
    assert coordinator._known_devices == [active_device]


@pytest.mark.asyncio
async def test_data_coordinator_raises_when_all_device_updates_fail(
    hass: HomeAssistant, mock_client
) -> None:
    """Test refresh fails when no known device can be updated."""
    # Arrange: Seed one known device and make its refresh raise a transient error.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    mock_client.update_device = AsyncMock(
        side_effect=ViConnectionError("device offline")
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Treat the failed poll as an unavailable coordinator update.
    with pytest.raises(UpdateFailed, match="Failed to update all devices"):
        await coordinator._async_update_data()

    # Assert: Keep the immutable device reference for a later recovery attempt.
    assert coordinator._known_devices == [known_device]
    assert not coordinator.is_device_available("gw-main_device-0")


@pytest.mark.asyncio
async def test_data_coordinator_marks_only_failed_device_unavailable(
    hass: HomeAssistant, mock_client
) -> None:
    """Test partial refresh failures only make the affected device unavailable."""
    # Arrange: Refresh one device and fail the second device with a transient error.
    refreshed_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    failing_device = _build_device(device_id="device-1", gateway_serial="gw-backup")
    mock_client.update_device = AsyncMock(
        side_effect=[refreshed_device, ViConnectionError("device offline")]
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [refreshed_device, failing_device]
    coordinator._failed_device_keys = {"gw-main_device-0"}

    # Act: Refresh the coordinator with one successful and one failed device poll.
    result = await coordinator._async_update_data()

    # Assert: Preserve the failed device for recovery while exposing its outage.
    assert result == {
        "gw-main_device-0": refreshed_device,
        "gw-backup_device-1": failing_device,
    }
    assert coordinator.is_device_available("gw-main_device-0")
    assert not coordinator.is_device_available("gw-backup_device-1")


@pytest.mark.asyncio
async def test_data_coordinator_raises_reauth_when_device_update_loses_auth(
    hass: HomeAssistant, mock_client
) -> None:
    """Test refresh raises ConfigEntryAuthFailed when device polling loses auth."""
    # Arrange: Seed one known device and make the update raise ViAuthError.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    mock_client.update_device = AsyncMock(side_effect=ViAuthError("token expired"))
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: The auth failure is escalated to Home Assistant reauth.
    with pytest.raises(ConfigEntryAuthFailed, match="token expired"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_data_coordinator_propagates_oauth_reauth_error(
    hass: HomeAssistant, mock_client
) -> None:
    """Test polling preserves an OAuth error that requires reauthentication."""
    # Arrange: Seed a device and reject its refresh token during polling.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    reauth_error = _make_reauth_error()
    mock_client.update_device = AsyncMock(side_effect=reauth_error)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Home Assistant receives the original reauth-class error.
    with pytest.raises(OAuth2TokenRequestReauthError) as raised_error:
        await coordinator._async_update_data()
    assert raised_error.value is reauth_error


@pytest.mark.asyncio
async def test_data_coordinator_propagates_transient_oauth_error(
    hass: HomeAssistant, mock_client
) -> None:
    """Test polling preserves a transient OAuth error for coordinator retry."""
    # Arrange: Seed a device and simulate a temporary token endpoint failure.
    known_device = _build_device(device_id="device-0", gateway_serial="gw-main")
    token_error = _make_token_error()
    mock_client.update_device = AsyncMock(side_effect=token_error)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator._known_devices = [known_device]

    # Act and Assert: Home Assistant receives the original retryable error.
    with pytest.raises(OAuth2TokenRequestError) as raised_error:
        await coordinator._async_update_data()
    assert raised_error.value is token_error


@pytest.mark.asyncio
async def test_confirmed_write_survives_partial_failure_and_recovery(
    hass: HomeAssistant, mock_client
) -> None:
    """Keep confirmed state while only the failed device becomes unavailable."""
    # Arrange: Discover two devices, then confirm a new slope for the first.
    device_key = "gw-main_device-0"
    other_key = "gw-main_device-1"
    feature_name = "heating.circuits.0.heating.curve.slope"
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    written_device = _build_curve_device(slope=1.2, shift=0.0)
    recovered_device = _build_curve_device(slope=1.3, shift=0.0)
    other_device = replace(initial_device, id="device-1")
    other_written_device = replace(written_device, id="device-1")
    mock_client.get_installations = AsyncMock(
        return_value=[SimpleNamespace(id="installation-1")]
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[initial_device, other_device]
    )
    mock_client.update_device = AsyncMock(side_effect=[initial_device, other_device])
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    await coordinator.async_refresh()
    entity = ViClimateNumber(
        coordinator, device_key, feature_name, NumberEntityDescription(key=feature_name)
    )
    other_entity = ViClimateNumber(
        coordinator, other_key, feature_name, NumberEntityDescription(key=feature_name)
    )
    mock_client.set_feature = AsyncMock(
        return_value=(
            CommandResponse(success=True, message=None, reason=None),
            written_device,
        )
    )
    await coordinator.async_set_feature(device_key, feature_name, 1.2)

    # Act: The written device fails to poll while the second device stays reachable.
    mock_client.update_device = AsyncMock(
        side_effect=[ViConnectionError("device offline"), other_device]
    )
    await coordinator.async_refresh()

    # Assert: Preserve the confirmed write internally and isolate availability.
    assert coordinator.data[device_key] is written_device
    assert not entity.available
    assert other_entity.available
    mock_client.set_feature = AsyncMock(
        return_value=(
            CommandResponse(success=True, message=None, reason=None),
            other_written_device,
        )
    )
    await coordinator.async_set_feature(other_key, feature_name, 1.2)
    assert other_entity.native_value == 1.2
    assert not entity.available

    # Act: Recover the failed device and publish its current state.
    mock_client.update_device = AsyncMock(
        side_effect=[recovered_device, other_written_device]
    )
    await coordinator.async_refresh()

    # Assert: Recovery polls the retained confirmed state and restores availability.
    assert mock_client.update_device.call_args_list[0].args[0] is written_device
    assert entity.available
    assert entity.native_value == 1.3
    assert other_entity.available
    mock_client.set_feature.return_value = (
        CommandResponse(success=True, message=None, reason=None),
        _build_curve_device(slope=1.4, shift=0.0),
    )
    await coordinator.async_set_feature(device_key, feature_name, 1.4)
    assert mock_client.set_feature.call_args.args[0] is recovered_device
    assert entity.native_value == 1.4


@pytest.mark.asyncio
async def test_refresh_waits_for_write_and_polls_confirmed_device(
    hass: HomeAssistant, mock_client
) -> None:
    """A queued refresh and subsequent write both use the latest device state."""
    # Arrange: Discover two devices and block a write before it is confirmed.
    device_key = "gw-main_device-0"
    feature_name = "heating.circuits.0.heating.curve.slope"
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    written_device = _build_curve_device(slope=1.2, shift=0.0)
    other_device = replace(initial_device, id="device-1")
    mock_client.get_installations = AsyncMock(
        return_value=[SimpleNamespace(id="installation-1")]
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[initial_device, other_device]
    )
    mock_client.update_device = AsyncMock(side_effect=[initial_device, other_device])
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    await coordinator.async_refresh()
    write_started = asyncio.Event()
    allow_write_to_finish = asyncio.Event()

    async def mock_set_feature(
        device: Device, feature: Feature, value: object
    ) -> tuple[CommandResponse, Device]:
        write_started.set()
        await allow_write_to_finish.wait()
        return CommandResponse(success=True, message=None, reason=None), written_device

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature)
    mock_client.update_device = AsyncMock(side_effect=lambda device: device)

    # Act: Queue a refresh while the write is still in flight.
    write_task = asyncio.create_task(
        coordinator.async_set_feature(device_key, feature_name, 1.2)
    )
    await write_started.wait()
    refresh_task = asyncio.create_task(coordinator.async_refresh())
    await asyncio.sleep(0)
    mock_client.update_device.assert_not_called()
    allow_write_to_finish.set()
    await asyncio.gather(write_task, refresh_task)

    # Assert: The refresh retains the confirmed state for a subsequent command.
    assert coordinator.data[device_key] is written_device
    assert mock_client.update_device.call_args_list[0].args[0] is written_device
    await coordinator.async_set_feature(device_key, feature_name, 1.2)
    assert mock_client.set_feature.call_args.args[0] is written_device


@pytest.mark.asyncio
async def test_data_coordinator_serializes_writes_per_device(
    hass: HomeAssistant, mock_client
) -> None:
    """Test a queued write resolves its feature from the previous write result."""
    # Arrange: Queue a curve-shift write behind a blocked curve-slope write.
    device_key = "gw-main_device-0"
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    slope_updated_device = _build_curve_device(slope=1.2, shift=0.0)
    final_device = _build_curve_device(slope=1.2, shift=0.4)
    first_write_started = asyncio.Event()
    allow_first_write_to_finish = asyncio.Event()
    calls: list[tuple[Device, Feature, object]] = []

    async def mock_set_feature(
        device: Device, feature: Feature, value: object
    ) -> tuple[CommandResponse, Device]:
        calls.append((device, feature, value))
        if feature.name.endswith("slope"):
            first_write_started.set()
            await allow_first_write_to_finish.wait()
            return CommandResponse(
                success=True, message=None, reason=None
            ), slope_updated_device
        return CommandResponse(success=True, message=None, reason=None), final_device

    mock_client.set_feature = AsyncMock(side_effect=mock_set_feature)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator.data = {device_key: initial_device}

    # Act: Start two writes for command parameters sharing one device.
    slope_write = asyncio.create_task(
        coordinator.async_set_feature(
            device_key,
            "heating.circuits.0.heating.curve.slope",
            1.2,
        )
    )
    await first_write_started.wait()
    shift_write = asyncio.create_task(
        coordinator.async_set_feature(
            device_key,
            "heating.circuits.0.heating.curve.shift",
            0.4,
        )
    )
    await asyncio.sleep(0)
    allow_first_write_to_finish.set()
    await asyncio.gather(slope_write, shift_write)

    # Assert: The queued write uses the device returned by the first command.
    assert calls[1][0] is slope_updated_device
    assert calls[1][1].value == 0.0
    assert coordinator.data[device_key] is final_device


@pytest.mark.asyncio
async def test_data_coordinator_does_not_overwrite_a_write_with_stale_refresh(
    hass: HomeAssistant, mock_client
) -> None:
    """Test a write waits for an in-progress refresh before updating coordinator data."""
    # Arrange: Start a refresh whose response still contains the old curve slope.
    device_key = "gw-main_device-0"
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    refreshed_device = _build_curve_device(slope=0.7, shift=0.0)
    written_device = _build_curve_device(slope=1.2, shift=0.0)
    refresh_started = asyncio.Event()
    allow_refresh_to_finish = asyncio.Event()

    async def mock_update_device(device: Device) -> Device:
        refresh_started.set()
        await allow_refresh_to_finish.wait()
        return refreshed_device

    mock_client.update_device = AsyncMock(side_effect=mock_update_device)
    mock_client.set_feature = AsyncMock(
        return_value=(
            CommandResponse(success=True, message=None, reason=None),
            written_device,
        )
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator.data = {device_key: initial_device}
    coordinator._known_devices = [initial_device]

    # Act: Begin a refresh, then write a new slope before its stale response returns.
    refresh_task = asyncio.create_task(coordinator.async_refresh())
    await refresh_started.wait()
    write_task = asyncio.create_task(
        coordinator.async_set_feature(
            device_key,
            "heating.circuits.0.heating.curve.slope",
            1.2,
        )
    )
    await asyncio.sleep(0)
    assert mock_client.set_feature.call_count == 0
    allow_refresh_to_finish.set()
    await asyncio.gather(refresh_task, write_task)

    # Assert: The completed write remains the coordinator's current device data.
    updated_feature = coordinator.data[device_key].get_feature(
        "heating.circuits.0.heating.curve.slope"
    )
    assert updated_feature is not None
    assert updated_feature.value == 1.2


@pytest.mark.asyncio
async def test_data_coordinator_notifies_entities_after_successful_write(
    hass: HomeAssistant, mock_client
) -> None:
    """Test a successful write publishes the updated device to listeners."""
    # Arrange: Register a listener for a device whose curve slope will change.
    device_key = "gw-main_device-0"
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    updated_device = _build_curve_device(slope=1.2, shift=0.0)
    mock_client.set_feature = AsyncMock(
        return_value=(
            CommandResponse(success=True, message=None, reason=None),
            updated_device,
        )
    )
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    coordinator.data = {device_key: initial_device}
    listener_data: list[Device] = []
    coordinator.async_add_listener(
        lambda: listener_data.append(coordinator.data[device_key])
    )

    try:
        # Act: Set the slope through the shared coordinator write path.
        await coordinator.async_set_feature(
            device_key,
            "heating.circuits.0.heating.curve.slope",
            1.2,
        )

        # Assert: Every coordinator entity receives the new immutable device object.
        assert listener_data == [updated_device]
    finally:
        await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_frequent_writes_preserve_scheduled_poll(
    hass: HomeAssistant, mock_client, freezer
) -> None:
    """Commands publish immediately without postponing measurement refreshes."""
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    await coordinator.async_refresh()
    device_key = next(iter(coordinator.data))
    feature_name = "heating.circuits.0.heating.curve.slope"
    listener = MagicMock()
    remove_listener = coordinator.async_add_listener(listener)
    mock_client.update_device = AsyncMock(wraps=mock_client.update_device)

    try:
        # Act: Keep issuing commands more frequently than the three-minute poll.
        for minute in range(1, 7):
            freezer.tick(timedelta(minutes=1))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
            await coordinator.async_set_feature(device_key, feature_name, 1.2)

            # Assert: Each command notifies immediately; polls still happen on time.
            assert listener.call_count == minute + minute // 3
            assert mock_client.update_device.await_count == minute // 3
            feature = coordinator.data[device_key].get_feature(feature_name)
            assert feature is not None
            assert feature.value == 1.2
    finally:
        remove_listener()
        await coordinator.async_shutdown()

    # No poll or notification survives removal and shutdown.
    listener.reset_mock()
    mock_client.update_device.reset_mock()
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    listener.assert_not_called()
    mock_client.update_device.assert_not_awaited()


@pytest.mark.parametrize("is_token_failure", [False, True])
@pytest.mark.asyncio
async def test_write_after_full_outage_preserves_availability_until_poll(
    hass: HomeAssistant, mock_client, freezer, is_token_failure: bool
) -> None:
    """Only device refreshes restore availability after device or token failures."""
    # Arrange: Discover two devices and observe their public entity state.
    initial_device = _build_curve_device(slope=0.7, shift=0.0)
    other_device = replace(initial_device, id="device-1")
    written_device = _build_curve_device(slope=1.2, shift=0.0)
    mock_client.get_installations = AsyncMock(
        return_value=[SimpleNamespace(id="installation-1")]
    )
    mock_client.get_full_installation_status = AsyncMock(
        return_value=[initial_device, other_device]
    )
    mock_client.update_device = AsyncMock(side_effect=lambda device: device)
    coordinator = ViClimateDataUpdateCoordinator(hass, mock_client)
    await coordinator.async_refresh()
    feature_name = "heating.circuits.0.heating.curve.slope"
    entity = ViClimateNumber(
        coordinator,
        "gw-main_device-0",
        feature_name,
        NumberEntityDescription(key=feature_name),
    )
    other_entity = ViClimateNumber(
        coordinator,
        "gw-main_device-1",
        feature_name,
        NumberEntityDescription(key=feature_name),
    )
    observed_states: list[tuple[bool, bool, float | None]] = []
    remove_listener = coordinator.async_add_listener(
        lambda: observed_states.append(
            (entity.available, other_entity.available, entity.native_value)
        )
    )
    mock_client.update_device.side_effect = (
        _make_token_error() if is_token_failure else ViConnectionError("offline")
    )
    try:
        # Act: A scheduled poll fails globally, then a command succeeds.
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert not coordinator.last_update_success
        last_exception = coordinator.last_exception
        assert observed_states == [(False, False, 0.7)]
        mock_client.set_feature = AsyncMock(
            return_value=(
                CommandResponse(success=True, message=None, reason=None),
                written_device,
            )
        )
        await coordinator.async_set_feature("gw-main_device-0", feature_name, 1.2)

        # Assert: Publish confirmed values without claiming either device recovered.
        assert observed_states[-1] == (False, False, 1.2)
        assert len(observed_states) == 2
        assert not coordinator.last_update_success
        assert coordinator.last_exception is last_exception

        # Act: The next poll confirms only the written device is reachable.
        mock_client.update_device.side_effect = [
            written_device,
            ViConnectionError("other device offline"),
        ]
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert observed_states[-1] == (True, False, 1.2)
        assert mock_client.update_device.call_args_list[-2].args[0] is written_device

        mock_client.update_device.side_effect = lambda device: device
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert observed_states[-1] == (True, True, 1.2)
    finally:
        remove_listener()
        await coordinator.async_shutdown()
