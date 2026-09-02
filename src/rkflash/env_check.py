"""环境检查：驱动/权限/设备就绪状态。"""
import os
import sys

_RULES_NAME = "99-rkdevtool-rockchip.rules"
_REPO_RULES = os.path.join(os.path.dirname(__file__), "..", "..",
                           "packaging", "linux", _RULES_NAME)


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
            result["hints"].append(
                "安装 udev 规则：sudo cp packaging/linux/99-rkdevtool-rockchip.rules "
                "/lib/udev/rules.d/ && sudo udevadm control --reload-rules"
                "（规则文件已随本仓库提供，见 packaging/linux/）")
    from .device import list_devices
    try:
        result["devices_ok"] = len(list_devices()) > 0
    except Exception as e:  # noqa: BLE001
        result["hints"].append(f"设备枚举失败：{e}")
    driver_ok = result["rockusb_driver_ok"] if platform == "win32" else result["udev_ok"]
    if not result["devices_ok"] and driver_ok:
        result["hints"].append("驱动已装，未检测到设备——请进入 Maskrom/Loader 模式")
    return result


def _rockusb_driver_ok() -> bool:
    # Windows：SetupAPI 枚举调用成功即视为驱动已装（与 devices_ok=枚举非空区分）
    from .transport.windows_rockusb import list_devices as _ld
    try:
        _ld()
        return True
    except Exception:  # noqa: BLE001
        return False


def _udev_rules_ok() -> bool:
    candidates = ("/lib/udev/rules.d/" + _RULES_NAME,
                  "/etc/udev/rules.d/" + _RULES_NAME,
                  # 仓库内自带规则的相对路径回退（未安装到系统时仍可识别）
                  _REPO_RULES)
    return any(os.path.exists(p) for p in candidates)
