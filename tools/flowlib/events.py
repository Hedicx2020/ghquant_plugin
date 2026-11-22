"""事件时间线的读取与人话描述。

写入在 tools/state.py（状态的唯一写入口，案例锁与哈希链也在那里）。这里只读：
v2 案例读 events.jsonl；v1 案例把 state 里的事件与门禁按时间归并成同样的形状，
这样看板和 status 不用区分新旧案例。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tools import state as st

STAGE_CN = {
    "init": "初始化",
    "extract": "提取",
    "plan": "计划",
    "spec_audit": "规格审计",
    "implement": "编码",
    "code_audit": "代码审计",
    "verify": "验证",
    "iterate": "迭代",
    "result_audit": "结果审计",
    "oos": "样本外",
    "report": "报告",
    "review": "人工评审",
}
STAGE_STATUS_CN = {
    "pending": "未开始",
    "running": "进行中",
    "done": "已完成",
    "failed": "失败",
    "skipped": "已跳过",
    "blocked": "阻断",
}
TOP_STATUS_CN = {
    "running": "运行中",
    "paused_blocked": "已暂停，等人处理",
    "awaiting_review": "等待评审",
    "done": "已完成",
    "done_partial": "部分完成",
    "aborted": "已终止",
}
MILESTONE_FIELD_CN = {"implement": "编码", "code_review": "内审", "verify": "验证"}
WAITING_STATUSES = {"paused_blocked", "awaiting_review"}
TERMINAL_STATUSES = {"done", "done_partial", "aborted"}
MAINTENANCE_EVENTS = {"migrate:v2"}
DEFAULT_STALL_HOURS = 3.0


def timeline(root: Path, report_id: str, state: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """完整的事件时间线：[{seq, ts, event, payload}]，按发生先后排列。"""
    state = state if state is not None else st.load_state(root, report_id)
    if st.is_v2(state):
        return [
            {"seq": r.get("seq"), "ts": r.get("ts"), "event": r.get("event"), "payload": r.get("payload")}
            for r in st.read_event_records(root, report_id)
        ]
    merged = st._merge_history(state.get("events") or [], state.get("gates") or [])
    return [{"seq": i, "ts": ts, "event": event, "payload": payload} for i, (ts, event, payload) in enumerate(merged, 1)]


def _short(value: Any, limit: int = 80) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


def describe(event: str, payload: Any = None) -> str:
    """把事件名和载荷写成一句人话。认不出的事件原样给出，不吞信息。"""
    parts = str(event).split(":")
    head = parts[0]
    if event == "state:init":
        return "建立案例"
    if event == "state:init_legacy":
        return "按旧案例归档"
    if event == "migrate:v2":
        return "状态文件升级到 v2（完整历史移入 events.jsonl）"
    if head == "stage" and len(parts) == 3:
        return f"{STAGE_CN.get(parts[1], parts[1])}：{STAGE_STATUS_CN.get(parts[2], parts[2])}"
    if head == "gate" and len(parts) == 2:
        verdict = (payload or {}).get("verdict") if isinstance(payload, dict) else None
        failed = [
            c.get("id") for c in (payload or {}).get("checks") or [] if isinstance(c, dict) and c.get("result") == "FAIL"
        ] if isinstance(payload, dict) else []
        text = f"门禁 {STAGE_CN.get(parts[1], parts[1])}：{'通过' if verdict == 'PASS' else '未过'}"
        return text + (f"（{'、'.join(str(f) for f in failed)}）" if failed else "")
    if head == "milestone" and len(parts) == 4:
        return f"{parts[1]} {MILESTONE_FIELD_CN.get(parts[2], parts[2])}：{STAGE_STATUS_CN.get(parts[3], parts[3])}"
    if head == "set" and len(parts) >= 2:
        key = ":".join(parts[1:])
        value = payload.get("value") if isinstance(payload, dict) and "value" in payload else payload
        if key == "status":
            return f"状态改为「{TOP_STATUS_CN.get(str(value), str(value))}」"
        return f"设置 {key} = {_short(value, 60)}"
    if event == "migrate_stages":
        return "补齐阶段条目"
    kernel = _describe_kernel(parts, payload if isinstance(payload, dict) else {})
    if kernel:
        return kernel
    return str(event) + (f"：{_short(payload)}" if payload not in (None, "", {}, []) else "")


_REVIEW_CN = {"spec": "规格外审", "code": "代码外审", "result": "结果外审", "second_opinion": "第二意见"}
_FAIL_CLASS_CN = {"incomplete": "交回的东西不全", "blocked": "受阻", "crashed": "中途崩了", "degraded": "降级"}


def _describe_kernel(parts: list[str], payload: dict[str, Any]) -> Optional[str]:
    """v3 内核写的事件。认不出返回 None，由调用方原样给出。"""
    head, event = parts[0], ":".join(parts)
    if event == "flow:init":
        return "由内核建立案例"
    if head == "checkpoint" and len(parts) == 3:
        from . import checkpoints as cps  # 延迟导入：checkpoints 依赖本模块

        name, what = parts[1], parts[2]
        label = f"检查点 {payload.get('id', '')}「{cps.cn(name)}」".replace("  ", " ")
        if what == "opened":
            if payload.get("kind") == "auto":
                return f"按策略自动放行并留痕「{cps.cn(name)}」：{_short(payload.get('reason'), 120)}"
            return f"{label}打开，等人决定：{_short(payload.get('reason'), 120)}"
        if payload.get("by") == "policy" and payload.get("choice") == "auto":
            return f"「{cps.cn(name)}」已按策略放行"
        choice = str(payload.get("choice") or "")
        option = dict(cps.HUMAN[name][2]).get(choice, choice) if name in cps.HUMAN else choice
        quote = f"，原话「{_short(payload.get('quote'), 80)}」" if payload.get("quote") else ""
        return f"{label}已决定：{option}{quote}（凭据：{cps.CREDENTIAL_CN.get(str(payload.get('credential')), payload.get('credential'))}）"
    if head == "step" and len(parts) >= 3:
        step, what = ":".join(parts[1:-1]), parts[-1]
        if what == "issued":
            size = f"，任务文件 {int(payload.get('task_bytes') or 0) / 1024:.0f}KB" if payload.get("task_bytes") else ""
            why = f"，原因：{_short(payload.get('reason'), 80)}" if payload.get("reason") else ""
            who = {"exec": "外审", "judge": "主会话裁决"}.get(str(payload.get("kind")), str(payload.get("role") or ""))
            return f"派出 {step}（第 {payload.get('attempt', 1)} 次，{who}{size}{why}）"
        if what == "launched":
            return f"外审 {step} 已启动"
        if what == "redo":
            return f"{step} 要重做：{_short(payload.get('reason'), 100)}"
        if what == "failed":
            note = f"：{_short(payload.get('note'), 100)}" if payload.get("note") else ""
            return f"{step} 没有做成（{_FAIL_CLASS_CN.get(str(payload.get('class')), payload.get('class'))}）{note}"
        if what == "done":
            if payload.get("kind") == "kernel":
                return f"内核步骤 {step.split('@')[0]} 完成"
            if payload.get("kind") == "judge":
                return f"主会话对 {step} 的裁决已入账（{payload.get('ruled', 0)} 条）"
            if "state" in payload:
                ok = payload.get("state") == "success"
                tail = "" if ok else f"（{payload.get('reason')}）"
                return f"外审 {step} {'完成' if ok else '失败'}{tail}" + (f"，用时 {fmt_duration(float(payload['seconds']) / 3600)}" if payload.get("seconds") else "")
            took = f"，用时 {fmt_duration(float(payload['seconds']) / 3600)}" if payload.get("seconds") is not None else ""
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
            tokens = f"，累计输入 {int(usage.get('total_input') or 0) / 10000:.1f} 万 token" if usage else ""
            stale = "；它依据的内容在途中变过" if payload.get("stale_on_arrival") else ""
            return f"点收 {step}{took}{tokens}{stale}"
    if head == "guard":
        if parts[1:] == ["rejected"]:
            return f"拒绝了一次绕过闸门的写入（{payload.get('op', '?')} {payload.get('key') or payload.get('event') or ''}，当前状态 {TOP_STATUS_CN.get(str(payload.get('status')), payload.get('status'))}）"
        if parts[1:] == ["denied"]:
            return f"护栏拦下一次读取：{_short(payload.get('path'), 100)}（{payload.get('agent_type') or '子 agent'}）"
        if parts[1:] == ["violation"]:
            return f"事后核对：{payload.get('step')} 读了不该读的路径 {_short('、'.join(payload.get('paths') or []), 120)}"
    if event == "review:blind_violation":
        return f"外审的盲提取调用读过 spec（{payload.get('step')}），这一轮的盲提取不算独立"
    if head == "review" and len(parts) == 3:
        counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
        found = "、".join(f"{k} {v}" for k, v in counts.items() if v) or "没有意见"
        return f"{_REVIEW_CN.get(parts[1], parts[1])}第 {payload.get('round', 1)} 轮结果已合并：{found}" + ("（已降级）" if payload.get("degraded") else "")
    if head == "reopen":
        if parts[1:] == ["from_terminal"]:
            return "重开已收尾的案例"
        kind = {"revise": "按假设修订定向重跑", "reopen": "回退重开"}.get(parts[1] if len(parts) > 1 else "", "重开")
        stones = f"，milestone {'、'.join(payload.get('milestones') or [])}" if payload.get("milestones") else ""
        return f"{kind}：从{STAGE_CN.get(str(payload.get('from')), payload.get('from'))}起重做{stones}（第 {payload.get('generation')} 代）。{_short(payload.get('reason'), 100)}"
    if head == "pin" and len(parts) == 3:
        return f"{STAGE_CN.get(parts[1], parts[1])}阶段改由{'执行卡' if parts[2] == 'card' else '内核'}驱动：{_short(payload.get('reason'), 100)}"
    if head == "precheck" and len(parts) == 2:
        target = {"result": "结果外审之前", "report": "写报告之前"}.get(parts[1], parts[1])
        blocked = payload.get("blocked")
        return f"一致性预检（{target}）：{'有必须先改的不一致' if blocked else '通过'}" + (f"，共 {payload.get('findings')} 处" if payload.get("findings") else "")
    if head == "trial":
        return "转入 mock 试跑（这一轮不出结论）" if parts[1:] == ["on"] else "结束 mock 试跑"
    if head == "data":
        if parts[1:2] == ["disposition"]:
            from . import datacheck

            return f"数据缺口处置：{datacheck.DISPOSITION_CN.get(parts[2], parts[2])}（{'、'.join(str(g) for g in payload.get('gaps') or [])}）"
        if parts[1:] == ["recheck"]:
            return "数据重检通过"
    if head == "adhoc":
        return f"表外派发 {parts[1] if len(parts) > 1 else ''}（{payload.get('role')}）：{_short(payload.get('reason'), 100)}"
    if event == "accept":
        return f"最终评审通过，案例收尾（{TOP_STATUS_CN.get(str(payload.get('status')), payload.get('status'))}）"
    if event == "revise":
        return f"第 {payload.get('round')} 轮 revise，影响面 {payload.get('scope')}"
    if event == "fork":
        return f"由 {payload.get('from')} 复制而来，从{STAGE_CN.get(str(payload.get('start')), payload.get('start'))}阶段起"
    if event == "pack:get":
        return f"{payload.get('step') or '有人'} 按需取了 {payload.get('kind')} {payload.get('key')}"
    if event == "stall:resumed":
        return "停滞后由人确认继续"
    if event == "pdf_unparseable":
        return "PDF 读不出文字，没有建案"
    return None


def parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=st.TZ_CN)


def hours_since(value: Any, now: Optional[datetime] = None) -> Optional[float]:
    then = parse_ts(value)
    if then is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - then).total_seconds() / 3600


def fmt_duration(hours: Optional[float]) -> str:
    if hours is None:
        return "未知"
    if hours < 1 / 60:
        return "不到 1 分钟"
    if hours < 1:
        return f"{int(hours * 60)} 分钟"
    if hours < 48:
        return f"{hours:.1f} 小时"
    return f"{hours / 24:.1f} 天"


def _state_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    """state 里留存的事件，整理成时间线的形状（v2 只留最近若干条）。"""
    return [
        {"ts": e.get("timestamp"), "event": e.get("event"), "payload": e.get("payload")}
        for e in state.get("events") or []
        if isinstance(e, dict)
    ]


def last_activity_ts(state: dict[str, Any], timeline: Optional[list[dict[str, Any]]] = None) -> Any:
    """最后一次业务动作的时间。迁移这类维护动作会刷新 updated_at，但不算业务动作。"""
    items = timeline if timeline is not None else _state_events(state)
    if items and items[-1].get("event") in MAINTENANCE_EVENTS:
        for item in reversed(items):
            if item.get("event") not in MAINTENANCE_EVENTS and item.get("ts"):
                return item["ts"]
    return state.get("updated_at")


def activity_span(state: dict[str, Any], timeline: Optional[list[dict[str, Any]]] = None) -> tuple[Any, Any]:
    """案例的业务起止时间：第一条事件（没有就取建立时间）到最后一次业务动作。"""
    items = timeline if timeline is not None else _state_events(state)
    first = next((item.get("ts") for item in items if item.get("ts")), None)
    return (first or state.get("created_at"), last_activity_ts(state, timeline))


def status_since_ts(state: dict[str, Any], timeline: Optional[list[dict[str, Any]]] = None) -> Any:
    """进入当前状态的时间：最近一条状态变更事件；对不上就退回最后一次业务动作的时间。"""
    items = timeline if timeline is not None else _state_events(state)
    for item in reversed(items):
        if item.get("event") == "set:status":
            payload = item.get("payload")
            value = payload.get("value") if isinstance(payload, dict) else payload
            if value == state.get("status") and item.get("ts"):
                return item["ts"]
            break
    return last_activity_ts(state, timeline)


def stall_info(
    state: dict[str, Any],
    now: Optional[datetime] = None,
    threshold_hours: float = DEFAULT_STALL_HOURS,
    timeline: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """这个案例现在在等谁、等了多久、算不算停滞。

    idle_hours 是距最后一次业务动作多久；waiting_hours 只在等人的状态下有值，从进入该状态算起。
    运行中超过阈值没有新事件算停滞（可能是会话断了）；等人的状态不算停滞。
    传入完整时间线更准；不传时只看 state 里留存的事件。
    """
    status = state.get("status")
    idle = hours_since(last_activity_ts(state, timeline), now)
    waiting = hours_since(status_since_ts(state, timeline), now) if status in WAITING_STATUSES else None
    waiting_for = {"running": "流程自己", "awaiting_review": "你来评审", "paused_blocked": "你来处理阻断"}.get(str(status))
    stalled = status == "running" and idle is not None and idle > threshold_hours
    return {"status": status, "idle_hours": idle, "waiting_hours": waiting, "waiting_for": waiting_for, "stalled": stalled}
