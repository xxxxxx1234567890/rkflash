import argparse
import os
import sys
import time

from . import __version__
from .device import RockDevice, list_devices, open_device
from .errors import RkFlashError
from .output import emit_json, emit_progress, fail
from .protocol.command_block import ResetOpcode


def _transport() -> str:
    return os.environ.get("RKFLASH_TRANSPORT", "auto")


def _add_path(p: argparse.ArgumentParser) -> None:
    p.add_argument("--path", help="设备路径（多设备时必填）")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rkflash", description="Rockchip USB flashing engine")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--dry-run", action="store_true",
                   help="只规划/演示，不执行破坏性操作")
    p.add_argument("--transport", default="auto", choices=["auto", "mock", "windows", "linux"],
                   help="传输层（默认 auto 按平台选择）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出在线 Rockchip 设备")

    info = sub.add_parser("info", help="读取芯片/Flash/Capability 信息（只读）")
    _add_path(info)
    test = sub.add_parser("test", help="Test Unit Ready 就绪探测（只读）")
    _add_path(test)

    reset = sub.add_parser("reset", help="重启设备")
    _add_path(reset)
    reset.add_argument("--opcode", default="reset",
                       choices=[op.name.lower() for op in ResetOpcode],
                       help="复位类型（默认 reset）")

    boot = sub.add_parser("boot-loader", help="Maskrom 模式下载 Loader（救砖）")
    _add_path(boot)
    boot.add_argument("loader", help="Loader 文件（MiniLoaderAll.bin / download.bin）")

    flash = sub.add_parser("flash", help="分区/按地址烧写（破坏性）")
    _add_path(flash)
    flash.add_argument("--part", action="append", default=[],
                       metavar="NAME=PATH",
                       help="分区名=镜像路径（可多次；NAME 可为 lba:ADDR 或 parameter）")
    flash.add_argument("--loader", help="先下载 Loader（Maskrom 救砖流程）")
    flash.add_argument("--yes", action="store_true", help="确认执行（跳过二次确认）")

    up = sub.add_parser("upgrade", help="整包固件升级（破坏性）")
    _add_path(up)
    up.add_argument("update_img", help="update.img 文件")
    up.add_argument("--no-reset", action="store_true", help="升级后不重启")
    up.add_argument("--yes", action="store_true", help="确认执行（跳过二次确认）")

    erase = sub.add_parser("erase", help="擦除 LBA 区间（破坏性）")
    _add_path(erase)
    erase.add_argument("--lba", required=True, metavar="START:COUNT",
                       help="起始扇区:扇区数")
    erase.add_argument("--yes", action="store_true")

    export = sub.add_parser("export", help="导出 LBA 区间到文件（只读）")
    _add_path(export)
    export.add_argument("--lba", required=True, metavar="START:COUNT")
    export.add_argument("--out", required=True, help="输出文件")

    storage = sub.add_parser("storage", help="查询/切换存储介质")
    _add_path(storage)
    storage.add_argument("--set", metavar="NAME", help="切换（如 emmc / spi_nand）")

    sub.add_parser("env-check", help="环境检查（驱动/udev/设备就绪）")
    return p


def _resolve(transport: str, path: str | None) -> RockDevice:
    if not path:
        devs = list_devices(transport)
        if len(devs) != 1:
            raise RkFlashError("DEVICE_AMBIGUOUS", "multiple/no devices; specify --path",
                               "run `rkflash devices` and pass --path")
        path = devs[0].path
    return open_device(path, transport)


def _lba_pair(spec: str) -> tuple[int, int]:
    try:
        start, count = spec.split(":", 1)
        start, count = int(start, 0), int(count, 0)
        if count <= 0:
            raise ValueError("count must be positive")
        return start, count
    except ValueError as e:
        raise RkFlashError("BAD_ARGS",
                           f"invalid --lba '{spec}' (need START:COUNT, count>0)", "") from e


def _wait_loader_device(transport: str, tries: int = 60) -> RockDevice:
    """Maskrom 下载 Loader 后设备会重枚举为 Loader：轮询重开直到 TestUnitReady 通过。"""
    import time
    for _ in range(tries):
        for d in list_devices(transport):
            try:
                dev = open_device(d.path, transport)
                dev.test_unit_ready()
                return dev
            except Exception:  # noqa: BLE001
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(0.25)
    raise RkFlashError("DEVICE_LOST",
                       "loader did not reappear after Maskrom boot",
                       "确认板子已进入 Loader 模式后重试 `rkflash devices`")


