"""erase / export / storage 命令（对齐 device_ops erase/export 语义）。"""
import struct

from ..protocol.command_block import StorageIndex
from .lba import SECTOR_SIZE, READ_LBA_CHUNK

ERASE_LBA_CHUNK = 1024 * 32        # 每次 EraseLBA 最大扇区


def flash_sectors(dev) -> int:
    data = dev.flash_info()
    return struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0


def erase_range(dev, first: int, count: int) -> None:
    """分块擦除 LBA 区间。"""
    remaining = count
    cur = first
    while remaining > 0:
        n = min(remaining, ERASE_LBA_CHUNK)
        dev.erase_lba(cur, n)
        cur += n
        remaining -= n


def export_image(dev, first: int, count: int, out_path: str) -> str:
    """按 128 扇区块读出写文件；短读报错。"""
    if count <= 0:
        raise ValueError("export sector count must be positive")
    written = 0
    remaining = count
    with open(out_path, "wb") as f:
        while remaining > 0:
            n = min(remaining, READ_LBA_CHUNK)
            data = dev.read_lba(first + written, n)
            if len(data) != n * SECTOR_SIZE:
                raise IOError(f"short LBA read at {first + written}: "
                              f"{len(data)} bytes, expected {n * SECTOR_SIZE}")
            f.write(data)
            written += n
            remaining -= n
    return f"exported {count} sectors from LBA 0x{first:x} to {out_path}"


_STORAGE_ALIASES = {s.name.lower(): int(s) for s in StorageIndex}
_STORAGE_ALIASES.update({"spi_nand": 16})   # 实测 RK3506：bit16


def query_storage(dev) -> dict:
    raw = dev.storage()
    value = int.from_bytes(raw[:4], "little") if raw else 0
    bit = value.bit_length() - 1 if value else None
    names = {v: k for k, v in _STORAGE_ALIASES.items()}
    return {"raw": hex(value), "index": bit, "name": names.get(bit, "unknown")}


def switch_storage(dev, name: str) -> dict:
    idx = _STORAGE_ALIASES.get(name.strip().lower())
    if idx is None:
        raise ValueError(f"unknown storage: {name} "
                         f"(choices: {sorted(_STORAGE_ALIASES)})")
    dev.switch_storage(idx)
    return query_storage(dev)
