"""M3-E：parameter/GPT/sparse（移植 android.rs 测试）。"""
import struct

import pytest

from rkflash.firmware.parameter import (GptPartition, build_gpt_tables,
                                        parse_partitions, parse_sparse_chunk,
                                        parse_sparse_header)

PARAMETER = (b"PARM\x00TYPE: GPT\x00CMDLINE:mtdparts=rk29xxnand:"
             b"0x00002000@0x00002000(security),0x00002000@0x00004000(uboot),"
             b"0x00014000@0x0000c800(boot),-@0x00020800(userdata:grow)\x00")
PARAMETER_UUID = (b"PARM\x00TYPE: GPT\x00CMDLINE:mtdparts=rk29xxnand:"
                  b"0x00020000@0x00008000(boot),0x00c00000@0x00078000(rootfs)\n"
                  b"uuid:rootfs=614e0000-0000-4b53-8000-1d28000054a9\x00")


def test_parses_gpt_ranges_from_parameter():
    parts = parse_partitions(PARAMETER)
    assert parts[2].name == "boot"
    assert parts[2].start_sector == 0xC800
    assert parts[2].sector_count == 0x14000
    assert parts[3].name == "userdata"
    assert parts[3].sector_count is None  # grow


def test_parses_uuid_guid():
    parts = parse_partitions(PARAMETER_UUID)
    rootfs = next(p for p in parts if p.name == "rootfs")
    assert rootfs.unique_guid == bytes([0x00, 0x00, 0x4e, 0x61, 0x00, 0x00,
                                        0x53, 0x4b, 0x80, 0x00, 0x1d, 0x28,
                                        0x00, 0x00, 0x54, 0xa9])


def test_build_gpt_layout():
    parts = parse_partitions(PARAMETER)
    tables = build_gpt_tables(parts, 0x0080_0000)
    assert tables.primary[512:520] == b"EFI PART"
    boot_entry = 2 * 512 + 2 * 128
    assert struct.unpack_from("<Q", tables.primary, boot_entry + 32)[0] == 0xC800
    assert struct.unpack_from("<Q", tables.primary, boot_entry + 40)[0] == 0x207FF
    assert tables.backup_start_sector == 0x0080_0000 - 33


def test_grow_partition_ends_at_last_usable():
    parts = parse_partitions(PARAMETER)
    tables = build_gpt_tables(parts, 0x0080_0000)
    userdata_entry = 2 * 512 + 3 * 128
    assert struct.unpack_from("<Q", tables.primary, userdata_entry + 32)[0] == 0x20800
    assert struct.unpack_from("<Q", tables.primary, userdata_entry + 40)[0] == 0x0080_0000 - 34


def test_gpt_rejects_partition_exceeding_flash():
    parts = parse_partitions(PARAMETER)
    with pytest.raises(ValueError):
        build_gpt_tables(parts, 0x0002_0000)


def _sparse_header(blocks=2, chunks=1):
    h = bytearray(28)
    struct.pack_into("<I", h, 0, 0xED26FF3A)
    struct.pack_into("<H", h, 4, 1)
    struct.pack_into("<H", h, 8, 28)
    struct.pack_into("<H", h, 10, 12)
    struct.pack_into("<I", h, 12, 4096)
    struct.pack_into("<I", h, 16, blocks)
    struct.pack_into("<I", h, 20, chunks)
    return bytes(h)


def test_sparse_header_and_raw_chunk():
    sparse = parse_sparse_header(_sparse_header())
    chunk = bytearray(12)
    struct.pack_into("<H", chunk, 0, 0xCAC1)
    struct.pack_into("<I", chunk, 4, 2)
    struct.pack_into("<I", chunk, 8, 12 + 8192)
    parsed = parse_sparse_chunk(sparse, bytes(chunk))
    assert sparse.output_bytes == 8192
    assert parsed.kind == "raw"
    assert parsed.output_bytes == 8192
    assert parsed.payload_bytes == 8192


def test_sparse_fill_and_dont_care():
    sparse = parse_sparse_header(_sparse_header())
    fill = bytearray(12)
    struct.pack_into("<H", fill, 0, 0xCAC2)
    struct.pack_into("<I", fill, 4, 1)
    struct.pack_into("<I", fill, 8, 16)
    assert parse_sparse_chunk(sparse, bytes(fill)).payload_bytes == 4

    dc = bytearray(12)
    struct.pack_into("<H", dc, 0, 0xCAC3)
    struct.pack_into("<I", dc, 4, 1)
    struct.pack_into("<I", dc, 8, 12)
    parsed = parse_sparse_chunk(sparse, bytes(dc))
    assert parsed.kind == "dontcare"
    assert parsed.output_bytes == 4096
