"""内存 mock RockUSB 设备：无硬件跑通协议与烧写逻辑。"""
from .protocol.command_block import (CommandBlock, CommandStatus, Status)
from .protocol.operations import OperationFailed, execute_full, write_area

CHIP_INFO_RK3588 = b"3588" + b"\x00" * 12


class MockTransport:
    """按 CBW 应答的假传输。"""

    def __init__(self):
        self.storage = {}          # LBA -> bytes（512 对齐）
        self.written = []          # (start_sector, data)
        self.last_cbw = None
        self.fail_next = False
        self._payload = b""
        self.control_calls = []

    def bulk_write(self, data):
        if len(data) == 31:
            self.last_cbw = CommandBlock.from_bytes(data)
            return
        # 数据相（write_lba 负载）
        self._payload = data

    def bulk_read(self, n):
        cbw = self.last_cbw
        if cbw is None:
            raise RuntimeError("bulk_read before command block")
        if n == 13:  # CSW
            tag = cbw.tag
            if self.fail_next:
                self.fail_next = False
                return b"USBS" + tag.to_bytes(4, "big") + b"\x00" * 4 + bytes([Status.FAILED])
            return b"USBS" + tag.to_bytes(4, "big") + b"\x00" * 4 + bytes([Status.SUCCESS])
        # 数据相（IN）
        if cbw.cd_code == 0x1B:      # chip_info
            return CHIP_INFO_RK3588
        if cbw.cd_code == 0x01:      # flash_id
            return b"xxxxx"
        if cbw.cd_code == 0x1A:      # flash_info
            return b"\x00\x00\x40\x00" + b"\x00" * 7  # 0x400000 sectors
        if cbw.cd_code == 0xAA:      # capability
            return b"\x00\x00\x00\x00\x00\x00\x00\x00"
        if cbw.cd_code == 0x2B:      # storage：one-hot 位 1 = Emmc
            return b"\x02\x00\x00\x00"
        if cbw.cd_code == 0x14:      # read_lba
            start = cbw.cd_address
            count = cbw.cd_length
            return b"".join(self.storage.get(start + i, b"\x00" * 512) for i in range(count))
        raise RuntimeError(f"unhandled IN command 0x{cbw.cd_code:02x}")

    def control_transfer(self, request_type, request, value, index, data):
        self.control_calls = self.control_calls + [(index, data)]


class MockRockDevice:
    """高层 API，供 CLI/测试使用（Task 7 的 RockDevice 会替换为通用实现）。"""

    def __init__(self, transport: MockTransport | None = None):
        self.transport = transport or MockTransport()

    def chip_info(self) -> bytes:
        return execute_full(self.transport, CommandBlock.chip_info())

    def flash_id(self) -> bytes:
        return execute_full(self.transport, CommandBlock.flash_id())

    def flash_info(self) -> bytes:
        return execute_full(self.transport, CommandBlock.flash_info())

    def capability(self) -> bytes:
        return execute_full(self.transport, CommandBlock.capability())

    def storage(self) -> bytes:
        return execute_full(self.transport, CommandBlock.storage())

    def write_lba(self, start_sector: int, data: bytes) -> None:
        sectors = len(data) // 512
        execute_full(self.transport, CommandBlock.write_lba(start_sector, sectors), data_out=data)
        for i in range(sectors):
            self.transport.storage[start_sector + i] = data[i * 512:(i + 1) * 512]

    def read_lba(self, start_sector: int, sectors: int) -> bytes:
        return execute_full(self.transport, CommandBlock.read_lba(start_sector, sectors))

    def erase_lba(self, first: int, count: int) -> None:
        execute_full(self.transport, CommandBlock.erase_lba(first, count))
        for i in range(count):
            self.transport.storage.pop(first + i, None)

    def reset(self, opcode=0) -> None:
        execute_full(self.transport, CommandBlock.reset_device(opcode))

    def test_unit_ready(self) -> None:
        execute_full(self.transport, CommandBlock.test_unit_ready())

    def write_area(self, area: int, data: bytes) -> None:
        write_area(self.transport, area, data)
