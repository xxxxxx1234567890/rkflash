# RK3506 SPI-NAND 官方烧写布局（真机实测 2026-09-02）

来源：官方 RKDevTool 从 Maskrom 烧录 V1.8.1 后，用我们的 RAM Loader 读回逐扇区解析。

## 结论：NAND 与 eMMC 布局不同，loader 写机制是遗留缺口

| 项 | eMMC 假设（RK3576 语义） | RK3506 NAND 实测 | 我们的现状 |
|---|---|---|---|
| GPT | 有 TYPE:GPT parameter 才建表 | **官方总是写 GPT**（LBA0 protective MBR/0、LBA1 `EFI PART`、entries@2、first_usable=0x22、backup@尾部） | 有 build_gpt_tables 但把该固件 parameter 误判为 legacy 没写 → **需修 parameter GPT 判定** |
| Loader | 写 LBA 0x40（普通 write_lba） | **NAND 保留区（0x22 起）普通 LBA 写是 no-op**（写"成功"实际 0xFF）；loader 是 U-Boot，需厂商专用 IDB 写路径 | **缺口**：需 Rockchip NAND IDB 写机制（vendor 命令） |
| 分区 | 按固件声明 LBA | 与固件声明**完全一致**（uboot@0x2000、vnvm@0x4000、kernel@0x4200、dtb@0xc200、app@0xca00、rtrootfs@0x14a00、misc@0x24a00、recovery@0x25200、boot@0x31a00、oem@0x39200、rootfs@0x41200、userdata@0x77200-0x7fbde） | ✅ 已验证分区写正确（misc 读回哈希一致） |

## 实测数据锚点
- GPT 头 LBA1：`EFI PART`，header 标准 92B；entries_lba=2, count=128, size=128；first_usable=0x22, last_usable=0x7fbde
- protective MBR（LBA0）全零（非 0x55aa 保护区——官方写 0）
- loader 区首扇 0x22 内容含 U-Boot 文本 `Missing FDT description in DTB\n` → loader = Rockchip U-Boot，存放于 GPT 之后保留区
- 我们 botched 升级的教训：把 loader 当普通分区写 0x40（成功但未落盘）+ 未写 GPT + parameter@0x2000 被 uboot@0x2000 覆盖 → 板子不引导（回 Maskrom）

## 离线验证（2026-09-02，无板）
用我们的引擎从该 update.img 重建 GPT，与官方读回布局比对：
- `parse_partitions` 从 parameter 解出与官方 GPT **完全一致**的 12 分区（uboot/vnvm/kernel/dtb/app/rtrootfs/misc/recovery/boot/oem/rootfs/userdata）
- `build_gpt_tables` 产物：`EFI PART`@LBA1、first_usable=0x22、**uboot entry 0x2000..0x3fff 与官方逐字节一致** ✅
→ **GPT 生成逻辑正确**；之前失败源于"判定跳过未写 GPT"+ loader 写机制错，而非 GPT 构造。

## 遗留工作（需 Rockchip NAND 工具语义）
1. NAND loader IDB 写机制：rkdeveloptool/upgrade_tool 对 NAND 用 loader 专用命令写保留区（非 write_lba）。需查厂商协议或 SDK 命令实现。
2. parameter GPT 判定增强：官方在参数无显式 `TYPE: GPT` 字样时仍写 GPT（此固件 parameter 仅 `FIRMWARE_VER/MACHINE_MODEL/CMDLINE`）——判据需对齐官方策略（可能 loader 驱动默认）。
3. eMMC（RK3576）整包升级路径待真机验证。
