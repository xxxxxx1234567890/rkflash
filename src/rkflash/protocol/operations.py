"""RockUSB 操作执行（对齐 rockusb operation.rs）。"""
from .command_block import (CommandBlock, CommandStatus, Direction, Status)

MAX_LBA_CHUNK_SECTORS = 128  # MAXIO_SIZE = 128 * 512


def crc16_ibm_3740(data: bytes) -> int:
    """CRC-16/IBM-3740：poly 0x1021，init 0xFFFF，refin/refout False，xorout 0（check=0x29B1）。"""
    return _crc_step(0xFFFF, data)


def _crc_step(crc: int, chunk: bytes) -> int:
    """流式 CRC16 单步：对 chunk 逐字节更新状态（对齐 crc::Crc 的 update）。"""
    for b in chunk:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class OperationFailed(RuntimeError):
    pass


def execute_full(transport, cbw: CommandBlock, data_out: bytes = b"") -> bytes:
    """完整协议：CBW→数据相→CSW。返回 IN 数据（无则 b""）。"""
    transport.bulk_write(cbw.to_bytes())
    data_in = b""
    if cbw.transfer_length > 0:
        if cbw.direction == Direction.OUT:
            transport.bulk_write(data_out)
        else:
            data_in = transport.bulk_read(cbw.transfer_length)
    csw = CommandStatus.from_bytes(transport.bulk_read(13))
    if csw.status == Status.FAILED:
        raise OperationFailed("device indicated operation failed")
    if csw.tag != cbw.tag:
        raise RuntimeError("tag mismatch between command and status")
    return data_in


def _write_control_chunk(transport, area, block: bytes):
    transport.control_transfer(request_type=0x40, request=0x0C,
                               value=0, index=area, data=block)


def write_area(transport, area: int, data: bytes) -> None:
    """Maskrom 模式下载（对齐 rockusb MaskRomOperation 状态机）。

    - 全块 4096：直接发送（CRC 流式累加）
    - 末尾恰 4095：补 1 字节 0 凑满 4096 发送（CRC 覆盖 4096），之后补发 2 字节 CRC
    - 末尾 1..4094：追加 2 字节 CRC 内联发送；凑满 4096 时再补发 1 字节 dummy；
      此分支不再补发 CRC
    """
    offset = 0
    crc = 0xFFFF
    tail_sent_crc = False
    while offset < len(data):
        chunk_size = min(4096, len(data) - offset)
        block = data[offset:offset + chunk_size]
        offset += chunk_size
        if chunk_size == 4096:
            crc = _crc_step(crc, block)
            _write_control_chunk(transport, area, block)
        elif chunk_size == 4095:
            block = block + b"\x00"
            crc = _crc_step(crc, block)
            _write_control_chunk(transport, area, block)
        else:
            crc = _crc_step(crc, block)
            block = block + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
            _write_control_chunk(transport, area, block)
            if len(block) == 4096:
                _write_control_chunk(transport, area, b"\x00")
            tail_sent_crc = True
    if not tail_sent_crc:
        # 数据以整块或 4095 补齐块结束：补发累积 CRC 后缀（rockusb chunksize==0 步）
        _write_control_chunk(transport, area, bytes([(crc >> 8) & 0xFF, crc & 0xFF]))
