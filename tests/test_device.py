import sys

import pytest

from rkflash.device import RockDevice, list_devices, open_device
from rkflash.mock_transport import MockRockDevice, MockTransport
from rkflash.protocol.command_block import SECTOR_SIZE


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
    assert devs[0].location is None


def test_list_devices_mock_platform_neutral(monkeypatch):
    # mock 枚举不得牵入 Windows 专用模块（Linux/CI 上无 setupapi）
    import rkflash.device as device_mod
    monkeypatch.delitem(sys.modules, "rkflash.transport.windows_rockusb", raising=False)
    devs = device_mod.list_devices("mock")
    assert len(devs) >= 1
    assert "rkflash.transport.windows_rockusb" not in sys.modules


def test_write_lba_rejects_unaligned_length():
    dev = RockDevice(MockTransport())
    with pytest.raises(ValueError):
        dev.write_lba(0, b"\x00" * (SECTOR_SIZE - 1))
