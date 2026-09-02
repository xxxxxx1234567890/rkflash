import argparse
import os
import sys

from . import __version__
from .device import RockDevice, list_devices, open_device
from .errors import RkFlashError
from .output import emit_json, emit_progress, fail
from .protocol.command_block import ResetOpcode

# M3/M4 接线的子命令：在打开设备之前一律返回 NOT_IMPLEMENTED
NOT_IMPLEMENTED_COMMANDS = ("flash", "upgrade", "boot-loader",
                            "erase", "storage", "export")


def _transport() -> str:
    return os.environ.get("RKFLASH_TRANSPORT", "auto")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rkflash", description="Rockchip USB flashing engine")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--dry-run", action="store_true", help="只规划，不执行（当前仅 reset 支持）")
    p.add_argument("--transport", default="auto", choices=["auto", "mock", "windows", "linux"],
                   help="传输层（默认 auto 按平台选择）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出在线 Rockchip 设备")

    for name in NOT_IMPLEMENTED_COMMANDS:
        sub.add_parser(name, help=f"{name} (M3/M4 接线)")

    info = sub.add_parser("info", help="读取芯片/Flash/Capability 信息（只读；忽略 --dry-run）")
    info.add_argument("--path", help="设备路径（多设备时必填）")

    reset = sub.add_parser("reset", help="重启设备")
    reset.add_argument("--path", help="设备路径（多设备时必填）")
    reset.add_argument("--opcode", default="reset",
                       choices=[op.name.lower() for op in ResetOpcode],
                       help="复位类型（默认 reset）")
    # default=SUPPRESS：仅在显式给出时覆盖顶层 --dry-run（两种位置都可用）
    reset.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                       help="只规划，不碰设备")

    test = sub.add_parser("test", help="Test Unit Ready 就绪探测（只读；忽略 --dry-run）")
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


def _run_wired(dev: RockDevice, args) -> int:
    """已接线命令的执行体；由调用方保证 dev.close()。"""
    if args.command == "info":
        emit_json({"chip": dev.chip_info().hex(),
                   "flash_id": dev.flash_id().hex(),
                   "flash_info": dev.flash_info().hex(),
                   "capability": dev.capability().hex(),
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
    raise RkFlashError("INTERNAL", f"unhandled command {args.command}",
                       "这是 rkflash 的 bug，请上报")


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
        if args.command in NOT_IMPLEMENTED_COMMANDS:
            return fail("NOT_IMPLEMENTED",
                        f"command '{args.command}' is not wired yet (planned M3/M4)",
                        "先用 info/test/verify 设备连通性；烧写功能在 M3/M4 接线")
        if args.command == "reset" and args.dry_run:
            emit_json({"dry_run": True, "command": "reset",
                       "path": getattr(args, "path", None), "opcode": args.opcode})
            return 0
        dev = _open_or_fail(args)
        try:
            return _run_wired(dev, args)
        finally:
            dev.close()
    except RkFlashError as e:
        return fail(e.code, e.message, e.action_hint)
    except Exception as e:  # noqa: BLE001
        return fail("INTERNAL", str(e),
                    "查看上方 stderr 日志；若是设备问题先跑 env-check")


if __name__ == "__main__":
    sys.exit(main())
