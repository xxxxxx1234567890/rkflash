"""Windows：纯 ctypes 经官方 Rockusb 驱动通信（对齐 rockusb windows.rs）。

驱动要求：设备必须绑定 Rockchip Rockusb 驱动（非 WinUSB/ADB）。驱动暴露
GUID_DEVINTERFACE_USB_DEVICE，bulk 走 \\\\pipe00/\\\\pipe01 文件 I/O，
Maskrom 写走两个 vendor IOCTL。
"""
import ctypes
import ctypes.wintypes as wt
import re
from ctypes import wintypes

from . import DeviceInfo

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _GUID(ctypes.Structure):
    # Python 3.13 的 ctypes.wintypes 不再提供 GUID，自定义同布局结构
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


# 同上：Python 3.13 的 wintypes 缺失 ULONG_PTR
if not hasattr(wt, "ULONG_PTR"):
    wt.ULONG_PTR = ctypes.c_size_t


# ---- 常量 ----
GUID_DEVINTERFACE_USB_DEVICE = _GUID(
    0xA5DCBF10, 0x6530, 0x11D2,
    (ctypes.c_ubyte * 8)(0xAC, 0x2F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
SPDRP_SERVICE = 0x11
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
IOCTL_MASKROM_WRITE_471 = 0x8000A000
IOCTL_MASKROM_WRITE_472 = 0x8000A004
ROCKUSB_SERVICE = "rockusb"
VID_RE = re.compile(r"VID_2207&PID_([0-9A-Fa-f]{4})", re.I)


def pid_from_instance_id(instance_id: str) -> int:
    m = VID_RE.search(instance_id)
    if not m:
        raise ValueError(f"not a Rockchip VID_2207 instance: {instance_id}")
    return int(m.group(1), 16)


def infer_mode(pid: int) -> str:
    # 对齐 rockusb windows.rs:339-348：Maskrom PID 常见 0x?0c 形态；
    # RK3568 Maskrom 枚举为 0x300a（其 Loader PID 为 0x350a）。
    if pid & 0xF == 0xC or pid == 0x300A:
        return "Maskrom"
    return "Loader"


# ---- SetupAPI 结构 ----
class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("InterfaceClassGuid", _GUID),
                ("Flags", wt.DWORD), ("Reserved", wt.ULONG_PTR)]


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("ClassGuid", _GUID),
                ("DevInst", wt.DWORD), ("Reserved", wt.ULONG_PTR)]


class _SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
    # DevicePath 为变长数组，仅用 1 个 WCHAR 占位；读取用 wstring_at(地址)
    _fields_ = [("cbSize", wt.DWORD), ("DevicePath", wt.WCHAR * 1)]


# ---- 函数原型 ----
SetupDiGetClassDevsW = setupapi.SetupDiGetClassDevsW
SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(_GUID), wintypes.LPCWSTR,
                                 wintypes.HWND, wt.DWORD]
SetupDiGetClassDevsW.restype = ctypes.c_void_p
SetupDiEnumDeviceInterfaces = setupapi.SetupDiEnumDeviceInterfaces
SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA),
                                        ctypes.POINTER(_GUID), wt.DWORD,
                                        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA)]
SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
SetupDiGetDeviceInterfaceDetailW = setupapi.SetupDiGetDeviceInterfaceDetailW
SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ctypes.POINTER(_SP_DEVICE_INTERFACE_DETAIL_DATA), wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.POINTER(_SP_DEVINFO_DATA)]
SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
SetupDiGetDeviceInstanceIdW = setupapi.SetupDiGetDeviceInstanceIdW
SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA),
                                        wintypes.LPWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD)]
SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
SetupDiGetDeviceRegistryPropertyW = setupapi.SetupDiGetDeviceRegistryPropertyW
SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(_SP_DEVINFO_DATA), wt.DWORD, ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(ctypes.c_byte), wt.DWORD, ctypes.POINTER(wt.DWORD)]
SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
SetupDiDestroyDeviceInfoList = setupapi.SetupDiDestroyDeviceInfoList
SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
CreateFileW = kernel32.CreateFileW
CreateFileW.argtypes = [wintypes.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                        wt.DWORD, wt.DWORD, ctypes.c_void_p]
CreateFileW.restype = ctypes.c_void_p
ReadFile = kernel32.ReadFile
ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                     ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
ReadFile.restype = wintypes.BOOL
WriteFile = kernel32.WriteFile
WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                      ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
WriteFile.restype = wintypes.BOOL
DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
                            ctypes.c_void_p]
DeviceIoControl.restype = wintypes.BOOL
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [ctypes.c_void_p]
CloseHandle.restype = wintypes.BOOL


