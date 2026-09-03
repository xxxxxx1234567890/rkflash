"""Rockchip parameter / GPT / Android sparse 解析与 GPT 构造。

对齐 rkdevtool firmware/android.rs（98% 直译，常量照抄）。
"""
import struct
from dataclasses import dataclass

SECTOR_SIZE = 512
GPT_ENTRY_SIZE = 128
GPT_ENTRY_COUNT = 128
GPT_ENTRY_SECTORS = GPT_ENTRY_SIZE * GPT_ENTRY_COUNT // SECTOR_SIZE  # 32
GPT_PRIMARY_SECTORS = 2 + GPT_ENTRY_SECTORS                          # 34
GPT_BACKUP_SECTORS = 1 + GPT_ENTRY_SECTORS                           # 33

ROCKCHIP_PARAMETER_MAGIC = b"PARM"
SPARSE_MAGIC = 0xED26FF3A

BASIC_DATA_GUID = bytes([0xa2, 0xa0, 0xd0, 0xeb, 0xe5, 0xb9, 0x33, 0x44,
                         0x87, 0xc0, 0x68, 0xb6, 0xb7, 0x26, 0x99, 0xc7])
DISK_GUID = bytes([0x52, 0x4b, 0x44, 0x54, 0x4f, 0x4f, 0x4c, 0x00,
                   0x91, 0x80, 0x64, 0x65, 0x76, 0x74, 0x6f, 0x6f])


@dataclass
class GptPartition:
    name: str
    start_sector: int
    sector_count: int | None
    unique_guid: bytes | None = None


@dataclass
class GptTables:
    primary: bytes
    backup_start_sector: int
    backup: bytes


class SparseChunkKind:
    RAW = "raw"
    FILL = "fill"
    DONT_CARE = "dontcare"
    CRC32 = "crc32"


@dataclass
class SparseHeader:
    file_header_size: int
    chunk_header_size: int
    block_size: int
    total_chunks: int
    output_bytes: int


@dataclass
class SparseChunk:
    kind: str
    output_bytes: int
    payload_bytes: int


def _parameter_payload(data: bytes) -> bytes:
    """剥除 PARM 头（对齐 android.rs parameter_payload）。"""
    if not data.startswith(ROCKCHIP_PARAMETER_MAGIC):
        return data
    if len(data) < 8:
        raise ValueError("incomplete Rockchip PARM header")
    payload_len = struct.unpack_from("<I", data, 4)[0]
    payload_end = 8 + payload_len
    if payload_end <= len(data):
        return data[8:payload_end]
    if data[4] == 0 and all(65 <= b <= 90 for b in data[5:8]):
        return data
    raise ValueError(f"PARM payload length {payload_len} exceeds available data")


def parse_partitions(data: bytes) -> list[GptPartition] | None:
    """解析 CMDLINE:mtdparts 分区（含 PARM 头、uuid）。返回 None = 无 CMDLINE。"""
    payload = _parameter_payload(data)
    text = payload.decode("utf-8", "replace")
    idx = text.find("CMDLINE:")
    if idx < 0:
        return None
    cmdline = text[idx + len("CMDLINE:"):].split("\x00")[0]
    _, _, entries = cmdline.partition(":")
    guids = _parse_guids(text)

    parts: list[GptPartition] = []
    for entry in entries.split(","):
        entry = entry.strip()
        if not entry:
            continue
        size_s, rest = entry.split("@", 1)
        offset_s, name_s = rest.split("(", 1)
        name = name_s.split(")", 1)[0].split(":", 1)[0].strip()
        if not name or not name.isascii():
            raise ValueError(f"invalid GPT partition name: {name}")
        sector_count = None if size_s.strip() == "-" else _hex(size_s.strip())
        parts.append(GptPartition(
            name=name, start_sector=_hex(offset_s.strip()),
            sector_count=sector_count,
            unique_guid=guids.get(name.lower())))
    if not parts:
        raise ValueError("parameter has no partitions")
    return parts


