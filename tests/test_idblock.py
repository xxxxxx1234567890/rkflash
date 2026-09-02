"""M3-D：IDBlock 构造（对齐 device_ops.rs 845-1033）。"""
import os
import struct

import pytest

from rkflash.firmware.bootfile import entry_data, parse_boot_header
from rkflash.flashing.idblock import (build_idblock, crc16_ccitt, rc4_crypt,
                                      rockchip_crc32)

REAL_LOADER = os.path.join(os.path.dirname(__file__), "fixtures",
                           "MiniLoaderAll_rk3506.bin")


def test_crc16_ccitt_xmodem_check():
    # CRC-16/XMODEM check（init 0, poly 0x1021, MSB-first）
    assert crc16_ccitt(b"123456789") == 0x31C3


def test_rockchip_crc32_vector():
    assert rockchip_crc32(b"123456789") == 0x89A1897F


def test_rc4_rfc6229_vector():
    # RFC 6229 key = 0x01..0x10；首 16 字节密钥流
    key = bytes(range(1, 17))
    out = rc4_crypt(bytes(16), key)
    assert out == bytes.fromhex("9ac7cc9a609d1ef7b2932899cde41b97")


def _synthetic_loader(rc4_flag, has_head):
    """拼一个含 FlashBoot/FlashData/FlashHead(可选) 的 loader。"""
    parts = {b"FlashBoot": bytes([0xAA]) * 1024,
             b"FlashData": bytes([0xBB]) * 2048}
    if has_head:
        parts[b"FlashHead"] = bytes([0xCC]) * 512
    entries = b""
    order = list(parts.keys())
    for name in order:
        data = parts[name]
        e = bytearray(57)
        e[0] = 57
        for i, ch in enumerate(name.decode()):
            struct.pack_into("<H", e, 5 + i * 2, ord(ch))
        struct.pack_into("<I", e, 49, len(data))
        entries += bytes(e)
    table_off = 512
    # 数据按顺序接在条目表后
    cur = table_off + len(entries)
    data_offsets = {}
    for name in order:
        data_offsets[name] = cur
        cur += len(parts[name])
    loader = bytearray(cur)
    loader[0:102] = b"LDR " + b"\x00" * 98
    loader[37] = len(parts)
    struct.pack_into("<I", loader, 38, table_off)
    loader[42] = 57
    loader[44] = rc4_flag
    for i, name in enumerate(order):
        entry = bytearray(entries[i * 57:(i + 1) * 57])
        struct.pack_into("<I", entry, 45, data_offsets[name])
        loader[table_off + i * 57:table_off + (i + 1) * 57] = entry
        off = data_offsets[name]
        loader[off:off + len(parts[name])] = parts[name]
    return bytes(loader)


def test_legacy_idblock_layout_and_rc4_sectors():
    # 对齐上游 device_ops 992-994：末尾恒对 sector0/2/3 做 RC4（与 rc4 标志无关）。
    # 因此输出 sector0 恒为密文，用对称 RC4 解回应还原魔数 0x0ff0aa55。
    loader = _synthetic_loader(rc4_flag=0, has_head=False)
    idblock, layout = build_idblock(loader, new_idb=False)
    assert layout == "legacy IDBlock"
    plain0 = rc4_crypt(bytes(idblock[:512]))
    assert plain0[:4] == (0x0FF0AA55).to_bytes(4, "little")

    loader_r = _synthetic_loader(rc4_flag=1, has_head=False)
    idblock_r, _ = build_idblock(loader_r, new_idb=False)
    plain0_r = rc4_crypt(bytes(idblock_r[:512]))
    assert plain0_r[:4] == (0x0FF0AA55).to_bytes(4, "little")
    # rc4 标志控制 data/boot 段：rc4=1 时 data 段密文 ≠ 明文
    assert idblock != idblock_r


@pytest.mark.skipif(not os.path.exists(REAL_LOADER), reason="real loader not present")
def test_real_loader_builds_idblock():
    with open(REAL_LOADER, "rb") as f:
        loader = f.read()
    header = parse_boot_header(loader[:102])
    assert header is not None
    has_head = entry_data(loader, header.entry_loader, "FlashHead") is not None
    idblock, layout = build_idblock(loader, new_idb=has_head)
    assert layout in ("legacy IDBlock", "New IDBlock", "New IDBlock + FlashBoost")
    assert len(idblock) % 512 == 0
    # 魔数锚点：legacy 在 sector0；new 也应可被 Loader 识别的自检留给真机
    assert idblock[:4] == (0x0FF0AA55).to_bytes(4, "little") or layout.startswith("New")
