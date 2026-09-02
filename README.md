# rkflash — Rockchip USB 烧写引擎（纯 Python）

基于开源 [rkdevtool](https://github.com/hiifong/rkdevtool)（Tauri/Rust）烧写能力重新实现的**零依赖 Python 引擎 + Claude Code 技能**，通过 RockUSB 协议在 Windows / Linux 上对 Rockchip SoC 完成 USB 烧写。

引擎与参考实现逐字节对齐（协议 CBW/CSW、Loader IDBlock、RC4/CRC、RKAF/RKFW 解包、GPT/parameter、Android sparse）。协议字节、固件格式的实证细节见 `docs/firmware-formats.md` 与 `docs/superpowers/specs/`。

## 能力

| 命令 | 说明 | 破坏性 |
|---|---|---|
| `devices` / `info` / `test` | 设备发现、芯片/Flash/Capability 读取、就绪探测 | 只读 |
| `boot-loader <loader>` | Maskrom 下把 Loader 载入 RAM 运行（救砖/引导） | 否 |
| `flash --part NAME=IMG [--loader L]` | 分区 / 按地址 / parameter 烧录 | 是 |
| `upgrade <update.img> [--no-reset]` | 整包升级（解包→装 Loader→GPT→逐分区→重启） | 是 |
| `erase --lba START:COUNT` | 擦除 LBA 区间 | 是 |
| `export --lba START:COUNT --out F` | 读回导出 | 只读 |
| `storage [--set NAME]` | 存储介质查询/切换 | 切换 |
| `env-check` | 驱动/udev/设备就绪 | 只读 |

破坏性命令（flash/upgrade/erase）需 `--yes`；一切写操作先 `--dry-run` 生成计划。结果走 stdout JSON，进度走 stderr。

## 快速开始

```bash
# 依赖：Python 3.10+；无运行期 pip 依赖
export PYTHONPATH=src                 # Windows 用 `py -3`
py -3 -m rkflash env-check
py -3 -m rkflash devices
# 演练（无设备）：--transport mock
py -3 -m rkflash --transport mock info
```

**Windows**：需安装 Rockchip Rockusb 驱动（DriverAssistant），设备绑定 Rockusb 服务。
**Linux**：`apt install libusb-1.0-0` + udev 规则 `packaging/linux/99-rkdevtool-rockchip.rules`。

## 测试

```bash
py -3 -m pytest            # 85 个测试，无硬件依赖
```

真实固件/镜像 fixture（可选，缺失自动 skip）放在 `tests/fixtures/`（gitignore）：
- `*V1.8.1.img`：RK3506 NAND 整包 update.img（RKFW 容器，14 分区）
- `MiniLoaderAll_rk3506.bin`：从上述固件抽取的 Loader

## 真机验证状态

- ✅ M2：RK3576（eMMC 64GB）与 RK3506（SPI-NAND 256MB）的 devices/info/test/reset 全通；双存储介质读取一致
- ⏳ M3/M4：引擎与真实固件 fixture 验证完成；**待真机** Maskrom→boot-loader、分区/整包烧写（需确认 RC-Pi-3506 的 Maskrom 进法）

## 结构

```
src/rkflash/
├── protocol/     # RockUSB 命令块/状态、操作执行（CBW 31B / CSW 13B）
├── transport/    # Windows(Rockusb 三句柄 ctypes) / Linux(libusb) / mock
├── firmware/     # RKAF/RKFW 解包、boot 文件条目、parameter/GPT/sparse
├── flashing/     # IDBlock、LBA、Loader 下载、分区/整包烧写、erase/export/storage
├── device.py     # 跨平台设备发现 + RockDevice 门面
└── cli.py        # 全部子命令入口
```

设计规格与实现计划见 `docs/superpowers/specs/`、`docs/superpowers/plans/`。Claude Code 使用入口：`SKILL.md`。
