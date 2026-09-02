# 芯片实测参照

真机实测数据（Windows Rockusb 驱动，板子进 Loader 模式读取）。

| 芯片 | chip_info 原始 | chip_info 反序 | Loader USB PID | 存储 | flash_id | 备注 |
|---|---|---|---|---|---|---|
| RK3576 | `46 37 35 33`→"6753" | "3576" | 0x350E | eMMC 64GB | "EMMC " | storage one-hot bit1 |
| RK3506 | `46 30 35 33`→"F053" | "350F" | 0x350F | SPI-NAND 256MB | "SNAND" | storage bit16(=SPI NAND, 超出 StorageIndex 0-12) |

- `mode`（Maskrom/Loader）用 PID 启发式（上游 rockusb windows.rs）：`pid&0xF==0xC || pid==0x300A → Maskrom`，否则 Loader。对新型号可能误判，以实际操作结果为准。
- RK3506 固件特征：RKFW 容器 → 内嵌 RKAF；Boot/Loader 文件 magic `LDR `；loader 分区名 `bootloader`、full_path `MiniLoaderAll.bin`。
- SPI-NAND 分区块大小 128KB；eMMC 扇区写上限 128 扇区/次（引擎统一处理）。
