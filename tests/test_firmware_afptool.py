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
