"""M3-H：分区/按地址烧写 + sparse 流式写。"""
import struct

import pytest

from rkflash.device import RockDevice
from rkflash.flashing.download import run_download, write_firmware_image
from rkflash.flashing.lba import DownloadPartition, SECTOR_SIZE
from rkflash.firmware.format import FirmwareImage
from rkflash.mock_transport import MockRockDevice, MockTransport


def _mock_dev():
    # MockRockDevice.write_lba 会持久化到 storage（RockDevice+MockTransport 不会）
    return MockRockDevice()


def _fill_sectors(dev, start, sectors):
    return b"".join(dev.transport.storage.get(start + i, b"\x00" * 512)
                    for i in range(sectors))


def test_run_download_by_partition_and_parameter(tmp_path):
    dev = _mock_dev()
    uboot = tmp_path / "uboot.img"
    uboot.write_bytes(b"\xAA" * (3 * 512))
    param = tmp_path / "parameter.txt"
    param.write_bytes(b"PARM-TEXT")
    parts = {"uboot": DownloadPartition("uboot", 0x2000, 64)}
    run_download(dev, parts, [("uboot", str(uboot)), ("parameter", str(param))],
                 flash_sectors=0x800000)
    assert _fill_sectors(dev, 0x2000, 3) == b"\xAA" * (3 * 512)
    # parameter -> LBA 0x20（不足一扇区补 0）
    raw = dev.transport.storage.get(0x20, b"\x00" * 512)
    assert raw.startswith(b"PARM-TEXT")


def _sparse_file(tmp_path, blocks):
    """构造 block_size=512 的 sparse：raw 1 块、dontcare 1 块、fill 1 块。"""
    p = tmp_path / "sparse.img"
    out = bytearray()
    out += struct.pack("<I", 0xED26FF3A)
    out += struct.pack("<H", 1)            # major
    out += struct.pack("<H", 0)            # minor
    out += struct.pack("<H", 28)           # file_header_size
    out += struct.pack("<H", 12)           # chunk_header_size
    out += struct.pack("<I", 512)          # block_size
    out += struct.pack("<I", 3)            # total_blocks
    out += struct.pack("<I", 3)            # total_chunks
    out += struct.pack("<I", 0)            # checksum(0)
    # chunk1 raw(1 block=512)
    out += struct.pack("<H", 0xCAC1) + struct.pack("<H", 0)
    out += struct.pack("<I", 1) + struct.pack("<I", 12 + 512)
    out += b"\x11" * 512
    # chunk2 dontcare(1 block)
    out += struct.pack("<H", 0xCAC3) + struct.pack("<H", 0)
    out += struct.pack("<I", 1) + struct.pack("<I", 12)
    # chunk3 fill(1 block)
    out += struct.pack("<H", 0xCAC2) + struct.pack("<H", 0)
    out += struct.pack("<I", 1) + struct.pack("<I", 12 + 4)
    out += b"\x22\x22\x22\x22"
    p.write_bytes(bytes(out))
    return str(p)


def test_sparse_image_written_logical(tmp_path):
    dev = _mock_dev()
    img = FirmwareImage(name="system", path=_sparse_file(tmp_path, 3),
                        flash_offset_sectors=0x1000, flash_size_sectors=16,
                        byte_count=3 * 512)
    write_firmware_image(dev, img, flash_sectors=0x800000)
    # logical: [0]=0x11*512, [1]=dontcare 跳过, [2]=0x22*512
    assert _fill_sectors(dev, 0x1000, 1) == b"\x11" * 512
    assert _fill_sectors(dev, 0x1002, 1) == b"\x22" * 512
    assert dev.transport.storage.get(0x1001) is None  # dontcare 不写


def test_short_write_padding(tmp_path):
    dev = _mock_dev()
    p = tmp_path / "part.bin"
    p.write_bytes(b"\xAB" * 500)          # 非整扇区
    img = FirmwareImage(name="x", path=str(p), flash_offset_sectors=5,
                        flash_size_sectors=4, byte_count=500)
    write_firmware_image(dev, img, flash_sectors=0x1000)
    data = dev.transport.storage.get(5)
    assert data == b"\xAB" * 500 + b"\x00" * 12
