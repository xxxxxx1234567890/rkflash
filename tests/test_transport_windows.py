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


def test_pipe_path_format():
    assert w._pipe_path(r"\\?\usb#vid_2207&pid_350a#1#{guid}", 0) == \
        r"\\?\usb#vid_2207&pid_350a#1#{guid}\pipe00"
    assert w._pipe_path(r"\\?\usb#vid_2207&pid_350a#1#{guid}", 1) == \
        r"\\?\usb#vid_2207&pid_350a#1#{guid}\pipe01"


def _fake_createfile(sequence):
    """按序列返回句柄；None 表示失败（INVALID_HANDLE_VALUE）。"""
    calls = iter(sequence)

    def fake(path, access, *args, **kwargs):
        result = next(calls)
        if result is None:
            w.ctypes.set_last_error(2)  # ERROR_FILE_NOT_FOUND
            return w.INVALID_HANDLE_VALUE
        return result
    return fake


def test_open_opens_three_handles_with_pipe_access(monkeypatch):
    opened = []
    monkeypatch.setattr(w, "CreateFileW",
                        lambda path, access, *a, **k: opened.append((path, access)) or 100 + len(opened))
    t = w.WindowsRockusbTransport.open(r"\\?\iface")
    assert opened == [
        (r"\\?\iface", w.GENERIC_READ | w.GENERIC_WRITE),
        (r"\\?\iface\pipe00", w.GENERIC_READ),
        (r"\\?\iface\pipe01", w.GENERIC_WRITE),
    ]
    assert (t.control_handle, t.read_handle, t.write_handle) == (101, 102, 103)


def test_open_rolls_back_opened_handles_on_failure(monkeypatch):
    closed = []
    monkeypatch.setattr(w, "CloseHandle", lambda h: closed.append(h))
    # 根句柄 7、pipe00 句柄 8 成功；pipe01 失败 → 须回滚关闭 8 和 7
    monkeypatch.setattr(w, "CreateFileW", _fake_createfile([7, 8, None]))
    with pytest.raises(RuntimeError):
        w.WindowsRockusbTransport.open(r"\\?\iface")
    assert sorted(closed) == [7, 8]

    # pipe00 失败 → 仅回滚根句柄
    closed.clear()
    monkeypatch.setattr(w, "CreateFileW", _fake_createfile([7, None]))
    with pytest.raises(RuntimeError):
        w.WindowsRockusbTransport.open(r"\\?\iface")
    assert closed == [7]


def test_bulk_and_control_route_to_distinct_handles(monkeypatch):
    t = w.WindowsRockusbTransport(control_handle=1, read_handle=2, write_handle=3)
    used = {"read": [], "write": [], "ioctl": []}

    def fake_read(handle, buf, n, read_ptr, overlapped):
        used["read"].append(handle)
        read_ptr._obj.value = n
        return 1

    def fake_write(handle, buf, n, written_ptr, overlapped):
        used["write"].append(handle)
        written_ptr._obj.value = n
        return 1

    def fake_ioctl(handle, ioctl, inbuf, inlen, outbuf, outlen, returned, overlapped):
        used["ioctl"].append(handle)
        returned._obj.value = inlen     # buffered IOCTL 返回输入长度
        return 1

    monkeypatch.setattr(w, "ReadFile", fake_read)
    monkeypatch.setattr(w, "WriteFile", fake_write)
    monkeypatch.setattr(w, "DeviceIoControl", fake_ioctl)

    assert t.bulk_read(4) == b"\x00" * 4
    t.bulk_write(b"\xAB" * 8)
    out = t.control_transfer(0x40, 0x0C, 0, 0x471, b"\x01\x02")
    assert out == b""

    assert used["read"] == [2]
    assert used["write"] == [3]
    assert used["ioctl"] == [1]


def test_close_closes_all_three_handles(monkeypatch):
    closed = []
    monkeypatch.setattr(w, "CloseHandle", lambda h: closed.append(h))
    t = w.WindowsRockusbTransport(control_handle=1, read_handle=2, write_handle=3)
    t.close()
    assert sorted(closed) == [1, 2, 3]
    assert (t.control_handle, t.read_handle, t.write_handle) == (None, None, None)
    t.close()  # 幂等


def test_guid_matches_windows_sys_authority():
    # 权威值：windows-sys 0.52 Usb/mod.rs from_u128(0xa5dcbf10_6530_11d2_901f_00c04fb951ed)
    # 真机教训：GUID 值曾写错（Data4=AC2F...）导致枚举恒空
    assert w.GUID_DEVINTERFACE_USB_DEVICE.Data1 == 0xA5DCBF10
    assert w.GUID_DEVINTERFACE_USB_DEVICE.Data2 == 0x6530
    assert w.GUID_DEVINTERFACE_USB_DEVICE.Data3 == 0x11D2
    assert bytes(w.GUID_DEVINTERFACE_USB_DEVICE.Data4) == \
        bytes([0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED])


def test_spdrp_service_matches_windows_sys_authority():
    # 真机教训：SPDRP_SERVICE 曾误写 0x11（无效属性号），查询必败致设备全被过滤
    assert w.SPDRP_SERVICE == 0x4


def test_detail_path_read_at_field_offset_not_cbsize():
    # 真机实测（x64 Win11）：cbSize 传 8（SetupAPI 校验），但 DevicePath 在偏移 4
    assert w._SP_DEVICE_INTERFACE_DETAIL_DATA.DevicePath.offset == 4
    assert w.DETAIL_DATA_CBSIZE == 8
