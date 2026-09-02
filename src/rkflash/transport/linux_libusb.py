"""Linux：ctypes 直调 libusb-1.0（零 pip 依赖）。

系统依赖：libusb-1.0（apt install libusb-1.0-0）。设备需 udev 规则授权
（VID 0x2207），否则须 sudo。

M2 阶段提供枚举骨架；open/bulk/control 在 Linux 真机阶段补齐
（libusb 调用序列见 _load() 的原型声明）。
"""
import ctypes
import ctypes.util

from . import DeviceInfo

_ROCKCHIP_VID = 0x2207


class _libusb_device_descriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8), ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16), ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8), ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8), ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16), ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8), ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8), ("bNumConfigurations", ctypes.c_uint8)]


def _load():
    """声明 libusb-1.0 原型并返回库句柄（真机阶段使用）。"""
    path = ctypes.util.find_library("usb-1.0") or ctypes.util.find_library("usb")
    if not path:
        raise RuntimeError("libusb-1.0 not found; run: sudo apt install libusb-1.0-0")
    lib = ctypes.CDLL(path)
    lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_init.restype = ctypes.c_int
    lib.libusb_get_device_list.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_get_device_list.restype = ctypes.c_ssize_t
    lib.libusb_free_device_list.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_get_device_descriptor.argtypes = [ctypes.c_void_p,
                                                 ctypes.POINTER(_libusb_device_descriptor)]
    lib.libusb_get_device_descriptor.restype = ctypes.c_int
    lib.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_open.restype = ctypes.c_int
    lib.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_claim_interface.restype = ctypes.c_int
    lib.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_release_interface.restype = ctypes.c_int
    lib.libusb_bulk_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_char_p, ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
    lib.libusb_bulk_transfer.restype = ctypes.c_int
    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint16,
        ctypes.c_uint16, ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint]
    lib.libusb_control_transfer.restype = ctypes.c_int
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_exit.argtypes = [ctypes.c_void_p]
    return lib


def list_devices():
    """枚举 VID 0x2207 的 Rockchip USB 设备（Linux 真机阶段补齐 bus/device 编号）。"""
    lib = _load()
    ctx = ctypes.c_void_p()
    if lib.libusb_init(ctypes.byref(ctx)) != 0:
        raise RuntimeError("libusb_init failed")
    devs = ctypes.c_void_p()
    try:
        n = lib.libusb_get_device_list(ctx, ctypes.byref(devs))
        result = []
        for i in range(n):
            dev = ctypes.cast(
                ctypes.c_void_p(ctypes.cast(devs, ctypes.POINTER(ctypes.c_void_p))[i]),
                ctypes.c_void_p)
            desc = _libusb_device_descriptor()
            if lib.libusb_get_device_descriptor(dev, ctypes.byref(desc)) != 0:
                continue
            if desc.idVendor != _ROCKCHIP_VID:
                continue
            # TODO(真机): 用 libusb_get_bus_number/get_device_address 生成 "bus:device"
            result.append(DeviceInfo(path=f"usb:{i}", instance_id="",
                                     pid=desc.idProduct, mode="Unknown"))
        return result
    finally:
        if devs.value:
            lib.libusb_free_device_list(devs, 1)
        lib.libusb_exit(ctx)


class LinuxLibusbTransport:
    """libusb 句柄封装。open/bulk/control 在 Linux 真机阶段补齐。"""

    def __init__(self, lib, handle, iface, ep_out, ep_in):
        self._lib = lib
        self._handle = handle
        self._iface = iface
        self._ep_out = ep_out
        self._ep_in = ep_in

    @classmethod
    def open(cls, path: str) -> "LinuxLibusbTransport":
        # TODO(真机): 按 path 匹配设备，libusb_open + claim_interface(0) +
        # 从 config descriptor 提取首个 bulk OUT/IN 端点
        raise NotImplementedError("open(): Linux hardware-phase wiring")

    def bulk_write(self, data):
        raise NotImplementedError("bulk_write(): Linux hardware-phase")

    def bulk_read(self, n):
        raise NotImplementedError("bulk_read(): Linux hardware-phase")

    def control_transfer(self, request_type, request, value, index, data):
        raise NotImplementedError("control_transfer(): Linux hardware-phase")

    def close(self):
        if self._handle:
            self._lib.libusb_release_interface(self._handle, self._iface)
            self._lib.libusb_close(self._handle)
            self._handle = None
