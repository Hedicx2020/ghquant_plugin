"""检查点审阅包：案例停下来等人决定时，内核给人看的一页纸。

每个检查点一份 markdown，放在 workspace/<id>/reviews/cp_NN_<名称>.md。内容全部由机器从文书
和产物里取：要素块、假设、矩阵行读 spec / assumptions / coverage_matrix 原文；凡是「达标数」
一律按 templates/standards.json 重算（check_gates.recalc_comparison），不采信 comparison.json
里自述的 pass。

固定结构：标题 → 为什么停在这里 → 主体（按检查点不同）→ 你可以怎么决定 → 文末声明。
每种审阅包有字节上限（PACK_LIMITS，其余默认 6KB）。超出时结论行与选项保留，明细从最长的
小节开始逐条截掉，并注明「其余 N 条见 <原文件路径>」。文书缺失的小节写「（尚无）」。

render() 是纯函数：只读文件，不写任何东西，同样的输入给出同样的输出（不带生成时间）。
write() 只写审阅包文件本身。看板（tools/board.py）复用这里的检查点中文名、默认选项和放行命令。
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from tools import check_gates as cg
from tools import state as st

from . import mdslice as ms
from .events import MILESTONE_FIELD_CN, STAGE_CN, STAGE_STATUS_CN
from .packs import CaseDocs

KB = 1024
# 方案 5.1 的上限表；表里没有的检查点走 DEFAULT_LIMIT
PACK_LIMITS: dict[str, int] = {
    "spec_final": 8 * KB,
    "plan_final": 10 * KB,
    "milestone_done": 5 * KB,
    "verify_done": 8 * KB,
    "iterate_round": 5 * KB,
    "pre_report": 6 * KB,
}
DEFAULT_LIMIT = 6 * KB
REVIEWS_DIR = "reviews"
EMPTY = "（尚无）"
FOOTER = "本文件由内核生成，数字均取自机器产物。"
FLOW = "flow"  # 命令前缀；实际调用方式见宿主适配卡（uv run python "$REPRODUCE_TOOLS/flow.py" …）
QUOTE_PLACEHOLDER = "<你的原话>"
CP_PLACEHOLDER = "<检查点编号>"
MAX_OPTIONS = 8
MAX_ITEMS = 300  # 单个小节参与排版的明细条数上限，多出的直接计入「其余 N 条」

# 检查点的中文名与选项以内核的表（tools/flowlib/checkpoints.py）为准，见 _kernel()。
# 下面这几张表是内核模块不可用时的兜底，键与内核保持一致。
CHECKPOINT_CN: dict[str, str] = {
    # 只能人工放行
    "pdf_duplicate": "同一份 PDF 已有案例",
    "spec_final": "spec 定稿",
    "data_gap": "数据缺口处置",
    "data_wait": "等人补数据",
    "mock_spec": "mock 规格确认",
    "feasibility_blocked": "可行性阻断",
    "blocking_ambiguity": "阻断级歧义",
    "plan_final": "plan 定稿",
    "milestone_done": "milestone 完成",
    "verify_done": "verify 完成",
    "trial_done": "试跑完成",
    "iterate_round": "迭代一轮结束",
    "iterate_blocked": "迭代缺外部输入",
    "pre_report": "写报告之前",
    "final_review": "最终评审",
    "circuit_breaker": "门禁连败熔断",
    "redispatch_exhausted": "重派超过上限",
    "review_rounds_exhausted": "复审超过上限",
    "step_blocked": "子 agent 报告受阻",
    "critical_dispute": "critical 意见有争议",
    "tamper": "事件流校验未通过",
    "stall": "长时间没有新进展",
    "budget": "预算超限",
    "until": "到达指定阶段",
    "step": "单步停点",
    "legacy_pause": "迁移前的暂停",
    "manual_pause": "手动暂停",
    "stuck": "内核判断不了下一步",
    # 按策略自动放行，只留痕
    "external_degraded": "外审降级",
    "false_fail_rerun": "假 FAIL 复跑",
    "redispatch": "限额内重派",
}
AUTO_CHECKPOINTS = frozenset({"external_degraded", "false_fail_rerun", "redispatch"})
FINAL_REVIEW = "final_review"

WHY: dict[str, str] = {
    "spec_final": "规格书已经提取完。进入计划之前，请你先看一眼研报要素有没有抄漏、抄错。",
    "plan_final": "复现计划已经过了规格审计。开工之前，请你确认分诊、milestone 拆分和高亮假设。",
    "milestone_done": "这个 milestone 已经实现，并通过了 milestone 级验证。请你确认后再接着做下一个。",
    "verify_done": "全量验证已经跑完。进入迭代或结果审计之前，请你看一眼对数结果。",
    "iterate_round": "这一轮迭代已经重跑完。要不要接着迭代，请你决定。",
    "pre_report": "结果审计已经收口。写报告之前，请你确认结论口径和遗留项。",
    "final_review": "最终报告已经生成，等你评审：确认收尾、定向重跑，或者回退重开。",
    "data_gap": "数据体检发现复现要用的数据有缺口。怎么处置只能由你决定，内核不会自行降级。",
    "data_wait": "案例在等你补数据。补齐后执行 `flow data recheck`，体检通过才会继续。",
    "mock_spec": "试跑要用的 mock 数据规格已经起草好，生成之前请你过目。",
    "trial_done": "用 mock 数据的试跑已经完成。试跑不出结论，下一步怎么走由你决定。",
    "circuit_breaker": "同一个检查项连续多次没过，内核已经熔断，不再自动重试。",
    "feasibility_blocked": "计划判定这份研报在现有条件下做不下去，需要你决定补条件、降级还是放弃。",
    "blocking_ambiguity": "研报里有阻断级歧义，自动裁决的边界内给不出可事后校验的口径。",
    "iterate_blocked": "诊断结论是 blocked：再迭代也收敛不了，缺的是外部输入。",
    "redispatch_exhausted": "同一步的重派次数已经用完，仍没有交出合格产物。",
    "review_rounds_exhausted": "同一个审查点的「审、修、复审」已经到了轮数上限，仍有意见没有闭环。",
    "critical_dispute": "一条 critical 意见被审方与外审各执一词，按规则不能由它们自己裁决。",
    "tamper": "事件流的哈希链与状态文件对不上，可能有人绕过内核改过记录。",
    "stall": "在途步骤超过阈值没有新事件，可能是会话断了。",
    "budget": "用量或耗时超过了启动时声明的预算。",
    "pdf_duplicate": "这份 PDF 的内容哈希与已有案例相同，可能是重复开案。",
    "until": "到了启动时用 --until 指定的停点。",
    "step": "按 --step 的要求，每走一步停一次。",
    "step_blocked": "子 agent 报告这一步做不下去，需要你看一眼是补条件、换做法还是终止。",
    "stuck": "内核按步骤表既派不出下一步，也收不了口。",
    "legacy_pause": "这个案例在迁移到新流程之前就已经暂停。",
    "manual_pause": "案例被置为暂停，等人处理。",
}

_REVIEW_OPTIONS = [
    {"key": "approve", "label": "通过，继续"},
    {"key": "modify", "label": "修改后继续：原话里写明要改什么，交给负责的角色去改"},
    {"key": "edited", "label": "我已经直接改了文件，请重新核对后继续"},
    {"key": "rollback", "label": "回退到更早的阶段重做（放行命令加 --to <阶段|mN> 指定从哪里开始）"},
    {"key": "abort", "label": "终止这个案例"},
]
DEFAULT_OPTIONS: dict[str, list[dict[str, str]]] = {
    "spec_final": _REVIEW_OPTIONS,
    "plan_final": _REVIEW_OPTIONS,
    "milestone_done": _REVIEW_OPTIONS,
    "verify_done": _REVIEW_OPTIONS,
    "iterate_round": _REVIEW_OPTIONS,
    "pre_report": _REVIEW_OPTIONS,
    "until": _REVIEW_OPTIONS,
    "step": _REVIEW_OPTIONS,
    "final_review": [
        {"key": "accept", "label": "通过并收尾（flow accept）"},
        {"key": "revise", "label": "修改假设后定向重跑（flow revise）"},
        {"key": "reopen", "label": "回退到更早的阶段重做（flow reopen）"},
        {"key": "abort", "label": "终止这个案例"},
    ],
    "data_gap": [
        {"key": "supply", "label": "补数据：我去补，补完再体检"},
        {"key": "substitute", "label": "等价替代：用本地等价数据（strict 模式下会切到实验模式）"},
        {"key": "narrow", "label": "缩小范围：只在有数据的区间或标的上复现"},
        {"key": "mock", "label": "先用 mock 试跑：只把代码和流水线跑通，这一轮不出结论"},
        {"key": "drop", "label": "砍掉相关要素：标为 infeasible，其余照做"},
        {"key": "abort", "label": "终止：放弃这份研报"},
    ],
    "trial_done": [
        {"key": "wait_real", "label": "等真实数据到位再出结论"},
        {"key": "change", "label": "改用别的处置方式，按真实数据走完"},
        {"key": "abort", "label": "终止这个案例"},
    ],
    "circuit_breaker": [
        {"key": "retry", "label": "再试一轮（相关计数清零）"},
        {"key": "pin_card", "label": "这个阶段退回执行卡驱动，由主会话按说明处理"},
        {"key": "abort", "label": "终止这个案例"},
    ],
}
FALLBACK_OPTIONS = [
    {"key": "continue", "label": "已处理，继续"},
    {"key": "abort", "label": "终止这个案例"},
]
# 最终评审的三种决定各有自己的命令，不走 flow decide；和别的放行一样要带人的原话
FINAL_COMMANDS: dict[str, str] = {
    "accept": '{flow} accept {id} --quote "{quote}"',
    "revise": '{flow} revise {id} --assumption <假设编号> --new-text "<新口径>" --quote "{quote}"',
    "reopen": '{flow} reopen {id} --from <阶段或 milestone> --reason "<原因>" --quote "{quote}"',
}
REVISE_FROM_EXCEL = '{flow} revise {id} --from-excel --quote "{quote}"'  # 读回 assumptions.xlsx 成批修订
# 个别选项要多带一个参数内核才收（flow decide 的 --to、--budget-tokens / --budget-hours）
CHOICE_ARGS: dict[str, str] = {
    "rollback": "--to <阶段或 milestone>",
    "raise": "--budget-tokens <新上限>",
}
# 凭据等级与放行方的中文说法；凭据以内核的表为准（见 credential_cn），这里是兜底
CREDENTIAL_CN: dict[str, str] = {
    "hook": "钩子记录的用户原话",
    "terminal": "人在终端输入了短码",
    "self_report": "自述（没有人在场凭据）",
    "policy": "按策略，不需要凭据",
}
BY_CN: dict[str, str] = {"human": "人", "policy": "策略"}
STEP_STATUS_CN: dict[str, str] = {"inflight": "在途", "done": "完成", "failed": "失败", "redo": "待重派"}  # flow.steps 里的步骤状态
# 方案 4.5 的缺口处置表：（处置, 可能的选项键, 含义, 之后）
DATA_GAP_ROWS: list[tuple[str, tuple[str, ...], str, str]] = [
    ("补数据", ("supply",), "你去补", "暂停；补完执行 `flow data recheck`"),
    ("等价替代", ("substitute",), "用本地等价数据。沿用现有 substitute 规则，strict 模式下仍须切到实验模式", "登记假设，继续"),
    ("缩小范围", ("narrow", "shrink", "scope"), "只在有数据的区间或标的上复现", "登记假设，继续"),
    (
        "先用 mock 试跑",
        ("mock",),
        "用模拟数据先把代码和流水线跑通；这一轮只算试跑，不出结论",
        "编码、内审、代码外审照常；验证只查跑得通、产物齐、指标都算得出，然后停在「试跑完成」，不进迭代、不出 verdict、不写报告",
    ),
    ("砍掉相关要素", ("drop", "cut", "skip"), "标为 infeasible（data_missing），其余照做", "继续"),
    ("终止", ("abort", "stop"), "放弃这份研报", "案例置为 aborted"),
]

ELEMENT_ORDER = ("D", "F", "B", "R", "SA")
SKIPPED_STATUSES = ("skipped", "infeasible")
DENIED_WORDS = ("否定", "不支持", "证伪", "相反")
STALL_IMPROVEMENT = 0.10  # 同一指标一轮的偏差改善不到这个比例，算「没有改善」

_ROUND_DIR_RE = re.compile(r"^iter_(\d+)$")
_KEY_ELEMENT_RE = re.compile(r"^(SA|[DFBR])(\d+(?:\.\d+)?)(?![0-9A-Za-z])", re.IGNORECASE)
# 下面这些正则都只做线性扫描：相邻的量词不重叠、不嵌套，免得一行病态文书把渲染拖住（渲染在内核事务里做）
_SRC_FILE_RE = re.compile(r"((?:src|common)/[\w./-]{1,200}?\.py)")
_VERDICT_LINE_RE = re.compile(r"^[ \t>*-]*(.{0,16}verdict\s*[:：]\s*\S.*)$", re.IGNORECASE | re.MULTILINE)
_NOT_FOUND_RE = re.compile(r"^.*判定[:：]\s*not_?found", re.IGNORECASE | re.MULTILINE)  # 同 G-CA-3 的口径
_ISSUE_LINE_RE = re.compile(r"^\s*(?:#{2,4}\s+|[-*]\s+\**|\|\s*\**)([A-Z]{1,5}\d{0,2}-[A-Z]{0,2}\d{1,3})\b(.*)$")
_SEVERITY_RE = re.compile(r"(critical|major|minor)", re.IGNORECASE)
_LOCATION_RE = re.compile(r"^(?:[一-鿿]{2,6}\s*[:：]\s*)?`?[\w./-]+\.(?:py|md|json|xlsx|parquet|ya?ml)\b")
_CONCLUSION_RE = re.compile(r"^[\s*-]*(?:结论|状态|判定)[\s*]*[:：]")
_DIAG_CONCLUSION_RE = re.compile(r"结论\s*[:：][\s*_`]*(continue|stop_partial|blocked)\b")
_RATING_RE = re.compile(r"可信度评级[^A-Za-z\n]{0,12}([ABC])(?![A-Za-z])")
_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.、)）]|[-*])\s+(.*)$")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})(?=\s)")
_FENCE_LINE_RE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")
_RESPONSE_ID_RE = re.compile(r"^CDX-[A-Z]-")
_PLACEHOLDER = "[verify 后填]"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _nbytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _clip(value: Any, limit: int) -> str:
    """压成一行，超过 limit 个字符就截短。"""
    flat = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return flat if len(flat) <= limit else flat[: max(limit - 1, 1)] + "…"


def _cell(value: Any, limit: int) -> str:
    """表格单元格：压成一行、截短、转义竖线。"""
    return _clip(value, limit).replace("|", "\\|") or "-"


def _num(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and not isinstance(value, bool):
        return f"{value:.4g}" if math.isfinite(value) else str(value)
    return _clip(value, 24)


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.1%}" if abs(value) < 10 else f"{value:.0%}"


def _ts(value: Any) -> str:
    text = str(value or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else (text or "-")


def _finite(value: Any) -> Optional[float]:
    """有限的数值；数字字符串也认（与 check_gates 的 float() 取值一致），其余返回 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _inside(rel: Any) -> str:
    """状态里记的相对路径：是工作区内的相对路径才用（去掉末尾的斜杠），否则返回空串。"""
    if not isinstance(rel, str) or not rel.strip():
        return ""
    path = Path(rel.strip())
    return "" if path.is_absolute() or ".." in path.parts else path.as_posix()


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return None


