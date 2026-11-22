#!/usr/bin/env python3
"""state.json 唯一写入口（研报复现系统 v2）。

子命令：
    init <report_id> --pdf <path> [--mode auto|interactive] [--max-iter N] [--legacy]
    show <report_id>
    set-stage <report_id> <stage> <status>
    set <report_id> <key> <value>
    record-event <report_id> <event> [--json <payload>]
    milestone <report_id> <mid> <field> <status>
    gate <report_id> <stage> <verdict> --checks <json>
    next-id --slug <slug>          # 分配下一个统一编号 id（rNNN_<slug>，只读）
    resolve <query>                # 编号缩写/前缀 → 完整 report_id（只读）

设计要点：
    - 原子写：临时文件写入 + os.replace 原子替换，异常时清理残留临时文件。
    - 每次落盘前校验 schema（字段齐全、枚举合法），非法状态一律拒绝写入。
    - 时间戳统一 ISO8601 + 北京时区 (+08:00)。
    - 路径一律存为相对仓库根的 POSIX 风格字符串。
    - 子 agent 不得导入本模块；仅供主会话与 tools/check_gates.py 调用。
    - 每个写操作都在案例锁内完成「读 → 改 → 写」，并行写不丢更新。
    - schema v2（v3 内核用）：完整的事件与门禁历史追加写入 events.jsonl（带哈希链），
      state.json 只留最近 50 条事件和各阶段最新一条门禁记录。v1 案例的读写行为不变，
      只有显式迁移（tools/flow.py migrate）才会升级。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# 常量：stage 顺序与各类枚举词表（与设计文档 §三 / §十一 字段名一致，不得改名）
# ---------------------------------------------------------------------------

STAGE_ORDER: list[str] = [
    "init",
    "extract",
    "plan",
    "spec_audit",
    "implement",
    "code_audit",
    "verify",
    "iterate",
    "result_audit",
    "oos",
    "report",
    "review",
]

STAGE_STATUS_VALUES = {"pending", "running", "done", "failed", "skipped", "blocked"}
TOP_STATUS_VALUES = {"running", "paused_blocked", "awaiting_review", "done", "done_partial", "aborted"}
MODE_VALUES = {"auto", "interactive"}
REPRODUCTION_MODE_VALUES = {"strict", "experimental"}  # strict=数值对齐原文；experimental=市场迁移复现（等价数据替代，数值判定豁免）
DIFFICULTY_VALUES = {"easy", "medium", "hard"}
# 5 类型模板：factor/timing/allocation/fixed_income/ml（见 templates/ 与设计文档 §十一 standards 表）
TYPE_VALUES = {"factor", "timing", "allocation", "fixed_income", "ml"}
# feasibility 枚举未在设计文档中逐字给出取值集合，此处按 §七 "补数据/降级复现/放弃" 与
# G-PL 断言 "feasibility != blocked" 推定为三态；detail 见任务报告"取舍决策"。
FEASIBILITY_VALUES = {"feasible", "degraded", "blocked"}
VERDICT_RESULT_VALUES = {"pass", "partial", "fail"}
GATE_VERDICT_VALUES = {"PASS", "FAIL"}
# milestone 的 implement/code_review/verify 子状态复用 stage 状态词表（同属"过程状态"语义）
MILESTONE_STATUS_VALUES = STAGE_STATUS_VALUES
MILESTONE_FIELDS = {"implement", "code_review", "verify"}

SCHEMA_VERSION = 1  # 新建案例的默认版本；v3 内核接管 init 之后才改为 2
SCHEMA_VERSION_V2 = 2
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION, SCHEMA_VERSION_V2}
# v2 新增的顶层字段（v1 不得出现）。后续各期只在 ext 下加子键。
V2_TOP_FIELDS = {"flow", "gate_latest", "counters", "checkpoints", "policy", "events_head", "ext"}
# v2 的 state.json 内保留的最近事件条数；完整历史在 events.jsonl
STATE_EVENTS_KEEP = 50
# 以下字段归内核所有：v2 案例里不能用 `state.py set` 直接改，只能经 flow 的命令改
KERNEL_OWNED_FIELDS = {"flow", "gate_latest", "counters", "checkpoints", "policy", "events_head", "ext"}
WAITING_STATUSES = {"paused_blocked", "awaiting_review"}
TERMINAL_STATUSES = {"done", "done_partial", "aborted"}
# 同一（阶段, 检查项）连续这么多次 FAIL 就熔断，停下等人
BREAKER_THRESHOLD = 3
CHECKPOINT_PENDING = "pending"
CHECKPOINT_RESOLVED = "resolved"
# 内核与人工放行专用的事件名：v2 案例里不能用 `state.py record-event` 写入
_RESERVED_EVENT_HEADS = (
    "checkpoint", "decide", "decision", "step", "order", "adhoc", "gate", "stage", "set", "milestone", "migrate",
    "flow", "guard", "pin", "policy", "usage", "review", "data", "pack", "receipt", "fork", "reopen", "tamper",
    "stall", "budget", "trial", "precheck", "state", "breaker", "presence", "revise", "accept",
)
_RESERVED_EVENT_RE = re.compile(
    r"^(?:" + "|".join(_RESERVED_EVENT_HEADS) + r")[:.]"
    r"|override|authoriz|approv|human_|user_confirm|degrade_decision|^accept$|^decide$|_confirmed$",
    re.IGNORECASE,
)

CANONICAL_TOP_FIELDS = {
    "schema_version",
    "report_id",
    "pdf_path",
    "paths",
    "mode",
    "reproduction_mode",
    "max_iter",
    "type",
    "tags",
    "difficulty",
    "difficulty_override",
    "feasibility",
    "pdf_pages",
    "current_stage",
    "status",
    "stages",
    "gates",
    "external_reviews",
    "milestones",
    "iteration",
    "verdict",
    "coverage_stats",
    "assumptions",
    "blockers",
    "pending_question",
    "events",
    "created_at",
    "updated_at",
}

TZ_CN = timezone(timedelta(hours=8))


class StateValidationError(ValueError):
    """state.json 未通过 schema 校验，禁止落盘。"""


class StateGuardError(ValueError):
    """这次写入被状态层的守卫拒绝（等待态下改状态、改内核字段、写保留事件名等）。"""


# ---------------------------------------------------------------------------
# 路径 / 时间戳工具
# ---------------------------------------------------------------------------


def default_root() -> Path:
    """仓库根目录：工具文件所在目录的上一级。

    支持 REPORT_REPRODUCE_ROOT 环境变量覆盖（仅供测试用隔离 tmp_path 根，
    正常使用不设置该变量时行为不变）。
    """
    override = os.environ.get("REPORT_REPRODUCE_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


def now_iso() -> str:
    """ISO8601 时间戳，固定带 +08:00 偏移。"""
    return datetime.now(TZ_CN).isoformat(timespec="seconds")


def workspace_dir(root: Path, report_id: str) -> Path:
    return root / "workspace" / report_id


def src_dir(root: Path, report_id: str) -> Path:
    return root / "src" / report_id


def output_dir(root: Path, report_id: str) -> Path:
    return root / "output" / report_id


def state_path(root: Path, report_id: str) -> Path:
    return workspace_dir(root, report_id) / "state.json"


def _rel(root: Path, path: Path) -> str:
    """把绝对路径转成相对仓库根的 POSIX 字符串；无法归约时原样返回。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_pdf_path(root: Path, pdf_path: str) -> str:
    p = Path(pdf_path)
    if p.is_absolute():
        return _rel(root, p)
    return p.as_posix()


# ---------------------------------------------------------------------------
# 默认 schema
# ---------------------------------------------------------------------------


def _default_stage_entry() -> dict[str, Any]:
    return {"status": "pending", "attempts": 0, "updated_at": None, "issues": 0}


