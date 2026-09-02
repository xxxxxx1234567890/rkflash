"""Maskrom Loader 下载与 Loader IDBlock 写入（对齐 device_ops 1035-1080、
download_boot / download_boot_to_device 语义 + rockfile 471/472 上传）。

设备就绪：write_loader_idblock 前目标须已是 Loader 模式（本文件也含 wait_for_loader）。
"""
import time

from ..firmware.bootfile import entry_data, parse_boot_header
from .idblock import build_idblock

IDBLOCK_START_SECTOR = 0x40
WRITE_LBA_CHUNK_SECTORS = 128
LOADER_READY_RETRIES = 120
LOADER_READY_INTERVAL = 0.25          # 秒
LOADER_BOOT_SETTLE = 1.0              # 秒


def _cap_new_idb(capability_bytes: bytes) -> bool:
    """NEW_IDB capability 位：cap[1] & 0x01。"""
    return len(capability_bytes) >= 2 and bool(capability_bytes[1] & 0x01)


def _sleep(seconds: float):
    if seconds > 0:
        time.sleep(seconds)


def upload_maskrom_boot(dev, loader: bytes, area: int, entries) -> None:
    """把 0x471/0x472 组的各 blob 经 write_area 上传。"""
    if entries.size < 57:
        raise ValueError("boot entry table smaller than a boot entry")
    for index in range(entries.count):
        off = entries.offset + entries.size * index
        rec = loader[off:off + 57]
        if len(rec) < 57:
            break
        from ..firmware.bootfile import parse_boot_entry
        entry = parse_boot_entry(rec)
        data = loader[entry.data_offset:entry.data_offset + entry.data_size]
        dev.write_area(area, data)
        _sleep(entry.data_delay / 1000.0)


def download_boot(dev, loader_path: str) -> str:
    """Maskrom 模式上传 Loader：0x471(SRAM)→0x472(DRAM)，随后等 Loader 设备。"""
    with open(loader_path, "rb") as f:
        loader = f.read()
    header = parse_boot_header(loader[:102])
    if header is None:
        raise ValueError(f"not a Rockchip Boot/Loader file: {loader_path}")

    log_lines = [f"download-boot {loader_path}"]
    if header.entry_471.count:
        upload_maskrom_boot(dev, loader, 0x471, header.entry_471)
        log_lines.append(f"uploaded {header.entry_471.count} blob(s) to area 0x471")
        _sleep(LOADER_BOOT_SETTLE)
    if header.entry_472.count:
        upload_maskrom_boot(dev, loader, 0x472, header.entry_472)
        log_lines.append(f"uploaded {header.entry_472.count} blob(s) to area 0x472")
        _sleep(LOADER_BOOT_SETTLE)
    return "\n".join(log_lines)


def wait_for_loader(dev) -> bool:
    """轮询直到 TestUnitReady 通过（≤120×250ms）。"""
    for _ in range(LOADER_READY_RETRIES):
        try:
            dev.test_unit_ready()
            return True
        except Exception:  # noqa: BLE001
            _sleep(LOADER_READY_INTERVAL)
    return False


def write_loader_idblock(dev, loader_path: str, flash_sectors: int) -> str:
    """在 Loader 模式下把构造的 IDBlock 写到 LBA 0x40。"""
    with open(loader_path, "rb") as f:
        loader = f.read()
    cap = dev.capability()
    idblock, layout = build_idblock(loader, _cap_new_idb(cap))
    sectors = len(idblock) // 512
    if IDBLOCK_START_SECTOR + sectors > flash_sectors:
        raise ValueError("Loader IDBlock exceeds the target flash size")

    total = len(idblock)
    written = 0
    while written < total:
        chunk = idblock[written:written + WRITE_LBA_CHUNK_SECTORS * 512]
        sector = IDBLOCK_START_SECTOR + written // 512
        dev.write_lba(sector, chunk)
        written += len(chunk)
    return f"Written Loader IDBlock ({layout}): LBA 0x40-0x{IDBLOCK_START_SECTOR + sectors - 1:x}"
