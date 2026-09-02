import json

import pytest

from rkflash.cli import main


def test_devices_smoke(capsys):
    rc = main(["--transport", "mock", "devices"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["path"].startswith("mock:")
    assert out[0]["location"] is None


def test_version_flag():
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_info_mock(capsys):
    rc = main(["--transport", "mock", "info", "--path", "mock:0"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["chip"] == "33353838000000000000000000000000"
    assert out["flash_id"] == "7878787878"
    assert set(out) == {"chip", "flash_id", "flash_info", "capability", "storage"}


def test_reset_mock():
    assert main(["--transport", "mock", "reset", "--path", "mock:0"]) == 0


def test_test_mock():
    assert main(["--transport", "mock", "test", "--path", "mock:0"]) == 0


def test_reset_dry_run_does_not_touch_device(capsys, monkeypatch):
    monkeypatch.setattr("rkflash.cli.open_device",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open")))
    rc = main(["--dry-run", "--transport", "mock", "reset", "--path", "mock:0",
               "--opcode", "maskrom"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and out["opcode"] == "maskrom"


def test_reset_opcode_choices_from_enum():
    from rkflash.protocol.command_block import ResetOpcode
    for op in ResetOpcode:
        rc = main(["--dry-run", "--transport", "mock", "reset",
                   "--path", "mock:0", "--opcode", op.name.lower()])
        assert rc == 0


def test_flash_and_erase_need_confirmation(capsys):
    assert main(["--transport", "mock", "flash", "--part", "uboot=no.img"]) != 0
    assert "CONFIRM_REQUIRED" in capsys.readouterr().err
    assert main(["--transport", "mock", "erase", "--lba", "0x40:1"]) != 0
    assert "CONFIRM_REQUIRED" in capsys.readouterr().err


def test_dry_run_plans_without_touching_device(capsys, monkeypatch):
    monkeypatch.setattr("rkflash.cli.open_device",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not open")))
    rc = main(["--dry-run", "--transport", "mock", "erase", "--lba", "0x40:4"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_internal_error_wrapped_without_traceback(capsys, monkeypatch):
    monkeypatch.setattr("rkflash.cli.list_devices", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("exploded unexpectedly")))
    rc = main(["devices"])
    captured = capsys.readouterr()
    assert rc != 0
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