def _read_json(path: Path) -> Any:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _counts(values: list[str], order: tuple[str, ...] = ()) -> str:
    """把一组取值数成「a 3 · b 1」；order 里的排前面，其余按出现先后。"""
    tally: dict[str, int] = {}
    for value in values:
        tally[value] = tally.get(value, 0) + 1
    keys = [k for k in order if k in tally] + [k for k in tally if k not in order]
    return " · ".join(f"{k or '未填'} {tally[k]}" for k in keys)


# ---------------------------------------------------------------------------
# 小节与排版
# ---------------------------------------------------------------------------


@dataclass
class Sec:
    """审阅包的一个小节。lines 是必留的结论行；items 是放不下时可以截掉的明细。"""

    title: str
    lines: list[str] = field(default_factory=list)
    lead: list[str] = field(default_factory=list)  # 明细的表头，至少显示一条明细时才输出
    items: list[str] = field(default_factory=list)
    source: str = ""  # 明细的原文件（相对工作区根），写进「其余 N 条见 …」
    keep: int = 0  # 尽量保留的明细条数；别的小节都截无可截时才会动它
    extra: int = 0  # 没有进入 items 的明细条数，直接计入「其余 N 条」
    sep: str = "\n"  # 明细之间的分隔；明细是成段的文字（不是一行一条）时用空行

    def render(self, shown: Optional[int] = None) -> str:
        n = len(self.items) if shown is None else max(0, min(shown, len(self.items)))
        hidden = len(self.items) - n + self.extra
        parts: list[str] = []
        if self.lines:
            parts.append("\n".join(self.lines))
        if n:
            parts.append(self.sep.join([*self.lead, *self.items[:n]]))
        if hidden > 0:
            note = f"其余 {hidden} 条见 `{self.source}`" if self.source else f"其余 {hidden} 条未列出"
            if n and self.items[0].startswith("- "):
                parts[-1] += f"\n- {note}"  # 接成列表的最后一条，免得被渲染器并进上一条
            else:
                parts.append(note)
        if not parts:
            parts.append(EMPTY)
        return f"## {self.title}\n\n" + "\n\n".join(parts) + "\n\n"


def _cap(sec: Sec) -> Sec:
    if len(sec.items) > MAX_ITEMS:
        sec.extra += len(sec.items) - MAX_ITEMS
        del sec.items[MAX_ITEMS:]
    return sec


def _cut_bytes(text: str, limit: int) -> str:
    """按字节截断，尽量停在行尾。"""
    if _nbytes(text) <= limit:
        return text
    cut = text.encode("utf-8")[: max(limit, 0)].decode("utf-8", errors="ignore")
    head, sep, _tail = cut.rpartition("\n")
    return head + sep if sep else cut


def _compose(head: str, secs: list[Sec], tail: str, limit: int) -> str:
    """把各小节拼成全文并压到 limit 字节以内。

    先保结论与选项：头（标题、为什么停）和尾（怎么决定、声明）不动，小节里的结论行不动；
    只截明细，每次从当前最长的小节末尾去掉一条。
    """
    secs = [_cap(s) for s in secs]
    shown = [len(s.items) for s in secs]
    sizes = [_nbytes(s.render(n)) for s, n in zip(secs, shown)]
    fixed = _nbytes(head) + _nbytes(tail)
    while fixed + sum(sizes) > limit:
        trimmable = [i for i, s in enumerate(secs) if shown[i] > s.keep] or [i for i, n in enumerate(shown) if n > 0]
        if not trimmable:
            break
        target = max(trimmable, key=lambda i: sizes[i])
        shown[target] -= 1
        sizes[target] = _nbytes(secs[target].render(shown[target]))
    body = "".join(s.render(n) for s, n in zip(secs, shown))
    if fixed + _nbytes(body) <= limit:
        return head + body + tail
    # 明细截完仍放不下（结论行本身过长）：正文按字节硬截，选项与声明照留
    note = "（正文超出上限，已截断；完整内容见各小节标注的原文件）\n\n"
    room = limit - fixed - _nbytes(note)
    if room <= 0:
        return _cut_bytes(head + tail, limit)
    return head + _cut_bytes(body, room) + note + tail


# ---------------------------------------------------------------------------
# 检查点的名称、选项与放行命令（看板也用）
# ---------------------------------------------------------------------------


def limit_for(name: str) -> int:
    return PACK_LIMITS.get(name, DEFAULT_LIMIT)


def _round_no(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    for key in ("round", "iteration", "iter"):
        m = re.search(r"\d+", str(payload.get(key))) if payload.get(key) is not None else None
        if m:
            return int(m.group(0))
    return None


def _kernel() -> Any:
    """内核的检查点表（tools/flowlib/checkpoints.py）；模块不可用时返回 None。

    检查点叫什么、给人哪些选项，以内核那份为准，这样审阅包、看板和 flow status 说的是同一套话。
    延迟导入，因为内核开检查点时会回头调用本模块。
    """
    try:
        from . import checkpoints as kernel
    except Exception:  # noqa: BLE001 - 展示层不因内核模块的问题失败，退回本模块自带的表
        return None
    return kernel if isinstance(getattr(kernel, "HUMAN", None), dict) else None


def _options_list(raw: Any) -> list[dict[str, str]]:
    """把选项整理成 [{key, label}]；{key, label} 字典和（key, label）二元组两种写法都认。"""
    out: list[dict[str, str]] = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        if isinstance(item, dict) and item.get("key"):
            out.append({"key": str(item["key"]), "label": str(item.get("label") or "")})
        elif isinstance(item, (list, tuple)) and len(item) == 2 and item[0]:
            out.append({"key": str(item[0]), "label": str(item[1] or "")})
    return out


def checkpoint_title(name: Any, checkpoint: Optional[dict[str, Any]] = None) -> str:
    """检查点的中文名；milestone 完成与迭代一轮把对象一并写出。认不出的名称原样返回。"""
    name = str(name or "")
    kernel = _kernel()
    entry = kernel.HUMAN.get(name) if kernel else None
    title = str(entry[0]) if isinstance(entry, (list, tuple)) and entry and entry[0] else ""
    title = title or str((getattr(kernel, "AUTO", None) or {}).get(name) or "") or CHECKPOINT_CN.get(name, name or "检查点")
    payload = (checkpoint or {}).get("payload")
    if isinstance(payload, dict):
        if name == "milestone_done" and payload.get("milestone"):
            return f"{title}（{_clip(payload['milestone'], 12)}）"
        if name in ("iterate_round", "iterate_blocked") and _round_no(payload) is not None:
            return f"{title}（第 {_round_no(payload)} 轮）"
    return title


def is_final_review(checkpoint: Optional[dict[str, Any]]) -> bool:
    return isinstance(checkpoint, dict) and checkpoint.get("name") == FINAL_REVIEW


def is_auto(checkpoint: Optional[dict[str, Any]], name: Any = None) -> bool:
    """按策略自动放行、只留痕的检查点。以检查点自己的 kind 为准，没有时按名称判断。"""
    kind = (checkpoint or {}).get("kind")
    if kind in ("human", "auto"):
        return kind == "auto"
    wanted = str(name if name is not None else (checkpoint or {}).get("name"))
    return wanted in AUTO_CHECKPOINTS or wanted in (getattr(_kernel(), "AUTO", None) or {})


def checkpoint_options(name: Any, checkpoint: Optional[dict[str, Any]] = None) -> list[dict[str, str]]:
    """这个检查点可选的决定：检查点自带的优先，其次是内核表里这个名称的选项，再不然用本模块的兜底表。

    最终评审的三种决定（accept / revise / reopen）各有独立的命令，不依赖检查点自己列没列，
    所以检查点自带的选项里缺哪一种就补上哪一种。
    """
    name = str(name)
    options = _options_list((checkpoint or {}).get("options"))
    if not options:
        kernel = _kernel()
        entry = kernel.HUMAN.get(name) if kernel else None
        if isinstance(entry, (list, tuple)) and len(entry) >= 3:
            options = _options_list(entry[2])
    options = options or [dict(o) for o in DEFAULT_OPTIONS.get(name, FALLBACK_OPTIONS)]
    if name == FINAL_REVIEW:
        have = {o["key"] for o in options}
        options += [dict(o) for o in DEFAULT_OPTIONS[FINAL_REVIEW] if o["key"] in FINAL_COMMANDS and o["key"] not in have]
    return options


def credential_cn(credential: Any) -> str:
    """凭据等级的中文说法：内核表里有的用内核的，其余用本模块的；认不出的原样返回。"""
    key = str(credential or "")
    table = getattr(_kernel(), "CREDENTIAL_CN", None)
    return str((table if isinstance(table, dict) else {}).get(key) or CREDENTIAL_CN.get(key) or key or "未记录")


def decide_command(report_id: str, cp_id: Any, key: str, quote: str = QUOTE_PLACEHOLDER) -> str:
    extra = f" {CHOICE_ARGS[key]}" if key in CHOICE_ARGS else ""
    return f'{FLOW} decide {report_id} {cp_id or CP_PLACEHOLDER} --choice {key}{extra} --quote "{quote}"'


def option_command(report_id: str, name: Any, cp_id: Any, key: str) -> str:
    """某个选项对应的、可以直接复制的命令。"""
    if str(name) == FINAL_REVIEW and key in FINAL_COMMANDS:
        return FINAL_COMMANDS[key].format(flow=FLOW, id=report_id, quote=QUOTE_PLACEHOLDER)
    return decide_command(report_id, cp_id, key)


def _slug(text: Any) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "_", str(text)).strip("_") or "x"


