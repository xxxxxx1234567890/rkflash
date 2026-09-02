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


def _write_gpt_if_needed(dev, images, flash_sectors: int) -> bool:
    """images 中若有 TYPE:GPT 的 parameter 文件则建表写 GPT + parameter@0x2000。"""
    gpt_param = None
    for img in images:
        try:
            with open(img.path, "rb") as f:
                head = f.read(4096)
        except OSError:
            continue
        if head.startswith(b"PARM") and b"TYPE: GPT" in head:
            gpt_param = img
            break
    if gpt_param is None:
        return False
    parts = parse_partitions(open(gpt_param.path, "rb").read())
    if not parts:
        return False
    tables = build_gpt_tables(parts, flash_sectors)
    # primary 自 LBA0；parameter(PARM payload)固定落 0x2000；backup 落尾部
    for i in range(0, len(tables.primary), SECTOR_SIZE):
        dev.write_lba(i // SECTOR_SIZE, tables.primary[i:i + SECTOR_SIZE])
    _write_parameter(dev, gpt_param.path, FIRMWARE_PARAMETER_START_SECTOR)
    for i in range(0, len(tables.backup), SECTOR_SIZE):
        dev.write_lba(tables.backup_start_sector + i // SECTOR_SIZE,
                      tables.backup[i:i + SECTOR_SIZE])
    return True


def _write_parameter(dev, param_path: str, lba: int) -> None:
    """parameter 文件（含 PARM 头）按原样写入固定地址（对齐上游持久化 PARM 块）。"""
    with open(param_path, "rb") as f:
        payload = f.read()
    n = (len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE
    padded = payload + b"\x00" * (n * SECTOR_SIZE - len(payload))
    dev.write_lba(lba, padded)


def run_upgrade_images(dev, images, loader_path, no_reset=False) -> str:
    flash_sectors = _flash_sectors(dev)
    lines = []
    if loader_path:
        lines.append(write_loader_idblock(dev, loader_path, flash_sectors))
    wrote_gpt = _write_gpt_if_needed(dev, images, flash_sectors)
    for img in images:
        # GPT 分支已处理 parameter；普通 parameter/其余正常烧
        from .download import write_firmware_image
        if wrote_gpt and _is_gpt_param(img):
            continue
        lines.append(write_firmware_image(dev, img, flash_sectors))
    if not no_reset:
        dev.reset()
        lines.append("Reset Device Success")
    lines.append("Firmware upgrade succeeded")
    return "\n".join(lines)


def _is_gpt_param(img) -> bool:
    try:
        with open(img.path, "rb") as f:
            head = f.read(64)
    except OSError:
        return False
    return head.startswith(b"PARM") and b"TYPE: GPT" in head


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
