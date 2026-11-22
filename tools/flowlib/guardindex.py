"""在途步骤与待决检查点的索引：workspace/_registry/guard_index.json。

钩子（tools/guard.py、tools/presence.py）只读这一个文件，不解析各案例的状态文件：
- 护栏据此知道哪些步骤在途、各自的任务文件、回执路径与禁读清单；
- 「人在场」记录据此知道现在有没有检查点在等人（没有就不记用户输入）。

每条推进类命令结束时由 flow.py 调一次 sync。没有在途步骤也没有待决检查点的案例不进索引。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from tools import state as st

from .core import INFLIGHT, read_json, write_json

INDEX_REL = "workspace/_registry/guard_index.json"


def case_entry(root: Path, state: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not st.is_v2(state):
        return None
    inflight: dict[str, Any] = {}
    for step_id, rec in ((state.get("flow") or {}).get("steps") or {}).items():
        if rec.get("status") != INFLIGHT or rec.get("kind") != "dispatch":
            continue
        manifest = read_json(root / str(rec.get("manifest") or "")) or {}
        inflight[step_id] = {
            "role": rec.get("role"),
            "attempt": rec.get("attempt"),
            "task": manifest.get("task_file"),
            "receipt": rec.get("receipt"),
            "forbid": manifest.get("forbid") or [],
        }
    pending = [{k: cp.get(k) for k in ("id", "code", "name", "opened_at")} for cp in st.pending_checkpoints(state)]
    if not inflight and not pending:
        return None
    return {"inflight": inflight, "pending": pending}


def sync(root: Path, report_id: str, state: Optional[dict[str, Any]] = None) -> None:
    """按案例的当前状态刷新索引里它的那一项。出任何问题都不抛：索引只是护栏的输入。"""
    try:
        state = state if state is not None else st.load_state(root, report_id)
        path = root / INDEX_REL
        index = read_json(path)
        index = index if isinstance(index, dict) and isinstance(index.get("cases"), dict) else {"cases": {}}
        entry = case_entry(root, state)
        before = index["cases"].get(report_id)
        if entry is None:
            index["cases"].pop(report_id, None)
        else:
            index["cases"][report_id] = entry
        if index["cases"].get(report_id) != before:
            index["updated_at"] = st.now_iso()
            write_json(path, index)
    except Exception:  # noqa: BLE001
        pass
