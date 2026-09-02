"""M3-C：Boot 文件解析（对齐 rockfile boot.rs + device_ops loader_entry_data）。"""
import os
import struct

import pytest

from rkflash.firmware.bootfile import (RkBootHeader, RkBootHeaderEntry,
                                       entry_data, parse_boot_entry, parse_boot_header)

REAL_LOADER = os.path.join(os.path.dirname(__file__), "fixtures",
                           "MiniLoaderAll_rk3506.bin")


def make_header(entries_offset=512, loader_count=3, rc4=0, tag=b"LDR "):
    """构造 102 字节 RkBootHeader。entries: entry_loader 指向 offset(字节) 的表。"""
    h = bytearray(102)
    h[0:4] = tag
    struct.pack_into("<H", h, 4, 0x200)     # size
    struct.pack_into("<I", h, 6, 1)         # version
    struct.pack_into("<I", h, 10, 1)        # merge_version
    h[14] = 0x07                            # 起始 release year lo...
    h[21:25] = b"3506"                      # supported_chip
    # entry_471 @25, entry_472 @31, entry_loader @37: (count u8, offset u32le, size u8)
    struct.pack_into("<B", h, 25, 0)
    struct.pack_into("<B", h, 31, 0)
    struct.pack_into("<B", h, 37, loader_count)
    struct.pack_into("<I", h, 38, entries_offset)
    struct.pack_into("<B", h, 42, 57)
    h[43] = 0          # sign_flag
    h[44] = rc4        # rc4_flag
    return bytes(h)


def make_entry(name: str, data_offset: int, data_size: int, delay: int = 0) -> bytes:
    e = bytearray(57)
    e[0] = 57
    struct.pack_into("<I", e, 1, 0)         # type
    for i, ch in enumerate(name[:20]):
        struct.pack_into("<H", e, 5 + i * 2, ord(ch))
    struct.pack_into("<I", e, 45, data_offset)
    struct.pack_into("<I", e, 49, data_size)
    struct.pack_into("<I", e, 53, delay)
    return bytes(e)


def test_parse_synthetic_header_loader_and_entries():
    blob = bytearray(b"\x00" * 4096)
    blob[0:102] = make_header(entries_offset=1024, loader_count=2)
    blob[1024:1024 + 57] = make_entry("FlashBoot", 2048, 128)
    blob[1081:1081 + 57] = make_entry("FlashData", 2176, 256)
    blob[2048:2048 + 128] = b"\xAA" * 128
    blob[2176:2176 + 256] = b"\xBB" * 256
    data = bytes(blob)

    header = parse_boot_header(data[:102])
    assert header is not None
    assert header.tag == b"LDR "
    assert header.entry_loader.count == 2
    assert header.entry_loader.offset == 1024
    assert header.rc4_flag == 0

    boot = entry_data(data, header.entry_loader, "FlashBoot")
    assert boot == b"\xAA" * 128
    fdata = entry_data(data, header.entry_loader, "FlashData")
    assert fdata == b"\xBB" * 256
    assert entry_data(data, header.entry_loader, "FlashBoost") is None


def test_bad_tag_returns_none():
    assert parse_boot_header(b"XXXX" + b"\x00" * 98) is None


def test_entry_roundtrip_57_bytes():
    e = parse_boot_entry(make_entry("FlashBoot", 0x100, 0x200, delay=10))
    assert e.name == "FlashBoot"
    assert e.data_offset == 0x100
    assert e.data_size == 0x200
    assert e.data_delay == 10


@pytest.mark.skipif(not os.path.exists(REAL_LOADER), reason="real loader not present")
def test_real_loader_header_and_entries():
    with open(REAL_LOADER, "rb") as f:
        blob = f.read()
    header = parse_boot_header(blob[:102])
    assert header is not None
    assert header.tag in (b"BOOT", b"LDR ")
    for name in ("FlashBoot", "FlashData"):
        blob_data = entry_data(blob, header.entry_loader, name)
        assert blob_data is not None and len(blob_data) > 0
