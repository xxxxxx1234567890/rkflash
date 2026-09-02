"""传输层统一接口。

任何传输（Windows Rockusb / Linux libusb / mock）须实现：
- bulk_write(data: bytes) -> None
- bulk_read(n: int) -> bytes
- control_transfer(request_type: int, request: int, value: int, index: int, data: bytes) -> bytes
"""
