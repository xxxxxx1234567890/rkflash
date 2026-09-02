import pytest

import rkflash.transport.windows_rockusb as w


def test_pid_from_instance_id():
    assert w.pid_from_instance_id("USB\\VID_2207&PID_330A\\abcdef") == 0x330A
    with pytest.raises(ValueError):
        w.pid_from_instance_id("USB\\VID_1234\\abcdef")


def test_infer_mode_known_pid():
    # 判别性断言，逐字对齐 rockusb windows.rs:339-348 的 infer_mode 启发式
    assert w.infer_mode(0x330C) == "Maskrom"
    assert w.infer_mode(0x300A) == "Maskrom"
    assert w.infer_mode(0x330A) == "Loader"
    assert w.infer_mode(0x350A) == "Loader"
    assert w.infer_mode(0x320C) == "Maskrom"
