"""传输层统一接口。

任何传输（Windows Rockusb / Linux libusb / mock）须实现：
- bulk_write(data: bytes) -> None
- bulk_read(n: int) -> bytes
- control_transfer(request_type: int, request: int, value: int, index: int, data: bytes) -> bytes
"""


class DeviceInfo:
    """平台中立的设备描述（Windows/Linux/mock 共用）。

    location 为 USB 拓扑短位置（如 Windows 的 "1-11-3"），真机阶段填充；
    path 是打开设备的身份标识。
    """

    def __init__(self, path, instance_id, pid, mode, location=None):
        self.path = path
        self.instance_id = instance_id
        self.pid = pid
        self.mode = mode
        self.location = location
