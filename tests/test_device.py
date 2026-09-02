from rkflash.device import list_devices, open_device
from rkflash.mock_transport import MockRockDevice, MockTransport


def test_mock_chip_info():
    dev = MockRockDevice()
    out = dev.chip_info()
    assert out.startswith(b"3588")


def test_mock_write_read_lba():
    dev = MockRockDevice()
    dev.write_lba(64, b"\xAA" * 512)
    assert dev.read_lba(64, 1) == b"\xAA" * 512


def test_open_mock_device():
    dev = open_device(path="mock:0", transport="mock")
    assert dev.chip_info().startswith(b"3588")


def test_list_devices_mock():
    devs = list_devices(transport="mock")
    assert len(devs) >= 1
    assert devs[0].path.startswith("mock:")
