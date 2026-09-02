"""RKFW/RKAF 固件容器解析与解包。

字节布局为实证反向工程（docs/firmware-formats.md），对齐 rkdevtool extract.rs 的
字段语义与路径安全规则。RKFW/RKAF 条目 112 字节：name[32]+full_path[32]+12*u32。
"""
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from .format import FirmwareImage

RKFW_MAGIC = b"RKFW"
RKAF_MAGIC = b"RKAF"

PART_STRIDE = 112
NAME_BYTES = 32
PATH_BYTES = 32
# 12×u32 的索引身份（经真实固件内容验证）
_I_FLASH_SIZE = 7       # 扇区
_I_PART_OFFSET = 8      # 本条目在 RKAF 段内的字节偏移
_I_FLASH_OFFSET = 9     # LBA 扇区；0xffffffff = 不烧
_I_BYTE_COUNT = 11

_LOADER_NAMES = {"download.bin", "miniloaderall.bin"}
_MAX_NAME = 31


class FirmwareError(RuntimeError):
    pass


@dataclass
class Part:
    name: str
    full_path: str
    flash_size: int      # 扇区
    flash_offset: int    # LBA 扇区；0xffffffff = 不烧
    part_offset: int     # 相对 RKAF 段
    byte_count: int


@dataclass
class Unpacked:
    images: list[FirmwareImage]
    loader_path: str | None


def detect_container(path) -> str | None:
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic == RKFW_MAGIC:
        return "RKFW"
    if magic == RKAF_MAGIC:
        return "RKAF"
    return None


def _cstr(buf: bytes, off: int) -> str:
    end = buf.find(b"\x00", off)
    if end == -1 or end - off > _MAX_NAME:
        end = min(off + _MAX_NAME, len(buf))
    return buf[off:end].decode("latin-1")


def _rkaf_segment(path: str) -> tuple[int, int]:
    """返回 (RKAF 文件内偏移, 段长)。RKFW 需解出内嵌 RKAF；RKAF 直接是自身。"""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic == RKAF_MAGIC:
            return 0, os.path.getsize(path)
        if magic != RKFW_MAGIC:
            raise FirmwareError("unsupported firmware format")
        f.seek(0)
        head = f.read(0x29)
    boot_off = struct.unpack_from("<I", head, 0x19)[0]
    boot_size = struct.unpack_from("<I", head, 0x1d)[0]
    upd_off = struct.unpack_from("<I", head, 0x21)[0]
    upd_size = struct.unpack_from("<I", head, 0x25)[0]
    if boot_off + boot_size > upd_off:
        raise FirmwareError("RKFW boot region overlaps embedded update.img")
    return upd_off, upd_size


def _valid_name(name: str) -> bool:
    return (0 < len(name) <= _MAX_NAME
            and all(32 <= ord(c) < 127 for c in name))


def enumerate_parts(path: str) -> list[Part]:
    """从 RKAF/RKFW 文件枚举分区条目（启发式：从 0x8c 起按 112 步长）。"""
    seg_off, seg_size = _rkaf_segment(path)
    with open(path, "rb") as f:
        f.seek(seg_off)
        rkaf = f.read(min(seg_size, 256 * 1024))  # 条目表必在段头 256KB 内
    if not rkaf.startswith(RKAF_MAGIC):
        raise FirmwareError("embedded RKAF not found")

    parts: list[Part] = []
    # 条目表起始：RKAF 段头首个条目名 "package-file" 出现在 0x8c（实证）
    start = 0x8c
    while start + PART_STRIDE <= len(rkaf):
        name = _cstr(rkaf, start)
        if not _valid_name(name):
            break
        full_path = _cstr(rkaf, start + NAME_BYTES)
        u = struct.unpack_from("<12I", rkaf, start + NAME_BYTES + PATH_BYTES)
        po, bc = u[_I_PART_OFFSET], u[_I_BYTE_COUNT]
        if not full_path or not (0 < bc <= seg_size) or not (0 <= po < seg_size):
            break
        parts.append(Part(name=name, full_path=full_path,
                          flash_size=u[_I_FLASH_SIZE], flash_offset=u[_I_FLASH_OFFSET],
                          part_offset=po, byte_count=bc))
        start += PART_STRIDE
    return parts


def safe_relative_path(full_path: str) -> str:
    """规范化条目路径并拒绝逃逸（对齐 extract.rs safe_relative_path）。"""
    normalized = full_path.replace("\\", "/")
    out: list[str] = []
    for comp in normalized.split("/"):
        if comp in ("", "."):
            continue
        if comp == ".." or ":" in comp or comp.startswith(".") and comp not in (".",):
            raise FirmwareError(f"unsafe firmware entry path: {full_path}")
        out.append(comp)
    if not out:
        raise FirmwareError(f"empty firmware entry path: {full_path}")
    return "/".join(out)


def _is_loader(full_path: str) -> bool:
    name = full_path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.lower() in _LOADER_NAMES


def _extract(path: str, seg_off: int, part_offset: int, byte_count: int, out_path: Path) -> None:
    with open(path, "rb") as src, open(out_path, "wb") as dst:
        src.seek(seg_off + part_offset)
        remaining = byte_count
        while remaining > 0:
            chunk = src.read(min(remaining, 64 * 1024))
            if not chunk:
                raise FirmwareError("firmware entry truncated")
            dst.write(chunk)
            remaining -= len(chunk)


def unpack_firmware(path: str, out_dir: str) -> Unpacked:
    """解包全部条目到 out_dir，返回可烧写 images 与 loader 路径。"""
    container = detect_container(path)
    if container is None:
        raise FirmwareError("unsupported firmware format (RKFW or RKAF/update.img required)")
    seg_off, seg_size = _rkaf_segment(path)
    os.makedirs(out_dir, exist_ok=True)

    images: list[FirmwareImage] = []
    loader_path = None
    for part in enumerate_parts(path):
        rel = safe_relative_path(part.full_path)
        out_path = Path(out_dir) / rel
        _extract(path, seg_off, part.part_offset, part.byte_count, out_path)
        if _is_loader(part.full_path):
            loader_path = str(out_path)
        if part.flash_offset != 0xFFFFFFFF:
            images.append(FirmwareImage(
                name=part.name, path=str(out_path),
                flash_offset_sectors=part.flash_offset,
                flash_size_sectors=part.flash_size,
                byte_count=part.byte_count))
    return Unpacked(images=images, loader_path=loader_path)
