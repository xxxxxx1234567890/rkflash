import pytest

from rkflash.protocol.command_block import (
    CommandBlock, CommandStatus, Direction, ResetOpcode, Status,
)


def test_cbw_roundtrip():
    c = CommandBlock(tag=0xDEAD, transfer_length=0x11223344, direction=Direction.OUT,
                     lun=0x66, cdb_length=0x77, cd_code=0x0B, cd_opcode=0x10,
                     cd_address=0x11223344, cd_length=0x5566)
    assert CommandBlock.from_bytes(c.to_bytes()) == c


def test_cbw_exact_bytes():
    c = CommandBlock(tag=0x00000001, transfer_length=16, direction=Direction.IN,
                     lun=0, cdb_length=0x06, cd_code=0x1B, cd_opcode=0,
                     cd_address=0, cd_length=0)
    b = c.to_bytes()
    assert b[0:4] == b"USBC"
    assert b[4:8] == b"\x00\x00\x00\x01"      # tag BE
    assert b[8:12] == b"\x10\x00\x00\x00"      # transfer_length LE
    assert b[12] == 0x80                       # Direction.IN
    assert b[14] == 0x06                       # cdb_length
    assert b[15] == 0x1B                       # cd_code ReadChipInfo
    assert len(b) == 31


def test_csw_roundtrip():
    s = CommandStatus(tag=0x11223344, residue=0x55667788, status=Status.SUCCESS)
    assert CommandStatus.from_bytes(s.to_bytes()) == s


def test_csw_bad_signature():
    with pytest.raises(ValueError):
        CommandStatus.from_bytes(b"XXXX" + b"\x00" * 9)


def test_write_lba_transfer_length():
    c = CommandBlock.write_lba(start_sector=0, sectors=8)
    assert c.transfer_length == 8 * 512
    assert c.cd_code == 0x15
    assert c.cd_length == 8