def _cmd(dev: RockDevice, args) -> int:
    if args.command == "info":
        emit_json({"chip": dev.chip_info().hex(), "flash_id": dev.flash_id().hex(),
                   "flash_info": dev.flash_info().hex(), "capability": dev.capability().hex(),
                   "storage": dev.storage().hex()})
        return 0
    if args.command == "test":
        dev.test_unit_ready()
        emit_json({"ready": True})
        return 0
    if args.command == "reset":
        dev.reset(ResetOpcode[args.opcode.upper()])
        emit_json({"reset": args.opcode})
        return 0
    if args.command == "boot-loader":
        from .flashing.loader import download_boot, wait_for_loader
        if args.dry_run:
            emit_json({"dry_run": True, "command": "boot-loader", "loader": args.loader})
            return 0
        log = download_boot(dev, args.loader)
        emit_progress(log)
        emit_json({"loader": args.loader, "maskrom_boot": True})
        return 0
    if args.command == "flash":
        if not args.part:
            raise RkFlashError("BAD_ARGS", "flash 需要至少一个 --part NAME=PATH", "")
        if not (args.dry_run or args.yes):
            raise RkFlashError("CONFIRM_REQUIRED",
                               "flash 会覆盖设备分区，需 --yes 确认", "加 --yes 确认执行")
        from .flashing.download import run_download
        from .flashing.lba import read_device_partitions
        targets = []
        for item in args.part:
            name, _, path = item.partition("=")
            if not path:
                raise RkFlashError("BAD_ARGS", f"--part 需要 NAME=PATH: {item}", "")
            targets.append((name.strip(), path))
        if args.dry_run:
            emit_json({"dry_run": True, "command": "flash", "parts": targets})
            return 0
        worker = dev
        try:
            if args.loader:
                # Maskrom：先载入 Loader，设备会重枚举——必须关旧句柄、等新 Loader 重开
                from .flashing.loader import download_boot
                emit_progress(download_boot(dev, args.loader))
                dev.close()
                worker = _wait_loader_device(
                    args.transport if args.transport != "auto" else _transport())
            parts = {p.name.lower(): p for p in read_device_partitions(worker)}
            from .flashing.device_ops import flash_sectors
            fs = flash_sectors(worker)
            emit_progress(run_download(worker, parts, targets, fs))
            emit_json({"flashed": [t[0] for t in targets]})
            return 0
        finally:
            if worker is not dev:
                worker.close()
    if args.command == "upgrade":
        if not (args.dry_run or args.yes):
            raise RkFlashError("CONFIRM_REQUIRED",
                               "upgrade 会覆盖整机，需 --yes 确认", "加 --yes 确认执行")
        from .flashing.upgrade import run_upgrade_images
        from .flashing.afptool import unpack_firmware
        import tempfile
        tmp = tempfile.mkdtemp(prefix="rkflash-upgrade-")
        try:
            unpacked = unpack_firmware(args.update_img, tmp)
            log = run_upgrade_images(dev, unpacked.images, unpacked.loader_path,
                                     no_reset=args.no_reset)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        emit_progress(log)
        emit_json({"upgraded": args.update_img, "reset": not args.no_reset})
        return 0
    if args.command == "erase":
        if not args.yes:
            raise RkFlashError("CONFIRM_REQUIRED", "erase 会清除数据，需 --yes 确认",
                               "加 --yes 确认执行")
        first, count = _lba_pair(args.lba)
        if args.dry_run:
            emit_json({"dry_run": True, "command": "erase", "lba": (first, count)})
            return 0
        from .flashing.device_ops import erase_range
        erase_range(dev, first, count)
        emit_json({"erased": {"start": first, "count": count}})
        return 0
    if args.command == "export":
        first, count = _lba_pair(args.lba)
        from .flashing.device_ops import export_image
        emit_progress(export_image(dev, first, count, args.out))
        emit_json({"exported": args.out, "start": first, "count": count})
        return 0
    if args.command == "storage":
        from .flashing.device_ops import query_storage, switch_storage
        if args.set:
            emit_json({"set": args.set, **switch_storage(dev, args.set)})
        else:
            emit_json(query_storage(dev))
        return 0
    raise RkFlashError("INTERNAL", f"unhandled command {args.command}", "")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    transport = args.transport if args.transport != "auto" else _transport()
    try:
        if args.command == "env-check":
            from .env_check import env_check
            emit_json(env_check())
            return 0
        if args.command == "devices":
            emit_json([vars(d) for d in list_devices(transport)])
            return 0
        if args.dry_run and args.command in ("reset", "flash", "erase", "upgrade"):
            plan = {"dry_run": True, "command": args.command}
            if args.command == "reset":
                plan["opcode"] = args.opcode
            elif args.command == "flash":
                plan["parts"] = [tuple(x.split("=", 1)) for x in args.part]
            elif args.command == "erase":
                plan["lba"] = _lba_pair(args.lba)
            else:
                plan["update_img"] = args.update_img
            emit_json(plan)
            return 0
        dev = _resolve(transport, getattr(args, "path", None))
        try:
            return _cmd(dev, args)
        finally:
            dev.close()
    except RkFlashError as e:
        return fail(e.code, e.message, e.action_hint)
    except Exception as e:  # noqa: BLE001
        return fail("INTERNAL", str(e), "查看上方 stderr 日志；若是设备问题先跑 env-check")


if __name__ == "__main__":
    sys.exit(main())