def pack_path(report_id: str, cp_id: str, name: str) -> str:
    """审阅包相对工作区根的路径：workspace/<id>/reviews/cp_NN_<name>.md"""
    return f"workspace/{report_id}/{REVIEWS_DIR}/{_slug(cp_id)}_{_slug(name)}.md"


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    root: Path
    report_id: str
    name: str
    state: dict[str, Any]
    cp: dict[str, Any]  # 检查点；没有时是空字典
    _docs: Optional[CaseDocs] = None
    _docs_loaded: bool = False
    _docs_error: str = ""
    _standards: Optional[dict[str, Any]] = None

    @property
    def ws(self) -> str:
        return f"workspace/{self.report_id}"

    @property
    def out(self) -> str:
        return f"output/{self.report_id}"

    @property
    def payload(self) -> dict[str, Any]:
        payload = self.cp.get("payload")
        return payload if isinstance(payload, dict) else {}

    @property
    def docs(self) -> Optional[CaseDocs]:
        if not self._docs_loaded:
            self._docs_loaded = True
            try:
                self._docs = CaseDocs.load(self.root, self.report_id)
            except (OSError, ValueError) as exc:  # 文书读不出来（含编码错误）：按缺失处理，并在文末说明
                self._docs = None
                self._docs_error = f"{type(exc).__name__}：{_clip(exc, 100)}"
        return self._docs

    @property
    def standards(self) -> dict[str, Any]:
        if self._standards is None:
            self._standards = cg.load_standards(self.root)
        return self._standards

    @property
    def experimental(self) -> bool:
        return self.state.get("reproduction_mode") == "experimental"

    def file(self, rel: str) -> Path:
        return self.root / rel

    def link(self, rel: str, label: Optional[str] = None) -> str:
        """指向工作区内某个文件的 markdown 链接，路径相对审阅包所在目录。"""
        target = os.path.relpath(self.root / rel, self.root / self.ws / REVIEWS_DIR)
        return f"[{label or Path(rel).name}]({Path(target).as_posix()})"


@dataclass
class _Recalc:
    """一份 comparison.json 按 standards.json 重算后的结果。"""

    metrics: list[dict[str, Any]]
    results: list[cg.MetricRecalc]
    qualitative: list[dict[str, Any]]
    experimental: bool
    self_report: Optional[str]

    @property
    def n_pass(self) -> int:
        return sum(r.passed is True for r in self.results)

    @property
    def n_fail(self) -> int:
        return sum(r.passed is False for r in self.results)

    @property
    def n_waived(self) -> int:
        return sum(r.passed is None for r in self.results)

    @property
    def q_pass(self) -> int:
        return sum(q.get("passed") is True for q in self.qualitative)

    def count_text(self) -> str:
        """「数值 a/b、定性 c/d」。unverifiable 的指标不计入分母（同 G-VF-3）。"""
        text = f"数值 {self.n_pass}/{self.n_pass + self.n_fail}"
        if self.qualitative:
            text += f"、定性 {self.q_pass}/{len(self.qualitative)}"
        return text

    def summary(self) -> str:
        if self.experimental:
            text = f"实验模式，数值对齐按模式豁免，只核产出是否在位：{self.count_text()} 在位"
        else:
            text = f"按 standards.json 重算达标：{self.count_text()}"
            if self.n_waived:
                text += f"；另有 {self.n_waived} 项 unverifiable 不计入分母"
        return text + (f"（文件自报 {self.self_report}，不采信）" if self.self_report else "")

    def by_key(self) -> dict[str, tuple[dict[str, Any], cg.MetricRecalc]]:
        return {r.key: (m, r) for m, r in zip(self.metrics, self.results)}

    def failures(self) -> list[tuple[dict[str, Any], cg.MetricRecalc]]:
        """没过的数值指标，按相对偏差从大到小；算不出偏差的排最后。"""
        pairs = [(m, r, _dev(m, r)) for m, r in zip(self.metrics, self.results) if r.passed is False]
        return [(m, r) for m, r, _d in sorted(pairs, key=lambda item: (item[2] is None, -(item[2] or 0.0)))]


_LEVEL_CN = {"directional": "只核方向", "magnitude": "只核数量级"}


def _dev(metric: dict[str, Any], result: cg.MetricRecalc) -> Optional[float]:
    """展示与排序用的相对偏差。

    重算给了偏差就用重算的。核验分级降到只核方向或数量级的指标，重算不出偏差，这里按同一条
    公式 |复现值 - 研报值| / |研报值| 现算一个，只用来排序和展示，不参与达标判定。
    """
    dev = _finite(result.rel_dev)
    if dev is not None:
        return dev
    report, reproduced = _finite(metric.get("report_value")), _finite(metric.get("reproduced_value"))
    if report is None or reproduced is None or report == 0:
        return None
    return abs(reproduced - report) / abs(report)


def _recalc(ctx: _Ctx, rel: str) -> Optional[_Recalc]:
    """读一份 comparison.json 并重算；文件不在或读不懂返回 None。"""
    data = _read_json(ctx.file(rel))
    if not isinstance(data, dict):
        return None
    metrics = [m for m in data.get("metrics") or [] if isinstance(m, dict)]
    qualitative = [q for q in data.get("qualitative") or [] if isinstance(q, dict)]
    try:
        result = cg.recalc_comparison(
            {"metrics": metrics, "qualitative": qualitative}, ctx.standards, ctx.state.get("type"), ctx.experimental
        )
    except (TypeError, ValueError, AttributeError, KeyError):
        return None
    self_report = None
    if data.get("pass_count") is not None and data.get("total") is not None:
        self_report = f"{_clip(data['pass_count'], 8)}/{_clip(data['total'], 8)}"
    return _Recalc(metrics, result.metrics, result.qualitative, result.experimental, self_report)


def _metric_elements(metric: dict[str, Any]) -> list[str]:
    """一条指标对应的要素编号：先看 source_element，再看 key 的前缀（r1_… / R1_…）。"""
    refs = ms.extract_refs(str(metric.get("source_element") or ""))
    if refs:
        return refs
    m = _KEY_ELEMENT_RE.match(str(metric.get("key") or ""))
    return [f"{m.group(1).upper()}{m.group(2)}"] if m else []


def _metric_line(metric: dict[str, Any], result: cg.MetricRecalc) -> str:
    dev = _dev(metric, result)
    text = f"- `{_clip(result.key, 48)}` 研报 {_num(metric.get('report_value'))} / 复现 {_num(metric.get('reproduced_value'))}"
    text += f"，偏差 {_pct(dev)}" if dev is not None else f"，{_clip(result.reason, 30)}"
    notes = [_LEVEL_CN[level] for level in [str(metric.get("verification_level") or "")] if level in _LEVEL_CN]
    if metric.get("attribution_status"):
        notes.append(f"归因 {_clip(metric['attribution_status'], 20)}")
    return text + (f"（{'；'.join(notes)}）" if notes else "")


def _pages(block: ms.Block) -> str:
    fld = block.field("页码")
    return _clip(fld.value, 28) if fld and fld.value else "页码未注"


def _field_text(block: ms.Block, *prefixes: str) -> str:
    """按字段名前缀取第一条非空字段的首行；首行空着的取字段正文的下一行。"""
    for prefix in prefixes:
        for fld in block.fields:
            if not fld.name.startswith(prefix):
                continue
            if fld.value:
                return fld.value
            rest = [line.strip() for line in fld.text.splitlines()[1:] if line.strip()]
            if rest:
                return rest[0]
    return ""


def _ambiguities(ctx: _Ctx) -> list[ms.Block]:
    docs = ctx.docs
    if docs is None or docs.ambiguities is None:
        return []
    return [b for b in ms.parse_blocks(docs.ambiguities.text) if b.prefix == "A"]


def _matrix(ctx: _Ctx) -> list[dict[str, str]]:
    docs = ctx.docs
    return [r.cells for r in docs.matrix_rows] if docs else []


def _row(cells: dict[str, str], *keywords: str) -> str:
    return ms.row_get(cells, *keywords)


def _responses(ctx: _Ctx) -> Optional[list[dict[str, str]]]:
    """audit_responses.md 里带 CDX-X-NN 编号的回应行（识别口径同 check_gates._parse_audit_responses）。"""
    text = _read_text(ctx.file(f"{ctx.ws}/audit/audit_responses.md"))
    if text is None:
        return None
    rows: list[dict[str, str]] = []
    for row in ms.parse_table_rows(text):
        rid = next((v.strip() for v in row.cells.values() if v and _RESPONSE_ID_RE.match(v.strip())), "")
        if rid:
            rows.append(
                {
                    "id": rid,
                    "severity": _row(row.cells, "severity").lower(),
                    "summary": _row(row.cells, "摘要"),
                    "disposal": _row(row.cells, "处置"),
                    "recheck": _row(row.cells, "复核"),
                }
            )
    return rows


def _reviews(ctx: _Ctx) -> list[dict[str, Any]]:
    return [r for r in ctx.state.get("external_reviews") or [] if isinstance(r, dict)]


def _review_text(review: dict[str, Any]) -> str:
    engine = str(review.get("engine") or "未记录")
    degraded = "fallback" in engine or engine == "skipped"
    text = f"引擎 {engine}（{'降级' if degraded else '未降级'}） · 结论 {review.get('verdict') or '未记录'}"
    text += f" · critical {review.get('critical', '-')} / major {review.get('major', '-')} / minor {review.get('minor', '-')}"
    note = review.get("note") or review.get("reason")
    return text + (f" · {_clip(note, 70)}" if note else "")


def _round_dirs(ctx: _Ctx) -> list[int]:
    base = ctx.file(f"{ctx.ws}/iterations")
    if not base.is_dir():
        return []
    return sorted(int(m.group(1)) for p in base.iterdir() if p.is_dir() and (m := _ROUND_DIR_RE.match(p.name)))


