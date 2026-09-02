"""M3-F：LBA 分块计划与设备分区表读取。"""
import pytest

from rkflash.device import RockDevice
from rkflash.firmware.parameter import build_gpt_tables, parse_partitions
from rkflash.flashing.lba import (SECTOR_SIZE, read_device_partitions,
                                  write_lba_chunk_plan)
from rkflash.mock_transport import MockTransport

PARAM = (b"PARM\x00TYPE: GPT\x00CMDLINE:mtdparts=rk29xxnand:"
         b"0x00002000@0x00002000(security),0x00002000@0x00004000(uboot),"
         b"-@0x00020800(userdata:grow)\x00")


def test_chunk_plan_aligned():
    # 65536*2 + 500 字节 → 每块 65536；末块补到扇区
    chunks = write_lba_chunk_plan(0x40, 65536 * 2 + 500)
    assert [c.source_len for c in chunks] == [65536, 65536, 500]
    assert chunks[0].start_sector == 0x40
    assert chunks[1].start_sector == 0x40 + 128
    assert chunks[2].transfer_len == 512  # 500 → 补齐 1 扇区
    assert chunks[2].start_sector == 0x40 + 256


def test_chunk_plan_empty_rejected():
    with pytest.raises(ValueError):
        write_lba_chunk_plan(0, 0)


def _mock_with_gpt(flash_sectors=0x0080_0000):
    parts = parse_partitions(PARAM)
    tables = build_gpt_tables(parts, flash_sectors)
    t = MockTransport()
    for i in range(0, len(tables.primary), SECTOR_SIZE):
        t.storage[i // SECTOR_SIZE] = tables.primary[i:i + SECTOR_SIZE]
    return RockDevice(t)


def test_read_device_partitions_via_gpt():
    dev = _mock_with_gpt()
    parts = read_device_partitions(dev)
    names = [p.name for p in parts]
    assert "uboot" in names
    assert "userdata" in names
    assert next(p for p in parts if p.name == "uboot").start_sector == 0x4000
