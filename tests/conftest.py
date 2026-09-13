import pytest
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from vi_api_client import FixtureViClient


@pytest.fixture
def mock_client() -> FixtureViClient:
    """Return the Vitocal250A fixture client for testing."""
    return FixtureViClient("Vitocal250A")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return None


@pytest.fixture
def snapshot(snapshot):
    """Override the snapshot fixture to force using the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