def _bullet(lines: list[str], index: int) -> str:
    """从第 index 行起的一条列表项：把折行的续行接上（中文之间不加空格，英文之间加）。"""
    text = lines[index].strip()
    for line in lines[index + 1:]:
        if not line.startswith((" ", "\t")) or not line.strip() or _LIST_ITEM_RE.match(line):
            break
        more = line.strip()
        text += ("" if not text or ord(text[-1]) > 127 or ord(more[0]) > 127 else " ") + more
    return text


def _section_items(text: str, title_has: str, skip_title: str = "") -> list[str]:
    """标题含某个词的小节里的列表项（带上折行的续行）；小节嵌套时不重复取。"""
    out: list[str] = []
    taken_until = -1
    for sec in ms.sections(text):
        if title_has not in sec.title or (skip_title and skip_title in sec.title) or sec.start < taken_until:
            continue
        taken_until = sec.end
        lines = sec.text.splitlines()[1:]
        out.extend(_bullet(lines, i) for i, line in enumerate(lines) if _LIST_ITEM_RE.match(line) and not line.startswith((" ", "\t")))
    return out


# ---------------------------------------------------------------------------
# 各检查点的主体
# ---------------------------------------------------------------------------


def _spec_final(ctx: _Ctx) -> list[Sec]:
    docs = ctx.docs
    spec_rel = f"{ctx.ws}/spec/spec.md"
    amb_rel = f"{ctx.ws}/spec/ambiguities.md"
    blocks = docs.spec_blocks if docs else []
    groups = {p: [b for b in blocks if b.prefix == p] for p in ELEMENT_ORDER}

    count = Sec("要素计数")
    if docs and docs.spec:
        fm = cg.parse_frontmatter(docs.spec.text)[0] or {}
        about = "，".join(str(fm[k]) for k in ("title", "institution") if fm.get(k))
        if about:
            count.lines.append(f"- 研报：{_clip(about, 70)}" + (f"，{_clip(fm['pdf_pages'], 6)} 页" if fm.get("pdf_pages") else ""))
        count.lines.append("- 按标题块实数：" + " · ".join(f"{p} {len(groups[p])}" for p in ELEMENT_ORDER) + f"，共 {len(blocks)} 条")
        declared = fm.get("element_counts")
        if isinstance(declared, dict):
            diff = [f"{p} 自报 {declared.get(p)}、实数 {len(groups[p])}" for p in ELEMENT_ORDER if p in declared and declared.get(p) != len(groups[p])]
            count.lines.append("- 与 spec 自报的 element_counts " + ("一致" if not diff else "不一致：" + "；".join(diff)))

    formulas = Sec("F 类公式（首行）", source=spec_rel)
    formulas.items = [
        f"- {b.id} {_clip(b.title, 34)}（{_pages(b)}）：{_clip(_field_text(b, '公式', '说明（转写）', '说明') or '未写公式', 96)}"
        for b in groups["F"]
    ]

    params = Sec("B 类参数表", source=spec_rel, lead=["| 编号 | 设置 | 参数值 | 页码 |", "| --- | --- | --- | --- |"])
    params.items = [
        f"| {b.id} | {_cell(b.title, 34)} | {_cell(_field_text(b, '参数值', '参数') or '未写', 60)} | {_cell(_pages(b), 28)} |"
        for b in groups["B"]
    ]

    results = Sec("R 表清单", source=spec_rel)
    results.items = [f"- {b.id} {_clip(b.title, 48)}（{_pages(b)}）" for b in groups["R"]]

    ambs = _ambiguities(ctx)
    levels = {b.id: _field_text(b, "等级").strip().lower() for b in ambs}
    statuses = {b.id: _field_text(b, "状态").strip() or "未填" for b in ambs}

    def amb_line(b: ms.Block) -> str:
        related = _field_text(b, "关联要素")
        ruling = _field_text(b, "裁决结果")
        detail = f"裁决：{_clip(ruling, 70)}" if ruling else f"候选：{_clip(_field_text(b, '候选解释') or '未写', 80)}"
        return f"- {b.id} {_clip(b.title, 36)}（{_pages(b)}" + (f"；关联 {_clip(related, 30)}" if related else "") + f"；状态 {statuses[b.id]}）：{detail}"

    blocking = Sec("blocking 歧义", source=amb_rel)
    major = Sec("major 歧义", source=amb_rel)
    if docs and docs.ambiguities is not None:
        blocking.lines.append(
            f"- 歧义共 {len(ambs)} 条：{_counts(list(levels.values()), ('blocking', 'major', 'minor')) or '无'}；"
            f"尚未裁决（状态不是 resolved）{sum(s != 'resolved' for s in statuses.values())} 条"
        )
        blocking.items = [amb_line(b) for b in ambs if levels[b.id] == "blocking"]
        blocking.keep = len(blocking.items)
        major.items = [amb_line(b) for b in ambs if levels[b.id] == "major"]
        if not major.items:
            major.lines.append("- 没有 major 级歧义")

    missing = Sec("缺失数据", source=spec_rel)
    if groups["D"]:
        data_status = {b.id: _clip(_field_text(b, "数据状态") or "未填", 16) for b in groups["D"]}
        missing.lines.append(f"- 数据要求 {len(groups['D'])} 条：{_counts(list(data_status.values()), ('available', 'derive', 'missing'))}")
        missing.items = [
            f"- {b.id} {_clip(b.title, 34)}（{_pages(b)}）：{_clip(_field_text(b, '说明') or '未写说明', 90)}"
            for b in groups["D"]
            if "missing" in data_status[b.id]
        ]
        missing.keep = len(missing.items)
    return [count, formulas, params, results, blocking, major, missing]


def _plan_final(ctx: _Ctx) -> list[Sec]:
    docs = ctx.docs
    plan_rel = f"{ctx.ws}/plan.md"
    asm_rel = f"{ctx.ws}/assumptions.md"
    matrix_rel = f"{ctx.ws}/spec/coverage_matrix.md"
    fm = docs.plan_fm if docs else {}

    triage = Sec("分诊依据", source=plan_rel)
    if docs and docs.plan is not None:
        picked = {key: fm.get(key) or ctx.state.get(key) or "未填" for key in ("type", "difficulty", "feasibility")}
        line = f"- 类型 {picked['type']} · 难度 {picked['difficulty']} · 可行性 {picked['feasibility']}"
        mode = fm.get("reproduction_mode") or ctx.state.get("reproduction_mode")
        triage.lines.append(line + (f" · 复现模式 {mode}" if mode else ""))
        reqs = [r for r in fm.get("data_requirements") or [] if isinstance(r, dict)]
        if reqs:
            triage.lines.append(f"- 数据需求 {len(reqs)} 条：{_counts([str(r.get('status') or '未填') for r in reqs], ('available', 'derive', 'substitute', 'missing'))}")
        taken_until = -1
        for sec in ms.sections(docs.plan.text):
            if not re.search("分诊|难度判定", sec.title) or sec.start < taken_until:
                continue
            taken_until = sec.end
            for raw in sec.text.splitlines()[1:]:
                text = re.sub(r"^\s*(?:[-*]|\d+[.、])\s*", "", raw).strip()
                if text and not text.startswith(("|", "#", ">")):
                    triage.items.append(f"- {_clip(text, 130)}")

    miles = Sec("milestone 表", source=plan_rel, lead=["| 编号 | 名称 | 依赖 | 要素 |", "| --- | --- | --- | --- |"])
    plan_ms = docs.plan_milestones() if docs else []
    for m in plan_ms or [x for x in ctx.state.get("milestones") or [] if isinstance(x, dict) and x.get("id")]:
        mid = str(m["id"])
        elements = docs.step_elements(mid) if docs else []
        deps = m.get("deps") if isinstance(m.get("deps"), list) else []
        listing = " ".join(elements[:10]) + (" …" if len(elements) > 10 else "")
        miles.items.append(
            f"| {_cell(mid, 8)} | {_cell(m.get('name'), 36)} | {_cell(' '.join(str(d) for d in deps), 20)} | {len(elements)} 个：{_cell(listing, 70)} |"
        )
    miles.keep = len(miles.items)

    highlighted = Sec("major-auto 假设（逐条）", source=asm_rel)
    asm_blocks = docs.assumption_blocks if docs else []
    for b in asm_blocks:
        if "major-auto" not in _field_text(b, "高亮等级"):
            continue
        notes = [f"来源 {_clip(_field_text(b, '来源') or '未填', 22)}"]
        if _field_text(b, "影响 milestone"):
            notes.append(f"影响 {_clip(_field_text(b, '影响 milestone'), 18)}")
        if _field_text(b, "参数绑定"):
            notes.append(f"参数 {_clip(_field_text(b, '参数绑定'), 28)}")
        highlighted.items.append(f"- {b.id} {_clip(b.title, 40)}（{'；'.join(notes)}）：{_clip(_field_text(b, '假设内容') or '未写假设内容', 76)}")
    highlighted.keep = len(highlighted.items)
    if docs and docs.assumptions is not None:
        highlighted.lines.append(f"- 假设共 {len(asm_blocks)} 条，其中 major-auto {len(highlighted.items)} 条")

    skipped = Sec("core 级被跳过的要素", source=matrix_rel)
    rows = _matrix(ctx)
    if rows:
        core = [r for r in rows if _row(r, "优先级") == "core"]
        hit = [r for r in core if _row(r, "状态") in SKIPPED_STATUSES]
        skipped.lines.append(f"- core 要素 {len(core)} 个，其中被跳过或判不可行 {len(hit)} 个")
        skipped.items = [
            f"- {_row(r, '要素ID')} {_clip(_row(r, '描述'), 30)}（{_clip(_row(r, '页码'), 16) or '页码未注'}；{_row(r, '状态')}）：{_clip(_row(r, '状态理由') or '未写理由', 90)}"
            for r in hit
        ]
        skipped.keep = len(skipped.items)

    review = Sec("spec 外审结论")
    spec_reviews = [r for r in _reviews(ctx) if r.get("checkpoint") == "spec"]
    if spec_reviews:
        review.lines.append(f"- {_review_text(spec_reviews[-1])}")
    responses = _responses(ctx)
    if responses is not None:
        mine = [r for r in responses if r["id"].startswith("CDX-S-")]
        if mine:
            open_critical = [r["id"] for r in mine if r["severity"] == "critical" and r["recheck"].lower() != "pass"]
            review.lines.append(
                f"- 回应表里 CDX-S 意见 {len(mine)} 条：处置 {_counts([r['disposal'] or '未填' for r in mine], ('accepted', 'rejected', 'deferred'))}；"
                f"复核 pass {sum(r['recheck'].lower() == 'pass' for r in mine)} 条；critical 未闭环 {len(open_critical)} 条"
                + (f"（{' '.join(open_critical)}）" if open_critical else "")
            )
        else:
            review.lines.append("- 回应表里还没有 CDX-S 意见")

    excel = Sec("Excel 批量回改入口")
    excel.lines.append(
        f"要成批改假设：用 `tools/assumptions_xlsx.py export {ctx.report_id}` 导出 `{ctx.ws}/assumptions.xlsx`，在黄底三列里填好，"
        "再选「修改后继续」并说明走 Excel；内核按 `apply` 给出的影响面定重跑范围。"
        + ("" if ctx.file(f"src/{ctx.report_id}/config.py").is_file() else "`config.py` 还没有生成，眼下只收文字修订。")
    )
    return [triage, miles, highlighted, skipped, review, excel]


