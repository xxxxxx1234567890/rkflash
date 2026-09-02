import json
import sys


def emit_json(obj) -> None:
    """机器可读结果 → stdout JSON（单行）。

    ensure_ascii=True：Windows 控制台代码页（GBK 等）下中文不乱码，
    JSON 转义无损，消费方解析后还原。
    """
    print(json.dumps(obj, ensure_ascii=True, default=str), file=sys.stdout)


def emit_progress(text: str) -> None:
    """进度/日志 → stderr，不污染 stdout。"""
    print(text, file=sys.stderr, flush=True)


def fail(code: str, message: str, action_hint: str = "") -> int:
    """打印结构化错误到 stderr，返回非 0 退出码。"""
    emit_progress(json.dumps({"code": code, "message": message, "action_hint": action_hint}))
    return 1
