import argparse
import sys

from . import __version__
from .errors import RkFlashError
from .output import emit_json, emit_progress, fail

SUBCOMMANDS = [
    "devices", "flash", "upgrade", "boot-loader",
    "erase", "info", "reset", "storage", "export",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rkflash", description="Rockchip USB flashing engine")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--dry-run", action="store_true", help="只规划，不执行")
    sub = p.add_subparsers(dest="command", required=True)
    for name in SUBCOMMANDS:
        sub.add_parser(name, help=f"{name} (TODO)")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    emit_progress(f"[rkflash] command={args.command} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