def list_devices():
    """枚举绑定 Rockusb 驱动的 Rockchip(VID_2207) USB 接口。"""
    guid = GUID_DEVINTERFACE_USB_DEVICE
    info_set = ctypes.c_void_p(SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE))
    if not info_set.value:
        return []
    devices = []
    try:
        index = 0
        while True:
            iface = _SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
            if not SetupDiEnumDeviceInterfaces(info_set, None, ctypes.byref(guid),
                                               index, ctypes.byref(iface)):
                break
            index += 1
            dev_info = _SP_DEVINFO_DATA()
            dev_info.cbSize = ctypes.sizeof(_SP_DEVINFO_DATA)
            needed = wt.DWORD(0)
            SetupDiGetDeviceInterfaceDetailW(info_set, ctypes.byref(iface),
                                             None, 0, ctypes.byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value)
            detail = ctypes.cast(buf, ctypes.POINTER(_SP_DEVICE_INTERFACE_DETAIL_DATA))
            # cbSize 按微软要求填结构体大小；若真机枚举失败，尝试 4（仅 DWORD）
            detail.contents.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DETAIL_DATA)
            if not SetupDiGetDeviceInterfaceDetailW(info_set, ctypes.byref(iface),
                                                    detail, needed.value, None,
                                                    ctypes.byref(dev_info)):
                continue
            path = ctypes.wstring_at(ctypes.addressof(detail.contents.DevicePath))
            inst_buf = ctypes.create_unicode_buffer(256)
            SetupDiGetDeviceInstanceIdW(info_set, ctypes.byref(dev_info), inst_buf,
                                        ctypes.sizeof(inst_buf), None)
            instance_id = inst_buf.value
            if "VID_2207" not in instance_id:
                continue
            svc_buf = ctypes.create_unicode_buffer(256)
            SetupDiGetDeviceRegistryPropertyW(
                info_set, ctypes.byref(dev_info), SPDRP_SERVICE, None,
                ctypes.cast(svc_buf, ctypes.POINTER(ctypes.c_byte)),
                ctypes.sizeof(svc_buf), None)
            if svc_buf.value.lower() != ROCKUSB_SERVICE:
                continue
            devices.append(DeviceInfo(path, instance_id,
                                      pid_from_instance_id(instance_id),
                                      infer_mode(pid_from_instance_id(instance_id))))
    finally:
        SetupDiDestroyDeviceInfoList(info_set)
    return devices


def _raise_winerror(operation: str):
    import ctypes as _c
    code = _c.get_last_error()
    raise RuntimeError(f"{operation}: Win32 error {code}")


class WindowsRockusbTransport:
    """Rockusb 驱动句柄封装：bulk 走文件 I/O，Maskrom 写走 DeviceIoControl。"""

    def __init__(self, handle):
        self.handle = handle

    @classmethod
    def open(cls, path: str) -> "WindowsRockusbTransport":
        h = CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING,
                        FILE_ATTRIBUTE_NORMAL, None)
        if h == INVALID_HANDLE_VALUE or not h:
            _raise_winerror(f"CreateFileW({path})")
        return cls(h)

    def bulk_write(self, data):
        written = wt.DWORD(0)
        buf = ctypes.create_string_buffer(data, len(data))
        if not WriteFile(self.handle, buf, len(data), ctypes.byref(written), None):
            _raise_winerror("WriteFile")
        if written.value != len(data):
            raise RuntimeError(f"short write: {written.value}/{len(data)}")

    def bulk_read(self, n):
        out = bytearray()
        while len(out) < n:
            chunk = ctypes.create_string_buffer(n - len(out))
            read = wt.DWORD(0)
            if not ReadFile(self.handle, chunk, n - len(out), ctypes.byref(read), None):
                _raise_winerror("ReadFile")
            if read.value == 0:
                raise RuntimeError(f"short read: {len(out)}/{n} bytes, device closed")
            out += chunk.raw[:read.value]
        return bytes(out)

    def control_transfer(self, request_type, request, value, index, data):
        # Rockusb 驱动仅支持 Maskrom vendor write 0x40/0x0c 到 area 0x471/0x472
        if request_type != 0x40 or request != 0x0C:
            raise RuntimeError(f"unsupported control transfer 0x{request_type:02x}/0x{request:02x}")
        ioctl = {0x471: IOCTL_MASKROM_WRITE_471, 0x472: IOCTL_MASKROM_WRITE_472}.get(index)
        if ioctl is None:
            raise RuntimeError(f"unsupported maskrom area 0x{index:04X}")
        inbuf = ctypes.create_string_buffer(data, len(data))
        outbuf = ctypes.create_string_buffer(64)
        returned = wt.DWORD(0)
        if not DeviceIoControl(self.handle, ioctl, inbuf, len(data),
                               outbuf, ctypes.sizeof(outbuf), ctypes.byref(returned), None):
            _raise_winerror(f"DeviceIoControl(0x{ioctl:08X}, area 0x{index:04X})")
        return outbuf.raw[:returned.value]

    def close(self):
        if self.handle:
            CloseHandle(self.handle)
            self.handle = None
