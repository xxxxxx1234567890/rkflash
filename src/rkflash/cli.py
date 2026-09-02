import argparse
import os
import sys

from . import __version__
from .device import RockDevice, list_devices, open_device
from .errors import RkFlashError
from .output import emit_json, emit_progress, fail

SUBCOMMANDS = ["devices", "flash", "upgrade", "boot-loader",
               "erase", "info", "reset", "test", "storage", "export"]

RESET_OPCODES = {"reset": 0, "msc": 1, "poweroff": 2, "maskrom": 3, "disconnect": 4}


def _transport() -> str:
    return os.environ.get("RKFLASH_TRANSPORT", "auto")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rkflash", description="Rockchip USB flashing engine")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--dry-run", action="store_true", help="只规划，不执行")
    p.add_argument("--transport", default="auto", choices=["auto", "mock", "windows", "linux"],
                   help="传输层（默认 auto 按平台选择）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出在线 Rockchip 设备")

    for name in ("flash", "upgrade", "boot-loader", "erase", "storage", "export"):
        sub.add_parser(name, help=f"{name} (M3/M4 接线)")

    info = sub.add_parser("info", help="读取芯片/Flash/Capability 信息")
    info.add_argument("--path", help="设备路径（多设备时必填）")

    reset = sub.add_parser("reset", help="重启设备")
    reset.add_argument("--path", help="设备路径（多设备时必填）")
    reset.add_argument("--opcode", default="reset", choices=sorted(RESET_OPCODES),
                       help="复位类型（默认 reset）")

    test = sub.add_parser("test", help="Test Unit Ready 就绪探测")
    test.add_argument("--path", help="设备路径（多设备时必填）")

    sub.add_parser("env-check", help="环境检查（驱动/udev/设备就绪）")
    return p


def _open_or_fail(args) -> RockDevice:
    path = getattr(args, "path", None)
    if not path:
        devs = list_devices(_transport() if args.transport == "auto" else args.transport)
        if len(devs) != 1:
            raise RkFlashError("DEVICE_AMBIGUOUS", "multiple/no devices; specify --path",
                               "run `rkflash devices` and pass --path")
        path = devs[0].path
    return open_device(path, args.transport)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    transport = args.transport if args.transport != "auto" else _transport()
    if args.command == "env-check":
        from .env_check import env_check
        emit_json(env_check())
        return 0
    if args.command == "devices":
        try:
            emit_json([vars(d) for d in list_devices(transport)])
            return 0
        except RkFlashError as e:
            return fail(e.code, e.message, e.action_hint)
    try:
        dev = _open_or_fail(args)
    except RkFlashError as e:
        return fail(e.code, e.message, e.action_hint)
    if args.command == "info":
        emit_json({"chip": dev.chip_info().decode("latin-1"),
                   "flash_id": dev.flash_id().decode("latin-1"),
                   "flash_info": dev.flash_info().hex(),
                   "capability": dev.capability().hex(),
                   "storage": dev.storage().hex()})
        return 0
    if args.command == "test":
        dev.test_unit_ready()
        emit_json({"ready": True})
        return 0
    if args.command == "reset":
        dev.reset(RESET_OPCODES[args.opcode])
        emit_json({"reset": args.opcode})
        return 0
    emit_progress(f"[rkflash] command={args.command} dry_run={args.dry_run} (M3/M4 接线)")
    dev.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
