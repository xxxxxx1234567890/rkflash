"""环境检查：驱动/权限/设备就绪状态。"""
import sys


def env_check(platform: str | None = None) -> dict:
    platform = platform or sys.platform
    result = {"platform": platform, "rockusb_driver_ok": None,
              "udev_ok": None, "devices_ok": False, "hints": []}
    if platform == "win32":
        result["rockusb_driver_ok"] = _rockusb_driver_ok()
        if not result["rockusb_driver_ok"]:
            result["hints"].append("安装 Rockchip DriverAssistant 并重插设备（须绑定 Rockusb 驱动）")
    else:
        result["udev_ok"] = _udev_rules_ok()
        if not result["udev_ok"]:
            result["hints"].append("安装 udev 规则：sudo cp packaging/linux/99-rkdevtool-rockchip.rules /lib/udev/rules.d/ && sudo udevadm control --reload-rules")
    from .device import list_devices
    try:
        result["devices_ok"] = len(list_devices()) > 0
    except Exception as e:  # noqa: BLE001
        result["hints"].append(f"设备枚举失败：{e}")
    return result


def _rockusb_driver_ok() -> bool:
    # Windows：SetupAPI 枚举时 service=="rockusb" 的设备存在即 OK
    from .transport.windows_rockusb import list_devices as _ld
    try:
        return any(True for _ in _ld())
    except Exception:  # noqa: BLE001
        return False


def _udev_rules_ok() -> bool:
    import os
    for p in ("/lib/udev/rules.d/99-rkdevtool-rockchip.rules",
              "/etc/udev/rules.d/99-rkdevtool-rockchip.rules"):
        if os.path.exists(p):
            return True
    return False
