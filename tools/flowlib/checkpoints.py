"""检查点：名称与选项、开与关、审阅包、凭据等级、停滞与预算。

底层读写在 tools/state.py（open_checkpoint_in / resolve_checkpoint_in），这里是策略：
哪些检查点只能人放行、每个检查点给人哪些选项、放行凭什么算数。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from tools import state as st

from . import events as ev
from .core import Ctx, FlowError, write_text

AWAIT = "awaiting_review"
PAUSE = "paused_blocked"

_REVIEW = [
    ("approve", "通过，继续"),
    ("modify", "修改后继续：原话里写明要改什么，交给负责的角色去改"),
    ("edited", "我已经直接改了文件，请重新核对后继续"),
    ("rollback", "回退到更早的阶段重做（放行命令加 --to <阶段|mN> 指定从哪里开始）"),
    ("abort", "终止这个案例"),
]
_RETRY = [
    ("retry", "再试一轮（相关计数清零）"),
    ("pin_card", "这个阶段退回执行卡驱动，由主会话按说明处理"),
    ("abort", "终止这个案例"),
]
_CONTINUE = [("continue", "已处理，继续"), ("abort", "终止这个案例")]

# 名称 → （中文名, 等待态, 选项）。只能由人放行。
HUMAN: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    "pdf_duplicate": ("同一份 PDF 已有案例", PAUSE, [("continue", "仍然新建并继续"), ("abort", "终止这个新案例，改去续跑已有的")]),
    "spec_final": ("spec 定稿", AWAIT, _REVIEW),
    "data_gap": (
        "数据缺口处置",
        PAUSE,
        [
            ("supply", "补数据：我去补，补完再体检"),
            ("substitute", "等价替代：用本地等价数据（strict 模式下会切到实验模式）"),
            ("narrow", "缩小范围：只在有数据的区间或标的上复现"),
            ("mock", "先用 mock 试跑：只把代码和流水线跑通，这一轮不出结论"),
            ("drop", "砍掉相关要素：标为 infeasible，其余照做"),
            ("abort", "终止：放弃这份研报"),
        ],
    ),
    "data_wait": ("等人补数据", PAUSE, [("recheck", "数据已补齐，重新体检"), ("change", "改用别的处置方式"), ("abort", "终止这个案例")]),
    "mock_spec": (
        "mock 规格确认",
        AWAIT,
        [
            ("approve", "按这份规格生成 mock 并试跑"),
            ("edited", "我改了规格文件，按改后的生成"),
            ("change", "不用 mock 了，改用别的处置方式"),
            ("abort", "终止这个案例"),
        ],
    ),
    "trial_done": ("试跑完成", AWAIT, [("wait_real", "等真实数据到位再出结论"), ("change", "改用别的处置方式，按真实数据走完"), ("abort", "终止这个案例")]),
    "feasibility_blocked": (
        "可行性阻断",
        PAUSE,
        [
            ("supply", "补数据后重新分诊"),
            ("experimental", "切换到实验模式：用本地等价数据做市场迁移复现（数值判定豁免，报告显著声明）"),
            ("degrade", "降级复现（原话里写明接受哪些降级）"),
            ("abort", "放弃这份研报"),
        ],
    ),
    "blocking_ambiguity": ("阻断级歧义", PAUSE, [("answer", "我来裁决（原话里写明每条歧义怎么定）"), ("abort", "终止这个案例")]),
    "plan_final": ("plan 定稿", AWAIT, _REVIEW),
    "milestone_done": ("milestone 完成", AWAIT, _REVIEW),
    "verify_done": ("verify 完成", AWAIT, _REVIEW),
    "iterate_round": ("迭代一轮结束", AWAIT, _REVIEW),
    "iterate_blocked": ("迭代缺外部输入", PAUSE, [("continue", "已补齐，继续下一轮"), ("stop_partial", "接受现状，按部分达标收尾"), ("abort", "终止这个案例")]),
    "pre_report": ("写报告之前", AWAIT, _REVIEW),
    "final_review": (
        "最终评审",
        AWAIT,
        [
            ("accept", "通过并收尾（flow accept）"),
            ("revise", "修改假设后定向重跑（flow revise）"),
            ("reopen", "回退到更早的阶段重做（flow reopen）"),
            ("abort", "终止这个案例"),
        ],
    ),
    "circuit_breaker": ("门禁连败熔断", PAUSE, _RETRY),
    "redispatch_exhausted": ("重派超过上限", PAUSE, _RETRY),
    "review_rounds_exhausted": ("复审超过上限", PAUSE, _RETRY),
    "step_blocked": ("子 agent 报告受阻", PAUSE, _RETRY),
    "stuck": ("内核判断不了下一步", PAUSE, _RETRY),
    "critical_dispute": ("critical 意见有争议", PAUSE, [("uphold", "意见成立，必须修复"), ("waive", "裁定意见不成立（原话里写明理由）"), ("abort", "终止这个案例")]),
    "tamper": ("事件流校验未通过", PAUSE, [("acknowledge", "已知悉，继续（原话里说明原因）"), ("abort", "终止这个案例")]),
    "stall": ("长时间没有新进展", PAUSE, _CONTINUE),
    "budget": ("预算超限", PAUSE, [("raise", "提高预算后继续（用 --budget-tokens / --budget-hours 给出新预算）"), ("continue", "不再设预算，继续"), ("abort", "终止这个案例")]),
    "until": ("到达指定阶段", AWAIT, _REVIEW),
    "step": ("单步停点", AWAIT, _REVIEW),
    "legacy_pause": ("迁移前的暂停", PAUSE, _CONTINUE),
    "manual_pause": ("手动暂停", PAUSE, _CONTINUE),
}
# 按策略自动放行、只留痕
AUTO = {"external_degraded": "外审降级", "false_fail_rerun": "假 FAIL 复跑", "redispatch": "限额内重派"}
# 不改变案例走向、只是让人看一眼的检查点：通过类选项统一处理
PASS_CHOICES = {"approve", "continue", "acknowledge"}
CREDENTIALS = ("hook", "terminal", "self_report")
CREDENTIAL_CN = {"hook": "钩子记录的用户原话", "terminal": "人在终端输入了短码", "self_report": "自述（没有人在场凭据）", "policy": "启动时预先声明的策略"}


def cn(name: str) -> str:
    if name in HUMAN:
        return HUMAN[name][0]
    return AUTO.get(name, name)


def options_of(name: str) -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in (HUMAN.get(name) or ("", "", _CONTINUE))[2]]


def _write_pack(ctx: Ctx, checkpoint: dict[str, Any], state: dict[str, Any]) -> Optional[str]:
    """生成审阅包；审阅包模块不可用或渲染出错时退回一份最简的，不能因为它开不了检查点。"""
    try:
        from . import reviewpacks

        return reviewpacks.write(ctx.root, ctx.report_id, checkpoint, state=state)
    except Exception as exc:  # noqa: BLE001 - 展示层的任何错误都不该挡住检查点
        rel = f"{ctx.ws}/reviews/{checkpoint['id']}_{checkpoint['name']}.md"
        lines = [
            f"# {cn(checkpoint['name'])} · {ctx.report_id}",
            "",
            f"为什么停在这里：{checkpoint.get('reason') or '（未说明）'}",
            "",
            "你可以怎么决定：",
            *[f"- `{o['key']}`：{o['label']}" for o in checkpoint.get("options") or []],
            "",
            f"放行命令：`flow decide {ctx.report_id} {checkpoint['id']} --choice <选项> --quote \"<你的原话>\"`（放行短码 {checkpoint.get('code')}）",
            "",
            f"（审阅包渲染出错，这是最简版本：{exc}）",
        ]
        write_text(ctx.root / rel, "\n".join(lines) + "\n")
        return rel


def open_human(
    txn: st.Txn,
    ctx: Ctx,
    name: str,
    *,
    reason: str,
    stage: Optional[str] = None,
    payload: Any = None,
    options: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """开一个只能由人放行的检查点，并生成审阅包。同名、同阶段、同载荷的检查点已在等时不重复开。"""
    if name not in HUMAN:
        raise FlowError(f"未知检查点: {name}")
    stage = stage if stage is not None else txn.state.get("current_stage")
    for existing in st.pending_checkpoints(txn.state):
        if existing.get("name") == name and existing.get("stage") == stage and existing.get("payload") == payload:
            return existing
    cp = st.open_checkpoint_in(
        txn,
        name,
        kind="human",
        stage=stage,
        reason=reason,
        options=options or options_of(name),
        pause_status=HUMAN[name][1],
        payload=payload,
        question=f"{cn(name)}：{reason}",
    )
    cp["pack"] = _write_pack(ctx, cp, txn.state)
    return cp


def record_auto(txn: st.Txn, name: str, *, reason: str, stage: Optional[str] = None, payload: Any = None) -> dict[str, Any]:
    """按策略自动放行的检查点：开了就关，只留痕。"""
    if name not in AUTO:
        raise FlowError(f"{name} 不是可以自动放行的检查点")
    cp = st.open_checkpoint_in(txn, name, kind="auto", stage=stage, reason=reason, pause_status=None, payload=payload)
    st.resolve_checkpoint_in(txn, cp, choice="auto", credential="policy", by="policy", resume_status=None)
    return cp


def ensure_wait_checkpoint(txn: st.Txn, ctx: Ctx) -> Optional[dict[str, Any]]:
    """案例在等待态却没有待决的人工检查点（比如执行卡把它置成了暂停）：补一个，让它有合法出口。"""
    state = txn.state
    if state.get("status") not in st.WAITING_STATUSES or st.pending_checkpoints(state):
        return None
    review = state.get("status") == AWAIT
    name = "final_review" if review and state.get("current_stage") in ("report", "review") else ("until" if review else "manual_pause")
    cp = st.open_checkpoint_in(
        txn,
        name,
        kind="human",
        reason=str(state.get("pending_question") or "") or ("等待评审" if review else "案例被置为暂停，等人处理"),
        options=options_of(name),
        pause_status=None,
        payload={"blockers": state.get("blockers") or []} if state.get("blockers") else None,
    )
    cp["prev_status"] = "running"
    cp["pack"] = _write_pack(ctx, cp, state)
    return cp


# ---------------------------------------------------------------------------
# 「人在场」凭据
# ---------------------------------------------------------------------------

PRESENCE_LOG = "workspace/_registry/presence.jsonl"


def presence_entries(root: Path, since: Optional[str] = None) -> list[dict[str, Any]]:
    """钩子记下的用户输入（tools/presence.py 写）。没有钩子的宿主上这个文件不存在。"""
    path = root / PRESENCE_LOG
    if not path.is_file():
        return []
    start = ev.parse_ts(since) if since else None
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        ts = ev.parse_ts(item.get("ts"))
        if start and ts and ts < start:
            continue
        out.append(item)
    return out


def _normalize(text: str) -> str:
    return "".join(str(text).split()).lower()


def credential_for(root: Path, checkpoint: dict[str, Any], quote: str, typed_code: Optional[str] = None) -> str:
    """这次放行凭什么算数。

    钩子：检查点打开之后，钩子记到了人的输入，并且能和这个检查点对上——
          人亲手输入的话里有放行短码，或包含这次引用的原话；
          或者人回答了一个带着这个检查点短码的提问（提问工具的回答）。
    终端：命令是在交互终端里执行的，并且当场输入的短码与检查点的一致；
    否则是自述。
    """
    code = str(checkpoint.get("code") or "")
    want = _normalize(quote)
    for entry in presence_entries(root, checkpoint.get("opened_at")):
        said = _normalize(entry.get("text") or "")
        if entry.get("source") == "ask":
            # 提问是编排者写的，只有题面带着这个检查点的短码，回答才算是针对它的
            if code and code.lower() in _normalize(entry.get("question") or "") and said:
                return "hook"
            continue
        if (code and code.lower() in said) or (len(want) >= 4 and want in said):
            return "hook"
    if typed_code and code and typed_code.strip().upper() == code.upper():
        return "terminal"
    return "self_report"


def ask_code_on_tty(checkpoint: dict[str, Any]) -> Optional[str]:
    """在交互终端里要求输入放行短码；不是交互终端时返回 None。"""
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or os.environ.get("REPRODUCE_NO_TTY"):
        return None
    try:
        return input(f"输入检查点 {checkpoint.get('id')} 的放行短码（见审阅包或看板）：").strip()
    except (EOFError, KeyboardInterrupt):
        return None


# ---------------------------------------------------------------------------
# 停滞与预算
# ---------------------------------------------------------------------------


def stall_hours(ctx: Ctx) -> float:
    configured = ctx.policy.get("stall_hours") or (ctx.config.get("flow") or {}).get("stall_hours")
    try:
        return float(configured) if configured else ev.DEFAULT_STALL_HOURS
    except (TypeError, ValueError):
        return ev.DEFAULT_STALL_HOURS


def stalled(ctx: Ctx, timeline: Optional[list[dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
    """运行中、有派给子 agent 的在途步骤、超过阈值没有新事件 → 停滞。外审在后台跑的时候不算。"""
    state = ctx.state
    if state.get("status") != "running":
        return None
    inflight = [(sid, rec) for sid, rec in ctx.steps.items() if rec.get("status") == "inflight"]
    if not inflight or any(rec.get("kind") == "exec" for _sid, rec in inflight):
        return None
    info = ev.stall_info(state, threshold_hours=stall_hours(ctx), timeline=timeline)
    if not info["stalled"]:
        return None
    return {"idle_hours": round(info["idle_hours"], 1), "steps": [sid for sid, _rec in inflight], "threshold": stall_hours(ctx)}


def budget_exceeded(ctx: Ctx, timeline: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """预算：墙钟按案例的业务起止时间算；token 取各步骤事件里记下的累计输入（读得到宿主记录时才有）。"""
    policy = ctx.policy
    hours_cap, token_cap = policy.get("budget_hours"), policy.get("budget_tokens")
    if not hours_cap and not token_cap:
        return None
    first = next((item.get("ts") for item in timeline if item.get("ts")), None)
    elapsed = ev.hours_since(first) if first else None
    tokens = 0
    for item in timeline:
        payload = item.get("payload")
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            tokens += int(usage.get("total_input") or 0) + int(usage.get("output") or 0)
    if hours_cap and elapsed is not None and elapsed > float(hours_cap):
        return {"kind": "hours", "used": round(elapsed, 1), "cap": hours_cap}
    if token_cap and tokens > float(token_cap):
        return {"kind": "tokens", "used": tokens, "cap": token_cap}
    return None
