---
name: rockchip-flash
description: 通过纯 Python rkflash 引擎对 Rockchip SoC 进行 USB 烧写——整包升级、单分区烧录、Maskrom 救砖、设备调试（读取/擦除/导出/存储切换）。Windows(Rockusb 驱动) + Linux(udev)。
---

# Rockchip 烧写技能

用本仓库的 `rkflash` CLI 安全地操作 Rockchip 设备的 USB 烧写。**本技能只做指导与编排；实际烧写一律调用 `rkflash`，绝不臆造命令。**

## 运行环境

```bash
cd <本项目目录>/rockchip-flash-skill
export PYTHONPATH=src            # Windows 用 `py -3` 而非 `python`
alias rkflash='py -3 -m rkflash' # (PowerShell: Set-Alias)
```

命令统一约定：**结果 = stdout JSON；进度/日志 = stderr；退出码 0/非 0**。先 `rkflash devices` 拿 `path`，涉及具体设备都用 `--path`。

## 六步工作流

### 1. 环境检查
`rkflash env-check`（Windows 验 Rockusb 驱动，Linux 验 udev）。`devices_ok` 为 false 时：确认设备已插 OTG 口、已在 Maskrom/Loader 模式；Windows 需绑定 Rockusb 驱动（DriverAssistant）。

### 2. 设备发现
`rkflash devices` → JSON 数组 `[{path, instance_id, pid, mode, location}]`。
- 在线设备 ≠ 1 时**必须**取 `path` 显式指定，绝不烧错板。
- `mode` 由 PID 启发式推断（Loader/Maskrom），仅供参考；以能否执行操作为准。

### 3. 烧写规划（破坏性操作前的强制一步）
对任何会写 flash 的命令先 `rkflash --dry-run <cmd> ...` 生成计划 JSON 并展示给用户，**获明确确认**后再执行。

### 4. 执行（破坏性命令必须 --yes）
| 目标 | 命令 |
|---|---|
| 整包升级（推荐，含分区表） | `rkflash upgrade <update.img> --yes [--path P]` |
| 单分区 | `rkflash flash --part <名>=<镜像> --yes [--loader <loader>]` |
| Maskrom 救砖（载入 RAM 运行，非破坏） | `rkflash boot-loader <MiniLoaderAll.bin>` → 等 Loader |
| 擦除区间 | `rkflash erase --lba START:COUNT --yes` |
| 导出区间（只读） | `rkflash export --lba START:COUNT --out file.img` |
| 重启 / 存储切换 | `rkflash reset [--opcode …]` / `rkflash storage [--set NAME]` |

- `--dry-run` 计划在前置返回，不碰设备；破坏性命令没有 `--yes` 会拒绝（`CONFIRM_REQUIRED`）。
- `boot-loader` 把 Loader 载入 SRAM/DRAM 运行、不写 flash——救砖与验证安全路径；之后设备变成 Loader。
- Loader 模式写入 Loader IDBlock / 分区发生在 `flash`/`upgrade` 内部（Loader IDBlock 落 LBA 0x40、GPT parameter 落 0x2000），引擎已处理顺序。

### 5. 验证
- 只读核验：`rkflash info`（chip/flash_id/capability 互相印证）；`rkflash devices` 确认仍在。
- 内容核验：`rkflash export --lba <起>:<扇区数> --out x.bin`，与烧写源比对（`cmp`/哈希）。
- 启动核验：`rkflash reset` 后观察板子是否正常引导（Loader/串口日志）。

### 6. 安全护栏（必须遵守）
1. **先规划后执行**：一切写操作先 `--dry-run`，向用户展示将写入的分区/LBA，获确认。
2. **显式目标**：设备 >1 时必须 `--path`；核对 instance_id 序列号防烧错板。
3. **破坏性需 --yes**：flash / upgrade / erase 无 `--yes` 会被引擎拒绝。
4. **固件一致**：`boot-loader`/`upgrade` 用与目标板匹配的 Loader（chip_info 实测：RK3576→"3576"、RK3506→"350F"）。
5. **失败处理**：报错含 code/message/action_hint（如 `DRIVER_NOT_FOUND`/`CONFIRM_REQUIRED`）。`INTERNAL` 先 `env-check` 与 `devices` 排查；设备丢失按提示重进模式。
6. **mock 试跑**：无设备或演练时 `--transport mock` 走内存模拟设备，验证流程。

## 常见问题
- **找不到设备**：Windows 查设备管理器是否绑定 Rockusb 驱动；Linux `lsusb` 看 VID 2207；确认进 Maskrom/Loader。
- **Maskrom 写超时(error 121)**：设备实际不在 Maskrom（Loader 在跑）——确认该板正确的 Maskrom 进法。
- **mode 显示不准**：PID 启发式对新型号可能误判，以实际操作结果为准。

## 边界（暂不支持）
- macOS 传输层未实现（代码仅 Windows/Linux）。
- upgrade_tool 兼容命令（分区表 PL/序列号 SN 等）不在本引擎范围。
