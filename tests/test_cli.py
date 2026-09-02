import pytest

from rkflash.cli import main


def test_devices_smoke(capsys):
    # 骨架阶段子命令仅打印进度并返回 0；真实接线在 Task 8
    rc = main(["devices"])
    assert rc == 0


def test_version_flag():
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_devices_mock(monkeypatch):
    monkeypatch.setenv("RKFLASH_TRANSPORT", "mock")
    rc = main(["devices"])
    assert rc == 0


def test_info_mock():
    rc = main(["--transport", "mock", "info", "--path", "mock:0"])
    assert rc == 0


def test_reset_mock():
    rc = main(["--transport", "mock", "reset", "--path", "mock:0"])
    assert rc == 0


def test_test_mock():
    rc = main(["--transport", "mock", "test", "--path", "mock:0"])
    assert rc == 0