def default_state(
    report_id: str,
    pdf_path: str,
    root: Path,
    mode: str = "auto",
    max_iter: int | None = None,
    reproduction_mode: str = "strict",
) -> dict[str, Any]:
    ts = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "pdf_path": pdf_path,
        "paths": {
            "workspace": _rel(root, workspace_dir(root, report_id)),
            "src": _rel(root, src_dir(root, report_id)),
            "output": _rel(root, output_dir(root, report_id)),
        },
        "mode": mode,
        "reproduction_mode": reproduction_mode,
        "max_iter": max_iter,
        "type": None,
        "tags": [],
        "difficulty": None,
        "difficulty_override": None,
        "feasibility": None,
        "pdf_pages": None,
        "current_stage": STAGE_ORDER[0],
        "status": "running",
        "stages": {stage: _default_stage_entry() for stage in STAGE_ORDER},
        "gates": [],
        "external_reviews": [],
        "milestones": [],
        "iteration": {"current": 0, "max": max_iter, "history": []},
        "verdict": {
            "result": None,
            "comparison_file": None,
            "metrics_pass": None,
            "metrics_total": None,
            "decided_at": None,
        },
        "coverage_stats": {"total": 0, "done": 0, "skipped": 0, "infeasible": 0, "pending": 0},
        "assumptions": {"total": 0, "assumed": 0, "confirmed": 0, "revised": 0},
        "blockers": [],
        "pending_question": None,
        "events": [{"event": "state:init", "timestamp": ts, "payload": None}],
        "created_at": ts,
        "updated_at": ts,
    }


# ---------------------------------------------------------------------------
# schema 校验
# ---------------------------------------------------------------------------


