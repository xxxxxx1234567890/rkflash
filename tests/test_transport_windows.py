import pytest

import rkflash.transport.windows_rockusb as w


def test_pid_from_instance_id():
    assert w.pid_from_instance_id("USB\\VID_2207&PID_330A\\abcdef") == 0x330A
    with pytest.raises(ValueError):
        w.pid_from_instance_id("USB\\VID_1234\\abcdef")


def test_infer_mode_known_pid():
    # 常见 Loader 模式 PID（对齐 rockusb windows.rs 的 infer_mode 语义）
    assert w.infer_mode(0x330A) in ("Loader", "Maskrom")
    assert w.infer_mode(0x330C) in ("Loader", "Maskrom")
