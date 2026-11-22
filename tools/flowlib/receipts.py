"""回执：子 agent 把回填内容写进回执，内核核对后合并进覆盖矩阵与假设登记簿。

回执是 agent 的自述，只用于路由（验证过没过、审计有没有 critical）与回填；放行只认门禁。
直接改表的旧做法兼容一个版本：没有回执、或回执里没有回填内容时，内核什么都不合并。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import mdslice as ms
from . import packs
from .core import Ctx, write_text
from .tasks import RECEIPT_FIELDS

MATRIX_REL = "spec/coverage_matrix.md"
ASSUMPTIONS_REL = "assumptions.md"
PLACEHOLDER = "[verify 后填]"

# 各角色可以改的矩阵列
MATRIX_COLUMNS = {
    "quant-coder": {"实现位置", "状态", "状态理由"},
    "quant-verifier": {"验证结果", "状态", "状态理由"},
    "quant-diagnoser": {"状态", "状态理由"},
}
STATUS_VALUES = {"pending", "in_progress", "done", "skipped", "infeasible"}
REASON_CODES = ("data_missing", "method_underspecified", "out_of_scope", "cost_prohibitive", "reference_only")
IMPACT_VALUES = {"data", "method", "param", "trading", "output"}
NEW_REQUIRED = ("假设内容", "影响面")
_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_LIST_SPLIT_RE = re.compile(r"[,，、;；/+＋]|\s+")


def impact_parts(value: Any) -> list[str]:
    """把「影响面」拆成各个面。一条假设可以跨几个面，登记簿里常写成「method、data」。去重，保持原顺序。"""
    return list(dict.fromkeys(part for part in _LIST_SPLIT_RE.split(str(value or "").strip()) if part))


def normalize_impact(value: Any) -> Optional[str]:
    """影响面的规范写法（各面用顿号并列）。什么都没写，或有不在枚举里的面，返回 None。"""
    parts = impact_parts(value)
    return "、".join(parts) if parts and all(part in IMPACT_VALUES for part in parts) else None


def normalize_binding(value: Any) -> Optional[str]:
    """参数绑定的规范写法：config.py 里的字段名，多个用英文逗号隔开。带了取值、说明等别的东西返回 None。"""
    parts = list(dict.fromkeys(part for part in re.split(r"[,，、;；]|\s+", str(value or "").strip()) if part))
    return ", ".join(parts) if parts and all(_FIELD_NAME_RE.fullmatch(part) for part in parts) else None


BINDING_RULE = "参数绑定只写 config.py 里的字段名，多个用英文逗号隔开，取值和说明写进假设内容"
IMPACT_RULE = f"影响面取 {' / '.join(sorted(IMPACT_VALUES))}，一条假设跨几个面时用顿号并列"
NEW_FIELD_ORDER = ("来源", "假设内容", "行业惯例依据", "参数绑定", "影响面", "影响 milestone", "影响指标", "预期影响", "验证后回看", "状态", "高亮等级")


class ReceiptError(ValueError):
    """回执不合法（格式不对，或要改的东西不归这一步）。reasons 逐条说明。"""

    def __init__(self, reasons: list[str]):
        super().__init__("；".join(reasons))
        self.reasons = reasons


@dataclass
class Merge:
    """一次合并的结果。"""

    matrix_rows: list[str] = field(default_factory=list)
    lookbacks: list[str] = field(default_factory=list)
    bindings: list[str] = field(default_factory=list)
    new_assumptions: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)  # 路由用的结论（verify / audit / diagnosis / skip）
    status: str = "done"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in self.__dict__.items() if v}
        out["status"] = self.status
        return out


def load(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ReceiptError([f"回执不是合法的 JSON：{exc}"]) from exc
    if not isinstance(data, dict):
        raise ReceiptError(["回执顶层必须是 JSON 对象"])
    return data


def _legal_transition(old: str, new: str, stage: str) -> bool:
    if old == new:
        return True
    if new in ("skipped", "infeasible"):
        return old in ("pending", "in_progress", "")
    if old == "done":
        return new == "in_progress" and stage in ("iterate", "result_audit", "implement", "code_audit")
    return (old or "pending", new) in {("pending", "in_progress"), ("pending", "done"), ("in_progress", "done")}


def _render_row(header: list[str], cells: dict[str, str], newline: str) -> str:
    values = [str(cells.get(col, "")).replace("\n", " ").replace("|", "\\|").strip() for col in header]
    return "| " + " | ".join(values) + " |" + newline


def _column(header: list[str], name: str) -> Optional[str]:
    """按列名找表头里的列：先精确，再退化为「列名含关键词」。"""
    if name in header:
        return name
    return next((col for col in header if name in col), None)


def merge_matrix(ctx: Ctx, updates: list[dict[str, Any]], *, role: str, stage: str, allowed_ids: Optional[set[str]]) -> tuple[str, list[str]]:
    """把行更新并进矩阵文本，返回（新文本, 改过的要素编号）。不落盘。"""
    path = ctx.path(f"{ctx.ws}/{MATRIX_REL}")
    text = ms.read_source(path)
    rows = {ms.row_get(r.cells, "要素ID"): r for r in ms.parse_table_rows(text) if ms.row_get(r.cells, "要素ID")}
    allowed_cols = MATRIX_COLUMNS.get(role, set())
    errors: list[str] = []
    edits: list[tuple[int, int, str]] = []
    changed: list[str] = []
    for item in updates:
        if not isinstance(item, dict) or not item.get("id"):
            errors.append(f"matrix 里有一项没有 id：{item!r}")
            continue
        rid = str(item["id"])
        row = rows.get(rid)
        if row is None:
            errors.append(f"覆盖矩阵里没有要素 {rid}")
            continue
        if allowed_ids is not None and rid not in allowed_ids:
            errors.append(f"要素 {rid} 不属于这一步，不能改它的矩阵行")
            continue
        header = list(row.cells.keys())
        cells = dict(row.cells)
        ok = True
        for key, value in item.items():
            if key == "id":
                continue
            col = _column(header, key)
            if col is None or key not in allowed_cols:
                errors.append(f"{rid}：这个角色不能改矩阵的「{key}」列")
                ok = False
                continue
            cells[col] = str(value)
        status_col = _column(header, "状态")
        new_status = cells.get(status_col, "") if status_col else ""
        old_status = row.cells.get(status_col, "") if status_col else ""
        if "状态" in item:
            if new_status not in STATUS_VALUES:
                errors.append(f"{rid}：状态 {new_status!r} 不合法")
                ok = False
            elif not _legal_transition(old_status, new_status, stage):
                errors.append(f"{rid}：状态不能从 {old_status or 'pending'} 改成 {new_status}")
                ok = False
            elif new_status in ("skipped", "infeasible"):
                reason = cells.get(_column(header, "状态理由") or "", "")
                if not any(reason.startswith(code) for code in REASON_CODES):
                    errors.append(f"{rid}：改 {new_status} 必须给「状态理由」，格式为 <理由码>: <一句话>，理由码取 {' / '.join(REASON_CODES)}")
                    ok = False
        if not ok:
            continue
        updated_col = _column(header, "最后更新")
        if updated_col:
            cells[updated_col] = stage
        if cells != row.cells:
            newline = "\n" if row.text.endswith("\n") else ""
            edits.append((row.start, row.end, _render_row(header, cells, newline)))
            changed.append(rid)
    if errors:
        raise ReceiptError(errors)
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, changed


def _replace_field(text: str, block: ms.Block, name: str, value: Optional[str]) -> str:
    """改写假设块里的一个字段：有就整行替换，没有就插在「假设内容」之后；value 为 None 时删掉该字段。"""
    fld = block.field(name)
    line = f"- {name}: {value}\n" if value is not None else ""
    if fld is not None:
        end = fld.end
        return text[:fld.start] + line + text[end:] if line else text[:fld.start] + text[end:].lstrip("\n")
    if not line:
        return text
    anchor = block.field("假设内容") or (block.fields[-1] if block.fields else None)
    pos = anchor.end if anchor is not None else block.heading_end
    prefix = "" if text[:pos].endswith("\n") else "\n"
    return text[:pos] + prefix + line + text[pos:]


def _find_block(text: str, as_id: str) -> Optional[ms.Block]:
    return next((b for b in ms.parse_blocks(text) if b.id == as_id), None)


def merge_assumptions(
    ctx: Ctx,
    payload: dict[str, Any],
    *,
    role: str,
    reserved: list[str],
) -> tuple[str, dict[str, list[str]]]:
    """把回看、绑定校正、新增条目并进假设登记簿文本。不落盘。"""
    path = ctx.path(f"{ctx.ws}/{ASSUMPTIONS_REL}")
    text = ms.read_source(path)
    errors: list[str] = []
    done: dict[str, list[str]] = {"lookback": [], "binding": [], "new": []}

    lookbacks = payload.get("lookback") or []
    bindings = payload.get("binding") or []
    news = payload.get("new") or []
    if lookbacks and role != "quant-verifier":
        errors.append("只有验证角色可以写「验证后回看」")
        lookbacks = []
    if bindings and role != "quant-coder":
        errors.append("只有编码角色可以校正「参数绑定」")
        bindings = []
    if news and role not in ("quant-coder", "quant-diagnoser"):
        errors.append("这个角色不能登记新假设")
        news = []

    for item in lookbacks:
        as_id, body = str((item or {}).get("id") or ""), str((item or {}).get("text") or "").strip()
        block = _find_block(text, as_id)
        if block is None:
            errors.append(f"假设登记簿里没有 {as_id or '（空编号）'}")
        elif not body or PLACEHOLDER in body:
            errors.append(f"{as_id}：回看内容为空，或者还带着占位符")
        else:
            text = _replace_field(text, block, "验证后回看", body.replace("\n", " "))
            done["lookback"].append(as_id)
    for item in bindings:
        as_id = str((item or {}).get("id") or "")
        block = _find_block(text, as_id)
        if block is None:
            errors.append(f"假设登记簿里没有 {as_id or '（空编号）'}")
            continue
        value = str((item or {}).get("参数绑定") or "").strip()
        binding = normalize_binding(value) if value else None
        if value and binding is None:
            errors.append(f"{as_id}：{BINDING_RULE}（收到 {value!r}）")
            continue
        text = _replace_field(text, block, "参数绑定", binding)
        done["binding"].append(as_id)

    existing = {b.id for b in ms.parse_blocks(text)}
    appended: list[str] = []
    for item in news:
        as_id, title = str((item or {}).get("id") or ""), str((item or {}).get("title") or "").strip()
        fields = (item or {}).get("fields") if isinstance((item or {}).get("fields"), dict) else {}
        if as_id not in reserved:
            errors.append(f"新假设的编号 {as_id or '（空）'} 不在预留给这一步的区间里（{reserved[0]}–{reserved[-1]}）" if reserved else "这一步没有预留新假设编号")
            continue
        if as_id in existing:
            errors.append(f"{as_id} 已经存在")
            continue
        missing = [name for name in NEW_REQUIRED if not str(fields.get(name) or "").strip()]
        if not title or missing:
            errors.append(f"{as_id}：新假设缺标题或必填字段 {missing}")
            continue
        impact = normalize_impact(fields.get("影响面"))
        if impact is None:
            errors.append(f"{as_id}：{IMPACT_RULE}（收到 {str(fields.get('影响面')).strip()!r}）")
            continue
        bound = str(fields.get("参数绑定") or "").strip()
        if bound and normalize_binding(bound) is None:
            errors.append(f"{as_id}：{BINDING_RULE}（收到 {bound!r}）")
            continue
        merged = {"来源": "coder 主动简化" if role == "quant-coder" else "迭代诊断", "验证后回看": PLACEHOLDER, "状态": "assumed", "高亮等级": "-"}
        merged.update({str(k): str(v).replace("\n", " ").strip() for k, v in fields.items() if v is not None and str(v).strip()})
        merged["影响面"] = impact
        if bound:
            merged["参数绑定"] = str(normalize_binding(bound))
        ordered = [name for name in NEW_FIELD_ORDER if name in merged] + [name for name in merged if name not in NEW_FIELD_ORDER]
        appended.append(f"### [{as_id}] {title}\n" + "".join(f"- {name}: {merged[name]}\n" for name in ordered))
        existing.add(as_id)
        done["new"].append(as_id)
    if errors:
        raise ReceiptError(errors)
    if appended:
        text = text.rstrip("\n") + "\n\n" + "\n".join(appended)
    return text, done


def apply(
    ctx: Ctx,
    record: dict[str, Any],
    receipt: Optional[dict[str, Any]],
    *,
    allowed_ids: Optional[set[str]] = None,
) -> Merge:
    """核对并合并一张回执。全部通过才落盘；任何一处不合法都整张拒收（抛 ReceiptError）。"""
    merge = Merge()
    if receipt is None:
        return merge
    role, stage = str(record.get("role")), str(record.get("stage"))
    allowed = RECEIPT_FIELDS.get(role, ())
    known = {"format", "step", "status", "summary", "notes"}
    errors = [f"这个角色的回执不能带「{key}」" for key in receipt if key not in known and key not in allowed]
    status = str(receipt.get("status") or "done")
    if status not in ("done", "blocked"):
        errors.append(f"status 只能是 done 或 blocked，收到 {status!r}")
    if errors:
        raise ReceiptError(errors)
    merge.status, merge.summary = status, str(receipt.get("summary") or "")[:500]

    matrix_text: Optional[str] = None
    assumptions_text: Optional[str] = None
    if receipt.get("matrix"):
        if not isinstance(receipt["matrix"], list):
            raise ReceiptError(["matrix 必须是数组"])
        matrix_text, merge.matrix_rows = merge_matrix(ctx, receipt["matrix"], role=role, stage=stage, allowed_ids=allowed_ids)
    if receipt.get("assumptions"):
        if not isinstance(receipt["assumptions"], dict):
            raise ReceiptError(["assumptions 必须是对象"])
        assumptions_text, changed = merge_assumptions(ctx, receipt["assumptions"], role=role, reserved=list(record.get("reserved") or []))
        merge.lookbacks, merge.bindings, merge.new_assumptions = changed["lookback"], changed["binding"], changed["new"]
    for key in ("verify", "audit", "diagnosis", "skip"):
        if isinstance(receipt.get(key), dict):
            merge.result[key] = receipt[key]
    verdict = (merge.result.get("verify") or {}).get("verdict")
    if "verify" in merge.result and verdict not in ("pass", "fail"):
        raise ReceiptError(["verify.verdict 只能是 pass 或 fail"])

    if matrix_text is not None and merge.matrix_rows:
        write_text(ctx.path(f"{ctx.ws}/{MATRIX_REL}"), matrix_text)
    if assumptions_text is not None and (merge.lookbacks or merge.bindings or merge.new_assumptions):
        write_text(ctx.path(f"{ctx.ws}/{ASSUMPTIONS_REL}"), assumptions_text)
    return merge


def step_element_ids(ctx: Ctx, milestone: Optional[str]) -> Optional[set[str]]:
    """这一步可以改哪些矩阵行：milestone 级的步骤只能改本步要素；全局步骤不限。"""
    if not milestone or milestone == "all":
        return None
    docs = packs.CaseDocs.load(ctx.root, ctx.report_id)
    return set(docs.step_elements(milestone))
