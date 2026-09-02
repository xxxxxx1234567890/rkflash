import pytest

from rkflash.mock_transport import MockRockDevice


@pytest.fixture
def mock_device() -> MockRockDevice:
    return MockRockDevice()
