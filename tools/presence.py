#!/usr/bin/env python3
"""「人在场」记录（Claude Code 的 UserPromptSubmit 与 PostToolUse:AskUserQuestion 钩子）。

检查点只能由人放行。放行命令 flow decide 要带上人的原话，内核拿原话和这里记下的内容对：对得上，
凭据等级记为「钩子」；对不上就只能算自述，在看板和报告附录里标出来。

只在有检查点待决时才记（平时不留用户输入），只记到 workspace/_registry/presence.jsonl，
单条截断、只保留最近 14 天。永远静默、永远以 0 退出：记不上就算了，不能挡住用户的输入，
也不能往标准输出写任何东西（那会变成上下文）。只用标准库，不导入内核。
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REGISTRY = "workspace/_registry"
INDEX = f"{REGISTRY}/guard_index.json"
LOG = f"{REGISTRY}/presence.jsonl"
MAX_TEXT = 2000
KEEP_DAYS = 14
TZ_CN = timezone(timedelta(hours=8))


def project_root(payload: dict[str, Any]) -> Optional[Path]:
    for raw in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if not raw:
            continue
        root = Path(raw)
        for candidate in (root, *root.parents[:3]):
            if (candidate / REGISTRY).is_dir():
                return candidate
    return None


def has_pending(root: Path) -> bool:
    try:
        index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    cases = index.get("cases") if isinstance(index, dict) else None
    return any((entry or {}).get("pending") for entry in (cases or {}).values())


def flatten(value: Any) -> str:
    """把提问工具的参数或结果摊成一段文字。结构没有公开承诺，所以不挑字段，能读出字符串的都拼上。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(part for part in (flatten(v) for v in value.values()) if part)
    if isinstance(value, (list, tuple)):
        return " ".join(part for part in (flatten(v) for v in value) if part)
    return str(value)


def build_entry(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    if payload.get("agent_id"):
        return None  # 子 agent 里发生的事不是人说的话
    event = payload.get("hook_event_name")
    entry: dict[str, Any] = {"ts": datetime.now(TZ_CN).isoformat(timespec="seconds"), "session": payload.get("session_id")}
    if event == "UserPromptSubmit":
        text = payload.get("prompt")
        if not isinstance(text, str) or not text.strip():
            return None
        entry.update(source="prompt", text=text.strip()[:MAX_TEXT])
        return entry
    if event == "PostToolUse" and payload.get("tool_name") == "AskUserQuestion":
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        question = flatten(tool_input.get("questions"))
        answer = flatten(payload.get("tool_response")) or flatten(tool_input.get("answers"))
        if not answer.strip():
            return None
        entry.update(source="ask", text=answer.strip()[:MAX_TEXT], question=question.strip()[:MAX_TEXT])
        return entry
    return None


def append(root: Path, entry: dict[str, Any]) -> None:
    path = root / LOG
    cutoff = time.time() - KEEP_DAYS * 86400
    kept: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ts = datetime.fromisoformat(json.loads(line)["ts"]).timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            if ts >= cutoff:
                kept.append(line)
    kept.append(json.dumps(entry, ensure_ascii=False))
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = project_root(payload)
    if root is None or not has_pending(root):
        return 0
    entry = build_entry(payload)
    if entry is not None:
        append(root, entry)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 记不上就算了
        pass
    sys.exit(0)
