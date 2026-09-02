"""RockUSB 协议字节结构（对齐 rockusb protocol.rs）。"""
from dataclasses import dataclass, field
from enum import IntEnum

SECTOR_SIZE = 512
COMMAND_BLOCK_BYTES = 31
COMMAND_STATUS_BYTES = 13


class Direction(IntEnum):
    IN = 0x80
    OUT = 0x00


class Status(IntEnum):
    SUCCESS = 0
    FAILED = 1


class CommandCode(IntEnum):
    TEST_UNIT_READY = 0x00
    READ_FLASH_ID = 0x01
    ERASE_FORCE = 0x0B
    READ_LBA = 0x14
    WRITE_LBA = 0x15
    READ_FLASH_INFO = 0x1A
    READ_CHIP_INFO = 0x1B
    ERASE_LBA = 0x25
    SWITCH_STORAGE = 0x2A
    GET_STORAGE_MEDIA = 0x2B
    READ_CAPABILITY = 0xAA
    DEVICE_RESET = 0xFF


class ResetOpcode(IntEnum):
    RESET = 0
    MSC = 1
    POWER_OFF = 2
    MASKROM = 3
    DISCONNECT = 4


class StorageIndex(IntEnum):
    NAND = 0
    EMMC = 1
    SD0 = 2
    SD1 = 3
    SPI_NOR = 4
    SPI_NAND = 5
    RAM = 6
    MTD_BLK_NAND = 7
    MTD_BLK_SPI_NAND = 8
    MTD_BLK_SPI_NOR = 9
    SATA = 10
    PCIE = 11
    UFS = 12


@dataclass
class CommandStatus:
    tag: int
    residue: int
    status: Status

    def to_bytes(self) -> bytes:
        return (b"USBS" + self.tag.to_bytes(4, "big")
                + self.residue.to_bytes(4, "little") + bytes([self.status]))

    @staticmethod
    def from_bytes(data: bytes) -> "CommandStatus":
        if len(data) < COMMAND_STATUS_BYTES or data[0:4] != b"USBS":
            raise ValueError("invalid command status")
        return CommandStatus(tag=int.from_bytes(data[4:8], "big"),
                             residue=int.from_bytes(data[8:12], "little"),
                             status=Status(data[12]))


@dataclass
class CommandBlock:
    tag: int
    transfer_length: int
    direction: Direction
    lun: int
    cdb_length: int
    cd_code: int
    cd_opcode: int
    cd_address: int
    cd_length: int
    # 随机 tag 的确定性替代：从 1 起递增，测试可注入
    _counter: int = field(default=1, init=False, repr=False)

    def to_bytes(self) -> bytes:
        return (b"USBC"
                + self.tag.to_bytes(4, "big")
                + self.transfer_length.to_bytes(4, "little")
                + bytes([self.direction, self.lun, self.cdb_length,
                         self.cd_code, self.cd_opcode])
                + self.cd_address.to_bytes(4, "big")
                + b"\x00"
                + self.cd_length.to_bytes(2, "big")
                + b"\x00" * 7)

    @staticmethod
    def from_bytes(data: bytes) -> "CommandBlock":
        if len(data) < COMMAND_BLOCK_BYTES or data[0:4] != b"USBC":
            raise ValueError("invalid command block")
        return CommandBlock(tag=int.from_bytes(data[4:8], "big"),
                            transfer_length=int.from_bytes(data[8:12], "little"),
                            direction=Direction(data[12]), lun=data[13],
                            cdb_length=data[14], cd_code=data[15],
                            cd_opcode=data[16], cd_address=int.from_bytes(data[17:21], "big"),
                            cd_length=int.from_bytes(data[22:24], "big"))

    # ---- builders（对齐 rockusb CommandBlock 构造函数）----
    @staticmethod
    def _next_tag() -> int:
        CommandBlock._counter = CommandBlock._counter + 1
        return CommandBlock._counter

    @classmethod
    def test_unit_ready(cls, subcode: int = 0) -> "CommandBlock":
        return cls(cls._next_tag(), 0, Direction.IN, 0, 0x06,
                   CommandCode.TEST_UNIT_READY, subcode, 0, 0)

    @classmethod
    def flash_id(cls) -> "CommandBlock":
        return cls(cls._next_tag(), 5, Direction.IN, 0, 0x06,
                   CommandCode.READ_FLASH_ID, 0, 0, 0)

    @classmethod
    def flash_info(cls) -> "CommandBlock":
        return cls(cls._next_tag(), 11, Direction.IN, 0, 0x06,
                   CommandCode.READ_FLASH_INFO, 0, 0, 0)

    @classmethod
    def capability(cls) -> "CommandBlock":
        return cls(cls._next_tag(), 8, Direction.IN, 0, 0x06,
                   CommandCode.READ_CAPABILITY, 0, 0, 0)

    @classmethod
    def chip_info(cls) -> "CommandBlock":
        return cls(cls._next_tag(), 16, Direction.IN, 0, 0x06,
                   CommandCode.READ_CHIP_INFO, 0, 0, 0)

    @classmethod
    def erase_lba(cls, first: int, count: int) -> "CommandBlock":
        return cls(cls._next_tag(), 0, Direction.OUT, 0, 0x0A,
                   CommandCode.ERASE_LBA, 0, first, count)

    @classmethod
    def erase_force(cls, first: int, count: int) -> "CommandBlock":
        return cls(cls._next_tag(), 0, Direction.OUT, 0, 0x0A,
                   CommandCode.ERASE_FORCE, 0, first, count)

    @classmethod
    def read_lba(cls, start_sector: int, sectors: int) -> "CommandBlock":
        return cls(cls._next_tag(), sectors * SECTOR_SIZE, Direction.IN, 0, 0x0A,
                   CommandCode.READ_LBA, 0, start_sector, sectors)

    @classmethod
    def write_lba(cls, start_sector: int, sectors: int) -> "CommandBlock":
        return cls(cls._next_tag(), sectors * SECTOR_SIZE, Direction.OUT, 0, 0x0A,
                   CommandCode.WRITE_LBA, 0, start_sector, sectors)

    @classmethod
    def reset_device(cls, opcode: ResetOpcode) -> "CommandBlock":
        return cls(cls._next_tag(), 0, Direction.OUT, 0, 0x06,
                   CommandCode.DEVICE_RESET, opcode, 0, 0)

    @classmethod
    def switch_storage(cls, index: StorageIndex) -> "CommandBlock":
        return cls(cls._next_tag(), 0, Direction.OUT, 0, 0x06,
                   CommandCode.SWITCH_STORAGE, index, 0, 0)

    @classmethod
    def storage(cls) -> "CommandBlock":
        return cls(cls._next_tag(), 4, Direction.IN, 0, 0x06,
                   CommandCode.GET_STORAGE_MEDIA, 0, 0, 0)
