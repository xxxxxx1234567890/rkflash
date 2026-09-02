"""设备发现与高层操作（跨平台分发）。"""
import sys

from .protocol.command_block import (CommandBlock, StorageIndex)
from .protocol.operations import execute_full, write_area


class RockDevice:
    """包裹具体传输层，提供高层操作。"""

    def __init__(self, transport):
        self.transport = transport

    def chip_info(self) -> bytes:
        return execute_full(self.transport, CommandBlock.chip_info())

    def flash_id(self) -> bytes:
        return execute_full(self.transport, CommandBlock.flash_id())

    def flash_info(self) -> bytes:
        return execute_full(self.transport, CommandBlock.flash_info())

    def capability(self) -> bytes:
        return execute_full(self.transport, CommandBlock.capability())

    def test_unit_ready(self) -> None:
        execute_full(self.transport, CommandBlock.test_unit_ready())

    def read_lba(self, start_sector: int, sectors: int) -> bytes:
        return execute_full(self.transport, CommandBlock.read_lba(start_sector, sectors))

    def write_lba(self, start_sector: int, data: bytes) -> None:
        execute_full(self.transport, CommandBlock.write_lba(
            start_sector, len(data) // 512), data_out=data)

    def erase_lba(self, first: int, count: int) -> None:
        execute_full(self.transport, CommandBlock.erase_lba(first, count))

    def reset(self, opcode=0) -> None:
        execute_full(self.transport, CommandBlock.reset_device(opcode))

    def switch_storage(self, index: StorageIndex) -> None:
        execute_full(self.transport, CommandBlock.switch_storage(index))

    def storage(self) -> bytes:
        return execute_full(self.transport, CommandBlock.storage())

    def write_area(self, area: int, data: bytes) -> None:
        write_area(self.transport, area, data)

    def close(self) -> None:
        if hasattr(self.transport, "close"):
            self.transport.close()


def list_devices(transport: str = "auto") -> list:
    """跨平台设备发现。transport: auto|mock|windows|linux。"""
    if transport == "mock":
        from .mock_transport import MockRockDevice
        return MockRockDevice.enumerate()
    if transport == "windows" or (transport == "auto" and sys.platform == "win32"):
        from .transport.windows_rockusb import list_devices as _ld
        return _ld()
    from .transport.linux_libusb import list_devices as _ld
    return _ld()


def open_device(path: str, transport: str = "auto"):
    """按 path 打开设备，返回 RockDevice。"""
    if transport == "mock" or path.startswith("mock:"):
        from .mock_transport import MockRockDevice
        return MockRockDevice.open(path)
    if transport == "windows" or (transport == "auto" and sys.platform == "win32"):
        from .transport.windows_rockusb import WindowsRockusbTransport
        return RockDevice(WindowsRockusbTransport.open(path))
    from .transport.linux_libusb import LinuxLibusbTransport
    return RockDevice(LinuxLibusbTransport.open(path))
