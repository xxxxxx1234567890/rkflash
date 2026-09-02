"""分区/按地址/整包烧写执行（对齐 device_ops 1128-1227、1750+）。

- Android sparse 图流式解块写入（DONT_CARE 跳过 / FILL 展开 / RAW 直写）
- 非 sparse 走 LBA 分块计划
- 'parameter' 名 → LBA 0x20；'lba:ADDR' → 按地址；否则查设备分区表
"""
import os
import struct

from ..firmware.parameter import parse_sparse_chunk, parse_sparse_header
from .lba import (PARAMETER_START_SECTOR, SECTOR_SIZE, write_lba_chunk_plan)


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
        raise ValueError(f"image LBA range exceeds flash")
    with open(path, "rb") as f:
        for c in chunks:
            data = f.read(c.source_len)
            if c.transfer_len > c.source_len:
                data += b"\x00" * (c.transfer_len - c.source_len)
            dev.write_lba(c.start_sector, data)
    return f"written {os.path.basename(path)}: LBA 0x{start_lba:x}+0x{total_sectors:x}"


def _write_sparse(dev, path: str, start_lba: int, flash_sectors: int,
                  partition_size_sectors: int = 0) -> str:
    """流式解析 sparse 并按其逻辑布局写盘。chunk 输出都是 block_size 的倍数。"""
    with open(path, "rb") as f:
        sparse = parse_sparse_header(f.read(28))
        if sparse is None:
            raise ValueError("bad sparse header")
        total_sectors = sparse.output_bytes // SECTOR_SIZE
        if partition_size_sectors and total_sectors > partition_size_sectors:
            raise ValueError("sparse output exceeds partition")
        if start_lba + total_sectors > flash_sectors:
            raise ValueError("sparse output exceeds flash")

        logical = 0  # 逻辑输出字节偏移（相对 sparse 起点）
        for _ in range(sparse.total_chunks):
            ch = f.read(sparse.chunk_header_size)
            if len(ch) < sparse.chunk_header_size:
                raise ValueError("truncated sparse chunk")
            parsed = parse_sparse_chunk(sparse, ch)
            nblocks = struct.unpack_from("<I", ch, 4)[0]
            out_bytes = parsed.output_bytes
            if parsed.kind == "dontcare":
                logical += out_bytes
            elif parsed.kind == "crc32":
                f.seek(parsed.payload_bytes, 1)
            else:
                payload = f.read(parsed.payload_bytes)
                if len(payload) < parsed.payload_bytes:
                    raise ValueError("truncated sparse payload")
                if parsed.kind == "raw":
                    data = payload
                else:  # fill: 4 字节展开到 block_size×nblocks
                    fill4 = payload[:4]
                    data = (fill4 * (sparse.block_size // 4)) * nblocks
                if out_bytes != len(data):
                    raise ValueError("sparse chunk expansion mismatch")
                _write_logical(dev, start_lba, logical, data)
                logical += out_bytes
    return f"written sparse {os.path.basename(path)}: LBA 0x{start_lba:x}+0x{total_sectors:x}"


def _write_logical(dev, base_lba: int, logical_off: int, data: bytes) -> None:
    """logical_off 为 512 倍数对齐（block_size 是 512 的倍数）。"""
    start = base_lba + logical_off // SECTOR_SIZE
    for i in range(0, len(data), SECTOR_SIZE):
        dev.write_lba(start + i // SECTOR_SIZE, data[i:i + SECTOR_SIZE])


def write_firmware_image(dev, image, flash_sectors: int) -> str:
    if _is_sparse_file(image.path):
        return _write_sparse(dev, image.path, image.flash_offset_sectors,
                             flash_sectors, image.flash_size_sectors)
    return _write_normal(dev, image.path, image.flash_offset_sectors,
                         flash_sectors, image.flash_size_sectors)


def run_download(dev, partitions: dict, targets, flash_sectors: int) -> str:
    """targets: [(name_or_lba_spec, path)]。返回日志。"""
    lines = []
    for name, path in targets:
        if name.lower() == "parameter":
            line = _write_normal(dev, path, PARAMETER_START_SECTOR,
                                 flash_sectors)
        elif name.lower().startswith("lba:"):
            lba = int(name[4:], 0)
            line = _write_normal(dev, path, lba, flash_sectors)
        else:
            part = partitions.get(name.lower())
            if part is None:
                raise ValueError(f"partition {name} not found on device")
            line = _write_normal(dev, path, part.start_sector, flash_sectors,
                                 part.sector_count or 0)
        lines.append(line)
    return "\n".join(lines)