def _check_enum(errors: list[str], key: str, value: Any, allowed: set, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    if value not in allowed:
        errors.append(f"{key} 取值非法: {value!r}，应属于 {sorted(allowed)}")


def default_v2_fields() -> dict[str, Any]:
    """v2 新增字段的默认值（新建 v2 案例与 v1 → v2 迁移共用）。"""
    return {
        "flow": {"inflight": [], "pinned": {}, "generation": 0, "steps": {}, "driver": "kernel", "adhoc": []},
        "gate_latest": {},
        "counters": {"gate_fail_streak": {}, "redispatch": {}, "review_rounds": {}, "adhoc": 0, "false_fail": {}},
        "checkpoints": [],
        "policy": {
            "on_no_answer": "stop",
            "on_missing": "ask",
            "until": None,
            "step": False,
            "budget_tokens": None,
            "budget_hours": None,
            "stall_hours": None,
        },
        "events_head": {"seq": 0, "hash": None},
        "ext": {},
    }


def _validate_v2_fields(state: dict) -> list[str]:
    errors: list[str] = []
    flow = state.get("flow")
    if not isinstance(flow, dict) or not {"inflight", "pinned", "generation"} <= flow.keys():
        errors.append("flow 字段不完整（需含 inflight/pinned/generation）")
    else:
        if not isinstance(flow.get("inflight"), list):
            errors.append("flow.inflight 必须是数组")
        if not isinstance(flow.get("pinned"), dict):
            errors.append("flow.pinned 必须是对象")
        if not isinstance(flow.get("generation"), int) or isinstance(flow.get("generation"), bool):
            errors.append("flow.generation 必须是整数")
    for key in ("gate_latest", "counters", "policy", "ext"):
        if not isinstance(state.get(key), dict):
            errors.append(f"{key} 必须是对象")
    if not isinstance(state.get("checkpoints"), list):
        errors.append("checkpoints 必须是数组")
    head = state.get("events_head")
    if not isinstance(head, dict) or not {"seq", "hash"} <= head.keys():
        errors.append("events_head 字段不完整（需含 seq/hash）")
    elif not isinstance(head.get("seq"), int) or isinstance(head.get("seq"), bool) or head["seq"] < 0:
        errors.append("events_head.seq 必须是非负整数")
    return errors


def validate_state(state: Any) -> list[str]:
    """返回校验错误列表；空列表代表合法。不抛异常，便于 check_gates 复用。"""
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state 必须是 JSON 对象"]

    version = state.get("schema_version")
    is_v2 = version == SCHEMA_VERSION_V2 and not isinstance(version, bool)
    if "schema_version" in state and (isinstance(version, bool) or version not in SUPPORTED_SCHEMA_VERSIONS):
        errors.append(f"不支持的 schema_version: {version!r}，应属于 {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    allowed_fields = CANONICAL_TOP_FIELDS | (V2_TOP_FIELDS if is_v2 else set())

    missing = allowed_fields - state.keys()
    if missing:
        errors.append(f"缺少顶层字段: {sorted(missing)}")
    extra = state.keys() - allowed_fields
    if extra:
        errors.append(f"存在未声明的顶层字段: {sorted(extra)}")
    if is_v2:
        errors.extend(_validate_v2_fields(state))

    if not isinstance(state.get("report_id"), str) or not state.get("report_id"):
        errors.append("report_id 必须是非空字符串")

    _check_enum(errors, "mode", state.get("mode"), MODE_VALUES, allow_none=False)
    _check_enum(errors, "reproduction_mode", state.get("reproduction_mode"), REPRODUCTION_MODE_VALUES, allow_none=False)
    _check_enum(errors, "status", state.get("status"), TOP_STATUS_VALUES, allow_none=False)
    _check_enum(errors, "difficulty", state.get("difficulty"), DIFFICULTY_VALUES)
    _check_enum(errors, "difficulty_override", state.get("difficulty_override"), DIFFICULTY_VALUES)
    _check_enum(errors, "type", state.get("type"), TYPE_VALUES)
    _check_enum(errors, "feasibility", state.get("feasibility"), FEASIBILITY_VALUES)
    _check_enum(errors, "current_stage", state.get("current_stage"), set(STAGE_ORDER), allow_none=False)

    if not isinstance(state.get("tags"), list):
        errors.append("tags 必须是数组")

    stages = state.get("stages")
    if not isinstance(stages, dict):
        errors.append("stages 必须是对象")
    else:
        missing_stages = [s for s in STAGE_ORDER if s not in stages]
        if missing_stages:
            errors.append(f"stages 缺少: {missing_stages}")
        unknown_stages = [s for s in stages if s not in STAGE_ORDER]
        if unknown_stages:
            errors.append(f"stages 含未知 stage: {unknown_stages}")
        for stage_name, entry in stages.items():
            if stage_name not in STAGE_ORDER:
                continue
            if not isinstance(entry, dict):
                errors.append(f"stages.{stage_name} 必须是对象")
                continue
            _check_enum(errors, f"stages.{stage_name}.status", entry.get("status"), STAGE_STATUS_VALUES, allow_none=False)
            attempts = entry.get("attempts")
            if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
                errors.append(f"stages.{stage_name}.attempts 必须是非负整数")

    gates = state.get("gates")
    if not isinstance(gates, list):
        errors.append("gates 必须是数组")
    else:
        for i, g in enumerate(gates):
            if not isinstance(g, dict) or not {"stage", "checks", "verdict", "timestamp"} <= g.keys():
                errors.append(f"gates[{i}] 字段不完整（需含 stage/checks/verdict/timestamp）")
                continue
            _check_enum(errors, f"gates[{i}].verdict", g.get("verdict"), GATE_VERDICT_VALUES, allow_none=False)
            if not isinstance(g.get("checks"), list):
                errors.append(f"gates[{i}].checks 必须是数组")

    external_reviews = state.get("external_reviews")
    if not isinstance(external_reviews, list):
        errors.append("external_reviews 必须是数组")

    milestones = state.get("milestones")
    if not isinstance(milestones, list):
        errors.append("milestones 必须是数组")
    else:
        seen_ids: set[str] = set()
        for i, m in enumerate(milestones):
            if not isinstance(m, dict) or not {"id", "name", "deps", "implement", "code_review", "verify"} <= m.keys():
                errors.append(f"milestones[{i}] 字段不完整（需含 id/name/deps/implement/code_review/verify）")
                continue
            if m["id"] in seen_ids:
                errors.append(f"milestones 存在重复 id: {m['id']}")
            seen_ids.add(m["id"])
            if not isinstance(m.get("deps"), list):
                errors.append(f"milestones[{i}].deps 必须是数组")
            for field in MILESTONE_FIELDS:
                _check_enum(errors, f"milestones[{i}].{field}", m.get(field), MILESTONE_STATUS_VALUES, allow_none=False)

    iteration = state.get("iteration")
    if not isinstance(iteration, dict) or not {"current", "max", "history"} <= iteration.keys():
        errors.append("iteration 字段不完整（需含 current/max/history）")
    else:
        if not isinstance(iteration.get("current"), int) or isinstance(iteration.get("current"), bool):
            errors.append("iteration.current 必须是整数")
        if not isinstance(iteration.get("history"), list):
            errors.append("iteration.history 必须是数组")

    verdict = state.get("verdict")
    if not isinstance(verdict, dict) or "result" not in verdict:
        errors.append("verdict 字段不完整（需含 result）")
    else:
        _check_enum(errors, "verdict.result", verdict.get("result"), VERDICT_RESULT_VALUES)

    for stat_field in ("coverage_stats", "assumptions"):
        obj = state.get(stat_field)
        if not isinstance(obj, dict):
            errors.append(f"{stat_field} 必须是对象")

    if not isinstance(state.get("blockers"), list):
        errors.append("blockers 必须是数组")
    if not isinstance(state.get("events"), list):
        errors.append("events 必须是数组")
    if not isinstance(state.get("paths"), dict):
        errors.append("paths 必须是对象")

    return errors


# ---------------------------------------------------------------------------
# 原子写 / 读
# ---------------------------------------------------------------------------


def atomic_write_json(path: Path, data: dict) -> None:
    """临时文件写入 + os.replace 原子替换；任何异常都不残留临时文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".state_", suffix=".json.tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def load_state(root: Path, report_id: str) -> dict[str, Any]:
    path = state_path(root, report_id)
    if not path.exists():
        raise FileNotFoundError(f"state.json 不存在: {path}（请先执行 init）")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(root: Path, report_id: str, state: dict[str, Any]) -> dict[str, Any]:
    errors = validate_state(state)
    if errors:
        raise StateValidationError("state.json 校验失败:\n" + "\n".join(f"- {e}" for e in errors))
    atomic_write_json(state_path(root, report_id), state)
    return state


# ---------------------------------------------------------------------------
# 案例锁：所有写操作的「读 → 改 → 写」都在锁内完成
# ---------------------------------------------------------------------------


class StateLockTimeout(RuntimeError):
    """等待案例锁超时（另一进程持锁未释放）。"""


LOCK_FILENAME = ".state.lock"
LOCK_TIMEOUT_SECONDS = 30.0
LOCK_STALE_SECONDS = 120.0  # 无法探活时（其他主机 / Windows）按锁龄判断
LOCK_HARD_STALE_SECONDS = 900.0  # 持锁进程看起来还活着时的兜底上限（防 pid 被复用）

# 同一进程内的重入登记。挂在 sys 上而不是模块变量：本模块可能同时以 `state` 和
# `tools.state` 两个名字被导入，登记必须只有一份，否则嵌套加锁会自己等自己。
_HELD_LOCKS: dict[str, dict[str, int]] = sys.__dict__.setdefault("_report_reproduce_case_locks", {})


def lock_path(root: Path, report_id: str) -> Path:
    return workspace_dir(root, report_id) / LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # Windows 上 os.kill(pid, 0) 会直接终止目标进程，不能用来探活；只靠锁龄判断。
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _lock_is_stale(path: Path) -> bool:
    """锁文件是否已失效：持锁进程已死，或锁龄超过上限。"""
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False  # 已被释放，调用方直接重试创建
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return age > 5.0  # 刚创建还没写完内容，给 5 秒宽限
    pid = info.get("pid") if isinstance(info, dict) else None
    same_host = isinstance(info, dict) and info.get("host") == socket.gethostname()
    if same_host and isinstance(pid, int) and not isinstance(pid, bool) and os.name != "nt":
        return (not _pid_alive(pid)) or age > LOCK_HARD_STALE_SECONDS
    return age > LOCK_STALE_SECONDS


def _break_stale_lock(path: Path) -> None:
    """移除失效的锁文件。用一把短命的清理锁串行化，并在清理锁内复查，避免误删别人刚拿到的新锁。"""
    breaker = path.with_name(path.name + ".break")
    try:
        fd = os.open(str(breaker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        # 另一个进程正在清理；清理者崩溃留下的残留超过 10 秒就移除
        with contextlib.suppress(OSError):
            if time.time() - breaker.stat().st_mtime > 10.0:
                breaker.unlink()
        return
    try:
        os.close(fd)
        if _lock_is_stale(path):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
    finally:
        with contextlib.suppress(FileNotFoundError):
            breaker.unlink()


@contextlib.contextmanager
def case_lock(root: Path, report_id: str, timeout: float = LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """案例级互斥锁（跨平台：独占创建锁文件，不依赖 fcntl）。同线程可重入。

    案例目录不存在时不加锁也不建目录，交给后续 load_state 报「不存在」。
    """
    ws = workspace_dir(root, report_id)
    if not ws.is_dir():
        yield
        return

    path = ws / LOCK_FILENAME
    key = str(path.resolve())
    me = threading.get_ident()
    held = _HELD_LOCKS.get(key)
    if held is not None and held["pid"] == os.getpid() and held["thread"] == me:
        held["depth"] += 1
        try:
            yield
        finally:
            held["depth"] -= 1
        return

    deadline = time.monotonic() + timeout
    delay = 0.01
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if _lock_is_stale(path):
                _break_stale_lock(path)
            if time.monotonic() >= deadline:
                raise StateLockTimeout(
                    f"等待案例锁超时（{timeout:.0f}s）: {path}。若确认没有其他进程在写，删除该文件后重试。"
                ) from None
            time.sleep(delay)
            delay = min(delay * 1.5, 0.2)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "host": socket.gethostname(), "ts": now_iso()}, f)
        break

    _HELD_LOCKS[key] = {"pid": os.getpid(), "thread": me, "depth": 1}
    try:
        yield
    finally:
        _HELD_LOCKS.pop(key, None)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


# ---------------------------------------------------------------------------
# 事件流（schema v2）：events.jsonl 追加写 + 哈希链
# ---------------------------------------------------------------------------

EVENTS_FILENAME = "events.jsonl"


def events_path(root: Path, report_id: str) -> Path:
    return workspace_dir(root, report_id) / EVENTS_FILENAME


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def event_hash(prev: str | None, seq: int, ts: str | None, event: str, payload: Any) -> str:
    """一条事件的哈希：上一条的哈希 + 本条的规范化内容。"""
    body = _canonical_json({"seq": seq, "ts": ts, "event": event, "payload": payload})
    return hashlib.sha256(((prev or "") + "\n" + body).encode("utf-8")).hexdigest()


def _make_event_record(prev: str | None, seq: int, ts: str | None, event: str, payload: Any) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts": ts,
        "event": event,
        "payload": payload,
        "prev": prev,
        "hash": event_hash(prev, seq, ts, event, payload),
    }


def _last_event_record(path: Path) -> dict[str, Any] | None:
    """读 events.jsonl 的最后一条（从文件尾部倒着找，不整读）。"""
    if not path.is_file():
        return None
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        block = b""
        while pos > 0:
            step = min(8192, pos)
            pos -= step
            f.seek(pos)
            block = f.read(step) + block
            lines = block.split(b"\n")
            complete = lines if pos == 0 else lines[1:]  # 未读到文件头时首段可能是半行
            candidates = [ln for ln in complete if ln.strip()]
            if candidates:
                try:
                    return json.loads(candidates[-1].decode("utf-8"))
                except ValueError as exc:
                    raise StateValidationError(f"events.jsonl 末行损坏，无法续写: {path}") from exc
    return None


def append_event_record(root: Path, report_id: str, event: str, payload: Any, ts: str | None) -> dict[str, Any]:
    """向 events.jsonl 追加一条并落盘，返回该条记录（含 seq 与 hash）。调用方须已持案例锁。"""
    path = events_path(root, report_id)
    last = _last_event_record(path)
    seq = int(last["seq"]) + 1 if last else 1
    record = _make_event_record(last["hash"] if last else None, seq, ts, event, payload)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return record


def write_event_log(path: Path, items: list[tuple[str | None, str, Any]]) -> dict[str, Any]:
    """整份重写事件流（新建 v2 案例与迁移用）：临时文件 + 原子替换。返回链头。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".events_", suffix=".jsonl.tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    prev: str | None = None
    seq = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ts, event, payload in items:
                seq += 1
                record = _make_event_record(prev, seq, ts, event, payload)
                prev = record["hash"]
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return {"seq": seq, "hash": prev}


def read_event_records(root: Path, report_id: str) -> list[dict[str, Any]]:
    """读出 events.jsonl 的全部记录（文件不存在时返回空列表）。"""
    path = events_path(root, report_id)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def verify_event_chain(root: Path, report_id: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """核对事件流的哈希链，以及它与 state.events_head 是否一致。

    返回 {ok, count, errors, uncommitted_tail}。uncommitted_tail 是写了事件但 state
    没有落盘的尾部条数（以 state 为准，不算错误）。防的是顺手改动，不防蓄意伪造。
    """
    errors: list[str] = []
    path = events_path(root, report_id)
    records: list[dict[str, Any]] = []
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    errors.append(f"第 {lineno} 行不是合法 JSON")
                    break

    prev: str | None = None
    for i, rec in enumerate(records, 1):
        if rec.get("seq") != i:
            errors.append(f"第 {i} 条的 seq={rec.get('seq')!r}，应为 {i}")
            break
        if rec.get("prev") != prev:
            errors.append(f"第 {i} 条的 prev 与上一条的 hash 不符")
            break
        expected = event_hash(prev, i, rec.get("ts"), rec.get("event"), rec.get("payload"))
        if rec.get("hash") != expected:
            errors.append(f"第 {i} 条的内容与 hash 不符（事件被改动过）")
            break
        prev = rec["hash"]

    uncommitted = 0
    head = (state or {}).get("events_head") if state is not None else None
    if isinstance(head, dict) and not errors:
        head_seq = head.get("seq") or 0
        if head_seq > len(records):
            errors.append(f"state.events_head.seq={head_seq} 超过事件流条数 {len(records)}（事件流被截断）")
        elif head_seq > 0 and records[head_seq - 1].get("hash") != head.get("hash"):
            errors.append(f"state.events_head 与事件流第 {head_seq} 条的 hash 不符")
        else:
            uncommitted = len(records) - head_seq
    return {"ok": not errors, "count": len(records), "errors": errors, "uncommitted_tail": uncommitted}


def is_v2(state: dict[str, Any]) -> bool:
    return state.get("schema_version") == SCHEMA_VERSION_V2


def _log_event(
    root: Path, report_id: str, state: dict[str, Any], event: str, payload: Any = None, ts: str | None = None
) -> None:
    """记一条事件。v1：追加进 state.events（与旧行为一致）。

    v2：先确认 state 合法，再写 events.jsonl，最后在 state 里留最近若干条并更新链头。
    先校验是为了不留下「事件写了、state 因校验失败没写」的孤儿事件。
    """
    ts = ts or now_iso()
    entry = {"event": event, "timestamp": ts, "payload": payload}
    if not is_v2(state):
        state["events"].append(entry)
        return
    errors = validate_state(state)
    if errors:
        raise StateValidationError("state.json 校验失败:\n" + "\n".join(f"- {e}" for e in errors))
    record = append_event_record(root, report_id, event, payload, ts)
    state["events"].append(entry)
    del state["events"][:-STATE_EVENTS_KEEP]
    state["events_head"] = {"seq": record["seq"], "hash": record["hash"]}


def _latest_gate_per_stage(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每个阶段只留最新一条门禁记录，整体仍按时间先后排列（最后一条即全局最新）。"""
    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, gate in enumerate(gates):
        latest[str(gate.get("stage"))] = (index, gate)
    return [gate for _index, gate in sorted(latest.values(), key=lambda item: item[0])]


GATE_DETAIL_KEEP = 500  # state 里每条未通过项的明细最多留这么多字符；全文在 events.jsonl


def _clip(text: Any, limit: int = GATE_DETAIL_KEEP) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + f"…（共 {len(text)} 字符，全文见 events.jsonl）"


def _gate_latest_entry(gate: dict[str, Any]) -> dict[str, Any]:
    failed = []
    for c in gate.get("checks", []):
        if not isinstance(c, dict) or c.get("result") != "FAIL":
            continue
        item = {k: c[k] for k in ("id", "desc") if c.get(k)}
        if c.get("detail"):
            item["detail"] = _clip(c["detail"])
        failed.append(item)
    return {"verdict": gate.get("verdict"), "timestamp": gate.get("timestamp"), "failed": failed}


def _strip_check_details(checks: list) -> list:
    """去掉检查项里的 detail（state.gates 保持与 v1 相同的条目形状，明细只进事件流）。"""
    return [{k: v for k, v in c.items() if k != "detail"} if isinstance(c, dict) else c for c in checks]


def _update_fail_streak(streak: dict[str, int], stage: str, checks: list) -> None:
    """按（阶段, 检查项）累计连续 FAIL 次数；该检查项通过即清零。

    verify 阶段只有 G-VF-3（指标超差）未过，是进入 iterate 的设计路径，不计入连败也不清零。
    """
    items = [c for c in checks if isinstance(c, dict) and c.get("id")]
    failed = {c["id"] for c in items if c.get("result") == "FAIL"}
    exempt = "G-VF-3" if stage == "verify" and failed == {"G-VF-3"} else None
    for check in items:
        key = f"{stage}:{check['id']}"
        if check.get("result") == "FAIL":
            if check["id"] != exempt:
                streak[key] = int(streak.get(key, 0)) + 1
        else:
            streak.pop(key, None)


def is_privileged(actor: str) -> bool:
    """内核命令（flow …）发起的写入不受守卫限制；其余一律按命令行对待。"""
    return isinstance(actor, str) and actor.startswith("flow")


def is_reserved_event(event: str) -> bool:
    return bool(_RESERVED_EVENT_RE.search(str(event)))


def _reject(root: Path, report_id: str, state: dict[str, Any], what: dict[str, Any], message: str) -> None:
    """守卫拒绝一次写入：先把这次尝试记进事件流，再抛错。"""
    ts = now_iso()
    _log_event(root, report_id, state, "guard:rejected", what, ts)
    state["updated_at"] = ts
    save_state(root, report_id, state)
    raise StateGuardError(message)


# ---------------------------------------------------------------------------
# 事务：内核的「读 → 改 → 记事件 → 写」在一把锁里完成，中途出错什么都不落盘
# ---------------------------------------------------------------------------


class Txn:
    """一次事务里的可变状态与待写事件。事件在提交时才进 events.jsonl。"""

    def __init__(self, root: Path, report_id: str, state: dict[str, Any], actor: str) -> None:
        self.root = root
        self.report_id = report_id
        self.state = state
        self.actor = actor
        self.dirty = False
        self._events: list[tuple[str, Any, str]] = []

    def log(self, event: str, payload: Any = None, ts: str | None = None) -> None:
        self._events.append((event, payload, ts or now_iso()))
        self.dirty = True

    def touch(self) -> None:
        self.dirty = True

    @property
    def v2(self) -> bool:
        return is_v2(self.state)


def _commit(txn: Txn) -> None:
    state = txn.state
    state["updated_at"] = now_iso()
    errors = validate_state(state)
    if errors:
        raise StateValidationError("state.json 校验失败:\n" + "\n".join(f"- {e}" for e in errors))
    for event, payload, ts in txn._events:
        _log_event(txn.root, txn.report_id, state, event, payload, ts)
    save_state(txn.root, txn.report_id, state)


@contextlib.contextmanager
def transaction(root: Path, report_id: str, actor: str = "flow") -> Iterator[Txn]:
    """内核专用的事务入口。块内改 txn.state、用 txn.log 记事件；正常退出且有改动才提交。"""
    with case_lock(root, report_id):
        txn = Txn(root, report_id, load_state(root, report_id), actor)
        yield txn
        if txn.dirty:
            _commit(txn)


# ---------------------------------------------------------------------------
# 检查点的底层读写（策略、审阅包、凭据在 tools/flowlib/checkpoints.py）
# ---------------------------------------------------------------------------

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉了容易看混的 I、O、0、1


def checkpoint_code(report_id: str, cp_id: str, opened_at: str) -> str:
    """检查点短码：放行时由人原样带上，用来把「人说过的话」和这次放行对上。"""
    digest = hashlib.sha256(f"{report_id}|{cp_id}|{opened_at}".encode("utf-8")).digest()
    return "".join(_CODE_ALPHABET[b % len(_CODE_ALPHABET)] for b in digest[:4])


def pending_checkpoints(state: dict[str, Any], human_only: bool = True) -> list[dict[str, Any]]:
    return [
        c
        for c in state.get("checkpoints") or []
        if isinstance(c, dict) and c.get("status") == CHECKPOINT_PENDING and (c.get("kind") == "human" or not human_only)
    ]


def find_checkpoint(state: dict[str, Any], key: str) -> dict[str, Any] | None:
    """按编号（cp_03 / 3）、短码或名称找检查点；名称重复时取最近一个待决的。"""
    items = [c for c in state.get("checkpoints") or [] if isinstance(c, dict)]
    norm = str(key).strip()
    m = re.fullmatch(r"(?:cp_?)?0*(\d+)", norm, re.IGNORECASE)
    if m:
        wanted = f"cp_{int(m.group(1)):02d}"
        for c in items:
            if c.get("id") == wanted:
                return c
    for c in items:
        if str(c.get("code", "")).upper() == norm.upper():
            return c
    named = [c for c in items if c.get("name") == norm]
    pending = [c for c in named if c.get("status") == CHECKPOINT_PENDING]
    return (pending or named or [None])[-1]


def open_checkpoint_in(
    txn: Txn,
    name: str,
    *,
    kind: str = "human",
    stage: str | None = None,
    reason: str = "",
    options: list[dict[str, Any]] | None = None,
    pause_status: str | None = "paused_blocked",
    pack: str | None = None,
    payload: Any = None,
    question: str | None = None,
) -> dict[str, Any]:
    """在事务里开一个检查点。human 类会把案例置为等待态；auto 类只留痕不停。"""
    state = txn.state
    if not is_v2(state):
        raise StateGuardError("检查点只在 v2 案例上可用；旧案例请先执行 flow migrate")
    if kind not in ("human", "auto"):
        raise ValueError(f"非法检查点类别: {kind}")
    ts = now_iso()
    cp_id = f"cp_{len(state['checkpoints']) + 1:02d}"
    cp: dict[str, Any] = {
        "id": cp_id,
        "name": name,
        "kind": kind,
        "stage": stage if stage is not None else state.get("current_stage"),
        "status": CHECKPOINT_PENDING,
        "opened_at": ts,
        "reason": reason,
        "options": options or [],
        "pack": pack,
        "payload": payload,
        "code": checkpoint_code(str(state.get("report_id")), cp_id, ts),
        "prev_status": state.get("status"),
        "decision": None,
    }
    state["checkpoints"].append(cp)
    if kind == "human" and pause_status:
        if pause_status not in WAITING_STATUSES:
            raise ValueError(f"检查点只能把案例置为等待态，收到: {pause_status}")
        state["status"] = pause_status
        if question or reason:
            state["pending_question"] = question or reason
    txn.log(f"checkpoint:{name}:opened", {"id": cp_id, "kind": kind, "stage": cp["stage"], "reason": reason}, ts)
    return cp


def resolve_checkpoint_in(
    txn: Txn,
    cp: dict[str, Any],
    *,
    choice: str,
    quote: str = "",
    credential: str = "self_report",
    by: str = "human",
    resume_status: str | None = "running",
    note: str = "",
) -> dict[str, Any]:
    """在事务里关闭一个检查点并记下是谁、凭什么、选了什么。

    resume_status 给了且没有别的人工检查点待决时，把案例状态改成它（None 表示不动状态）。
    """
    state = txn.state
    if cp.get("status") != CHECKPOINT_PENDING:
        raise StateGuardError(f"检查点 {cp.get('id')} 已经处理过（{cp.get('status')}）")
    ts = now_iso()
    cp["status"] = CHECKPOINT_RESOLVED
    cp["decision"] = {"choice": choice, "quote": quote, "credential": credential, "by": by, "at": ts, "note": note}
    if cp.get("name") == "circuit_breaker" and isinstance(cp.get("payload"), dict):
        streak = state["counters"].setdefault("gate_fail_streak", {})
        for key in cp["payload"].get("keys") or []:
            streak.pop(key, None)
    others = [c for c in pending_checkpoints(state) if c is not cp]
    if resume_status and not others:
        state["status"] = resume_status
        if resume_status == "running":
            state["pending_question"] = None
    txn.log(
        f"checkpoint:{cp.get('name')}:resolved",
        {"id": cp.get("id"), "choice": choice, "quote": quote, "credential": credential, "by": by, "note": note},
        ts,
    )
    return cp


def _trip_breaker(txn: Txn, stage: str) -> dict[str, Any] | None:
    """某个检查项连败到阈值就开熔断检查点；同一组检查项已有待决的熔断时不重复开。"""
    state = txn.state
    streak = state["counters"].get("gate_fail_streak") or {}
    keys = sorted(k for k, n in streak.items() if k.startswith(f"{stage}:") and int(n) >= BREAKER_THRESHOLD)
    if not keys:
        return None
    for cp in pending_checkpoints(state):
        if cp.get("name") == "circuit_breaker" and set(keys) <= set((cp.get("payload") or {}).get("keys") or []):
            return None
    detail = "、".join(f"{k.split(':', 1)[1]} 连续 {streak[k]} 次" for k in keys)
    return open_checkpoint_in(
        txn,
        "circuit_breaker",
        stage=stage,
        reason=f"{stage} 阶段的门禁 {detail}未过，已熔断，等人决定怎么办",
        options=[
            {"key": "retry", "label": "再试一轮（相关计数清零）"},
            {"key": "pin_card", "label": "这个阶段退回执行卡驱动，由主会话按说明处理"},
            {"key": "abort", "label": "终止这个案例"},
        ],
        pause_status="paused_blocked",
        payload={"keys": keys, "streak": {k: streak[k] for k in keys}},
    )


# ---------------------------------------------------------------------------
# 核心操作（供 CLI 与 check_gates.py 复用）
# ---------------------------------------------------------------------------


def set_stage_in(txn: Txn, stage: str, status: str) -> None:
    """事务内改阶段状态（事件名与 set_stage 相同）。"""
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知 stage: {stage}，应属于 {STAGE_ORDER}")
    if status not in STAGE_STATUS_VALUES:
        raise ValueError(f"非法 stage status: {status}，应属于 {sorted(STAGE_STATUS_VALUES)}")
    ts = now_iso()
    entry = txn.state["stages"].setdefault(stage, _default_stage_entry())
    entry["status"] = status
    entry["updated_at"] = ts
    if status == "running":
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
    txn.state["current_stage"] = stage
    txn.log(f"stage:{stage}:{status}", None, ts)


def set_in(txn: Txn, key_path: str, value: Any, log: bool = True) -> None:
    """事务内设置字段（事件名与 set_field 相同）。内核字段的改动默认也记事件。"""
    parts = key_path.split(".")
    if parts[0] not in txn.state:
        raise ValueError(f"未知顶层字段: {parts[0]}")
    if key_path in _ENUM_PATHS and value not in _ENUM_PATHS[key_path]:
        raise ValueError(f"{key_path} 取值非法: {value!r}，应属于 {sorted(_ENUM_PATHS[key_path])}")
    node = txn.state
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"路径不存在: {key_path}（在 {part!r} 处中断）")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"路径不是对象，无法设置: {key_path}")
    node[parts[-1]] = value
    if log:
        txn.log(f"set:{key_path}", {"value": value})
    else:
        txn.touch()


def milestone_in(txn: Txn, milestone_id: str, field: str, status: str) -> None:
    """事务内改 milestone 子状态（事件名与 set_milestone_field 相同）。值没变时不记事件。"""
    if field not in MILESTONE_FIELDS:
        raise ValueError(f"非法 milestone 字段: {field}，应属于 {sorted(MILESTONE_FIELDS)}")
    if status not in MILESTONE_STATUS_VALUES:
        raise ValueError(f"非法 milestone 状态: {status}，应属于 {sorted(MILESTONE_STATUS_VALUES)}")
    target = next((m for m in txn.state.get("milestones", []) if m.get("id") == milestone_id), None)
    if target is None:
        known = [m.get("id") for m in txn.state.get("milestones", [])]
        raise ValueError(f"未找到 milestone: {milestone_id!r}，已存在: {known}")
    if target.get(field) == status:
        return
    target[field] = status
    txn.log(f"milestone:{milestone_id}:{field}:{status}")


def gate_in(txn: Txn, stage: str, verdict: str, checks: list) -> dict[str, Any] | None:
    """事务内给门禁入账（v2）。连败到阈值时开熔断检查点并返回它。"""
    if verdict not in GATE_VERDICT_VALUES:
        raise ValueError(f"非法 verdict: {verdict}，应属于 {sorted(GATE_VERDICT_VALUES)}")
    state = txn.state
    ts = now_iso()
    gate = {"stage": stage, "checks": checks, "verdict": verdict, "timestamp": ts}
    slim = dict(gate, checks=_strip_check_details(checks))
    state["gates"] = _latest_gate_per_stage(state["gates"] + [slim])
    state["gate_latest"][stage] = _gate_latest_entry(gate)
    _update_fail_streak(state["counters"].setdefault("gate_fail_streak", {}), stage, checks)
    txn.log(f"gate:{stage}", {"verdict": verdict, "checks": checks}, ts)
    if verdict == "FAIL" and state.get("status") == "running":
        return _trip_breaker(txn, stage)
    return None


def init_state(
    root: Path,
    report_id: str,
    pdf_path: str,
    mode: str = "auto",
    max_iter: int | None = None,
    legacy: bool = False,
    reproduction_mode: str = "strict",
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    if mode not in MODE_VALUES:
        raise ValueError(f"非法 mode: {mode}，应属于 {sorted(MODE_VALUES)}")
    if reproduction_mode not in REPRODUCTION_MODE_VALUES:
        raise ValueError(f"非法 reproduction_mode: {reproduction_mode}，应属于 {sorted(REPRODUCTION_MODE_VALUES)}")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"非法 schema_version: {schema_version}，应属于 {sorted(SUPPORTED_SCHEMA_VERSIONS)}")

    for d in (
        workspace_dir(root, report_id) / "spec",
        workspace_dir(root, report_id) / "audit",
        workspace_dir(root, report_id) / "iterations",
        output_dir(root, report_id) / "results",
        src_dir(root, report_id),
    ):
        d.mkdir(parents=True, exist_ok=True)

    pdf_path_norm = _normalize_pdf_path(root, pdf_path)
    state = default_state(report_id, pdf_path_norm, root, mode=mode, max_iter=max_iter, reproduction_mode=reproduction_mode)

    if legacy:
        ts = state["updated_at"]
        for stage in STAGE_ORDER:
            state["stages"][stage]["status"] = "skipped"
            state["stages"][stage]["updated_at"] = ts
        state["status"] = "done"
        state["current_stage"] = STAGE_ORDER[-1]
        state["events"].append({"event": "state:init_legacy", "timestamp": ts, "payload": None})

    with case_lock(root, report_id):
        if schema_version == SCHEMA_VERSION_V2:
            head = write_event_log(
                events_path(root, report_id),
                [(e["timestamp"], e["event"], e["payload"]) for e in state["events"]],
            )
            state["schema_version"] = SCHEMA_VERSION_V2
            state.update(default_v2_fields())
            state["events_head"] = head
        save_state(root, report_id, state)
    return state


def _ts_sort_key(ts: Any) -> tuple[int, Any]:
    """时间戳排序键：能解析成带时区的时间就按时间比，否则退回按字符串比。"""
    if isinstance(ts, str):
        try:
            # Python 3.10 的 fromisoformat 不认结尾的 Z，先换成等价的偏移写法
            parsed = datetime.fromisoformat(ts[:-1] + "+00:00" if ts.endswith("Z") else ts)
        except ValueError:
            return (1, ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TZ_CN)
        return (0, parsed.timestamp())
    return (1, "")


def _merge_history(events: list[dict[str, Any]], gates: list[dict[str, Any]]) -> list[tuple[str | None, str, Any]]:
    """把 v1 的事件列表与门禁列表按时间归并成一条时间线。

    两个列表各自都是按发生先后追加的，所以做两路归并：事件保持原有相对顺序，
    门禁按时间戳插到第一个晚于它的事件之前。没有时间戳的事件不参与比较。
    """
    timeline: list[tuple[str | None, str, Any]] = []
    pending = [g for g in gates if isinstance(g, dict)]
    gi = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        ets = event.get("timestamp")
        if isinstance(ets, str):
            ekey = _ts_sort_key(ets)
            while gi < len(pending):
                gkey = _ts_sort_key(pending[gi].get("timestamp"))
                # 同一秒内门禁排在事件之前：实际流程是先记门禁、再把阶段置为 done
                if gkey[0] != ekey[0] or gkey[1] > ekey[1]:
                    break
                gate = pending[gi]
                timeline.append(
                    (gate.get("timestamp"), f"gate:{gate.get('stage')}", {"verdict": gate.get("verdict"), "checks": gate.get("checks")})
                )
                gi += 1
        timeline.append((ets, str(event.get("event")), event.get("payload")))
    for gate in pending[gi:]:
        timeline.append(
            (gate.get("timestamp"), f"gate:{gate.get('stage')}", {"verdict": gate.get("verdict"), "checks": gate.get("checks")})
        )
    return timeline


def migrate_to_v2(root: Path, report_id: str, dry_run: bool = False) -> dict[str, Any]:
    """把 v1 案例升级为 v2：完整历史写入 events.jsonl，state 只留最近事件与各阶段最新门禁。

    幂等：已是 v2 时不动。首次迁移把原文件备份为 state.v1.json。dry_run 只返回会怎么改。
    """
    with case_lock(root, report_id):
        state = load_state(root, report_id)
        if is_v2(state):
            return {"report_id": report_id, "migrated": False, "reason": "already_v2"}
        errors = validate_state(state)
        if errors:
            raise StateValidationError("迁移前 state.json 校验失败:\n" + "\n".join(f"- {e}" for e in errors))

        events = state.get("events") or []
        gates = state.get("gates") or []
        timeline = _merge_history(events, gates)
        kept_gates = _latest_gate_per_stage(gates)
        streak: dict[str, int] = {}
        for gate in gates:
            _update_fail_streak(streak, str(gate.get("stage")), gate.get("checks") or [])

        summary: dict[str, Any] = {
            "report_id": report_id,
            "migrated": not dry_run,
            "events": len(events),
            "gates": len(gates),
            "log_records": len(timeline) + 1,  # 另加一条 migrate:v2
            "state_events_kept": min(len(events) + 1, STATE_EVENTS_KEEP),
            "state_gates_kept": len(kept_gates),
            "gate_fail_streak": dict(streak),
        }
        if dry_run:
            summary["reason"] = "dry_run"
            return summary

        spath = state_path(root, report_id)
        backup = spath.with_name("state.v1.json")
        if not backup.exists():
            shutil.copy2(spath, backup)
        summary["backup"] = _rel(root, backup)

        head = write_event_log(events_path(root, report_id), timeline)
        state["schema_version"] = SCHEMA_VERSION_V2
        state.update(default_v2_fields())
        state["events_head"] = head
        state["gates"] = kept_gates
        state["gate_latest"] = {str(g.get("stage")): _gate_latest_entry(g) for g in kept_gates}
        state["counters"]["gate_fail_streak"] = streak
        del state["events"][:-STATE_EVENTS_KEEP]
        ts = now_iso()
        state["updated_at"] = ts
        migrate_payload: dict[str, Any] = {"events": len(events), "gates": len(gates)}

        # 在途的阶段钉在执行卡上跑完，下一阶段起才交给内核；已收尾的案例不用钉
        current = state.get("current_stage")
        current_status = (state["stages"].get(current) or {}).get("status")
        if (
            state.get("status") not in TERMINAL_STATUSES
            and current in STAGE_ORDER
            and current != "review"
            and current_status in {"running", "failed", "blocked"}
        ):
            state["flow"]["pinned"][current] = {
                "mode": "card",
                "reason": "legacy_inflight：迁移时这个阶段已经在执行卡驱动下进行到一半",
                "at": ts,
            }
            summary["pinned"] = current
            migrate_payload["pinned"] = current
        # 等待态必须对应一个待决的人工检查点，否则迁移之后没有合法出口。
        # 这个检查点是迁移补出来的，不单独记事件（迁移不算业务动作，不能刷新「等了多久」）。
        if state.get("status") in WAITING_STATUSES:
            txn = Txn(root, report_id, state, "flow:migrate")
            review = state.get("status") == "awaiting_review"
            cp = open_checkpoint_in(
                txn,
                "final_review" if review else "legacy_pause",
                stage="review" if review else current,
                reason="迁移前已在等待评审" if review else (str(state.get("pending_question") or "") or "迁移前已暂停，等人处理"),
                options=[
                    {"key": "accept", "label": "通过并收尾（flow accept）"},
                    {"key": "revise", "label": "修改假设后定向重跑（flow revise）"},
                    {"key": "abort", "label": "终止"},
                ]
                if review
                else [{"key": "continue", "label": "已处理，继续"}, {"key": "abort", "label": "终止"}],
                pause_status=None,
            )
            cp["prev_status"] = "running"
            summary["checkpoint"] = cp["id"]
            migrate_payload["checkpoint"] = {"id": cp["id"], "name": cp["name"]}
        _log_event(root, report_id, state, "migrate:v2", migrate_payload, ts)
        save_state(root, report_id, state)
        return summary


def migrate_stages(root: Path, report_id: str) -> list[str]:
    """STAGE_ORDER 演进后的旧 state 补键迁移。

    对 STAGE_ORDER 中缺失的 stage 补默认条目：顶层 status 已终态
    （done / done_partial / aborted）时补 skipped（不影响终态语义），
    否则补 pending。幂等：无缺键时不写文件。
    """
    with case_lock(root, report_id):
        state = load_state(root, report_id)
        terminal = state.get("status") in {"done", "done_partial", "aborted"}
        added: list[str] = []
        if "reproduction_mode" not in state:
            state["reproduction_mode"] = "strict"
            added.append("reproduction_mode=strict")
        for stage in STAGE_ORDER:
            if stage not in state.get("stages", {}):
                entry = _default_stage_entry()
                if terminal:
                    entry["status"] = "skipped"
                state["stages"][stage] = entry
                added.append(stage)
        if added:
            _log_event(
                root,
                report_id,
                state,
                "migrate_stages",
                {"added": added, "as": "skipped" if terminal else "pending"},
                now_iso(),
            )
            state["updated_at"] = now_iso()
            save_state(root, report_id, state)
    return added


def _guard_running(root: Path, report_id: str, state: dict[str, Any], actor: str, what: dict[str, Any]) -> None:
    """v2 案例在等待态或终态下，命令行不能改阶段、milestone 这类推进用的状态。"""
    if not is_v2(state) or is_privileged(actor) or state.get("status") == "running":
        return
    _reject(
        root,
        report_id,
        state,
        dict(what, status=state.get("status"), actor=actor),
        f"案例当前状态是 {state.get('status')}，不能直接改推进状态；等待态由人经 flow decide / flow accept / flow revise 放行后再继续。",
    )


def set_stage(root: Path, report_id: str, stage: str, status: str, actor: str = "cli") -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知 stage: {stage}，应属于 {STAGE_ORDER}")
    if status not in STAGE_STATUS_VALUES:
        raise ValueError(f"非法 stage status: {status}，应属于 {sorted(STAGE_STATUS_VALUES)}")

    with case_lock(root, report_id):
        state = load_state(root, report_id)
        _guard_running(root, report_id, state, actor, {"op": "set-stage", "stage": stage, "to": status})
        ts = now_iso()
        entry = state["stages"].setdefault(stage, _default_stage_entry())
        entry["status"] = status
        entry["updated_at"] = ts
        if status == "running":
            entry["attempts"] = int(entry.get("attempts", 0)) + 1

        state["current_stage"] = stage
        state["updated_at"] = ts
        _log_event(root, report_id, state, f"stage:{stage}:{status}", None, ts)
        save_state(root, report_id, state)
    return state


_ENUM_PATHS: dict[str, set] = {
    "mode": MODE_VALUES,
    "status": TOP_STATUS_VALUES,
    "difficulty": DIFFICULTY_VALUES,
    "difficulty_override": DIFFICULTY_VALUES,
    "type": TYPE_VALUES,
    "feasibility": FEASIBILITY_VALUES,
    "verdict.result": VERDICT_RESULT_VALUES,
}


def _parse_cli_value(raw: str) -> Any:
    """`set` 命令的取值尝试 JSON 解析，失败则原样当字符串。"""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _guard_set(root: Path, report_id: str, state: dict[str, Any], key_path: str, value: Any, actor: str) -> None:
    """v2 案例的两条写入守卫：内核字段只能由内核改；离开等待态、进入收尾态只能经合法出口。"""
    if not is_v2(state) or is_privileged(actor):
        return
    top_key = key_path.split(".")[0]
    if top_key in KERNEL_OWNED_FIELDS:
        _reject(
            root,
            report_id,
            state,
            {"op": "set", "key": key_path, "actor": actor},
            f"{top_key} 归内核管理，不能用 state.py set 直接改；请用对应的 flow 命令。",
        )
    if key_path != "status":
        return
    current = state.get("status")
    if value == current:
        return
    leaving_gate = current in WAITING_STATUSES or current in TERMINAL_STATUSES
    entering_final = value in {"done", "done_partial"}
    if leaving_gate or entering_final:
        _reject(
            root,
            report_id,
            state,
            {"op": "set", "key": "status", "from": current, "to": value, "actor": actor},
            f"状态不能从 {current} 直接改成 {value}。等待态要由人放行：flow decide（检查点）、flow accept（收尾）、"
            "flow revise（定向重跑）、flow reopen（回退重开）。",
        )


def set_field(root: Path, report_id: str, key_path: str, raw_value: str, actor: str = "cli") -> dict[str, Any]:
    with case_lock(root, report_id):
        state = load_state(root, report_id)
        parts = key_path.split(".")
        top_key = parts[0]
        if top_key not in state:
            raise ValueError(f"未知顶层字段: {top_key}（不允许通过 set 新增未声明字段）")

        value = _parse_cli_value(raw_value)
        if key_path in _ENUM_PATHS and value not in _ENUM_PATHS[key_path]:
            raise ValueError(f"{key_path} 取值非法: {value!r}，应属于 {sorted(_ENUM_PATHS[key_path])}")
        _guard_set(root, report_id, state, key_path, value, actor)

        node = state
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                raise ValueError(f"路径不存在: {key_path}（在 {part!r} 处中断）")
            node = node[part]
        if not isinstance(node, dict):
            raise ValueError(f"路径不是对象，无法设置: {key_path}")
        node[parts[-1]] = value

        ts = now_iso()
        state["updated_at"] = ts
        _log_event(root, report_id, state, f"set:{key_path}", {"value": value}, ts)
        save_state(root, report_id, state)
    return state


def record_event(root: Path, report_id: str, event: str, payload: Any = None, actor: str = "cli") -> dict[str, Any]:
    with case_lock(root, report_id):
        state = load_state(root, report_id)
        if is_v2(state) and not is_privileged(actor) and is_reserved_event(event):
            _reject(
                root,
                report_id,
                state,
                {"op": "record-event", "event": event, "actor": actor},
                f"事件名 {event!r} 是内核与人工放行专用的，不能用 record-event 写入。",
            )
        ts = now_iso()
        _log_event(root, report_id, state, event, payload, ts)
        state["updated_at"] = ts
        save_state(root, report_id, state)
    return state


def set_milestone_field(
    root: Path, report_id: str, milestone_id: str, field: str, status: str, actor: str = "cli"
) -> dict[str, Any]:
    if field not in MILESTONE_FIELDS:
        raise ValueError(f"非法 milestone 字段: {field}，应属于 {sorted(MILESTONE_FIELDS)}")
    if status not in MILESTONE_STATUS_VALUES:
        raise ValueError(f"非法 milestone 状态: {status}，应属于 {sorted(MILESTONE_STATUS_VALUES)}")

    with case_lock(root, report_id):
        state = load_state(root, report_id)
        _guard_running(root, report_id, state, actor, {"op": "milestone", "milestone": milestone_id, "field": field, "to": status})
        target = None
        for m in state.get("milestones", []):
            if m.get("id") == milestone_id:
                target = m
                break
        if target is None:
            known = [m.get("id") for m in state.get("milestones", [])]
            raise ValueError(f"未找到 milestone: {milestone_id!r}，已存在: {known}")

        target[field] = status
        ts = now_iso()
        state["updated_at"] = ts
        _log_event(root, report_id, state, f"milestone:{milestone_id}:{field}:{status}", None, ts)
        save_state(root, report_id, state)
    return state


def record_gate(root: Path, report_id: str, stage: str, verdict: str, checks: list) -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知 stage: {stage}，应属于 {STAGE_ORDER}")
    if verdict not in GATE_VERDICT_VALUES:
        raise ValueError(f"非法 verdict: {verdict}，应属于 {sorted(GATE_VERDICT_VALUES)}")
    if not isinstance(checks, list):
        raise ValueError("checks 必须是数组")

    with case_lock(root, report_id):
        state = load_state(root, report_id)
        ts = now_iso()
        gate = {"stage": stage, "checks": checks, "verdict": verdict, "timestamp": ts}
        state["updated_at"] = ts
        if is_v2(state):
            # v2：完整门禁历史（含未通过项明细全文）进 events.jsonl；state 只留各阶段最新一条，
            # 未通过项的明细截短后放在 gate_latest，并累计连败次数
            slim = dict(gate, checks=_strip_check_details(checks))
            state["gates"] = _latest_gate_per_stage(state["gates"] + [slim])
            state["gate_latest"][stage] = _gate_latest_entry(gate)
            _update_fail_streak(state["counters"].setdefault("gate_fail_streak", {}), stage, checks)
            _log_event(root, report_id, state, f"gate:{stage}", {"verdict": verdict, "checks": checks}, ts)
            if verdict == "FAIL" and state.get("status") == "running":
                # 熔断放在状态层：阶段不管由内核还是由执行卡推进，连败到阈值都会停下
                txn = Txn(root, report_id, state, "flow:breaker")
                if _trip_breaker(txn, stage) is not None:
                    for event, payload, ets in txn._events:
                        _log_event(root, report_id, state, event, payload, ets)
        else:
            state["gates"].append(gate)
        save_state(root, report_id, state)
    return state


def show_summary(root: Path, report_id: str) -> str:
    state = load_state(root, report_id)
    lines: list[str] = []
    lines.append(f"report_id: {state['report_id']}")
    override = state.get("difficulty_override")
    override_note = f"（override={override}）" if override else ""
    lines.append(
        f"当前 stage: {state['current_stage']}   顶层状态: {state['status']}   "
        f"mode: {state['mode']}"
    )
    lines.append(
        f"type: {state.get('type')}   tags: {state.get('tags')}   "
        f"difficulty: {state.get('difficulty')}{override_note}   feasibility: {state.get('feasibility')}"
    )
    lines.append("stage 状态:")
    for stage in STAGE_ORDER:
        entry = state["stages"].get(stage, {})
        lines.append(
            f"  - {stage:12s} {str(entry.get('status')):8s} "
            f"attempts={entry.get('attempts', 0)} updated_at={entry.get('updated_at')}"
        )
    it = state.get("iteration", {})
    lines.append(f"迭代: current={it.get('current')} max={it.get('max')}")
    verdict = state.get("verdict", {})
    lines.append(
        f"verdict: result={verdict.get('result')} "
        f"metrics_pass/total={verdict.get('metrics_pass')}/{verdict.get('metrics_total')}"
    )
    blockers = state.get("blockers") or []
    lines.append(f"blockers: {blockers if blockers else '无'}")
    pending_question = state.get("pending_question")
    lines.append(f"pending_question: {pending_question if pending_question else '无'}")

    if state.get("status") == "running":
        updated_at = state.get("updated_at")
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at)
                delta = datetime.now(dt.tzinfo) - dt
                if delta < timedelta(minutes=10):
                    lines.append("")
                    lines.append(
                        f"警告: 状态为 running 且 {int(delta.total_seconds())} 秒前刚更新，"
                        "疑似另一会话在跑，请勿并行操作同一 report_id。"
                    )
            except ValueError:
                pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 案例统一编号（rNNN_<slug>）：next-id 分配 / resolve 缩写解析，均为只读
# ---------------------------------------------------------------------------

ID_NUMBER_RE = re.compile(r"^r(\d{3})_")
SLUG_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")


def list_case_ids(root: Path) -> list[str]:
    """workspace/ 下含 state.json 的目录名（即全部案例 id），按名排序。"""
    ws = root / "workspace"
    if not ws.is_dir():
        return []
    return sorted(d.name for d in ws.iterdir() if d.is_dir() and (d / "state.json").is_file())


def next_numbered_id(root: Path, slug: str) -> str:
    """分配下一个统一编号 id：rNNN_<slug>，NNN 取现存最大编号 +1（无编号案例时从 r001）。

    只扫描不写盘；并发起两个新案例不在设计内（编号在 init 落盘时才被占用）。
    """
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"slug 不合法（需小写字母开头的 snake_case、≤40 字符）: {slug!r}")
    nums = [int(m.group(1)) for name in list_case_ids(root) if (m := ID_NUMBER_RE.match(name))]
    return f"r{(max(nums) + 1 if nums else 1):03d}_{slug}"


def resolve_case_id(root: Path, query: str) -> str:
    """把用户输入解析为唯一 report_id：完整 id > 编号缩写（r3 / r003 / 3）> 唯一前缀。

    id 均为字母开头（snake_case），纯数字输入不会与目录名歧义。
    零命中或多命中一律 ValueError（多命中时列出候选，让用户加长前缀）。
    """
    ids = list_case_ids(root)
    if query in ids:
        return query
    m = re.fullmatch(r"r?0*(\d+)", query)
    hits = [i for i in ids if i.startswith(f"r{int(m.group(1)):03d}_")] if m else []
    if not hits:  # 编号零命中（或非数字输入）→ 一般前缀匹配兜底，如 r00 是打一半的前缀而非编号 0
        hits = [i for i in ids if i.startswith(query)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"未找到匹配案例: {query!r}（现有: {', '.join(ids) if ids else '无'}）")
    raise ValueError(f"匹配到多个案例，请用更长前缀: {', '.join(hits)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="state.json 唯一写入口（研报复现系统 v2）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化 workspace 骨架与 state.json")
    p_init.add_argument("report_id")
    p_init.add_argument("--pdf", required=True, dest="pdf_path")
    p_init.add_argument("--mode", choices=sorted(MODE_VALUES), default="auto")
    p_init.add_argument("--max-iter", type=int, default=None, dest="max_iter")
    p_init.add_argument("--experimental", action="store_true", help="实验模式：市场迁移复现（等价数据替代，数值判定豁免，报告显著声明）")
    p_init.add_argument("--legacy", action="store_true")

    p_show = sub.add_parser("show", help="打印人读摘要")
    p_show.add_argument("report_id")

    p_set_stage = sub.add_parser("set-stage", help="更新 stage 状态")
    p_set_stage.add_argument("report_id")
    p_set_stage.add_argument("stage")
    p_set_stage.add_argument("status")

    p_set = sub.add_parser("set", help="设置顶层/嵌套字段（value 尝试 JSON 解析）")
    p_set.add_argument("report_id")
    p_set.add_argument("key")
    p_set.add_argument("value")

    p_event = sub.add_parser("record-event", help="追加事件")
    p_event.add_argument("report_id")
    p_event.add_argument("event")
    p_event.add_argument("--json", dest="payload_json", default=None)

    p_milestone = sub.add_parser("milestone", help="更新 milestone 子状态")
    p_milestone.add_argument("report_id")
    p_milestone.add_argument("milestone_id")
    p_milestone.add_argument("field", choices=sorted(MILESTONE_FIELDS))
    p_milestone.add_argument("status")

    p_migrate = sub.add_parser("migrate", help="STAGE_ORDER 演进后补齐旧 state 缺失的 stage 键（幂等）")
    p_migrate.add_argument("report_id")

    p_gate = sub.add_parser("gate", help="追加门禁记录")
    p_gate.add_argument("report_id")
    p_gate.add_argument("stage")
    p_gate.add_argument("verdict")
    p_gate.add_argument("--checks", required=True, help="JSON 数组: [{id,desc,result}, ...]")

    p_next = sub.add_parser("next-id", help="分配下一个统一编号案例 id（rNNN_<slug>，只读不占号）")
    p_next.add_argument("--slug", required=True, help="语义后缀，小写 snake_case（如 style_factor）")

    p_resolve = sub.add_parser("resolve", help="解析案例 id：完整 id / 编号缩写（r3、r003、3）/ 唯一前缀（只读）")
    p_resolve.add_argument("query")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = default_root()
    try:
        if args.command == "init":
            state = init_state(
                root,
                args.report_id,
                args.pdf_path,
                mode=args.mode,
                max_iter=args.max_iter,
                legacy=args.legacy,
                reproduction_mode="experimental" if args.experimental else "strict",
            )
            print(f"已初始化 {args.report_id}: {state_path(root, args.report_id)}")
            print(f"status={state['status']} current_stage={state['current_stage']}")
        elif args.command == "show":
            print(show_summary(root, args.report_id))
        elif args.command == "set-stage":
            state = set_stage(root, args.report_id, args.stage, args.status)
            entry = state["stages"][args.stage]
            print(f"stage={args.stage} status={args.status} attempts={entry['attempts']}")
        elif args.command == "set":
            set_field(root, args.report_id, args.key, args.value)
            print(f"已设置 {args.key}")
        elif args.command == "record-event":
            payload = json.loads(args.payload_json) if args.payload_json else None
            record_event(root, args.report_id, args.event, payload)
            print(f"已记录事件: {args.event}")
        elif args.command == "milestone":
            set_milestone_field(root, args.report_id, args.milestone_id, args.field, args.status)
            print(f"milestone={args.milestone_id} {args.field}={args.status}")
        elif args.command == "migrate":
            added = migrate_stages(root, args.report_id)
            print(f"已补齐 stage 键: {added}" if added else "无需迁移（stage 键完整）")
        elif args.command == "gate":
            checks = json.loads(args.checks)
            record_gate(root, args.report_id, args.stage, args.verdict, checks)
            print(f"已记录门禁: stage={args.stage} verdict={args.verdict}")
        elif args.command == "next-id":
            print(next_numbered_id(root, args.slug))
        elif args.command == "resolve":
            print(resolve_case_id(root, args.query))
        else:  # pragma: no cover - argparse 已保证 command 合法
            raise ValueError(f"未知命令: {args.command}")
    except (ValueError, FileNotFoundError, StateValidationError, StateLockTimeout, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
