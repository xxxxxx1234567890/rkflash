from rkflash.env_check import env_check


def test_env_check_shape(monkeypatch):
    monkeypatch.setattr("rkflash.env_check.sys.platform", "win32")
    result = env_check()
    assert set(result) == {"platform", "rockusb_driver_ok", "udev_ok", "devices_ok", "hints"}
