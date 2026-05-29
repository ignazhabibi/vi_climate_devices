import pytest
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from vi_api_client.mock_client import MockViClient


@pytest.fixture
def mock_client():
    """Return a mock client for testing."""
    # Load a specific device scenario (e.g. Heat Pump)
    return MockViClient(device_name="Vitocal250A", auth=None)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def snapshot(snapshot):
    """Override the snapshot fixture to force using the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