def _parse_guids(text: str) -> dict[str, bytes]:
    guids: dict[str, bytes] = {}
    for line in text.replace("\r", "\n").split("\n"):
        for piece in line.split("\x00"):
            if not piece.startswith("uuid:"):
                continue
            body = piece[5:]
            nm, _, val = body.partition("=")
            if nm and val:
                guids[nm.strip().lower()] = _parse_guid(val.strip())
    return guids


def _parse_guid(value: str) -> bytes:
    groups = value.split("-")
    if len(groups) != 5 or [len(g) for g in groups] != [8, 4, 4, 4, 12]:
        raise ValueError(f"invalid GPT partition UUID: {value}")
    first = int(groups[0], 16)
    second = int(groups[1], 16)
    third = int(groups[2], 16)
    guid = bytearray(16)
    guid[0:4] = first.to_bytes(4, "little")
    guid[4:6] = second.to_bytes(2, "little")
    guid[6:8] = third.to_bytes(2, "little")
    hexstr = groups[3] + groups[4]          # 4+12 hex → 8 字节
    for i in range(8):
        guid[8 + i] = int(hexstr[i * 2:i * 2 + 2], 16)
    return bytes(guid)


def _hex(value: str) -> int:
    v = value.lower()
    if v.startswith("0x"):
        v = v[2:]
    return int(v, 16)


def _crc32(data: bytes) -> int:
    """反射 CRC-32（poly 0xedb88320）——GPT 专用。"""
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & (0 - (crc & 1)))
    return crc ^ 0xFFFFFFFF


