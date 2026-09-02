import json

import pytest

from rkflash.cli import main

NOT_IMPLEMENTED = ["flash", "upgrade", "boot-loader", "erase", "storage", "export"]


def test_devices_smoke(capsys):
    # 冒烟走 mock 传输层，不做真实枚举；真实接线在 M3/M4
    rc = main(["--transport", "mock", "devices"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["path"].startswith("mock:")
    assert out[0]["location"] is None


def test_version_flag():
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_devices_mock(monkeypatch):
    monkeypatch.setenv("RKFLASH_TRANSPORT", "mock")
    rc = main(["devices"])
    assert rc == 0


def test_info_mock(capsys):
    rc = main(["--transport", "mock", "info", "--path", "mock:0"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # 统一 hex 输出：chip/flash_id 也是十六进制串
    assert out["chip"] == "33353838000000000000000000000000"
    assert out["flash_id"] == "7878787878"
    assert out["flash_info"].startswith("0000")
    assert set(out) == {"chip", "flash_id", "flash_info", "capability", "storage"}


def test_reset_mock():
    rc = main(["--transport", "mock", "reset", "--path", "mock:0"])
    assert rc == 0


def test_test_mock():
    rc = main(["--transport", "mock", "test", "--path", "mock:0"])
    assert rc == 0


@pytest.mark.parametrize("command", NOT_IMPLEMENTED)
def test_unimplemented_commands_fail_before_opening_device(command, capsys, monkeypatch):
    # NOT_IMPLEMENTED 必须在任何设备打开之前返回（mock 路径也不许碰）
    monkeypatch.setattr("rkflash.cli.open_device",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open")))
    rc = main([command])
    assert rc != 0
    err = capsys.readouterr().err
    assert "NOT_IMPLEMENTED" in err


def test_reset_dry_run_does_not_touch_device(capsys, monkeypatch):
    monkeypatch.setattr("rkflash.cli.open_device",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open")))
    rc = main(["--transport", "mock", "reset", "--dry-run",
               "--path", "mock:0", "--opcode", "maskrom"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"dry_run": True, "command": "reset", "path": "mock:0", "opcode": "maskrom"}


def test_reset_opcode_choices_from_enum():
    from rkflash.protocol.command_block import ResetOpcode
    for op in ResetOpcode:
        rc = main(["--transport", "mock", "reset", "--dry-run",
                   "--path", "mock:0", "--opcode", op.name.lower()])
        assert rc == 0


def test_internal_error_wrapped_without_traceback(capsys, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("exploded unexpectedly")
    monkeypatch.setattr("rkflash.cli.list_devices", boom)
    rc = main(["devices"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "INTERNAL" in captured.err
    assert "exploded unexpectedly" in captured.err
    assert "Traceback" not in captured.err


def test_wired_commands_close_device(monkeypatch):
    closed = []
    real_open = __import__("rkflash.cli", fromlist=["open_device"]).open_device

    def open_and_track(*a, **k):
        dev = real_open(*a, **k)
        monkeypatch.setattr(dev, "close", lambda: closed.append(True))
        return dev

    monkeypatch.setattr("rkflash.cli.open_device", open_and_track)
    for command in (["info", "--path", "mock:0"],
                    ["test", "--path", "mock:0"],
                    ["reset", "--path", "mock:0"]):
        closed.clear()
        assert main(["--transport", "mock"] + command) == 0
        assert closed == [True]