def _issue_text(rest: str, severity: str) -> str:
    """内审问题条目的一句话：去掉严重度标记，跳过只写代码位置的那一格。

    三种写法都认：标题（### IM2-01 [major] …）、加粗条目（- **CA-C01** / severity: major / …）、
    表格行（| CA-A01 | major | 位置 | 描述 |）。
    """
    cleaned = re.sub(r"\*\*|severity\s*[:：]", "", rest)
    cleaned = re.sub(rf"[\[【（(]?{re.escape(severity)}[\]】)）]?", " ", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)  # 空白先压成单个空格，下面的切分才不会在长空白上反复回溯
    parts = [p.strip(" :：/|") for p in re.split(r" ?\| ?| ?/ | /", cleaned)]
    parts = [p for p in parts if p]
    return next((p for p in parts if not _LOCATION_RE.match(p)), parts[0] if parts else "")


def _milestone_status(ctx: _Ctx, milestone: str) -> str:
    """state.json 里这个 milestone 的三项子状态（编码 / 内审 / 验证），写成一句；状态里没有这个 milestone 时返回空串。"""
    entry = next((m for m in ctx.state.get("milestones") or [] if isinstance(m, dict) and str(m.get("id")) == milestone), None)
    if entry is None:
        return ""
    return " · ".join(f"{cn} {STAGE_STATUS_CN.get(str(entry.get(key)), str(entry.get(key) or '未记录'))}" for key, cn in MILESTONE_FIELD_CN.items())


def _impl_audit(ctx: _Ctx, milestone: str) -> Sec:
    """内审结论：判定行、问题条数（按严重度）、有没有空壳判定。

    审计文件还不在时只陈述事实：这个 milestone 有没有单独的内审步骤、它眼下的状态。检查点是在
    milestone 级验证通过时开的，逐 milestone 的内审可能还在途，也可能留到代码审计阶段统一做。
    """
    sec = Sec("内审结论")
    rel = next(
        (r for r in (f"{ctx.ws}/audit/impl_audit_{milestone}.md", f"{ctx.ws}/audit/impl_audit_mall.md") if ctx.file(r).is_file()),
        None,
    )
    text = _read_text(ctx.file(rel)) if rel else None
    if text is None:
        wanted = f"`{ctx.ws}/audit/impl_audit_{milestone}.md`"
        records = (ctx.state.get("flow") or {}).get("steps") if isinstance(ctx.state.get("flow"), dict) else None
        step_id = f"implement.{milestone}.audit"
        rec = records.get(step_id) if isinstance(records, dict) else None
        if isinstance(rec, dict):
            status = str(rec.get("status") or "")
            sec.lines.append(f"- 内审步骤 `{step_id}` 眼下是「{STEP_STATUS_CN.get(status, status or '未记录')}」，审计文件 {wanted} 还没有交出来")
        else:
            sec.lines.append(f"- 审计文件 {wanted} 还不在，步骤表里也没有这个 milestone 单独的内审步骤")
        return sec
    sec.source = rel
    verdicts = [_clip(v, 48) for v in _VERDICT_LINE_RE.findall(text)]
    sec.lines.append(f"- 判定（{Path(rel).name}）：{'；'.join(verdicts[:4]) if verdicts else '文件里没有 verdict 行'}")
    issues: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = _ISSUE_LINE_RE.match(line)
        if not m or m.group(1) in issues:
            continue
        sev = _SEVERITY_RE.search(m.group(2))
        if sev:
            issues[m.group(1)] = (sev.group(1).lower(), _issue_text(m.group(2), sev.group(1)))
    if issues:
        sec.lines.append(f"- 问题 {len(issues)} 条：{_counts([s for s, _ in issues.values()], ('critical', 'major', 'minor'))}")
        sec.items = [f"- {iid}（{sev}）{_clip(rest, 64)}" for iid, (sev, rest) in issues.items()]
    else:
        sec.lines.append("- 没有识别出带严重度的问题条目")
    sec.lines.append("- 空壳判定（判定: not_found）：" + ("命中" if _NOT_FOUND_RE.search(text) else "未命中"))
    recheck = f"{ctx.ws}/audit/impl_audit_{milestone}_recheck.md"
    recheck_text = _read_text(ctx.file(recheck))
    if recheck_text is not None:
        again = [_clip(v, 48) for v in _VERDICT_LINE_RE.findall(recheck_text)]
        sec.lines.append(f"- 复核（{Path(recheck).name}）：{'；'.join(again[:2]) if again else '文件里没有 verdict 行'}")
    return sec


def _milestone_done(ctx: _Ctx) -> list[Sec]:
    docs = ctx.docs
    matrix_rel = f"{ctx.ws}/spec/coverage_matrix.md"
    milestone = str(ctx.payload.get("milestone") or "")
    elements = docs.step_elements(milestone) if docs and milestone else []
    rows = {_row(r, "要素ID"): r for r in _matrix(ctx)}

    delivered = Sec("交付要素", source=matrix_rel)
    files = Sec("实现文件", source=matrix_rel)
    if not milestone:
        delivered.lines.append("- 检查点没有指明是哪个 milestone")
    elif elements:
        delivered.lines.append(f"- {milestone} 共 {len(elements)} 个要素：{_counts([_row(rows.get(e, {}), '状态') or '矩阵无此行' for e in elements], ('done',))}")
        status = _milestone_status(ctx, milestone)
        if status:
            delivered.lines.append(f"- state.json 记的进度：{status}")
        delivered.items = [
            f"- {e} {_clip(_row(rows.get(e, {}), '描述'), 30)} · {_row(rows.get(e, {}), '优先级') or '未定级'} · {_row(rows.get(e, {}), '状态') or '矩阵无此行'}"
            for e in elements
        ]
        by_file: dict[str, list[str]] = {}
        blank = [e for e in elements if e in rows and not _row(rows[e], "实现位置") and _row(rows[e], "状态") not in SKIPPED_STATUSES]
        for e in elements:
            for path in dict.fromkeys(_SRC_FILE_RE.findall(_row(rows.get(e, {}), "实现位置"))):
                by_file.setdefault(path, []).append(e)
        files.items = [
            f"- `{path}`" + ("" if ctx.file(path).is_file() else "（文件不存在）") + f"：{_clip(' '.join(ids), 60)}" for path, ids in by_file.items()
        ]
        files.keep = len(files.items)
        if blank:
            files.lines.append(f"- 「实现位置」还空着的要素：{_clip(' '.join(blank), 80)}")

    matched = Sec("已对上的指标", source=f"{ctx.out}/results/comparison.json")
    recalc = _recalc(ctx, f"{ctx.out}/results/comparison.json")
    mine = [(m, r) for m, r in zip(recalc.metrics, recalc.results) if set(_metric_elements(m)) & set(elements)] if recalc and elements else []
    if mine:
        ok = [(m, r) for m, r in mine if r.passed is True]
        bad = [r.key for _m, r in mine if r.passed is False]
        matched.lines.append(
            f"- 按 standards.json 重算，归到 {milestone} 的数值指标 {len(mine)} 项：对上 {len(ok)} 项、没对上 {len(bad)} 项"
            + (f"、unverifiable {len(mine) - len(ok) - len(bad)} 项" if len(mine) - len(ok) - len(bad) else "")
        )
        if bad:
            matched.lines.append(f"- 没对上：{_clip('、'.join(bad), 110)}")
        matched.items = [_metric_line(m, r) for m, r in ok]
    elif elements:
        told = [(e, _row(rows.get(e, {}), "验证结果")) for e in elements if e[:1] in ("R", "S") and _row(rows.get(e, {}), "验证结果")]
        if told:
            matched.source = matrix_rel
            matched.lines.append("- comparison.json 里还没有归到这一步的指标；以下取自矩阵「验证结果」列，是 verifier 的记录，未经重算")
            matched.items = [f"- {e}：{_clip(text, 80)}" for e, text in told]
    fragment = f"{ctx.out}/verify_fragments/{milestone}.md"
    if milestone and ctx.file(fragment).is_file():
        matched.lines.append(f"- 这一步的验证记录：{ctx.link(fragment, fragment)}")

    added = Sec("这一步新增的假设", source=f"{ctx.ws}/assumptions.md")
    asm = docs.assumption_blocks if docs else []
    explicit = ctx.payload.get("new_assumptions")
    if isinstance(explicit, list):
        picked = [b for b in asm if b.id in {str(x) for x in explicit}]
        added.lines.append(f"- 内核登记这一步新增 {len(explicit)} 条")
    elif milestone:
        # 没有内核登记时的推断口径：来源不是歧义裁决（不以 A<数字> 开头），且主归属的第一个 milestone 是本步
        picked = [
            b
            for b in asm
            if not re.match(r"A\d", _field_text(b, "来源")) and docs is not None and docs.assumption_primary_milestones(b)[:1] == [milestone]
        ]
        if docs and docs.assumptions is not None:
            added.lines.append(f"- 按「来源不是歧义裁决、主归属为 {milestone}」推断，共 {len(picked)} 条")
    else:
        picked = []
    added.items = [
        f"- {b.id} {_clip(b.title, 40)}（来源 {_clip(_field_text(b, '来源') or '未填', 24)}；{_clip(_field_text(b, '高亮等级') or '-', 12)}）"
        for b in picked
    ]
    return [delivered, files, _impl_audit(ctx, milestone) if milestone else Sec("内审结论"), matched, added]


def _gate_line(ctx: _Ctx, stage: str) -> Optional[str]:
    latest = (ctx.state.get("gate_latest") or {}).get(stage)
    if not isinstance(latest, dict):
        return None
    failed = [str(f.get("id")) for f in latest.get("failed") or [] if isinstance(f, dict)]
    verdict = "通过" if latest.get("verdict") == "PASS" else "未过"
    return f"- {STAGE_CN.get(stage, stage)}门禁最近一次：{verdict}" + (f"（{'、'.join(failed)}）" if failed else "") + f"，{_ts(latest.get('timestamp'))}"


def _denied_assumptions(ctx: _Ctx) -> Sec:
    """被数据否定的假设。

    口径：假设条目里名字含「验证后回看」的字段（含各轮的修订版），正文出现「否定」「不支持」
    「证伪」「相反」任何一个词就列出，每条假设只列最新一处。这是纯关键词匹配，不判断语气
    （「无法证伪」也会命中），所以它是给人看的线索，不是结论。
    """
    sec = Sec("被数据否定的假设", source=f"{ctx.ws}/assumptions.md")
    docs = ctx.docs
    if docs is None or docs.assumptions is None:
        return sec
    pattern = re.compile("|".join(DENIED_WORDS))
    looked = 0
    for block in docs.assumption_blocks:
        lookbacks = [f for f in block.fields if "验证后回看" in f.name]
        looked += bool(lookbacks)
        for fld in reversed(lookbacks):
            body = re.sub(r"\s+", " ", fld.text.split(fld.name, 1)[-1].lstrip(":： "))
            m = pattern.search(body)
            if m:
                a, b = max(m.start() - 34, 0), min(m.end() + 34, len(body))
                sec.items.append(f"- {block.id} {_clip(block.title, 30)}：{'…' if a else ''}{body[a:b].strip()}{'…' if b < len(body) else ''}")
                break
    sec.lines.append(f"- {looked} 条假设写了「验证后回看」，其中 {len(sec.items)} 条出现「{' / '.join(DENIED_WORDS)}」字样（关键词匹配，供人复核）")
    return sec


def _result_tag(value: str) -> str:
    """证据表「结果」列的取值归一：只留开头的英文词（pass / fail …），没有就截短。"""
    word = re.match(r"[A-Za-z_]+", value.strip())
    if word:
        return word.group(0).lower()
    return _clip(re.split(r"[（(，,;；:：\s]", value.strip(), maxsplit=1)[0], 10) or "未填"