def build_gpt_tables(partitions: list[GptPartition], flash_sectors: int) -> GptTables:
    """按分区与 flash 构造 GPT（对齐 android.rs build_gpt_tables）。"""
    if flash_sectors <= GPT_PRIMARY_SECTORS + GPT_BACKUP_SECTORS:
        raise ValueError("flash is too small for a GPT")
    if len(partitions) > GPT_ENTRY_COUNT:
        raise ValueError("GPT parameter has too many partitions")
    first_usable = GPT_PRIMARY_SECTORS
    last_usable = flash_sectors - GPT_BACKUP_SECTORS - 1

    resolved = []
    for part in partitions:
        if part.sector_count is None:
            end = last_usable
        elif part.sector_count > 0:
            end = part.start_sector + part.sector_count - 1
        else:
            raise ValueError(f"GPT partition {part.name} has zero size")
        if part.start_sector < first_usable or end > last_usable:
            raise ValueError(f"GPT partition {part.name} is outside usable range")
        resolved.append((part, end))
    ranges = sorted(((p.start_sector, e, p.name) for p, e in resolved))
    for a, b in zip(ranges, ranges[1:]):
        if a[1] >= b[0]:
            raise ValueError(f"GPT partitions {a[2]} and {b[2]} overlap")

    entries = bytearray(GPT_ENTRY_SIZE * GPT_ENTRY_COUNT)
    for index, (part, end) in enumerate(resolved):
        e = bytearray(GPT_ENTRY_SIZE)
        e[0:16] = BASIC_DATA_GUID
        guid = part.unique_guid or bytes([index + 1] + [0] * 15)
        e[16:32] = guid
        e[32:40] = part.start_sector.to_bytes(8, "little")
        e[40:48] = end.to_bytes(8, "little")
        raw = part.name.encode("utf-16-le")
        for i in range(min(len(raw) // 2, 36)):
            e[56 + i * 2:58 + i * 2] = raw[i * 2:(i + 1) * 2]
        entries[index * GPT_ENTRY_SIZE:(index + 1) * GPT_ENTRY_SIZE] = e
    entries_crc = _crc32(bytes(entries))

    primary = bytearray(GPT_PRIMARY_SECTORS * SECTOR_SIZE)
    _write_protective_mbr(primary[:SECTOR_SIZE], flash_sectors)
    primary[SECTOR_SIZE:2 * SECTOR_SIZE] = _gpt_header(
        1, flash_sectors - 1, 2, first_usable, last_usable, entries_crc)
    primary[2 * SECTOR_SIZE:] = entries

    backup_start = flash_sectors - GPT_BACKUP_SECTORS
    backup = bytearray(GPT_BACKUP_SECTORS * SECTOR_SIZE)
    backup[:len(entries)] = entries
    backup[len(entries):len(entries) + SECTOR_SIZE] = _gpt_header(
        flash_sectors - 1, 1, backup_start, first_usable, last_usable, entries_crc)

    return GptTables(primary=bytes(primary), backup_start_sector=backup_start,
                     backup=bytes(backup))


def _write_protective_mbr(mbr: bytearray, flash_sectors: int) -> None:
    mbr[446 + 4] = 0xEE
    mbr[446 + 8:446 + 12] = (1).to_bytes(4, "little")
    mbr[446 + 12:446 + 16] = min(flash_sectors - 1, 0xFFFFFFFF).to_bytes(4, "little")
    mbr[510:512] = b"\x55\xaa"


def _gpt_header(current_lba: int, backup_lba: int, entries_lba: int,
                first_usable: int, last_usable: int, entries_crc: int) -> bytes:
    h = bytearray(SECTOR_SIZE)
    h[0:8] = b"EFI PART"
    h[8:12] = (0x00010000).to_bytes(4, "little")
    h[12:16] = (92).to_bytes(4, "little")
    h[24:32] = current_lba.to_bytes(8, "little")
    h[32:40] = backup_lba.to_bytes(8, "little")
    h[40:48] = first_usable.to_bytes(8, "little")
    h[48:56] = last_usable.to_bytes(8, "little")
    h[56:72] = DISK_GUID
    h[72:80] = entries_lba.to_bytes(8, "little")
    h[80:84] = GPT_ENTRY_COUNT.to_bytes(4, "little")
    h[84:88] = GPT_ENTRY_SIZE.to_bytes(4, "little")
    h[88:92] = entries_crc.to_bytes(4, "little")
    header_crc = _crc32(bytes(h[:92]))
    h[16:20] = header_crc.to_bytes(4, "little")
    return bytes(h)


# ---- Android sparse ----
def parse_sparse_header(data: bytes) -> SparseHeader | None:
    if len(data) < 4 or struct.unpack_from("<I", data, 0)[0] != SPARSE_MAGIC:
        return None
    if len(data) < 28:
        raise ValueError("incomplete sparse header")
    major = struct.unpack_from("<H", data, 4)[0]
    fhs = struct.unpack_from("<H", data, 8)[0]
    chs = struct.unpack_from("<H", data, 10)[0]
    block_size = struct.unpack_from("<I", data, 12)[0]
    total_blocks = struct.unpack_from("<I", data, 16)[0]
    total_chunks = struct.unpack_from("<I", data, 20)[0]
    if major != 1:
        raise ValueError(f"unsupported sparse major {major}")
    if fhs < 28 or chs < 12:
        raise ValueError("invalid sparse header size")
    if block_size == 0 or block_size % SECTOR_SIZE != 0:
        raise ValueError("sparse block size not multiple of 512")
    if total_blocks == 0 or total_chunks == 0:
        raise ValueError("sparse image has no output blocks")
    return SparseHeader(fhs, chs, block_size, total_chunks,
                        total_blocks * block_size)


def parse_sparse_chunk(sparse: SparseHeader, data: bytes) -> SparseChunk:
    if len(data) < sparse.chunk_header_size:
        raise ValueError("incomplete sparse chunk header")
    ctype = struct.unpack_from("<H", data, 0)[0]
    block_count = struct.unpack_from("<I", data, 4)[0]
    total_size = struct.unpack_from("<I", data, 8)[0]
    output = block_count * sparse.block_size
    hdr = sparse.chunk_header_size
    kind, payload = {
        0xCAC1: (SparseChunkKind.RAW, output),
        0xCAC2: (SparseChunkKind.FILL, 4),
        0xCAC3: (SparseChunkKind.DONT_CARE, 0),
        0xCAC4: (SparseChunkKind.CRC32, 4),
    }.get(ctype, (None, None))
    if kind is None:
        raise ValueError(f"unsupported sparse chunk type 0x{ctype:04x}")
    if total_size != hdr + payload:
        raise ValueError(f"invalid sparse chunk size for 0x{ctype:04x}")
    return SparseChunk(kind=kind, output_bytes=output, payload_bytes=payload)
