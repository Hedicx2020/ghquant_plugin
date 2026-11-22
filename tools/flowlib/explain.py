"""flow explain：按需取的处理说明。

说明文字放在 skills/reproduce/explain/*.md，一个阶段或主题一个文件，文件里用二级标题分段。
主会话平时不读这些文件：门禁没过、点收被拒、停在检查点时，内核把对应的那一段附在输出里，
或者由主会话用 `flow explain <键>` 取。

键可以是：
- 阶段名（verify）或步骤编号（implement.m2.code，取它所在阶段的那一份）；
- 门禁检查项编号（G-VF-6，只取那一段；G-VF 取整份）；
- 检查点名（data_gap，取 checkpoints.md 里的那一段）；
- 主题名（index 里列出的那些）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from tools import state as st

from .core import PLUGIN_ROOT

EXPLAIN_DIR = PLUGIN_ROOT / "skills" / "reproduce" / "explain"
GATE_STAGE = {
    "in": "init",
    "ex": "extract",
    "pl": "plan",
    "sa": "spec_audit",
    "im": "implement",
    "ca": "code_audit",
    "vf": "verify",
    "it": "iterate",
    "ra": "result_audit",
    "os": "oos",
    "fn": "report",
}
INLINE_LIMIT = 1000  # 附在门禁输出里的一段说明最多这么多字节

_GATE_RE = re.compile(r"g-([a-z]{2})(?:-(\d+))?")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]*")


def available(directory: Optional[Path] = None) -> list[str]:
    directory = directory or EXPLAIN_DIR
    return sorted(p.stem for p in directory.glob("*.md")) if directory.is_dir() else []


def resolve(key: str, directory: Optional[Path] = None) -> Optional[tuple[str, Optional[str]]]:
    """键 → （文件名, 段名）。段名为 None 表示取整份。认不出来返回 None。"""
    from . import checkpoints as cps

    directory = directory or EXPLAIN_DIR
    name = key.strip().split("#")[0].lower()
    if not name:
        return None
    gate = _GATE_RE.fullmatch(name)
    if gate:
        stage = GATE_STAGE.get(gate.group(1))
        return (stage, name.upper() if gate.group(2) else None) if stage else None
    if name in cps.HUMAN or name in cps.AUTO:
        return ("checkpoints", name)
    if (directory / f"{name}.md").is_file():
        return (name, None)
    head = name.split(".")[0]
    if head in st.STAGE_ORDER:
        return (head, None)
    return None


def section_of(text: str, name: str) -> Optional[str]:
    """文件里标题带着这个键的那一段（标题里的英文记号逐个比，不分大小写）。"""
    want = name.lower()
    headings = list(_HEADING_RE.finditer(text))
    for index, match in enumerate(headings):
        if want not in [t.lower() for t in _TOKEN_RE.findall(match.group(1))]:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[match.start() : end].rstrip() + "\n"
    return None


def lookup(key: str, directory: Optional[Path] = None) -> Optional[str]:
    """取说明：点名了某一段就只给那一段（前面带上文件的标题行），否则给整份。"""
    directory = directory or EXPLAIN_DIR
    found = resolve(key, directory)
    if found is None:
        return None
    stem, section = found
    path = directory / f"{stem}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if section is None:
        return text
    part = section_of(text, section)
    if part is None:
        return text
    title = text.splitlines()[0] if text.startswith("# ") else ""
    return (title + "\n\n" if title else "") + part


def inline(keys: list[str], limit: int = 3, directory: Optional[Path] = None) -> str:
    """附在门禁输出后面的说明：每个键取它自己那一段（没有单独成段的不附），最多 limit 段，每段截到 INLINE_LIMIT 字节。"""
    directory = directory or EXPLAIN_DIR
    parts: list[str] = []
    for key in keys:
        found = resolve(key, directory)
        if found is None or found[1] is None:
            continue
        path = directory / f"{found[0]}.md"
        if not path.is_file():
            continue
        part = section_of(path.read_text(encoding="utf-8"), found[1])
        if part is None:
            continue
        body = part.strip()
        if len(body.encode("utf-8")) > INLINE_LIMIT:
            body = body.encode("utf-8")[:INLINE_LIMIT].decode("utf-8", "ignore").rstrip() + f"…（全文：flow explain {key}）"
        if body not in parts:
            parts.append(body)
        if len(parts) >= limit:
            break
    return "\n\n".join(parts)
