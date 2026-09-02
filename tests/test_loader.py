"""M3-G：Maskrom Loader 下载 / Loader IDBlock 写入。"""
import os
import struct

import pytest

from rkflash.firmware.bootfile import entry_data, parse_boot_header
from rkflash.flashing.idblock import build_idblock
from rkflash.flashing.loader import (download_boot, wait_for_loader,
                                     write_loader_idblock)
from rkflash.mock_transport import MockRockDevice, MockTransport

REAL_LOADER = os.path.join(os.path.dirname(__file__), "fixtures",
                           "MiniLoaderAll_rk3506.bin")


def _boot_entry(name: str, data: bytes) -> bytes:
    e = bytearray(57)
    e[0] = 57
    for i, ch in enumerate(name):
        struct.pack_into("<H", e, 5 + i * 2, ord(ch))
    struct.pack_into("<I", e, 49, len(data))
    return bytes(e)


def _loader_with_471_472():
    d1 = b"\x11" * 256
    d2 = b"\x22" * 512
    entries = _boot_entry("A", d1) + _boot_entry("B", d2)
    table_off = 512
    data_off = table_off + len(entries)
    loader = bytearray(data_off + len(d1) + len(d2))
    loader[0:102] = b"BOOT" + b"\x00" * 98
    # entry_471 @25: count=2 offset=table_off size=57
    loader[25] = 1
    struct.pack_into("<I", loader, 26, table_off)
    loader[30] = 57
    # entry_472 @31: count=1 -> data2 (填 table_off+57)
    loader[31] = 1
    struct.pack_into("<I", loader, 32, table_off + 57)
    loader[36] = 57
    loader[table_off:table_off + len(entries)] = entries
    # 填 data_offset
    for i, (start, blob) in enumerate([(data_off, d1), (data_off + len(d1), d2)]):
        rec = bytearray(loader[table_off + i * 57:table_off + (i + 1) * 57])
        struct.pack_into("<I", rec, 45, start)
        loader[table_off + i * 57:table_off + (i + 1) * 57] = rec
        loader[start:start + len(blob)] = blob
    return bytes(loader)


def test_download_boot_uploads_471_then_472(tmp_path):
    p = tmp_path / "loader.bin"
    p.write_bytes(_loader_with_471_472())
    dev = MockRockDevice()
    log = download_boot(dev, str(p))
    areas = [a for a, _ in dev.transport.control_calls]
    assert 0x471 in areas
    assert 0x472 in areas
    assert areas.index(0x471) < areas.index(0x472)
    assert "download-boot" in log


def test_wait_for_loader_true_when_ready():
    dev = MockRockDevice()
    assert wait_for_loader(dev) is True


@pytest.mark.skipif(not os.path.exists(REAL_LOADER), reason="real loader not present")
def test_write_loader_idblock_real_loader(tmp_path):
    dev = MockRockDevice()
    # 真实 RK3506 loader 有 FlashHead，需 NEW_IDB capability（cap[1]&1）
    dev.capability = lambda: bytes([0x00, 0x01] + [0x00] * 6)
    write_loader_idblock(dev, REAL_LOADER, flash_sectors=0x800000)
    # 校验 LBA 0x40 起内容 == 我们独立构造的 idblock
    with open(REAL_LOADER, "rb") as f:
        loader = f.read()
    cap = dev.capability()
    idblock, _ = build_idblock(loader, new_idb=(cap[1] & 1) == 1)
    written = b"".join(dev.transport.storage.get(0x40 + i, b"") for i in range(len(idblock) // 512))
    assert written == idblock
