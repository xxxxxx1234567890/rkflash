"""完整固件升级编排（对齐 device_ops upgrade_firmware 1607-1691）。

顺序：解包 → (Maskrom 则 download_boot + 等 Loader) → 读 flash → 写 Loader
IDBlock → GPT(若 TYPE:GPT parameter) 先建表 → 逐分区写（含 parameter@0x2000）
→ 非 no_reset 时 reset。

dev_factory：每次调用重新打开当前设备（Maskrom→Loader 重枚举后换句柄）。
"""
import os
import struct
import tempfile

from ..firmware.afptool import unpack_firmware
from ..firmware.parameter import (SECTOR_SIZE, build_gpt_tables,
                                  parse_partitions)
from .loader import (download_boot, wait_for_loader, write_loader_idblock)

FIRMWARE_PARAMETER_START_SECTOR = 0x2000


def _flash_sectors(dev) -> int:
    data = dev.flash_info()
    if len(data) < 4:
        raise IOError("flash reports bad info")
    sectors = struct.unpack_from("<I", data, 0)[0]
    if sectors == 0:
        raise IOError("flash reports 0 sectors")
    return sectors


def _parameter_kind(img) -> str | None:
    """读 parameter 镜像首段：返回 'gpt' / 'legacy' / None(非 parameter)。

    对齐上游 firmware_write_target 语义：parameter 镜像（内容以 PARM 起始）
    无条件写往固定 0x2000，绝不按其声明的 flash_offset（legacy 常为 0）落盘。
    """
    try:
        with open(img.path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if not head.startswith(b"PARM"):
        return None
    return "gpt" if b"TYPE: GPT" in head else "legacy"


def _write_parameter(dev, param_path: str, lba: int) -> None:
    """parameter 文件（含 PARM 头）按原样写入固定地址（对齐上游持久化 PARM 块）。"""
    with open(param_path, "rb") as f:
        payload = f.read()
    n = (len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE
    padded = payload + b"\x00" * (n * SECTOR_SIZE - len(payload))
    dev.write_lba(lba, padded)


def _is_nand(dev) -> bool:
    """flash_info 块大小扇区>1 → NAND 类（需要擦除粒度，官方亦写 GPT）。"""
    from .loader import _nand_block_sectors
    return _nand_block_sectors(dev) > 1


def run_upgrade_images(dev, images, loader_path, no_reset=False) -> str:
    flash_sectors = _flash_sectors(dev)
    nand = _is_nand(dev)
    lines = []
    if loader_path:
        lines.append(write_loader_idblock(dev, loader_path, flash_sectors))

    gpt_written = False
    for img in images:
        kind = _parameter_kind(img)
        if kind is None:
            continue
        parts = parse_partitions(open(img.path, "rb").read())
        # NAND 板或 TYPE:GPT 参数 → 建 GPT（官方 NAND 布局即 GPT，实测验证）。
        # 分区信息已编码进 GPT 条目，不再单独落 PARM 块（避免与 uboot@0x2000 冲突）。
        if parts and (kind == "gpt" or nand) and not gpt_written:
            tables = build_gpt_tables(parts, flash_sectors)
            for i in range(0, len(tables.primary), SECTOR_SIZE):
                dev.write_lba(i // SECTOR_SIZE,
                              tables.primary[i:i + SECTOR_SIZE])
            for i in range(0, len(tables.backup), SECTOR_SIZE):
                dev.write_lba(tables.backup_start_sector + i // SECTOR_SIZE,
                              tables.backup[i:i + SECTOR_SIZE])
            gpt_written = True
        else:
            # legacy 无 GPT：parameter 重映射固定 0x2000（上游 firmware_write_target）
            _write_parameter(dev, img.path, FIRMWARE_PARAMETER_START_SECTOR)
        lines.append(f"written parameter to LBA 0x{FIRMWARE_PARAMETER_START_SECTOR:x}")

    for img in images:
        if _parameter_kind(img) is not None:
            continue  # parameter 已在上面统一处理
        from .download import write_firmware_image
        lines.append(write_firmware_image(dev, img, flash_sectors))
    if not no_reset:
        dev.reset()
        lines.append("Reset Device Success")
    lines.append("Firmware upgrade succeeded")
    return "\n".join(lines)


def run_upgrade(dev_factory, update_img: str, no_reset=False, is_maskrom=False,
                out_dir: str | None = None) -> str:
    """整包升级：解包 → 装 Loader(GPT/加载)→ 逐分区 → reset。返回日志。"""
    tmp = out_dir or tempfile.mkdtemp(prefix="rkflash-upgrade-")
    try:
        unpacked = unpack_firmware(update_img, tmp)
        if is_maskrom:
            if not unpacked.loader_path:
                raise ValueError("firmware has no Loader for Maskrom boot")
            dev = dev_factory()
            download_boot(dev, unpacked.loader_path)
            dev = dev_factory()
            if not wait_for_loader(dev):
                raise IOError("loader did not become ready after Maskrom boot")
        else:
            dev = dev_factory()
        return run_upgrade_images(dev, unpacked.images,
                                  unpacked.loader_path, no_reset)
    finally:
        if out_dir is None:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
