"""固件格式探测、FirmwareImage 模型与芯片嗅探。

探测/嗅探对齐 rkdevtool firmware/info.rs 的 detect_chip_from_blob 语义。
"""
from dataclasses import dataclass

CHIP_NAMES = ("RK3588", "RK3576", "RK3568", "RK3566", "RK3562", "RK3399",
              "RK3326", "RV1106", "RV1126", "RV1103", "PX30")


@dataclass
class FirmwareImage:
    """一个可烧写分区镜像。"""
    name: str
    path: str
    flash_offset_sectors: int
    flash_size_sectors: int
    byte_count: int


def detect_format(path: str) -> str | None:
    """探测固件格式：RKFW / RKAF / Loader(独立 boot 文件) / None。"""
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic == b"RKFW":
        return "RKFW"
    if magic == b"RKAF":
        return "RKAF"
    if magic in (b"BOOT", b"LDR "):
        return "Loader"
    return None


def sniff_chip_blob(blob: bytes) -> str | None:
    """在前 4MB 采样里找已知芯片名（对齐 info.rs detect_chip_from_blob）。"""
    sample = blob[:4 * 1024 * 1024].decode("latin-1", "replace")
    for chip in CHIP_NAMES:
        if chip in sample:
            return chip
    return None
