from rkflash.env_check import env_check


def test_env_check_shape(monkeypatch):
    monkeypatch.setattr("rkflash.env_check.sys.platform", "win32")
    result = env_check()
    assert set(result) == {"platform", "rockusb_driver_ok", "udev_ok", "devices_ok", "hints"}


def test_udev_rules_ok_detects_repo_fallback():
    # 系统目录无规则时，仓库内 packaging/linux/ 的规则文件也应被识别
    import rkflash.env_check as ec
    assert ec._udev_rules_ok() is True


def test_env_check_hint_when_no_devices_but_driver_ok(monkeypatch):
    import rkflash.device as device_mod
    import rkflash.transport.windows_rockusb as wmod
    monkeypatch.setattr(wmod, "list_devices", lambda: [])
    monkeypatch.setattr(device_mod, "list_devices", lambda transport="auto": [])
    result = env_check("win32")
    assert result["rockusb_driver_ok"] is True
    assert result["devices_ok"] is False
    assert any("Maskrom/Loader" in h for h in result["hints"])


def test_env_check_no_hint_when_driver_check_fails(monkeypatch):
    import rkflash.device as device_mod
    import rkflash.transport.windows_rockusb as wmod

    def boom():
        raise RuntimeError("SetupDiGetClassDevsW: Win32 error 1")
    monkeypatch.setattr(wmod, "list_devices", boom)
    monkeypatch.setattr(device_mod, "list_devices", boom)
    result = env_check("win32")
    assert result["rockusb_driver_ok"] is False
    assert not any("Maskrom/Loader" in h for h in result["hints"])
