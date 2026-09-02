import pytest

from rkflash.protocol.command_block import CommandBlock, Status
from rkflash.protocol.operations import crc16_ibm_3740, execute_full, write_area


class FakeTransport:
    """记录调用并回放 CSW 的假传输层；bulk_read 按长度分发（13=CSW）。"""

    def __init__(self, chip_info_reply=None, fail=False):
        self.chip_info_reply = chip_info_reply or (b"3588" + b"\x00" * 12)
        self.fail = fail
        self.writes = []
        self.controls = []
        self.last_tag = 0

    def bulk_write(self, data):
        self.writes.append(data)
        if len(data) == 31:
            self.last_tag = int.from_bytes(data[4:8], "big")

    def bulk_read(self, n):
        if n == 13:
            status = bytes([Status.FAILED]) if self.fail else bytes([Status.SUCCESS])
            return b"USBS" + self.last_tag.to_bytes(4, "big") + b"\x00" * 4 + status
        if n == 16:
            return self.chip_info_reply
        return b"\x00" * n

    def control_transfer(self, request_type, request, value, index, data):
        self.controls.append((request_type, request, value, index, data))
        return b""


def test_crc16_known_vector():
    # CRC-16/IBM-3740 check = 0x29B1（已核验 crc-catalog-2.4.0 源码）
    assert crc16_ibm_3740(b"123456789") == 0x29B1


def test_execute_full_read_chip_info():
    t = FakeTransport()
    out = execute_full(t, CommandBlock.chip_info())
    assert out == t.chip_info_reply
    assert len(t.writes) == 1 and len(t.writes[0]) == 31  # 仅 CBW，数据相走 bulk_read


def test_execute_full_status_failed_raises():
    t = FakeTransport(fail=True)
    with pytest.raises(RuntimeError):
        execute_full(t, CommandBlock.test_unit_ready())


def test_write_area_small_data_sends_crc_suffix():
    t = FakeTransport()
    data = b"\xAA" * 100
    write_area(t, 0x471, data)
    assert len(t.controls) == 1
    req_type, request, value, index, chunk = t.controls[0]
    assert (req_type, request, value, index) == (0x40, 0x0C, 0, 0x471)
    crc = crc16_ibm_3740(data)
    assert chunk == data + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def test_write_area_full_block_appends_crc():
    t = FakeTransport()
    data = b"\xBB" * 4096
    write_area(t, 0x471, data)
    # 1 个 4096 块 + 1 个 2 字节 CRC 后缀
    assert len(t.controls) == 2
    assert t.controls[0][4] == data
    crc = crc16_ibm_3740(data)
    assert t.controls[1][4] == bytes([(crc >> 8) & 0xFF, crc & 0xFF])
