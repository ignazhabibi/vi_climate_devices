import pytest
from vi_api_client.mock_client import MockViClient


@pytest.fixture
def mock_client():
    """Return a mock client for testing."""
    # Load a specific device scenario (e.g. Gas Boiler)
    return MockViClient(device_name="Vitodens200W", auth=None)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
