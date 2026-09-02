---
name: rockchip-flash
description: Rockchip SoC USB 烧写（更新固件、分区烧录、救砖、调试辅助）。
---

# Rockchip 烧写技能

## 工作流

1. **环境检查** —— 运行 `rkflash env-check`（Windows 验 Rockusb 驱动，Linux 验 udev 规则）；未就绪则给出安装指引后停止。
2. **设备发现** —— 运行 `rkflash devices`；若在线设备 >1，必须向用户确认目标 `path`。
3. **烧写规划** —— 根据目标（update.img / 分区镜像）调用 `rkflash <cmd> --dry-run` 生成计划，展示给用户，**获确认后再执行**。
4. **执行** —— 调用实际命令，读取 stdout JSON，stderr 进度实时反馈。
5. **验证** —— 烧写后按需 `rkflash export` 读回校验，或 `rkflash info` 确认，最后 `rkflash reset`。
6. **安全护栏** —— erase / 整包覆盖 / 救砖等破坏性操作必须二次确认；多设备必须显式指定 path；失败时给出 action_hint。
