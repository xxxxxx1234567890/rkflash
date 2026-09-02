# Rockchip 固件格式（实证反向工程）

来源：`tests/fixtures/Ruiching_RC-Pi-3506_Firmware_NAND_AMP_FACRTORY_V1.8.1.img`（RK3506 SPI-NAND，70.5 MiB）
实证方法：本仓库源码内无 afptool-rs；布局由真实 update.img 逐字节校验得出，内容锚点均已验证。
对齐参照：`rkdevtool/src-tauri/src/firmware/{extract,info}.rs`（字段语义）。

## RKFW 容器（文件首 4 字节 `RKFW`）

| 偏移 | 长度 | 字段 | 本固件实测 |
|---|---|---|---|
| 0x00 | 4 | 魔数 `RKFW` | `52 4b 46 57` |
| 0x06 | 2 LE | 版本号低 | `0x0066` |
| 0x08/0x09 | 各 1 | 版本中/高 | `01 08` → 版本 `8.1.102` |
| 0x0e.. | 7 | 日期 (year u16LE, mo,day,hr,min,sec) | |
| 0x15 | 1 | 芯片码 | `0x46`（表外 → "Unknown"，用检测兜底） |
| 0x19 | 4 LE | boot_offset | `0x66`（102） |
| 0x1d | 4 LE | boot_size | `0x0429c0`（272,832） |
| 0x21 | 4 LE | update_offset（内嵌 RKAF） | `0x042a26`（272,934） |
| 0x25 | 4 LE | update_size | `0x0463d004`（73,720,836） |

boot_offset+boot_size == update_offset（连续）。解出 boot 段 → 独立文件（此固件即 Loader）；解出 update 段 → 内嵌 `RKAF` update.img。

## RKAF update.img（内嵌，首 4 字节 `RKAF`）

固定头 ~0x8c 字节后为条目数组。芯片串如 `RK3506\0` 位于 [0x08..]。

### 分区条目 UpdatePart（**每 112 字节**，经验证 stride=0x70）

| 条目内偏移 | 大小 | 字段 |
|---|---|---|
| 0x00 | 32 | name（C 串） |
| 0x20 | 32 | full_path（C 串） |
| 0x40..0x70 | 48 | 12×u32 LE；**有效位在 u[7..11]** |

12 个 u32 的关键身份（经内容验证）：

| 索引 | 字段 | 证据 |
|---|---|---|
| u[7] | flash_size（扇区） | uboot=0x2000=8192 扇=4MB == byte_count |
| u[8] | **part_offset** | package-file@0x800→`# NAME PATH` 文本 ✓；parameter.txt@0x1000→`PARMT` ✓ |
| u[9] | flash_offset（扇区 LBA；0xffffffff=不烧） | package-file=0xffffffff ✓（extract.rs `has_flash_target`）；uboot=0x2000 |
| u[10] | （padded/预留，未用） | |
| u[11] | **part_byte_count** | package-file=0x111(273B)；uboot=0x400000(4MB) |

本固件条目序（0x8c → 0xfc → 0x18c → 0x1dc … 步长 0x70）：

| name | full_path | flash_size | flash_offset | part_offset | byte_count |
|---|---|---|---|---|---|
| package-file | package-file | 0 | 0xffffffff | 0x800 | 0x111 |
| parameter | parameter.txt | 0x2000 | 0 | 0x1000 | 0x260 |
| MiniLoaderAll.bin | (…/loader path) | | | | |
| uboot | uboot.img | 0x2000 | 0x2000 | 0x44800 | 0x400000 |
| kernel | … | … | … | | |

### 提取规则（对齐 extract.rs）

- `safe_relative_path`：拒绝 `../`、绝对路径、盘符前缀；`\` 归一为 `/`
- 跳过 `SELF` / `RESERVED`；`full_path=="package-file"` 不烧但仍解出
- loader 判定：`download.bin` / `MiniLoaderAll.bin`（大小写不敏感）→ loader_path
- `flash_offset==0xffffffff` 的条目不进入烧写 images
- 解出内容 = `RKAF段起始 + part_offset` 起 `part_byte_count` 字节

### 条目枚举

头部无可靠 num_parts 定位（实证），用启发式：从 0x8c 起按 112 步长枚举，条目 name 须为 ≤31 字符可打印 ASCII，且 part_offset 在文件范围内；遇空名/越界/连续非法即停。

## GPT / parameter / sparse（对齐 android.rs，无需实证）

见上游 `firmware/android.rs`：PARM 头剥除、CMDLINE mtdparts、`uuid:` GUID、protective MBR + EFI PART、sparse 0xed26ff3a/cac1-4。