def _verify_done(ctx: _Ctx) -> list[Sec]:
    cmp_rel = f"{ctx.out}/results/comparison.json"
    results_rel = f"{ctx.out}/results"
    recalc = _recalc(ctx, cmp_rel)

    tally = Sec("重算达标数")
    worst = Sec("超差前 10（按相对偏差）", source=cmp_rel)
    if recalc:
        tally.lines.append(f"- {recalc.summary()}")
        failures = recalc.failures()
        failed_quals = [str(q.get("key")) for q in recalc.qualitative if q.get("passed") is not True]
        if failed_quals:
            tally.lines.append(f"- 没过的定性项 {len(failed_quals)} 个：{_clip('、'.join(failed_quals), 120)}")
        worst.lines.append(f"- 没过的数值指标共 {len(failures)} 项" + ("，列偏差最大的 10 项" if len(failures) > 10 else ""))
        worst.items = [_metric_line(m, r) for m, r in failures[:10]]
        worst.extra = max(len(failures) - 10, 0)
    elif ctx.file(cmp_rel).is_file():
        tally.lines.append(f"- `{cmp_rel}` 在，但读不出来或重算不了，达标数给不出")
    gate = _gate_line(ctx, "verify")
    if gate:
        tally.lines.append(gate)

    charts = Sec("核心图", source=results_rel)
    results_dir = ctx.file(results_rel)
    if results_dir.is_dir():
        required = [str(n) for n in (ctx.standards.get(ctx.state.get("type")) or {}).get("required_charts") or []]
        present = sorted(p.name for p in results_dir.glob("*.png"))
        charts.lines.append(f"- 结果目录 `{results_rel}/` 里有 {len(present)} 张图" + (f"，其中 standards.json 要求的 {len(required)} 张如下" if required else ""))
        charts.items = [f"- {ctx.link(f'{results_rel}/{n}')}" if n in present else f"- {n}（缺）" for n in (required or present[:8])]
        charts.extra = 0 if required else max(len(present) - 8, 0)
        charts.keep = len(charts.items)

    evidence = Sec("证据链")
    manifest_rel = f"{ctx.ws}/audit/evidence_manifest.md"
    manifest = _read_text(ctx.file(manifest_rel))
    if manifest is not None:
        rows = [r.cells for r in ms.parse_table_rows(manifest) if any(re.match(r"^EVD-", (v or "").strip()) for v in r.cells.values())]
        evidence.lines.append(f"- {ctx.link(manifest_rel)}：证据 {len(rows)} 条" + (f"，结果 {_counts([_result_tag(_row(r, '结果')) for r in rows], ('pass',))}" if rows else ""))
    run_log = _read_text(ctx.file(f"{results_rel}/run_log.md"))
    if run_log is not None:
        evidence.lines.append(f"- {ctx.link(f'{results_rel}/run_log.md')}：{'含' if 'exit=0' in run_log else '不含'} exit=0")
    for rel in (f"{ctx.out}/verify_report.md", cmp_rel, f"{results_rel}/metrics.json"):
        if ctx.file(rel).is_file():
            size = ctx.file(rel).stat().st_size
            evidence.lines.append(f"- {ctx.link(rel)}（{size / KB:.0f}KB）" if size >= 10 * KB else f"- {ctx.link(rel)}（{size} 字节）")

    perturb = Sec("扰动结果", source=manifest_rel)
    if manifest is not None:
        for sec in ms.sections(manifest):
            if "扰动测试" not in sec.title:
                continue
            lines = sec.text.splitlines()[1:]
            hit = next((i for i, line in enumerate(lines) if _CONCLUSION_RE.match(line)), None)
            if hit is None:
                hit = next((i for i, line in enumerate(lines) if line.strip() and not line.startswith("#")), None)
            body = re.sub(r"^[-*]\s*", "", _bullet(lines, hit)).replace("**", "") if hit is not None else "这一段没有内容"
            perturb.items.append(f"- {_clip(sec.title, 34)}：{_clip(body, 110)}")
        if not perturb.items:
            perturb.lines.append("- 证据链文件里没有标题含「扰动测试」的段")
    return [tally, worst, charts, evidence, perturb, _denied_assumptions(ctx)]


def _stall_warnings(rounds: list[tuple[int, _Recalc]]) -> list[str]:
    """无改善预警。

    口径：最新一轮仍没过的数值指标，取最近三份快照的相对偏差 d0、d1、d2；两轮的改善幅度
    (d0-d1)/d0 与 (d1-d2)/d1 都不到 10% 就预警。快照不足三份时不判断。
    """
    if len(rounds) < 3:
        return []
    (n0, r0), (n1, r1), (n2, r2) = rounds[-3:]
    earlier = (r0.by_key(), r1.by_key())
    out: list[tuple[float, str]] = []
    for metric, res in r2.failures():
        devs = [_dev(*table[res.key]) if res.key in table else None for table in earlier] + [_dev(metric, res)]
        if any(d is None for d in devs) or devs[0] <= 0 or devs[1] <= 0:
            continue
        if (devs[0] - devs[1]) / devs[0] < STALL_IMPROVEMENT and (devs[1] - devs[2]) / devs[1] < STALL_IMPROVEMENT:
            out.append((devs[2], f"- `{_clip(res.key, 48)}`：iter_{n0:02d} {_pct(devs[0])} → iter_{n1:02d} {_pct(devs[1])} → iter_{n2:02d} {_pct(devs[2])}"))
    return [text for _latest, text in sorted(out, key=lambda item: -item[0])]


def _change_points(text: str) -> list[str]:
    """changes.md 的摘要：优先取第一张带「文件」列的表（改了哪个文件、改了什么），没有就取二三级标题。"""
    rows = ms.parse_table_rows(text)
    first = next((r for r in rows if any("文件" in k for k in r.cells)), None)
    if first is not None:
        out: list[str] = []
        for row in rows:
            if row.header_start != first.header_start:
                continue
            where = next((v for k, v in row.cells.items() if "文件" in k), "")
            what = next((v for key in ("改动内容", "改动性质", "改动", "内容") if (v := _row(row.cells, key))), "")
            what = what or list(row.cells.values())[-1]
            out.append(f"- {_clip(where.replace('`', ''), 70)}：{_clip(what.replace('`', ''), 110)}")
        return out
    heads = [h.title for h in ms.headings(text) if h.level in (2, 3)]
    return [f"- {_clip(h, 84)}" for h in ([h for h in heads if "修改点" in h] or heads)]


def _iterate_round(ctx: _Ctx) -> list[Sec]:
    numbers = _round_dirs(ctx)
    recorded = (ctx.state.get("iteration") or {}).get("current")
    current = _round_no(ctx.payload) or (recorded if isinstance(recorded, int) and recorded > 0 else None) or (numbers[-1] if numbers else None)

    def iter_rel(n: int) -> str:
        return f"{ctx.ws}/iterations/iter_{n:02d}"

    changes = Sec("本轮修改点")
    if current:
        changes.source = f"{iter_rel(current)}/changes.md"
        diagnosis = _read_text(ctx.file(f"{iter_rel(current)}/diagnosis.md"))
        conclusion = _DIAG_CONCLUSION_RE.search(diagnosis) if diagnosis else None
        if conclusion:
            changes.lines.append(f"- 第 {current} 轮诊断结论：{conclusion.group(1)}")
        text = _read_text(ctx.file(changes.source))
        if text is not None:
            changes.items = _change_points(text)
        elif diagnosis is not None:
            changes.lines.append("- 这一轮没有 changes.md（诊断结论为 stop_partial 或 blocked 时不出修改）")

    rounds = [(n, r) for n in numbers if (r := _recalc(ctx, f"{iter_rel(n)}/comparison.json")) is not None]
    shown = rounds[-6:]
    trend = Sec("指标 × 轮次趋势")
    if shown:
        trend.source = f"{ctx.ws}/iterations/"
        trend.lines.append("各轮 `iter_NN/comparison.json` 按 standards.json 重算；下表先列达标数，再列最新一轮没过的指标在各轮的相对偏差。")
        header = "| 指标 | " + " | ".join(f"iter_{n:02d}" for n, _r in shown) + " |"
        trend.lead = [header, "| --- |" + " --- |" * len(shown)]
        trend.items = ["| 重算达标 | " + " | ".join(r.count_text() for _n, r in shown) + " |"]
        tables = [r.by_key() for _n, r in shown]
        for _metric, res in shown[-1][1].failures():
            cells = []
            for table in tables:
                one = table.get(res.key)
                cells.append("-" if one is None else ("达标" if one[1].passed is True else _pct(_dev(*one))))
            trend.items.append(f"| `{_cell(res.key, 44)}` | " + " | ".join(cells) + " |")
        trend.keep = 1

    excluded = Sec("已排除假设")
    seen: set[str] = set()
    for n in reversed(numbers):
        text = _read_text(ctx.file(f"{iter_rel(n)}/diagnosis.md"))
        if text is None:
            continue
        excluded.source = excluded.source or f"{iter_rel(n)}/diagnosis.md"
        for raw in _section_items(text, "已排除假设", skip_title="已确认读过"):
            body = _LIST_ITEM_RE.match(raw).group(1) if _LIST_ITEM_RE.match(raw) else raw
            bold = re.search(r"\*\*(.+?)\*\*", body)
            key = re.sub(r"[（(].*$", "", bold.group(1) if bold else body[:24]).strip()
            if key and key not in seen:
                seen.add(key)
                excluded.items.append(f"- iter_{n:02d}：{_clip(body.replace('**', ''), 100)}")
    if numbers and not excluded.items:
        excluded.lines.append("- 各轮诊断里都没有「已排除假设」一节的条目")

    warn = Sec("无改善预警", source=f"{ctx.ws}/iterations/")
    if len(rounds) < 3:
        warn.lines.append(f"- 快照只有 {len(rounds)} 份，不足三份，暂不判断（口径：同一指标连续两轮偏差改善都不到 10%）")
    else:
        warn.items = _stall_warnings(rounds)
        warn.lines.append(
            f"- 最新一轮仍没过的指标里，有 {len(warn.items)} 项连续两轮偏差改善都不到 10%"
            + ("" if warn.items else "，没有需要预警的")
        )
    return [changes, trend, excluded, warn]


def _coverage(ctx: _Ctx) -> Optional[str]:
    stats = ctx.state.get("coverage_stats") or {}
    rows = _matrix(ctx)
    if not (isinstance(stats.get("total"), int) and stats["total"] > 0):
        if not rows:
            return None
        statuses = [_row(r, "状态") for r in rows]
        stats = {
            "total": len(rows),
            "done": statuses.count("done"),
            "skipped": statuses.count("skipped"),
            "infeasible": statuses.count("infeasible"),
            "pending": sum(s not in ("done", "skipped", "infeasible") for s in statuses),
        }
        origin = "按矩阵现算"
    else:
        origin = "取自 state.coverage_stats"
    total = stats.get("total") or 0
    text = f"- 覆盖率 {stats.get('done', 0)}/{total}（{stats.get('done', 0) / total:.1%}，{origin}）：跳过 {stats.get('skipped', 0)} · 不可行 {stats.get('infeasible', 0)} · 未完成 {stats.get('pending', 0)}"
    core = [r for r in rows if _row(r, "优先级") == "core"]
    if core:
        text += f"；core {sum(_row(r, '状态') == 'done' for r in core)}/{len(core)}"
    return text


