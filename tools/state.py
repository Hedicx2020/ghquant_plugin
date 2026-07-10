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

设计要点：
    - 原子写：临时文件写入 + os.replace 原子替换，异常时清理残留临时文件。
    - 每次落盘前校验 schema（字段齐全、枚举合法），非法状态一律拒绝写入。
    - 时间戳统一 ISO8601 + 北京时区 (+08:00)。
    - 路径一律存为相对仓库根的 POSIX 风格字符串。
    - 子 agent 不得导入本模块；仅供主会话与 tools/check_gates.py 调用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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

SCHEMA_VERSION = 1

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


def validate_state(state: Any) -> list[str]:
    """返回校验错误列表；空列表代表合法。不抛异常，便于 check_gates 复用。"""
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state 必须是 JSON 对象"]

    missing = CANONICAL_TOP_FIELDS - state.keys()
    if missing:
        errors.append(f"缺少顶层字段: {sorted(missing)}")
    extra = state.keys() - CANONICAL_TOP_FIELDS
    if extra:
        errors.append(f"存在未声明的顶层字段: {sorted(extra)}")

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
# 核心操作（供 CLI 与 check_gates.py 复用）
# ---------------------------------------------------------------------------


def init_state(
    root: Path,
    report_id: str,
    pdf_path: str,
    mode: str = "auto",
    max_iter: int | None = None,
    legacy: bool = False,
    reproduction_mode: str = "strict",
) -> dict[str, Any]:
    if mode not in MODE_VALUES:
        raise ValueError(f"非法 mode: {mode}，应属于 {sorted(MODE_VALUES)}")
    if reproduction_mode not in REPRODUCTION_MODE_VALUES:
        raise ValueError(f"非法 reproduction_mode: {reproduction_mode}，应属于 {sorted(REPRODUCTION_MODE_VALUES)}")

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

    save_state(root, report_id, state)
    return state


def migrate_stages(root: Path, report_id: str) -> list[str]:
    """STAGE_ORDER 演进后的旧 state 补键迁移。

    对 STAGE_ORDER 中缺失的 stage 补默认条目：顶层 status 已终态
    （done / done_partial / aborted）时补 skipped（不影响终态语义），
    否则补 pending。幂等：无缺键时不写文件。
    """
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
        state["events"].append({
            "event": "migrate_stages",
            "timestamp": now_iso(),
            "payload": {"added": added, "as": "skipped" if terminal else "pending"},
        })
        state["updated_at"] = now_iso()
        save_state(root, report_id, state)
    return added


def set_stage(root: Path, report_id: str, stage: str, status: str) -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知 stage: {stage}，应属于 {STAGE_ORDER}")
    if status not in STAGE_STATUS_VALUES:
        raise ValueError(f"非法 stage status: {status}，应属于 {sorted(STAGE_STATUS_VALUES)}")

    state = load_state(root, report_id)
    ts = now_iso()
    entry = state["stages"].setdefault(stage, _default_stage_entry())
    entry["status"] = status
    entry["updated_at"] = ts
    if status == "running":
        entry["attempts"] = int(entry.get("attempts", 0)) + 1

    state["current_stage"] = stage
    state["updated_at"] = ts
    state["events"].append({"event": f"stage:{stage}:{status}", "timestamp": ts, "payload": None})
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


def set_field(root: Path, report_id: str, key_path: str, raw_value: str) -> dict[str, Any]:
    state = load_state(root, report_id)
    parts = key_path.split(".")
    top_key = parts[0]
    if top_key not in state:
        raise ValueError(f"未知顶层字段: {top_key}（不允许通过 set 新增未声明字段）")

    value = _parse_cli_value(raw_value)
    if key_path in _ENUM_PATHS and value not in _ENUM_PATHS[key_path]:
        raise ValueError(f"{key_path} 取值非法: {value!r}，应属于 {sorted(_ENUM_PATHS[key_path])}")

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
    state["events"].append({"event": f"set:{key_path}", "timestamp": ts, "payload": {"value": value}})
    save_state(root, report_id, state)
    return state


def record_event(root: Path, report_id: str, event: str, payload: Any = None) -> dict[str, Any]:
    state = load_state(root, report_id)
    ts = now_iso()
    state["events"].append({"event": event, "timestamp": ts, "payload": payload})
    state["updated_at"] = ts
    save_state(root, report_id, state)
    return state


def set_milestone_field(root: Path, report_id: str, milestone_id: str, field: str, status: str) -> dict[str, Any]:
    if field not in MILESTONE_FIELDS:
        raise ValueError(f"非法 milestone 字段: {field}，应属于 {sorted(MILESTONE_FIELDS)}")
    if status not in MILESTONE_STATUS_VALUES:
        raise ValueError(f"非法 milestone 状态: {status}，应属于 {sorted(MILESTONE_STATUS_VALUES)}")

    state = load_state(root, report_id)
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
    state["events"].append({"event": f"milestone:{milestone_id}:{field}:{status}", "timestamp": ts, "payload": None})
    save_state(root, report_id, state)
    return state


def record_gate(root: Path, report_id: str, stage: str, verdict: str, checks: list) -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知 stage: {stage}，应属于 {STAGE_ORDER}")
    if verdict not in GATE_VERDICT_VALUES:
        raise ValueError(f"非法 verdict: {verdict}，应属于 {sorted(GATE_VERDICT_VALUES)}")
    if not isinstance(checks, list):
        raise ValueError("checks 必须是数组")

    state = load_state(root, report_id)
    ts = now_iso()
    state["gates"].append({"stage": stage, "checks": checks, "verdict": verdict, "timestamp": ts})
    state["updated_at"] = ts
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
        else:  # pragma: no cover - argparse 已保证 command 合法
            raise ValueError(f"未知命令: {args.command}")
    except (ValueError, FileNotFoundError, StateValidationError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
