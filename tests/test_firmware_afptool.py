"""RKAF/RKFW 解包测试——用真实 RK3506 fixture 验证（布局见 docs/firmware-formats.md）。"""
import os

import pytest

from rkflash.firmware.afptool import detect_container, enumerate_parts, unpack_firmware

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "Ruiching_RC-Pi-3506_Firmware_NAND_AMP_FACRTORY_V1.8.1.img")


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="real update.img fixture not present")
def test_detect_container_is_rkfw():
    assert detect_container(FIXTURE) == "RKFW"


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="real update.img fixture not present")
def test_enumerate_parts_finds_expected_partitions():
    parts = enumerate_parts(FIXTURE)
    names = {p.name for p in parts}
    paths = {p.full_path for p in parts}
    assert "uboot" in names
    assert "bootloader" in names            # 条目名
    assert "MiniLoaderAll.bin" in paths     # loader 全路径
    assert "parameter" in names
    # package-file/bootloader: flash_offset 0xffffffff → 不入烧写列表
    for p in parts:
        if p.flash_offset == 0xFFFFFFFF:
            assert p.full_path in ("package-file", "MiniLoaderAll.bin")


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="real update.img fixture not present")
def test_unpack_firmware_to_temp(tmp_path):
    result = unpack_firmware(FIXTURE, str(tmp_path))
    assert result.loader_path is not None  # MiniLoaderAll.bin / download.bin
    assert result.images, "应有可烧写分区"
    assert result.images[0].path
    assert os.path.exists(result.loader_path)


def _synthetic_rkaf_with_self(tmp_path):
    """RKAF：0x8c 头填充 + SELF 条目 + 正常 uboot 条目 + payload。"""
    import struct
    parts = [
        (b"SELF", b"SELF", 0xFFFFFFFF, 0x1000, 16),
        (b"uboot", b"uboot.img", 0x2000, 0x1020, 32),
    ]
    entries = b""
    for name, path, fo, po, bc in parts:
        e = bytearray(112)
        e[0:len(name)] = name
        e[32:32 + len(path)] = path
        u = [0] * 12
        u[7] = 0          # flash_size
        u[8] = po         # part_offset
        u[9] = fo         # flash_offset
        u[11] = bc        # byte_count
        struct.pack_into("<12I", e, 64, *u)
        entries += bytes(e)
    body = bytearray(0x2000)
    body[0x1000:0x1000 + 16] = b"Z" * 16
    body[0x1020:0x1020 + 32] = b"W" * 32
    data = bytearray(b"RKAF")
    data += b"\x00" * (0x8c - 4)
    data += entries
    data += body
    p = tmp_path / "self.img"
    p.write_bytes(bytes(data))
    return str(p)


def test_unpack_skips_self_and_reserved(tmp_path):
    from rkflash.firmware.afptool import unpack_firmware
    f = _synthetic_rkaf_with_self(tmp_path)
    out = tmp_path / "out"
    result = unpack_firmware(f, str(out))
    assert not (out / "SELF").exists()
    assert (out / "uboot.img").exists()
    assert [i.name for i in result.images] == ["uboot"]


def test_safe_relative_allows_dotfile():
    from rkflash.firmware.afptool import safe_relative_path
    assert safe_relative_path("Image/.boot") == "Image/.boot"
    assert safe_relative_path("uboot.img") == "uboot.img"
