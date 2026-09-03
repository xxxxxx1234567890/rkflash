"""M4-A：完整升级编排。"""
import os

import pytest

from rkflash.firmware.format import FirmwareImage
from rkflash.flashing.upgrade import run_upgrade_images
from rkflash.flashing.lba import SECTOR_SIZE
from rkflash.mock_transport import MockRockDevice


def _dev():
    d = MockRockDevice()
    # flash_info 返回 0x400000 扇区；capability NEW_IDB
    d.flash_info = lambda: (0x400000).to_bytes(4, "little") + b"\x00" * 7
    d.capability = lambda: bytes([0, 1] + [0] * 6)
    return d


def _img(name, off, data, size_sectors=64):
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), name)
    with open(p, "wb") as f:
        f.write(data)
    return FirmwareImage(name=name, path=p, flash_offset_sectors=off,
                         flash_size_sectors=size_sectors, byte_count=len(data))


def test_upgrade_writes_partitions_and_resets():
    dev = _dev()
    img1 = _img("uboot.img", 0x2000, b"\xAB" * (2 * 512))
    img2 = _img("boot.img", 0x4000, b"\xCD" * 512)
    log = run_upgrade_images(dev, [img1, img2], loader_path=None, no_reset=False)
    assert "succeeded" in log
    assert dev.read_lba(0x2000, 2) == b"\xAB" * (2 * 512)
    assert dev.read_lba(0x4000, 1) == b"\xCD" * 512


def test_upgrade_gpt_parameter_creates_tables(tmp_path):
    dev = _dev()
    gpt_param_text = (b"PARM\x00TYPE: GPT\x00CMDLINE:mtdparts=rk29xxnand:"
                      b"0x00002000@0x00004000(uboot),-@0x00020800(userdata:grow)\x00")
    p = tmp_path / "parameter.txt"
    p.write_bytes(gpt_param_text)
    img = FirmwareImage(name="parameter", path=str(p), flash_offset_sectors=0,
                        flash_size_sectors=8, byte_count=len(gpt_param_text))
    log = run_upgrade_images(dev, [img], loader_path=None, no_reset=True)
    assert "succeeded" in log
    # primary GPT 头在 LBA1（EFI PART）；分区信息入 GPT 条目，不再单独落 PARM 块
    assert dev.read_lba(1, 1)[:8] == b"EFI PART"
    raw = dev.read_lba(0x2000, 1)
    assert not raw.startswith(b"PARM")


def test_upgrade_legacy_parameter_remapped_to_0x2000(tmp_path):
    """非 GPT(legacy) parameter：flash_offset 常为 0，必须重映射到 0x2000 而非 LBA0。"""
    dev = _dev()
    legacy = (b"PARM\x00CMDLINE:mtdparts=rk29xxnand:"
              b"0x00002000@0x00002000(uboot),-@0x00020800(rootfs)\x00")
    p = tmp_path / "parameter.txt"
    p.write_bytes(legacy)
    img = FirmwareImage(name="parameter", path=str(p), flash_offset_sectors=0,
                        flash_size_sectors=8, byte_count=len(legacy))
    run_upgrade_images(dev, [img], loader_path=None, no_reset=True)
    # LBA0 不应被写（保护 MBR 区）；parameter 落在 0x2000
    assert dev.read_lba(0x2000, 1).startswith(b"PARM")
    assert dev.transport.storage.get(0) is None
