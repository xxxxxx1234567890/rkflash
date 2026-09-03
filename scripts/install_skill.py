#!/usr/bin/env python3
"""把仓库 SKILL.md 安装为 Claude Code 用户级全局技能（rockchip-flash）。

- 单一权威源：仓库根 SKILL.md；本脚本把其中的安装锚点段
  (<!-- RKFLASH-INSTALL-ANCHOR:START --> ... :END -->) 渲染为本机运行指引，
  注入仓库绝对路径，写入 ~/.claude/skills/rockchip-flash/SKILL.md。
- 幂等；重复执行即重新同步（仓库 SKILL.md 更新后重跑即可）。
- 零依赖：仅标准库。Windows/Linux/macOS 通用。
"""
import sys
from pathlib import Path

ANCHOR_START = "<!-- RKFLASH-INSTALL-ANCHOR:START -->"
ANCHOR_END = "<!-- RKFLASH-INSTALL-ANCHOR:END -->"
SKILL_NAME = "rockchip-flash"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def machine_block(repo: Path) -> str:
    """本机运行指引：直接 cd 到仓库 + 设置 PYTHONPATH/别名。"""
    repo_posix = repo.as_posix()
    if sys.platform == "win32":
        return f"""已安装为全局技能（引擎在本机固定路径）。运行前先确保引擎可用：

```bash
cd "{repo}"
export PYTHONPATH="src"            # Git Bash
# PowerShell: $env:PYTHONPATH = "src"
alias rkflash='py -3 -m rkflash'   # Windows 用 py -3；PowerShell: Set-Alias rkflash "py -3 -m rkflash"
```

引擎路径：`{repo_posix}`（若已移动：git clone https://github.com/xxxxxx1234567890/rkflash.git 后更新此处）。
"""
    return f"""已安装为全局技能（引擎在本机固定路径）。运行前先确保引擎可用：

```bash
cd "{repo_posix}"
export PYTHONPATH="$PWD/src"
alias rkflash='python3 -m rkflash'
```

引擎路径：`{repo_posix}`（若已移动：git clone https://github.com/xxxxxx1234567890/rkflash.git 后更新此处）。
"""


def main() -> int:
    repo = repo_root()
    source = repo / "SKILL.md"
    if not source.exists():
        print(f"未找到 {source}", file=sys.stderr)
        return 1

    text = source.read_text(encoding="utf-8")
    if ANCHOR_START not in text or ANCHOR_END not in text:
        print("SKILL.md 缺少安装锚点段，请先更新仓库 SKILL.md", file=sys.stderr)
        return 2

    head, _, rest = text.partition(ANCHOR_START)
    _, _, tail = rest.partition(ANCHOR_END)
    rendered = head + machine_block(repo) + tail

    dest_dir = Path.home() / ".claude" / "skills" / SKILL_NAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"
    dest.write_text(rendered, encoding="utf-8")
    print(f"已安装/同步技能 -> {dest}")
    print("Claude Code 将在新会话加载该技能；旧会话需重启以生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
