"""M3-A：固件格式探测 / FirmwareImage 模型 / 芯片嗅探。"""
import os

import pytest

from rkflash.firmware.format import FirmwareImage, detect_format, sniff_chip_blob

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "Ruiching_RC-Pi-3506_Firmware_NAND_AMP_FACRTORY_V1.8.1.img")


def test_detect_signatures(tmp_path):
    p = tmp_path / "f.img"
    p.write_bytes(b"RKFW" + b"\x00" * 64)
    assert detect_format(str(p)) == "RKFW"
    p.write_bytes(b"RKAF" + b"\x00" * 64)
    assert detect_format(str(p)) == "RKAF"
    p.write_bytes(b"data" + b"\x00" * 64)
    assert detect_format(str(p)) is None


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="fixture not present")
def test_detect_fixture_is_rkfw():
    assert detect_format(FIXTURE) == "RKFW"


def test_sniff_chip():
    blob = (b"garbage-RK3576-nonflash-") * 400  # 采样区含芯片名
    assert sniff_chip_blob(blob) == "RK3576"
    assert sniff_chip_blob(b"\x00" * 8192) is None


def test_firmware_image_fields():
    img = FirmwareImage(name="uboot", path="/tmp/uboot.img",
                        flash_offset_sectors=0x2000, flash_size_sectors=0x2000,
                        byte_count=4096)
    assert img.name == "uboot"
    assert img.flash_offset_sectors == 0x2000
