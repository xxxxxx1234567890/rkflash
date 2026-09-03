"""分区/按地址/整包烧写执行（对齐 device_ops 1128-1227、1750+）。

- 镜像为 Android sparse 时流式解块并按逻辑布局写（DONT_CARE 跳过 / FILL 展开 / RAW 直读）
- 非 sparse 走 LBA 分块计划（128 扇区/批，末块补扇区）
- sparse 文件头 file_header_size>28 时先跳过扩展头
- 'parameter' 名 → LBA 0x20；'lba:ADDR' → 按地址；否则按设备分区表名解析
"""
import os
import struct

from ..firmware.format import FirmwareImage
from ..firmware.parameter import parse_sparse_chunk, parse_sparse_header
from .lba import (PARAMETER_START_SECTOR, SECTOR_SIZE, write_lba_chunk_plan)

_WRITE_WINDOW = 128 * SECTOR_SIZE          # 与协议 MAXIO 一致的 128 扇区写块


def _is_sparse_file(path: str) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == struct.pack("<I", 0xED26FF3A)


def _write_normal(dev, path: str, start_lba: int, flash_sectors: int,
                  partition_size_sectors: int = 0) -> str:
    size = os.path.getsize(path)
    if size == 0:
        raise ValueError(f"image {path} is empty")
    chunks = write_lba_chunk_plan(start_lba, size)
    total_sectors = sum(c.transfer_len for c in chunks) // SECTOR_SIZE
    if partition_size_sectors and total_sectors > partition_size_sectors:
        raise ValueError(f"image ({total_sectors} sectors) exceeds partition "
                         f"({partition_size_sectors} sectors)")
    if start_lba + total_sectors > flash_sectors:
        raise ValueError("image LBA range exceeds flash")
    with open(path, "rb") as f:
        for c in chunks:
            data = f.read(c.source_len)
            if len(data) != c.source_len:
                raise IOError(f"image shrank while flashing {path}")
            if c.transfer_len > c.source_len:
                data += b"\x00" * (c.transfer_len - c.source_len)
            dev.write_lba(c.start_sector, data)
    return f"written {os.path.basename(path)}: LBA 0x{start_lba:x}+0x{total_sectors:x}"


def _put_window(dev, base_lba: int, logical_off: int, window: bytes) -> None:
    """把一个 ≤128 扇区(65536B)的数据窗写往其逻辑位置。"""
    start = base_lba + logical_off // SECTOR_SIZE
    dev.write_lba(start, window)


def _write_sparse(dev, path: str, start_lba: int, flash_sectors: int,
                  partition_size_sectors: int = 0) -> str:
    """流式解 sparse；DONT_CARE 跳过、FILL 按窗展开、RAW 按窗直读。写按 128 扇区。"""
    with open(path, "rb") as f:
        sparse = parse_sparse_header(f.read(28))
        if sparse is None:
            raise ValueError("bad sparse header")
        if sparse.file_header_size > 28:
            f.seek(sparse.file_header_size - 28, 1)   # 跳过扩展文件头
        total_sectors = sparse.output_bytes // SECTOR_SIZE
        if partition_size_sectors and total_sectors > partition_size_sectors:
            raise ValueError("sparse output exceeds partition")
        if start_lba + total_sectors > flash_sectors:
            raise ValueError("sparse output exceeds flash")

        logical = 0          # 相对 sparse 起点的逻辑输出字节
        fill_window = None
        for _ in range(sparse.total_chunks):
            ch = f.read(sparse.chunk_header_size)
            if len(ch) < sparse.chunk_header_size:
                raise ValueError("truncated sparse chunk")
            parsed = parse_sparse_chunk(sparse, ch)
            out_bytes = parsed.output_bytes
            if parsed.kind == "dontcare":
                logical += out_bytes
                continue
            if parsed.kind == "crc32":
                f.seek(parsed.payload_bytes, 1)
                continue
            if parsed.kind == "fill":
                if fill_window is None:
                    fill_window = f.read(4) * (_WRITE_WINDOW // 4)
                rem = out_bytes
                off = logical
                while rem > 0:
                    n = min(rem, _WRITE_WINDOW)
                    buf = fill_window[:n] if n < _WRITE_WINDOW else fill_window
                    _put_window(dev, start_lba, off, buf)
                    off += n
                    rem -= n
                logical = off
            else:  # raw：按窗直读直写，避免整块分配
                rem = out_bytes
                off = logical
                while rem > 0:
                    n = min(rem, _WRITE_WINDOW)
                    data = f.read(n)
                    if len(data) != n:
                        raise ValueError("truncated sparse raw payload")
                    _put_window(dev, start_lba, off, data)
                    off += n
                    rem -= n
                logical = off
    return f"written sparse {os.path.basename(path)}: LBA 0x{start_lba:x}+0x{total_sectors:x}"


def write_firmware_image(dev, image, flash_sectors: int) -> str:
    """写一个分区镜像（自动识别 sparse）。image: FirmwareImage。"""
    if _is_sparse_file(image.path):
        return _write_sparse(dev, image.path, image.flash_offset_sectors,
                             flash_sectors, image.flash_size_sectors)
    return _write_normal(dev, image.path, image.flash_offset_sectors,
                         flash_sectors, image.flash_size_sectors)


def run_download(dev, partitions: dict, targets, flash_sectors: int) -> str:
    """targets: [(name_or_lba_spec, path)]。统一走 write_firmware_image（sparse 感知）。

    name 解析：'parameter'→0x20；'lba:ADDR'→地址；否则查设备分区表。
    """
    lines = []
    for name, path in targets:
        if name.lower() == "parameter":
            offset, size = PARAMETER_START_SECTOR, 0
        elif name.lower().startswith("lba:"):
            offset, size = int(name[4:], 0), 0
        else:
            part = partitions.get(name.lower())
            if part is None:
                raise ValueError(f"partition {name} not found on device")
            offset, size = part.start_sector, part.sector_count or 0
        import os as _os
        img = FirmwareImage(name=name, path=path, flash_offset_sectors=offset,
                            flash_size_sectors=size,
                            byte_count=_os.path.getsize(path))
        lines.append(write_firmware_image(dev, img, flash_sectors))
    return "\n".join(lines)
