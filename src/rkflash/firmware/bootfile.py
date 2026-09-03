"""Rockchip Boot/Loader 文件解析（对齐 rockfile boot.rs + device_ops loader_entry_data）。

RkBootHeader：102 字节容器，有效字段 45 字节（tag4,size u16,ver u32,merge u32,
release 7,chip 4,entry_471/472/loader 各 6, sign, rc4）。
RkBootEntry：57 字节 = size u8 + type u32le + name[20]u16le + data_offset u32le
             + data_size u32le + data_delay u32le。
"""
import struct
from dataclasses import dataclass

ENTRY_BYTES = 57

_BOOT_TAGS = (b"BOOT", b"LDR ")


@dataclass
class RkBootHeaderEntry:
    count: int
    offset: int
    size: int


@dataclass
class RkBootEntry:
    size: int
    type_: int
    name: str
    data_offset: int
    data_size: int
    data_delay: int


@dataclass
class RkBootHeader:
    tag: bytes
    size: int
    version: int
    merge_version: int
    release: bytes          # 7 字节：year u16le + mo/day/hr/min/sec
    supported_chip: bytes   # 4 字节
    entry_471: RkBootHeaderEntry
    entry_472: RkBootHeaderEntry
    entry_loader: RkBootHeaderEntry
    sign_flag: int
    rc4_flag: int


def _entry_at(data: bytes, off: int) -> RkBootHeaderEntry:
    count = data[off]
    offset = struct.unpack_from("<I", data, off + 1)[0]
    size = data[off + 5]
    return RkBootHeaderEntry(count=count, offset=offset, size=size)


def parse_boot_header(data: bytes) -> RkBootHeader | None:
    """解析 102 字节 Boot 头；tag 非 BOOT/LDR 返回 None。"""
    if len(data) < 102 or data[:4] not in _BOOT_TAGS:
        return None
    size = struct.unpack_from("<H", data, 4)[0]
    version = struct.unpack_from("<I", data, 6)[0]
    merge_version = struct.unpack_from("<I", data, 10)[0]
    release = data[14:21]
    supported_chip = data[21:25]
    e471 = _entry_at(data, 25)
    e472 = _entry_at(data, 31)
    loader = _entry_at(data, 37)
    sign_flag = data[43]
    rc4_flag = data[44]
    return RkBootHeader(tag=data[:4], size=size, version=version,
                        merge_version=merge_version, release=release,
                        supported_chip=supported_chip,
                        entry_471=e471, entry_472=e472, entry_loader=loader,
                        sign_flag=sign_flag, rc4_flag=rc4_flag)


def parse_boot_entry(data: bytes) -> RkBootEntry:
    size = data[0]
    type_ = struct.unpack_from("<I", data, 1)[0]
    raw = struct.unpack_from("<20H", data, 5)
    name = "".join(chr(c) for c in raw).rstrip("\x00")
    data_offset = struct.unpack_from("<I", data, 45)[0]
    data_size = struct.unpack_from("<I", data, 49)[0]
    data_delay = struct.unpack_from("<I", data, 53)[0]
    return RkBootEntry(size=size, type_=type_, name=name,
                       data_offset=data_offset, data_size=data_size,
                       data_delay=data_delay)


def entry_data(loader: bytes, entries: RkBootHeaderEntry, name: str) -> bytes | None:
    """在 loader 文件中按名取条目数据（对齐 device_ops loader_entry_data）。

    entries.offset 是条目表在 loader 中的字节偏移；每条 entries.size 字节。
    """
    if entries.size < ENTRY_BYTES:
        raise ValueError("loader entry table smaller than a boot entry")
    for index in range(entries.count):
        entry_offset = entries.offset + entries.size * index
        if entry_offset + ENTRY_BYTES > len(loader):
            raise ValueError(f"loader entry table is truncated (entry {index})")
        chunk = loader[entry_offset:entry_offset + ENTRY_BYTES]
        entry = parse_boot_entry(chunk)
        if not entry.name.casefold() == name.casefold():
            continue
        start = entry.data_offset
        end = start + entry.data_size
        if end > len(loader):
            raise ValueError(f"loader entry {name} is truncated "
                             f"(offset 0x{start:x}, {entry.data_size} bytes, "
                             f"file {len(loader)})")
        return loader[start:end]
    return None