def _precheck_line(ctx: _Ctx) -> Optional[str]:
    """结果一致性预检的结论行：内核每次预检后写 audit/precheck_<阶段>.md，这里取最近一份的首行并给出链接。"""
    for stage in ("report", "result"):
        rel = f"{ctx.ws}/audit/precheck_{stage}.md"
        text = _read_text(ctx.file(rel))
        body = [line.strip() for line in (text or "").splitlines() if line.strip() and not line.startswith("#")]
        if body:
            return f"- {_clip(body[0], 200)}（明细：{ctx.link(rel, rel)}）"
    return None


def _pre_report(ctx: _Ctx) -> list[Sec]:
    matrix_rel = f"{ctx.ws}/spec/coverage_matrix.md"
    responses_rel = f"{ctx.ws}/audit/audit_responses.md"
    verdict = ctx.state.get("verdict") or {}
    recalc = _recalc(ctx, f"{ctx.out}/results/comparison.json")

    head = Sec("verdict 与覆盖率")
    if verdict.get("result") or recalc:
        head.lines.append(f"- verdict：{verdict.get('result') or '尚未写入 state'}" + (f"；{recalc.summary()}" if recalc else "；没有可重算的 comparison.json"))
    coverage = _coverage(ctx)
    if coverage:
        head.lines.append(coverage)
    precheck = _precheck_line(ctx)
    if precheck:
        head.lines.append(precheck)

    reviews = Sec("三审查点的引擎与降级", lead=["| 审查点 | 引擎 | 降级 | 结论 | critical / major / minor |", "| --- | --- | --- | --- | --- |"])
    all_reviews = _reviews(ctx)
    for point in ("spec", "code", "result"):
        mine = [r for r in all_reviews if r.get("checkpoint") == point]
        if not mine:
            reviews.items.append(f"| {point} | 尚无记录 | - | - | - |")
            continue
        last = mine[-1]
        engine = str(last.get("engine") or "未记录")
        degraded = "是" if "fallback" in engine or engine == "skipped" else "否"
        counts = " / ".join(_cell(last.get(level, "-"), 6) for level in ("critical", "major", "minor"))
        reviews.items.append(f"| {point} | {_cell(engine, 24)} | {degraded} | {_cell(last.get('verdict'), 20)} | {counts} |")
    reviews.keep = len(reviews.items)
    others = sorted({str(r.get("checkpoint")) for r in all_reviews} - {"spec", "code", "result"})
    if others:
        reviews.lines.append(f"- 另有增量审查记录：{_clip('、'.join(others), 60)}")
    if not all_reviews:
        reviews.items, reviews.keep = [], 0

    responses = _responses(ctx)
    rejected_rows = [r for r in responses or [] if r["disposal"] == "rejected"]
    rejected = Sec("rejected 意见", source=responses_rel)
    if responses is not None:
        rejected.lines.append(f"- 回应表共 {len(responses)} 条带编号的外审意见，其中 rejected {len(rejected_rows)} 条")
        rejected.items = [f"- {r['id']}（{r['severity'] or '未定级'}）：{_clip(r['summary'], 80)}" for r in rejected_rows]
        rejected.keep = len(rejected.items)

    rows = _matrix(ctx)
    undone = Sec("未复现清单", source=matrix_rel)
    if rows:
        hit = [r for r in rows if _row(r, "状态") in SKIPPED_STATUSES]
        undone.lines.append(f"- 矩阵 {len(rows)} 行里 skipped / infeasible 共 {len(hit)} 行")
        undone.items = [
            f"- {_row(r, '要素ID')} {_clip(_row(r, '描述'), 26)}（{_row(r, '优先级') or '未定级'}，{_row(r, '状态')}）：{_clip(_row(r, '状态理由') or '未写理由', 70)}"
            for r in hit
        ]

    precheck = Sec("G-FN 输入侧预检")
    if rows:
        open_rows = [_row(r, "要素ID") for r in rows if _row(r, "状态") in ("pending", "in_progress")]
        precheck.lines.append("- 矩阵没有 pending / in_progress 行（G-FN-3）：" + ("是" if not open_rows else f"否，还有 {_clip(' '.join(open_rows), 90)}"))
    else:
        precheck.lines.append("- 矩阵没有 pending / in_progress 行（G-FN-3）：无法检查，没有覆盖矩阵")
    docs = ctx.docs
    if docs and docs.assumptions is not None:
        left = [b.id for b in docs.assumption_blocks if _PLACEHOLDER in b.text]
        stray = docs.assumptions.text.count(_PLACEHOLDER)
        precheck.lines.append(
            f"- 假设登记簿没有残留 `{_PLACEHOLDER}`（G-FN-4）：" + ("是" if not stray else f"否，{stray} 处" + (f"（{_clip(' '.join(left), 80)}）" if left else ""))
        )
    else:
        precheck.lines.append(f"- 假设登记簿没有残留 `{_PLACEHOLDER}`（G-FN-4）：无法检查，没有 assumptions.md")
    ids = [r["id"] for r in rejected_rows]
    precheck.lines.append("- rejected 意见编号须原样写进报告（G-FN-5）：" + (_clip(" ".join(ids), 120) if ids else "没有 rejected 意见"))
    return [head, reviews, rejected, undone, precheck]


def _final_review(ctx: _Ctx) -> list[Sec]:
    report_rel = f"{ctx.ws}/final_report.md"
    report = _read_text(ctx.file(report_rel))
    verdict = ctx.state.get("verdict") or {}
    recalc = _recalc(ctx, f"{ctx.out}/results/comparison.json")

    conclusion = Sec("结论与评级")
    if verdict.get("result"):
        conclusion.lines.append(f"- verdict：{verdict['result']}")
    if report is not None:
        m = _RATING_RE.search(report)
        if m:
            end = report.find("\n", m.start())
            sentence = report[m.start(): end if end != -1 else len(report)]
            conclusion.lines.append(f"- {_clip(sentence.replace('**', ''), 230)}")
        else:
            conclusion.lines.append("- 最终报告里没有找到「可信度评级：X（…）」这句话")
    if recalc:
        conclusion.lines.append(f"- {recalc.summary()}")
    coverage = _coverage(ctx)
    if coverage and conclusion.lines:
        conclusion.lines.append(coverage)
    precheck = _precheck_line(ctx)
    if precheck:
        conclusion.lines.append(precheck)

    paths = Sec("报告与结果页")
    for label, rel in (("最终报告", report_rel), ("结果页", f"{ctx.out}/final_report.html"), ("验证报告", f"{ctx.out}/verify_report.md"), ("样本外报告", f"{ctx.ws}/oos_report.md")):
        if ctx.file(rel).is_file():
            paths.lines.append(f"- {label}：{ctx.link(rel, rel)}")
    xlsx = next((rel for rel in (f"{ctx.ws}/assumptions.xlsx", f"{ctx.out}/assumptions.xlsx") if ctx.file(rel).is_file()), None)
    batch = "`" + REVISE_FROM_EXCEL.format(flow=FLOW, id=ctx.report_id, quote=QUOTE_PLACEHOLDER) + "`"
    if xlsx:
        paths.lines.append(f"- 假设登记簿 Excel：{ctx.link(xlsx, xlsx)}（黄底三列可改；改完用 {batch} 成批修订）")
    elif paths.lines:
        paths.lines.append(
            f"- 假设登记簿 Excel：还没有导出，用 `tools/assumptions_xlsx.py export {ctx.report_id}` 生成 `{ctx.ws}/assumptions.xlsx`；"
            f"改完用 {batch} 成批修订"
        )
    return [conclusion, paths]


def _data_gap(ctx: _Ctx) -> list[Sec]:
    gap = _gap_section(ctx) or Sec("缺口清单", source=f"{ctx.ws}/data_check.json")
    keys = {o["key"] for o in checkpoint_options(ctx.name, ctx.cp)}
    table = Sec("处置选项", lead=["| 处置 | 选项键 | 含义 | 之后 |", "| --- | --- | --- | --- |"])
    for label, aliases, meaning, after in DATA_GAP_ROWS:
        key = next((a for a in aliases if a in keys), None)
        table.items.append(f"| {label} | {f'`{key}`' if key else '-'} | {meaning} | {after} |")
    table.keep = len(table.items)
    return [gap, table]


def _empty_leaves(node: Any, trail: str = "") -> list[str]:
    """metrics.json 里算不出来的叶子（空值、NaN、无穷）的路径。"""
    if isinstance(node, dict):
        return [hit for k, v in node.items() for hit in _empty_leaves(v, f"{trail}.{k}" if trail else str(k))]
    if isinstance(node, list):
        return [hit for i, v in enumerate(node) for hit in _empty_leaves(v, f"{trail}[{i}]")]
    bad = node is None or (isinstance(node, float) and not math.isfinite(node))
    return [trail or "(根)"] if bad else []


def _trial_facts(ctx: _Ctx, mock_rel: str) -> Optional[dict[str, Any]]:
    """试跑三件事的检查结果：内核试跑检查给了就用它的，没给就按同样的口径从结果目录现算。

    口径（同 kernelsteps.trial_check）：跑得通 = run_log.md 含 exit=0；产物齐 = standards.json 要求的
    图表、Excel 以及 metrics.json 都在且非空；指标都算得出 = metrics.json 里没有空值、NaN 或无穷。
    """
    payload = ctx.payload
    if isinstance(payload.get("ran"), bool):
        return {
            "ran": payload["ran"],
            "missing": [str(x) for x in payload.get("missing") or []],
            "empty": [str(x) for x in payload.get("empty_metrics") or []],
            "origin": "取自内核试跑检查的记录",
        }
    mock_dir = ctx.file(mock_rel)
    if not mock_dir.is_dir():
        return None
    run_log = _read_text(mock_dir / "run_log.md")
    std = ctx.standards.get(ctx.state.get("type")) or {}
    wanted = [str(n) for n in [*(std.get("required_charts") or []), *(std.get("required_excels") or [])]] + ["metrics.json"]
    metrics = _read_json(mock_dir / "metrics.json")
    return {
        "ran": run_log is not None and "exit=0" in run_log,
        "missing": [n for n in wanted if not (mock_dir / n).is_file() or (mock_dir / n).stat().st_size == 0],
        "empty": _empty_leaves(metrics)[:50] if metrics is not None else ["metrics.json 读不出来"],
        "origin": "按结果目录里的文件现算",
    }


def _trial_done(ctx: _Ctx) -> list[Sec]:
    mock_rel = _inside(ctx.payload.get("results_dir")) or f"{ctx.out}/results_mock"
    mock_dir = ctx.file(mock_rel)
    facts = _trial_facts(ctx, mock_rel)
    yes_no = {True: "是", False: "否"}

    checks = Sec("试跑只查三件事")
    if facts:
        checks.lines.append(f"- 跑得通：{yes_no[bool(facts['ran'])]}（run_log.md {'含' if facts['ran'] else '不含'} exit=0）")
        checks.lines.append(f"- 产物齐：{yes_no[not facts['missing']]}" + (f"（缺 {len(facts['missing'])} 个：{_clip('、'.join(facts['missing']), 110)}）" if facts["missing"] else ""))
        checks.lines.append(
            f"- 指标都算得出：{yes_no[not facts['empty']]}" + (f"（{len(facts['empty'])} 处算不出：{_clip('、'.join(facts['empty']), 110)}）" if facts["empty"] else "")
        )
        checks.lines.append(f"- 以上{facts['origin']}")
    else:
        checks.lines.append(f"- 试跑结果目录 `{mock_rel}/` 不存在，三件事都无从检查")
    checks.lines.append("- 试跑不出 verdict、不进迭代、不写报告；真实结果目录里不该有 mock 算出来的东西")

    where = Sec("试跑结果目录")
    where.lines.append(f"- `{mock_rel}/`" + (f"，{sum(1 for p in mock_dir.iterdir() if p.is_file())} 个文件" if mock_dir.is_dir() else "（尚不存在）"))

    # 数据清单由 common/data_loader.py 的 write_data_manifest 写出：files 里每条带 name 与 source（real / mock）
    mocked = Sec("哪些数据是 mock")
    manifest_rel = f"{mock_rel}/data_manifest.json"
    manifest = _read_json(ctx.file(manifest_rel))
    files = [f for f in manifest.get("files") or [] if isinstance(f, dict)] if isinstance(manifest, dict) else None
    if files is not None:
        mocked.source = manifest_rel
        names = [str(f.get("name") or f.get("path") or "未命名") for f in files if f.get("source") == "mock"]
        mocked.lines.append(f"- 数据清单 `{manifest_rel}` 记了 {len(files)} 个文件，其中 mock {len(names)} 个、真实 {len(files) - len(names)} 个")
        mocked.items = [f"- `{_clip(n, 90)}`" for n in names]
    elif isinstance(ctx.payload.get("mock_files"), list):
        names = [str(n) for n in ctx.payload["mock_files"]]
        mocked.lines.append(f"- 内核试跑检查记下 mock 文件 {len(names)} 个（数据清单 `{manifest_rel}` 现在读不到）")
        mocked.items = [f"- `{_clip(n, 90)}`" for n in names]
    return [checks, where, mocked]


