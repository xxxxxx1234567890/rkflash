"""Loader IDBlock 构造（对齐 rkdevtool device_ops.rs 845-1033）。

- crc16_ccitt：init 0，poly 0x1021，MSB-first（= CRC-16/XMODEM）
- rockchip_crc32：init 0，poly 0x04c11db7，MSB-first，xorout 0
- RC4：每 512 字节扇区独立密钥流（rockusb rc4_full_sectors）
"""
import struct

SECTOR_SIZE = 512
IDBLOCK_ALIGNMENT = 2048
_RC4_KEY = bytes([124, 78, 3, 4, 85, 5, 9, 7, 45, 44, 123, 56, 23, 13, 23, 17])


def crc16_ccitt(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
    return crc & 0xFFFF


def rockchip_crc32(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if (crc & 0x80000000) else (crc << 1)
    return crc & 0xFFFFFFFF


def _ksa(key: bytes) -> list[int]:
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i & 0x0F]) & 0xFF
        state[i], state[j] = state[j], state[i]
    return state


def rc4_crypt(data: bytes, key: bytes = _RC4_KEY) -> bytes:
    """对 data 逐字节 XOR 密钥流（单次 KSA，密钥与 data 等长异或）。"""
    state = _ksa(key)
    i = j = 0
    out = bytearray(len(data))
    for n in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        out[n] = data[n] ^ state[(state[i] + state[j]) & 0xFF]
    return bytes(out)


def _rc4_full_sectors(data: bytes) -> bytes:
    out = bytearray(data)
    for off in range(0, len(data) - SECTOR_SIZE + 1, SECTOR_SIZE):
        out[off:off + SECTOR_SIZE] = rc4_crypt(bytes(out[off:off + SECTOR_SIZE]))
    return bytes(out)


def _align_idblock(n: int) -> int:
    return (n + IDBLOCK_ALIGNMENT - 1) & ~(IDBLOCK_ALIGNMENT - 1)


def _new_idblock(head: bytes, boost: bytes | None, data: bytes, boot: bytes,
                 rc4: bool) -> bytes:
    if rc4:
        head = _rc4_full_sectors(head)
        if boost is not None:
            boost = _rc4_full_sectors(boost)
        data = _rc4_full_sectors(data)
        boot = _rc4_full_sectors(boot)
    head_size = _align_idblock(len(head))
    boost_size = _align_idblock(len(boost)) if boost is not None else 0
    data_size = _align_idblock(len(data))
    boot_size = _align_idblock(len(boot))
    total = head_size + boost_size + data_size + boot_size

    idblock = bytearray(total)
    idblock[0:len(head)] = head
    data_offset = head_size + boost_size
    if boost is not None:
        idblock[head_size:head_size + len(boost)] = boost
    idblock[data_offset:data_offset + len(data)] = data
    idblock[data_offset + data_size:data_offset + data_size + len(boot)] = boot
    return bytes(idblock)


def _legacy_idblock(data: bytes, boot: bytes, rc4: bool) -> bytes:
    data_sectors = _align_idblock(len(data)) // SECTOR_SIZE
    boot_sectors = _align_idblock(len(boot)) // SECTOR_SIZE
    code_sectors = data_sectors + boot_sectors
    if code_sectors > 0xFFFF:
        raise ValueError("loader data too large for a legacy IDBlock")
    if rc4:
        data = _rc4_full_sectors(data)
        boot = _rc4_full_sectors(boot)

    idblock = bytearray((4 + code_sectors) * SECTOR_SIZE)
    sector0 = bytearray(SECTOR_SIZE)
    sector0[0:4] = (0x0FF0AA55).to_bytes(4, "little")
    sector0[8:12] = (1 if rc4 else 0).to_bytes(4, "little")
    sector0[12:14] = (4).to_bytes(2, "little")
    sector0[14:16] = (4).to_bytes(2, "little")
    sector0[506:508] = (data_sectors).to_bytes(2, "little")
    sector0[508:510] = (code_sectors).to_bytes(2, "little")

    sector1 = bytearray(SECTOR_SIZE)
    sector1[0:2] = (0x000C).to_bytes(2, "little")
    sector1[2:4] = (0xFFFF).to_bytes(2, "little")
    sector1[10:14] = (0x38324B52).to_bytes(4, "little")

    sector2 = bytearray(SECTOR_SIZE)
    sector2[491:494] = b"VC\0"
    sector2[494:496] = (crc16_ccitt(bytes(sector0))).to_bytes(2, "little")
    sector2[496:498] = (crc16_ccitt(bytes(sector1))).to_bytes(2, "little")
    sector2[506:510] = b"CRC\0"

    idblock[0:512] = sector0
    idblock[512:1024] = sector1
    idblock[2048:2048 + len(data)] = data
    boot_start = (4 + data_sectors) * SECTOR_SIZE
    idblock[boot_start:boot_start + len(boot)] = boot

    sector2[498:502] = rockchip_crc32(bytes(idblock[2048:])).to_bytes(4, "little")
    sector2[510:512] = crc16_ccitt(bytes(idblock[1536:2048])).to_bytes(2, "little")
    idblock[1024:1536] = sector2

    out = bytearray(idblock)
    out[0:512] = rc4_crypt(bytes(out[0:512]))
    out[1024:1536] = rc4_crypt(bytes(out[1024:1536]))
    out[1536:2048] = rc4_crypt(bytes(out[1536:2048]))
    return bytes(out)


def build_idblock(loader: bytes, new_idb: bool):
    """构造 IDBlock。new_idb = 设备 capability 的 NEW_IDB 位。返回 (idblock, layout)。"""
    from ..firmware.bootfile import entry_data, parse_boot_header

    header = parse_boot_header(loader[:102])
    if header is None:
        raise ValueError("failed to parse Loader/Boot header")
    flash_boot = entry_data(loader, header.entry_loader, "FlashBoot")
    flash_data = entry_data(loader, header.entry_loader, "FlashData")
    if flash_boot is None or flash_data is None:
        raise ValueError("loader has no FlashBoot/FlashData entry")
    flash_head = entry_data(loader, header.entry_loader, "FlashHead")
    rc4_enabled = header.rc4_flag != 0

    if flash_head is not None:
        if not new_idb:
            raise ValueError("Loader requires New IDBlock support, but device lacks it")
        flash_boost = entry_data(loader, header.entry_loader, "FlashBoost")
        layout = "New IDBlock + FlashBoost" if flash_boost is not None else "New IDBlock"
        return (_new_idblock(flash_head, flash_boost, flash_data, flash_boot, rc4_enabled),
                layout)
    return (_legacy_idblock(flash_data, flash_boot, rc4_enabled), "legacy IDBlock")
