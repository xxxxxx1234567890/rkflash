"""LBA 分块读/写与设备端分区表读取（对齐 device_ops.rs 616-782、1096-1126）。"""
import struct
from dataclasses import dataclass

from ..firmware.parameter import (SECTOR_SIZE, GPT_ENTRY_SIZE,
                                  parse_partitions)

READ_LBA_CHUNK = 128            # 每块最多 128 扇区
WRITE_LBA_CHUNK = READ_LBA_CHUNK * SECTOR_SIZE
PARAMETER_START_SECTOR = 0x20
PARAMETER_READ_SECTORS = 128


@dataclass
class DownloadPartition:
    name: str
    start_sector: int
    sector_count: int | None


@dataclass
class LbaWriteChunk:
    start_sector: int
    source_len: int
    transfer_len: int


def write_lba_chunk_plan(start_sector: int, byte_count: int) -> list[LbaWriteChunk]:
    """把 byte_count 拆成 ≤128 扇区写块（对齐 device_ops 1096-1126）。"""
    if byte_count <= 0:
        raise ValueError("firmware image is empty")
    chunks: list[LbaWriteChunk] = []
    remaining = byte_count
    cur = start_sector
    while remaining > 0:
        source_len = min(remaining, WRITE_LBA_CHUNK)
        transfer_len = ((source_len + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
        chunks.append(LbaWriteChunk(cur, source_len, transfer_len))
        cur += transfer_len // SECTOR_SIZE
        remaining -= source_len
    return chunks


def read_lba_sectors(dev, start_sector: int, sector_count: int) -> bytes:
    """按 ≤128 扇区块读，短读报错（对齐 device_ops 724-753）。"""
    out = bytearray()
    done = 0
    while done < sector_count:
        count = min(sector_count - done, READ_LBA_CHUNK)
        data = dev.read_lba(start_sector + done, count)
        if len(data) != count * SECTOR_SIZE:
            raise IOError(f"short LBA read at {start_sector + done}: "
                          f"{len(data)} bytes, expected {count * SECTOR_SIZE}")
        out += data
        done += count
    return bytes(out)


def _gpt_entry_layout(header: bytes):
    """解析 GPT 头布局；非 GPT 返回 None。返回 (entries_lba, entry_count, entry_size)。"""
    if len(header) < SECTOR_SIZE or header[:8] != b"EFI PART":
        return None
    header_size = struct.unpack_from("<I", header, 12)[0]
    if not (92 <= header_size <= SECTOR_SIZE):
        raise ValueError("invalid GPT header size")
    entries_lba = struct.unpack_from("<Q", header, 72)[0]
    entry_count = struct.unpack_from("<I", header, 80)[0]
    entry_size = struct.unpack_from("<I", header, 84)[0]
    if entry_count == 0 or entry_count > 4096 or not (128 <= entry_size <= 4096):
        raise ValueError("unsupported GPT partition entry layout")
    return entries_lba, entry_count, entry_size


def _parse_gpt_partitions(header: bytes, entries: bytes) -> list[DownloadPartition]:
    layout = _gpt_entry_layout(header)
    if layout is None:
        return []
    entries_lba, entry_count, entry_size = layout
    total = entry_count * entry_size
    if len(entries) < total:
        raise ValueError("GPT partition table is incomplete")
    parts: list[DownloadPartition] = []
    for i in range(entry_count):
        e = entries[i * entry_size:(i + 1) * entry_size]
        if all(b == 0 for b in e[:16]):
            continue
        start = struct.unpack_from("<Q", e, 32)[0]
        end = struct.unpack_from("<Q", e, 40)[0]
        if end < start:
            raise ValueError("GPT partition has invalid sector range")
        # UTF-16LE name
        raw = e[56:]
        chars = []
        for j in range(0, len(raw) - 1, 2):
            w = struct.unpack_from("<H", raw, j)[0]
            if w == 0:
                break
            chars.append(chr(w))
        name = "".join(chars).strip()
        if not name:
            continue
        parts.append(DownloadPartition(name, start, end - start + 1))
    return parts


def read_device_partitions(dev) -> list[DownloadPartition]:
    """读设备分区表：LBA1 GPT 优先，否则 parameter@0x20 解析（对齐 755-781）。"""
    header = read_lba_sectors(dev, 1, 1)
    if _gpt_entry_layout(header) is not None:
        entries_lba, entry_count, entry_size = _gpt_entry_layout(header)
        entry_bytes = entry_count * entry_size
        entry_sectors = (entry_bytes + SECTOR_SIZE - 1) // SECTOR_SIZE
        entries = read_lba_sectors(dev, entries_lba, entry_sectors)
        parts = _parse_gpt_partitions(header, entries)
        if not parts:
            raise IOError("GPT partition table is missing")
        return parts

    parameter = read_lba_sectors(dev, PARAMETER_START_SECTOR, PARAMETER_READ_SECTORS)
    parsed = parse_partitions(parameter)
    if not parsed:
        raise IOError("no GPT or Rockchip parameter partition table found")
    return [DownloadPartition(p.name, p.start_sector, p.sector_count)
            for p in parsed]
