"""CLI 接线测试（M4-B）：export/erase/storage/flash/upgrade 走 mock。"""
import json

from rkflash.cli import main


def _run(args):
    return main(["--transport", "mock"] + args)


def test_export_writes_file(tmp_path, capsys):
    out = tmp_path / "dump.img"
    assert _run(["export", "--path", "mock:0", "--lba", "0x40:2", "--out", str(out)]) == 0
    assert out.read_bytes() == b"\x00" * 1024


def test_erase_requires_confirmation(capsys):
    assert _run(["erase", "--lba", "0x40:1"]) != 0
    assert "CONFIRM_REQUIRED" in capsys.readouterr().err


def test_erase_with_yes(capsys):
    assert _run(["erase", "--lba", "0x40:1", "--yes"]) == 0
    assert json.loads(capsys.readouterr().out)["erased"]["start"] == 0x40


def test_storage_query_and_switch(capsys):
    assert _run(["storage", "--path", "mock:0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "name" in out


def test_flash_dry_run_no_device(capsys):
    # dry-run 不应打开/写设备
    assert _run(["--dry-run", "flash", "--part", "uboot=no.img"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_flash_requires_confirm_without_yes(capsys):
    assert _run(["flash", "--part", "uboot=no.img"]) != 0
    assert "CONFIRM_REQUIRED" in capsys.readouterr().err
