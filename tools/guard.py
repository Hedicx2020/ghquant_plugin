#!/usr/bin/env python3
"""研报复现的工具调用护栏（Claude Code 的 PreToolUse 钩子）。

管两件事：
1. 任何会话都不许用写文件工具直接改状态文件、事件流和「人在场」记录——它们只能经 tools/state.py、
   tools/flow.py 写，否则闸门形同虚设。
2. 子 agent 读文件前按它正在做的那一步核对禁读清单：研报原文转写（非白名单角色）、别的步骤的任务文件与回执、
   状态与事件流、审阅包、扰动产物与运行缓存、不该直接打开的数据文件。

怎么知道子 agent 在做哪一步：内核把在途步骤写在 workspace/_registry/guard_index.json 里；子 agent 第一次
读到某个在途步骤的任务文件时，记下「这个 agent ↔ 这一步」，之后按这一步的禁读清单核对。还没读过任务文件的
量化角色，按同角色全部在途步骤禁读清单的交集处理；认不出来的 agent 一律放行。

拒绝方式：把原因写到 stderr 并以 2 退出（原因会交给模型）。除此之外任何情况（不是复现工作区、索引不存在、
输入解析不了、脚本自身出错）都以 0 退出放行——护栏坏了不能挡住正常工作。只用标准库，不导入内核。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

REGISTRY = "workspace/_registry"
INDEX = f"{REGISTRY}/guard_index.json"
AGENTS = f"{REGISTRY}/guard_agents.json"
PRESENCE = f"{REGISTRY}/presence.jsonl"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob"}
# 用读文件工具打不开、也不该直接打开的数据文件
DATA_SUFFIXES = (".parquet", ".ndjson", ".pkl", ".pickle", ".feather", ".h5", ".hdf5")
AGENT_KEEP_SECONDS = 3 * 24 * 3600


def project_root(payload: dict[str, Any]) -> Optional[Path]:
    """复现工作区的根；当前项目不是复现工作区时返回 None。"""
    for raw in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if not raw:
            continue
        root = Path(raw)
        for candidate in (root, *root.parents[:3]):
            if (candidate / "workspace").is_dir() and ((candidate / ".reproduce.json").is_file() or (candidate / REGISTRY).is_dir()):
                return candidate
    return None


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rel_path(root: Path, raw: Any) -> Optional[str]:
    """把工具参数里的路径化成相对工作区根的写法（解析掉软链接和 ..）；不在工作区里的返回 None。"""
    if not raw or not isinstance(raw, str):
        return None
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = root / path
    try:
        full, base = os.path.realpath(str(path)), os.path.realpath(str(root))
    except OSError:
        return None
    if full == base:
        return ""
    if not full.startswith(base + os.sep):
        return None
    return full[len(base) + 1:].replace(os.sep, "/")


def deny(root: Path, case: Optional[str], reason: str, detail: dict[str, Any]) -> int:
    if case:
        try:
            log = root / "workspace" / case / "flow" / "guard.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **detail}, ensure_ascii=False) + "\n")
        except OSError:
            pass
    sys.stderr.write(reason + "\n")
    return 2


def protected_write(rel: str) -> Optional[str]:
    """不许用写文件工具直接改的文件；返回原因。"""
    parts = rel.split("/")
    if rel in (PRESENCE, INDEX, AGENTS):
        return "这个文件由钩子和内核维护，不能直接改。"
    if len(parts) == 3 and parts[0] == "workspace" and parts[2] in ("state.json", "state.v1.json", "events.jsonl"):
        return (
            "状态文件和事件流不能直接改：状态只经 tools/state.py 写，推进与放行只经 tools/flow.py。"
            "要解除等待，请让人决定后执行 flow decide / flow accept / flow revise / flow reopen。"
        )
    return None


def matches(rel: str, entries: list[str]) -> Optional[str]:
    for entry in entries:
        if entry.endswith("/"):
            if rel.startswith(entry) or rel + "/" == entry:
                return entry
        elif rel == entry:
            return entry
    return None


def role_of(agent_type: Any) -> str:
    return str(agent_type or "").split(":")[-1]


def inflight_steps(index: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for case, entry in (index.get("cases") or {}).items():
        for step, info in ((entry or {}).get("inflight") or {}).items():
            if isinstance(info, dict):
                out.append({"case": case, "step": step, **info})
    return out


def remember_agent(root: Path, agent_id: str, step: dict[str, Any]) -> None:
    path = root / AGENTS
    data = load_json(path)
    data = data if isinstance(data, dict) else {}
    now = time.time()
    data = {k: v for k, v in data.items() if isinstance(v, dict) and now - float(v.get("at") or 0) < AGENT_KEEP_SECONDS}
    data[agent_id] = {"case": step["case"], "step": step["step"], "attempt": step.get("attempt"), "at": now}
    try:
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def steps_for_agent(root: Path, index: dict[str, Any], agent_id: str, agent_type: Any) -> tuple[list[dict[str, Any]], bool]:
    """这个 agent 可能在做的在途步骤，以及是否已经对上了具体的一步。"""
    steps = inflight_steps(index)
    mapping = load_json(root / AGENTS)
    mapped = mapping.get(agent_id) if isinstance(mapping, dict) else None
    if isinstance(mapped, dict):
        exact = [s for s in steps if s["case"] == mapped.get("case") and s["step"] == mapped.get("step")]
        if exact:
            return exact, True
    role = role_of(agent_type)
    if not role.startswith("quant-"):
        return [], False
    return [s for s in steps if s.get("role") == role], False


def check_read(root: Path, payload: dict[str, Any], index: dict[str, Any]) -> int:
    tool = payload.get("tool_name")
    args = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    agent_id = str(payload.get("agent_id") or "")
    all_steps = inflight_steps(index)
    target = rel_path(root, args.get("file_path") if tool == "Read" else args.get("path"))

    candidates, exact = steps_for_agent(root, index, agent_id, payload.get("agent_type"))

    # 第一次读到在途步骤的任务文件：记下这个 agent 在做哪一步。
    # 已经对上了另一个在途步骤，或角色对不上的，不改记——那是在读别人的任务文件，按禁读清单处理。
    if tool == "Read" and target:
        own = [s for s in all_steps if s.get("task") == target]
        role = role_of(payload.get("agent_type"))
        if own and not (exact and candidates[0]["step"] != own[0]["step"]) and not (role.startswith("quant-") and own[0].get("role") != role):
            remember_agent(root, agent_id, own[0])
            return 0

    if not candidates:
        return 0
    allowed = {p for s in candidates for p in (s.get("task"), s.get("receipt")) if p}
    forbid_sets = [set(s.get("forbid") or []) for s in candidates]
    forbid = sorted(set.intersection(*forbid_sets)) if forbid_sets else []
    case = candidates[0]["case"]
    who = {"tool": tool, "agent_type": payload.get("agent_type"), "steps": [s["step"] for s in candidates]}

    if tool == "Bash":
        command = str(args.get("command") or "")
        text = command
        for path in allowed:
            text = text.replace(str(root / path), "").replace(path, "")
        for entry in forbid:
            if entry.startswith("output/"):
                continue  # 产物目录（扰动结果、运行缓存）：脚本要往里写，命令里出现是正常的；只拦用读文件工具直接打开
            if entry in text or str(root / entry) in text:
                return deny(
                    root,
                    case,
                    f"这条命令碰到了这一步不该读的路径：{entry}。需要其中的信息请写进回执的 summary 说明原因，由主会话处理；"
                    "要取 spec 要素、假设或矩阵行，用任务文件里给的 flow get 命令。",
                    {**who, "path": entry},
                )
        return 0

    if not target or target in allowed:
        return 0
    hit = matches(target, forbid)
    if hit:
        return deny(
            root,
            case,
            f"这一步不该读 {target}（禁读清单：{hit}）。任务文件里的上下文包就是你该用的输入；"
            "缺要素、假设或矩阵行，用任务文件里给的 flow get 命令取。",
            {**who, "path": target},
        )
    if tool == "Read" and exact and target.lower().endswith(DATA_SUFFIXES):
        return deny(
            root,
            case,
            f"不要用读文件工具直接打开数据文件 {target}。要看数据就写脚本取形状、列名和统计量，输出重定向到日志只看关键行。",
            {**who, "path": target},
        )
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = project_root(payload)
    if root is None:
        return 0
    tool = payload.get("tool_name")
    args = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}

    if tool in WRITE_TOOLS:
        target = rel_path(root, args.get("file_path") or args.get("notebook_path"))
        reason = protected_write(target) if target else None
        if reason:
            case = target.split("/")[1] if target.count("/") == 2 and not target.startswith(REGISTRY) else None
            return deny(root, case, reason, {"tool": tool, "path": target, "agent_type": payload.get("agent_type"), "steps": []})
        return 0
    if tool == "Bash" and "presence.jsonl" in str(args.get("command") or ""):
        return deny(root, None, "「人在场」记录只由钩子写，命令里不能碰它。", {"tool": tool, "path": PRESENCE})

    if not payload.get("agent_id") or tool not in READ_TOOLS | {"Bash"}:
        return 0  # 主会话的读取不受禁读清单约束
    index = load_json(root / INDEX)
    if not isinstance(index, dict):
        return 0
    return check_read(root, payload, index)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - 护栏自身出错一律放行
        sys.exit(0)