def _circuit_breaker(ctx: _Ctx) -> list[Sec]:
    streak = ctx.payload.get("streak")
    streak = {str(k): n for k, n in streak.items()} if isinstance(streak, dict) else {}
    counters = Sec("连败的检查项")
    if streak:
        counters.items = [
            f"- {STAGE_CN.get(k.split(':', 1)[0], k.split(':', 1)[0])} {k.split(':', 1)[-1]}：连续 {_clip(n, 6)} 次未过" for k, n in streak.items()
        ]
        counters.keep = len(counters.items)
        counters.lines.append(f"- 同一（阶段，检查项）连续 {getattr(st, 'BREAKER_THRESHOLD', 3)} 次未过即熔断")

    # 连败计数的键是「阶段:检查项」；明细按这些阶段各取最近一次门禁结果，检查点自己的阶段兜底
    stages = [k.split(":", 1)[0] for k in streak if ":" in k] + [str(ctx.cp.get("stage") or ctx.state.get("current_stage") or "")]
    gate_latest = ctx.state.get("gate_latest") or {}
    detail = Sec("最近一次未过的明细", source=f"{ctx.ws}/events.jsonl")
    for stage in dict.fromkeys(s for s in stages if s):
        latest = gate_latest.get(stage)
        if not isinstance(latest, dict):
            continue
        failed = [f for f in latest.get("failed") or [] if isinstance(f, dict)]
        detail.lines.append(f"- {STAGE_CN.get(stage, stage)}门禁，{_ts(latest.get('timestamp'))}，结论 {latest.get('verdict')}，未过 {len(failed)} 项")
        detail.items += [f"- {f.get('id')} {_clip(f.get('desc'), 50)}" + (f"：{_clip(f.get('detail'), 220)}" if f.get("detail") else "") for f in failed]
    return [counters, detail]


def _demoted(text: str) -> list[tuple[int, str]]:
    """逐行返回（标题级别，行）：标题行降两级（# → ###）好嵌进审阅包的二级小节，其余行级别记 0、文字不动。

    代码围栏里的 # 行不算标题。
    """
    out: list[tuple[int, str]] = []
    fenced = False
    for line in text.strip("\n").splitlines():
        if _FENCE_LINE_RE.match(line):
            fenced = not fenced
        m = None if fenced else _HEADING_LINE_RE.match(line)
        out.append((len(m.group(1)), "#" * min(len(m.group(1)) + 2, 6) + line[m.end():]) if m else (0, line))
    return out


def _split_report(rows: list[tuple[int, str]]) -> tuple[str, list[str]]:
    """把一份自带标题的 markdown 拆成（开头, 各段）：一个标题一段，截断时按整段截。

    开头 = 第一个标题之前的文字，加上文档标题（一级标题）连同它下面的概述；放不下时开头也留着。
    """
    chunks: list[list[str]] = [[]]
    levels: list[int] = [0]
    for level, line in rows:
        if level:
            chunks.append([line])
            levels.append(level)
        else:
            chunks[-1].append(line)
    blocks = ["\n".join(chunk).strip("\n") for chunk in chunks]
    lead = 2 if len(levels) > 1 and levels[1] == 1 else 1
    return "\n\n".join(b for b in blocks[:lead] if b), [b for b in blocks[lead:] if b]


def _gap_section(ctx: _Ctx) -> Optional[Sec]:
    """内核渲染好的缺口清单（payload.gap_report）原样放入，只把它自带的标题降级；没有就返回 None。

    清单分了小节（一个缺口一节）时按整节截断，开头的概述总是留着；是表格或纯文字时逐行截断。
    """
    report = ctx.payload.get("gap_report")
    if not isinstance(report, str) or not report.strip():
        return None
    sec = Sec("缺口清单", source=f"{ctx.ws}/data_check.json")
    rows = _demoted(report)
    head, blocks = _split_report(rows)
    if blocks:
        sec.lines, sec.items, sec.sep = ([head] if head else []), blocks, "\n\n"
    else:
        sec.items = [line for _level, line in rows]
    return sec


def _generic(ctx: _Ctx) -> list[Sec]:
    """通用模板：payload 的要点按键逐行列出（过长截断）；带缺口清单的检查点把清单单列一节。"""
    gap = _gap_section(ctx)
    points = Sec("要点")
    for key, value in ctx.payload.items():
        if gap is not None and key == "gap_report":
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        points.items.append(f"- {_clip(key, 30)}：{_clip(text, 200)}")
    if not points.items:
        payload = ctx.cp.get("payload")
        if payload not in (None, "", {}, []) and not isinstance(payload, dict):
            points.items.append(f"- {_clip(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str), 300)}")
        elif gap is None:
            points.lines.append("- 内核没有附带更多要点；需要时看看板和 `flow status`")
    gate = _gate_line(ctx, str(ctx.cp.get("stage") or ctx.state.get("current_stage") or ""))
    if gate:
        points.lines.append(gate)
    return ([gap] if gap is not None else []) + ([points] if points.items or points.lines else [])


_BUILDERS: dict[str, Callable[[_Ctx], list[Sec]]] = {
    "spec_final": _spec_final,
    "plan_final": _plan_final,
    "milestone_done": _milestone_done,
    "verify_done": _verify_done,
    "iterate_round": _iterate_round,
    "pre_report": _pre_report,
    "final_review": _final_review,
    "data_gap": _data_gap,
    "trial_done": _trial_done,
    "circuit_breaker": _circuit_breaker,
}


# ---------------------------------------------------------------------------
# 头、尾与对外接口
# ---------------------------------------------------------------------------


def _head(ctx: _Ctx) -> str:
    cp_id = ctx.cp.get("id")
    lines = [f"# {checkpoint_title(ctx.name, ctx.cp)} · {ctx.report_id}" + (f"（{_clip(cp_id, 12)}）" if cp_id else ""), ""]
    meta: list[str] = []
    stage = ctx.cp.get("stage") or ctx.state.get("current_stage")
    if stage:
        meta.append(f"所在阶段：{STAGE_CN.get(str(stage), str(stage))}")
    if ctx.cp.get("opened_at"):
        meta.append(f"开出时间：{_ts(ctx.cp['opened_at'])}")
    if meta:
        lines += ["> " + " · ".join(meta), ""]
    reason = _clip(ctx.cp.get("reason"), 240)
    default = WHY.get(ctx.name, "")
    why = "\n\n".join(t for t in (reason, default) if t) or "流程走到了需要人来决定的地方，内核没有给出更具体的原因。"
    return "\n".join(lines + ["## 为什么停在这里", "", why]) + "\n\n"


def _tail(ctx: _Ctx) -> str:
    lines = ["## 你可以怎么决定", ""]
    decision = ctx.cp.get("decision")
    if isinstance(decision, dict) and decision.get("choice"):
        by = str(decision.get("by") or "")
        lines.append(
            f"这个检查点已经处理：选择 `{_clip(decision['choice'], 30)}`，放行方：{_clip(BY_CN.get(by, by) or '未记录', 12)}，"
            f"凭据：{_clip(credential_cn(decision.get('credential')), 24)}，{_ts(decision.get('at'))}。"
        )
    elif is_auto(ctx.cp, ctx.name):
        lines.append("这个检查点按策略自动放行，只留痕，不需要你决定。")
    else:
        options = checkpoint_options(ctx.name, ctx.cp)
        for option in options[:MAX_OPTIONS]:
            key = _clip(option["key"], 30)
            lines.append(f"- `{key}` {_clip(option['label'], 110)}".rstrip())
            lines.append(f"  `{option_command(ctx.report_id, ctx.name, ctx.cp.get('id'), key)}`")
        if len(options) > MAX_OPTIONS:
            lines.append(f"- 其余 {len(options) - MAX_OPTIONS} 个选项见 `{ctx.ws}/state.json`")
        code = ctx.cp.get("code")
        lines.append("")
        lines.append(
            (f"在自己的终端执行时要输入放行短码 `{_clip(code, 12)}`；在对话里答复也请带上它。" if code else "放行短码在检查点开出后由 `flow status` 给出，在自己的终端执行时要输入。")
            + "没有这个凭据的放行会记为「自述」。"
        )
    return "\n".join(lines + ["", "---", "", FOOTER]) + "\n"


def _pending_named(state: dict[str, Any], name: str) -> dict[str, Any]:
    """state 里同名且待决的检查点；没有就返回空字典（按「还没开出」渲染）。"""
    found = st.find_checkpoint(state, name)
    if isinstance(found, dict) and found.get("name") == name and found.get("status") == "pending":
        return found
    return {}


def render(root: Path, report_id: str, name: str, *, state: dict, checkpoint: dict | None = None) -> str:
    """生成某个检查点的审阅包正文（markdown）。纯函数：只读文件，不写任何东西。

    checkpoint 不给时，取 state 里同名且待决的那一个；没有就按「还没开出」渲染，
    命令里的检查点编号留占位符。
    """
    state = state if isinstance(state, dict) else {}
    cp = checkpoint if isinstance(checkpoint, dict) else _pending_named(state, str(name))
    ctx = _Ctx(Path(root), str(report_id), str(name), state, cp)
    try:
        secs = _BUILDERS.get(ctx.name, _generic)(ctx)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        # 文书写坏了也不能卡住「停下来等人」这一步：退回通用模板，并把原因写明
        secs = _generic(ctx) + [Sec("渲染说明", lines=[f"- 专用模板渲染失败（{type(exc).__name__}：{_clip(exc, 120)}），已退回通用模板；请直接看原始文书"])]
    if ctx._docs_error:
        secs.append(Sec("读取说明", lines=[f"- 案例文书读取失败（{ctx._docs_error}），上面凡是取自 spec / plan / 假设登记簿 / 覆盖矩阵的小节都按缺失处理"]))
    return _compose(_head(ctx), secs, _tail(ctx), limit_for(ctx.name))


def write(root: Path, report_id: str, checkpoint: dict, *, state: dict) -> str:
    """渲染并写到 pack_path，返回相对路径。reviews 目录不存在就创建。"""
    name = str(checkpoint.get("name") or "checkpoint")
    rel = pack_path(report_id, str(checkpoint.get("id") or "cp_00"), name)
    target = Path(root) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    text = render(Path(root), report_id, name, state=state, checkpoint=checkpoint)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    return rel
