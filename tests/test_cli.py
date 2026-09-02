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
