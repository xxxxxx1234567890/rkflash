from rkflash.mock_transport import MockRockDevice


def test_mock_chip_info():
    dev = MockRockDevice()
    out = dev.chip_info()
    assert out.startswith(b"3588")


def test_mock_write_read_lba():
    dev = MockRockDevice()
    dev.write_lba(64, b"\xAA" * 512)
    assert dev.read_lba(64, 1) == b"\xAA" * 512
