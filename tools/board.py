#!/usr/bin/env python3
"""复现看板：把一个案例的进度渲染成单文件静态页，另有全案例总览。

用法：
    uv run python tools/board.py <report_id>     → workspace/<id>/board.html
    uv run python tools/board.py --index         → workspace/board.html
    uv run python tools/board.py --all           → 全部案例 + 总览

不起服务，浏览器直接打开；案例运行中时页面每分钟自动刷新。只读 state.json、events.jsonl
和案例目录下的文件清单，只写看板文件本身。新旧案例（schema v1 / v2）都能渲染。
样式沿用结果页（tools/render_report.py）的那一套。

v2 案例另有：停在哪个检查点（状态条给出审阅包链接与放行命令）、待决检查点卡片、检查点记录
（谁放行、凭什么）、内核派出的步骤与返工清单、连败计数、被钉在执行卡上的阶段。旧案例没有
这些数据，对应的小节不出现。检查点的中文名、选项与放行命令取自 tools/flowlib/reviewpacks.py。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

from tools import render_report as rr  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import events as ev  # noqa: E402
from tools.flowlib import reviewpacks as rp  # noqa: E402
from tools.flowlib import steps  # noqa: E402
from tools.flowlib import usage as us  # noqa: E402

esc = html.escape

BOARD_NAME = "board.html"
STATUS_PILL = {
    "running": "gate",
    "paused_blocked": "fail",
    "awaiting_review": "warn",
    "done": "pass",
    "done_partial": "warn",
    "aborted": "dim",
}
STAGE_PILL = {"pending": "dim", "running": "gate", "done": "pass", "failed": "fail", "skipped": "dim", "blocked": "fail"}
MODE_CN = {"auto": "自动", "interactive": "交互"}
ACTIVE_ORDER = {"paused_blocked": 0, "awaiting_review": 1, "running": 2, "done_partial": 3, "done": 4, "aborted": 5}
# 放行凭据的等级：钩子与终端短码能证明有人在场；自述只有代理自己的说法，要显著标出。中文说法取自 rp.credential_cn
CREDENTIAL_PILL = {"hook": "pass", "terminal": "pass", "self_report": "fail", "policy": "dim"}
BY_CN = {**rp.BY_CN, "kernel": "内核"}
STEP_STATUS_CN = rp.STEP_STATUS_CN
STEP_PILL = {"inflight": "gate", "done": "pass", "failed": "fail", "redo": "warn"}
STEP_KIND_CN = {"dispatch": "派发", "exec": "执行", "judge": "裁决"}

EXTRA_CSS = """
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--accent);text-transform:uppercase}
.statusbar{border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--card);border-radius:0 6px 6px 0;
  padding:12px 16px;margin:16px 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px 24px;}
.statusbar.warn{border-left-color:var(--warn);background:var(--warn-wash)}
.statusbar.fail{border-left-color:var(--fail);background:var(--fail-wash)}
.statusbar.pass{border-left-color:var(--pass);background:var(--pass-wash)}
.statusbar .sb-label{font-size:12px;color:var(--dim)} .statusbar .sb-value{font-weight:700}
.statusbar .sb-wide{grid-column:1/-1;font-size:13.5px}
code.cmd{display:inline-block;user-select:all;-webkit-user-select:all;padding:2px 8px;margin:2px 0;white-space:pre-wrap;word-break:break-all}
.cp-card{border:1px solid var(--line);border-left:4px solid var(--warn);background:var(--card);border-radius:0 6px 6px 0;padding:12px 16px;margin:12px 0}
.cp-card.final{border-left-color:var(--accent)}
.cp-head{display:flex;gap:8px;flex-wrap:wrap;align-items:baseline} .cp-title{font-weight:800;font-size:15.5px}
.chips{display:flex;gap:6px;flex-wrap:wrap} .chips+.chips{margin-top:4px}
.small{font-size:12.5px}
.muted{color:var(--dim)} .nowrap{white-space:nowrap} .num{text-align:right;font-variant-numeric:tabular-nums}
td.detail{font-size:12.5px;color:var(--dim);min-width:14ch;max-width:60ch;word-break:break-word}
.links{columns:2;column-gap:32px;list-style:none;margin-left:0} .links li{break-inside:avoid}
a{color:var(--accent-deep)}
@media(max-width:720px){.links{columns:1}}
@media (prefers-color-scheme: dark){
  :root{--ink:#e4e9ee;--paper:#12171d;--card:#1a2129;--accent:#6fb1e3;--accent-deep:#9ccbee;--accent-wash:#1c2c3a;
    --pass:#6cc48f;--pass-wash:#16281e;--fail:#ee8a7c;--fail-wash:#2e1a17;--warn:#d9b061;--warn-wash:#2b2416;
    --line:#2e3944;--dim:#9aa6b2;--code:#222b34;}
  th{border-bottom-color:var(--dim)}
  .pill.pass{border-color:#2f5a41}.pill.fail{border-color:#6a352e}.pill.gate{border-color:#2f4d66}
  .pill.dim{background:#232c35;border-color:var(--line)}.pill.warn{border-color:#5c4a22}
}
"""


def _pill(text: str, tone: str) -> str:
    return f"<span class='pill {tone}'>{esc(text)}</span>"


def _fmt_ts(value: Any) -> str:
    """时间戳去掉秒以下和时区后缀，够人读即可。"""
    text = str(value or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else (text or "-")


def _fmt_tokens(n: Optional[float]) -> str:
    if n is None:
        return "-"
    if n >= 1e8:
        return f"{n / 1e8:.2f} 亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f} 万"
    return f"{int(n)}"


def _generated_at() -> str:
    """生成时间。页面上的时间都按状态文件的约定写成东八区。"""
    return f"生成于 {_fmt_ts(st.now_iso())}（页面上的时间均为东八区）"


def _rel(target: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _page(title: str, body: list[str], refresh: bool, script: str = "") -> str:
    refresh_tag = "<meta http-equiv='refresh' content='60'>" if refresh else ""
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"{refresh_tag}<title>{esc(title)}</title><style>{rr.CSS}{EXTRA_CSS}</style></head><body><main>"
        + "\n".join(body)
        + f"</main><script>{script}</script></body></html>"
    )


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------


def gate_history(timeline: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """每个阶段的门禁记录（按时间）。新旧案例都从时间线里取。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for item in timeline:
        event = str(item.get("event") or "")
        if not event.startswith("gate:"):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        out.setdefault(event.split(":", 1)[1], []).append(
            {"ts": item.get("ts"), "verdict": payload.get("verdict"), "checks": payload.get("checks") or []}
        )
    return out


def fail_streaks(history: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """按（阶段, 检查项）数当前的连续未过次数。"""
    streak: dict[str, int] = {}
    for stage, records in history.items():
        for record in records:
            st._update_fail_streak(streak, stage, record["checks"])
    return streak


def case_links(root: Path, report_id: str) -> list[tuple[str, Path]]:
    """这个案例现有的主要产物。"""
    ws = st.workspace_dir(root, report_id)
    out_dir = st.output_dir(root, report_id)
    candidates = [
        ("规格书 spec.md", ws / "spec" / "spec.md"),
        ("覆盖矩阵 coverage_matrix.md", ws / "spec" / "coverage_matrix.md"),
        ("歧义清单 ambiguities.md", ws / "spec" / "ambiguities.md"),
        ("复现计划 plan.md", ws / "plan.md"),
        ("假设登记簿 assumptions.md", ws / "assumptions.md"),
        ("假设登记簿 assumptions.xlsx", ws / "assumptions.xlsx"),
        ("审计回应 audit_responses.md", ws / "audit" / "audit_responses.md"),
        ("迭代日志 iteration_log.md", ws / "iterations" / "iteration_log.md"),
        ("验证报告 verify_report.md", out_dir / "verify_report.md"),
        ("指标对比 comparison.json", out_dir / "results" / "comparison.json"),
        ("运行日志 run_log.md", out_dir / "results" / "run_log.md"),
        ("样本外报告 oos_report.md", ws / "oos_report.md"),
        ("最终报告 final_report.md", ws / "final_report.md"),
        ("结果页 final_report.html", out_dir / "final_report.html"),
        ("策略代码目录 src/", st.src_dir(root, report_id)),
        ("结果目录 results/", out_dir / "results"),
    ]
    return [(label, path) for label, path in candidates if path.exists()]


def collect_usage(root: Path, report_id: str, state: dict[str, Any], timeline: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """从宿主的会话记录里读这个案例的用量；读不到返回 None，不让看板失败。"""
    try:
        span = us.span_interval(*ev.activity_span(state, timeline))
        sessions = us.collect_case_usage(
            root, report_id, state, intervals=[span] if span else None, other_ids=st.list_case_ids(root)
        )
    except Exception:  # noqa: BLE001 - 用量只是增强
        return None
    return us.summarize(sessions) if sessions else None


def checkpoints(state: dict[str, Any]) -> list[dict[str, Any]]:
    """v2 案例的全部检查点，按开出的先后；旧案例没有。"""
    if not st.is_v2(state):
        return []
    return [c for c in state.get("checkpoints") or [] if isinstance(c, dict)]


def pending_checkpoints(state: dict[str, Any]) -> list[dict[str, Any]]:
    """还在等人决定的检查点（按策略自动放行的不算）。"""
    return [c for c in checkpoints(state) if c.get("status") == "pending" and not rp.is_auto(c)]


def _flow(state: dict[str, Any]) -> dict[str, Any]:
    flow = state.get("flow") if st.is_v2(state) else None
    return flow if isinstance(flow, dict) else {}


def _steps_by(state: dict[str, Any], kernel: bool, time_key: str) -> list[tuple[str, dict[str, Any]]]:
    """flow.steps 里的一类记录，按 time_key 排；同一秒内的按写进状态文件的先后（字典顺序就是登记顺序）。"""
    records = _flow(state).get("steps")
    items = [(i, str(sid), rec) for i, (sid, rec) in enumerate(records.items()) if isinstance(rec, dict)] if isinstance(records, dict) else []
    picked = [item for item in items if (item[2].get("kind") == "kernel") == kernel]
    return [(sid, rec) for _i, sid, rec in sorted(picked, key=lambda item: (str(item[2].get(time_key) or "9"), item[0]))]


def step_records(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """内核派出去的步骤（flow.steps 里交给子 agent、外审或裁决的那些），按派发时间排。

    内核自己做完的机器步骤（kind == "kernel"，没有派发对象）不在这里，见 kernel_marks。
    旧案例和还没派过步骤的案例为空。
    """
    return _steps_by(state, kernel=False, time_key="issued_at")


def kernel_marks(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """内核自己做完的机器步骤（落地计划、数据体检、收口判定这一类），按完成时间排。"""
    return _steps_by(state, kernel=True, time_key="done_at")


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _fmt_bytes(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{value / 1024:.1f} KB" if value >= 1024 else f"{int(value)} B"


def _cp_label(cp: dict[str, Any]) -> str:
    return f"{rp.checkpoint_title(cp.get('name'), cp)}（{cp.get('id') or '-'}）"


def _cp_waited(cp: dict[str, Any]) -> str:
    return ev.fmt_duration(ev.hours_since(cp.get("opened_at")))


def _pack_link(root: Optional[Path], report_id: str, cp: dict[str, Any]) -> str:
    """审阅包的链接（相对看板所在目录）。状态里记的路径不在工作区内时只显示、不给链接。"""
    pack = cp.get("pack")
    if not isinstance(pack, str) or not pack.strip():
        return "<span class='muted'>尚未生成</span>"
    path = Path(pack.strip())
    if root is None or path.is_absolute() or ".." in path.parts:
        return f"<code>{esc(pack)}</code>"
    href = _rel(root / path, st.workspace_dir(root, report_id))
    missing = "" if (root / path).is_file() else " <span class='muted'>（文件不在）</span>"
    return f"<a href='{esc(href)}'>{esc(href)}</a>{missing}"


def _release_commands(report_id: str, cp: dict[str, Any]) -> list[str]:
    """状态条上给的放行命令：中途检查点是一条 flow decide；最终评审是 flow accept 与 flow revise。

    只放最常用的，其余选项（回退、终止等）各自的命令在下面的「待决检查点」卡片里。
    """
    if rp.is_final_review(cp):
        return [rp.option_command(report_id, cp.get("name"), cp.get("id"), key) for key in ("accept", "revise")]
    return [rp.decide_command(report_id, cp.get("id"), "<选项>")]


# ---------------------------------------------------------------------------
# 单个案例
# ---------------------------------------------------------------------------


def _order_text(state: dict[str, Any], order: dict[str, Any]) -> str:
    """「现在」一格：正在推进哪个阶段、由谁推进。"""
    stage = str(order.get("stage"))
    name = str(order.get("stage_name") or ev.STAGE_CN.get(stage, stage))
    if order.get("driver") == "kernel":
        inflight = [str(s) for s in _flow(state).get("inflight") or []]
        return f"{name}（由内核推进" + (f"，在途 {len(inflight)} 步" if inflight else "") + "）"
    attempts = order.get("attempts")
    return f"{name}（第 {attempts} 次尝试，由执行卡推进）" if attempts else f"{name}（尚未开始，由执行卡推进）"


def _checkpoint_bar(state: dict[str, Any], pending: list[dict[str, Any]], tone: str, root: Optional[Path]) -> str:
    """停在检查点时的状态条：停在哪个检查点、等了多久、审阅包在哪、怎么放行。"""
    cp = pending[0]
    report_id = str(state.get("report_id"))
    final = rp.is_final_review(cp)
    stage = str(cp.get("stage") or state.get("current_stage"))
    cells = [
        ("现在", "最终评审" if final else "中途检查点"),
        ("等谁", "你来评审最终结果" if final else "你来决定"),
        ("停在", f"{_cp_label(cp)}，已等 {_cp_waited(cp)}"),
        ("所在阶段", f"{ev.STAGE_CN.get(stage, stage)} 阶段"),
    ]
    inner = "".join(f"<div><div class='sb-label'>{esc(k)}</div><div class='sb-value'>{esc(v)}</div></div>" for k, v in cells)
    commands = " ".join(f"<code class='cmd'>{esc(c)}</code>" for c in _release_commands(report_id, cp))
    code = f" <span class='sb-label'>放行短码</span> <code>{esc(str(cp['code']))}</code>" if cp.get("code") else ""
    inner += f"<div class='sb-wide'><span class='sb-label'>审阅包</span> {_pack_link(root, report_id, cp)}</div>"
    inner += f"<div class='sb-wide'><span class='sb-label'>放行命令</span> {commands}{code}</div>"
    if len(pending) > 1:
        inner += f"<div class='sb-wide sb-label'>另有 {len(pending) - 1} 个检查点在等，见下方「待决检查点」。</div>"
    return f"<div class='statusbar {tone}'>{inner}</div>"


def _status_bar(state: dict[str, Any], timeline: list[dict[str, Any]], stall_hours: float, root: Optional[Path] = None) -> str:
    status = str(state.get("status"))
    info = ev.stall_info(state, threshold_hours=stall_hours, timeline=timeline)
    tone = {"awaiting_review": "warn", "paused_blocked": "fail", "done": "pass", "done_partial": "warn"}.get(status, "")
    if info["stalled"]:
        tone = "fail"
    pending = pending_checkpoints(state)
    if pending:
        return _checkpoint_bar(state, pending, tone or "warn", root)
    nxt = steps.plan_next(state)
    stage = state.get("current_stage")
    orders = nxt.get("orders") or []
    if orders:
        now = _order_text(state, orders[0])
    else:
        now = (nxt.get("halt") or {}).get("message", "-")
    waiting = info["waiting_for"] or "无"
    if info["stalled"]:
        waiting = f"流程自己，但已超过 {stall_hours:g} 小时没有新事件，可能是会话中断了"
    cells = [
        ("现在", now),
        ("等谁", waiting),
        ("停在", f"{ev.STAGE_CN.get(str(stage), str(stage))} 阶段"),
        ("已等待", ev.fmt_duration(info["waiting_hours"])) if info["waiting_hours"] is not None else ("距上次事件", ev.fmt_duration(info["idle_hours"])),
    ]
    inner = "".join(f"<div><div class='sb-label'>{esc(k)}</div><div class='sb-value'>{esc(v)}</div></div>" for k, v in cells)
    return f"<div class='statusbar {tone}'>{inner}</div>"


def _kpis(state: dict[str, Any]) -> str:
    verdict = state.get("verdict") or {}
    cov = state.get("coverage_stats") or {}
    it = state.get("iteration") or {}
    asm = state.get("assumptions") or {}
    reviews = state.get("external_reviews") or []
    cards: list[tuple[str, str, str]] = []
    if verdict.get("metrics_total"):
        cards.append(("指标达标", f"{verdict.get('metrics_pass', 0)}/{verdict['metrics_total']}", rr._cn(rr.VERDICT_CN, verdict.get("result")) if verdict.get("result") else "尚无结论"))
    if cov.get("total"):
        cards.append(("要素覆盖", f"{cov.get('done', 0)}/{cov['total']}", f"跳过 {cov.get('skipped', 0)} · 不可行 {cov.get('infeasible', 0)} · 未完成 {cov.get('pending', 0)}"))
    if it.get("max") is not None or it.get("current"):
        cards.append(("迭代轮次", f"{it.get('current', 0)}/{it.get('max') or '-'}", "自动修正"))
    if asm.get("total"):
        cards.append(("假设", str(asm["total"]), f"待验证 {asm.get('assumed', 0)} · 已确认 {asm.get('confirmed', 0)} · 已修订 {asm.get('revised', 0)}"))
    if reviews:
        degraded = sum(1 for r in reviews if "fallback" in str(r.get("engine")) or r.get("engine") == "skipped")
        cards.append(("外审", f"{len(reviews)} 次", f"其中降级 {degraded} 次" if degraded else "均为异构外审"))
    if not cards:
        return ""
    inner = "".join(
        f"<div class='kpi'><div class='k-label'>{esc(label)}</div><div class='k-value'>{esc(value)}</div><div class='k-sub'>{esc(sub)}</div></div>"
        for label, value, sub in cards
    )
    return f"<div class='kpis'>{inner}</div>"


def _stage_table(state: dict[str, Any], history: dict[str, list[dict[str, Any]]]) -> list[str]:
    milestones = state.get("milestones") or []
    field_of_stage = {"implement": "implement", "code_audit": "code_review", "verify": "verify"}
    pinned = _flow(state).get("pinned")
    pinned = pinned if isinstance(pinned, dict) else {}
    inflight: dict[str, list[str]] = {}  # 阶段 → 在途步骤（步骤号里带着 milestone）
    for sid, rec in step_records(state):
        if rec.get("status") == "inflight":
            again = f"（第 {_int(rec.get('attempt'))} 次）" if _int(rec.get("attempt")) > 1 else ""
            inflight.setdefault(str(rec.get("stage")), []).append(f"在途 {sid}{again}")
    rows: list[str] = []
    for stage in st.STAGE_ORDER:
        entry = (state.get("stages") or {}).get(stage) or {}
        status = str(entry.get("status") or "pending")
        records = history.get(stage) or []
        if records:
            last = records[-1]
            failed = [str(c.get("id")) for c in last["checks"] if isinstance(c, dict) and c.get("result") == "FAIL"]
            gate = _pill("通过" if last["verdict"] == "PASS" else "未过", "pass" if last["verdict"] == "PASS" else "fail")
            if failed:
                gate += f" <span class='muted'>{esc('、'.join(failed))}</span>"
            if len(records) > 1:
                fails = sum(1 for r in records if r["verdict"] != "PASS")
                gate += f" <span class='muted'>共 {len(records)} 次，未过 {fails} 次</span>"
        else:
            gate = "<span class='muted'>无记录</span>"
        chips = ""
        if stage in field_of_stage and milestones:
            key = field_of_stage[stage]
            chips = "<div class='chips'>" + "".join(
                _pill(f"{m.get('id')} {ev.STAGE_STATUS_CN.get(str(m.get(key)), str(m.get(key)))}", STAGE_PILL.get(str(m.get(key)), "dim"))
                for m in milestones
            ) + "</div>"
        if inflight.get(stage):
            chips += "<div class='chips'>" + "".join(_pill(text, "gate") for text in inflight[stage]) + "</div>"
        driver = ""
        pin = pinned.get(stage)
        if isinstance(pin, dict) and pin.get("mode") == "card":  # 这个阶段不走内核的步骤表，仍由执行卡推进
            driver = f" {_pill('执行卡', 'warn')}" + (f"<div class='muted small'>{esc(str(pin['reason']))}</div>" if pin.get("reason") else "")
        current = " <span class='muted'>← 当前</span>" if stage == state.get("current_stage") else ""
        rows.append(
            f"<tr><td class='nowrap'><strong>{esc(ev.STAGE_CN.get(stage, stage))}</strong> <span class='muted'>{esc(stage)}</span>{current}</td>"
            f"<td>{_pill(ev.STAGE_STATUS_CN.get(status, status), STAGE_PILL.get(status, 'dim'))}{driver}</td>"
            f"<td class='num'>{entry.get('attempts', 0)}</td><td class='nowrap'>{esc(_fmt_ts(entry.get('updated_at')))}</td>"
            f"<td>{gate}</td><td>{chips}</td></tr>"
        )
    return [
        "<section><h2>阶段进度</h2><div class='tbl-scroll'><table>",
        "<tr><th>阶段</th><th>状态</th><th>尝试次数</th><th>最近更新</th><th>最近一次门禁</th><th>各 milestone</th></tr>",
        *rows,
        "</table></div></section>",
    ]


def _checkpoint_cards(root: Path, report_id: str, state: dict[str, Any]) -> list[str]:
    """待决检查点：每个一张卡，写明原因、可选的决定与各自的命令、审阅包、放行短码。"""
    pending = pending_checkpoints(state)
    if not pending:
        return []
    out = ["<section><h2>待决检查点</h2>"]
    for cp in pending:
        final = rp.is_final_review(cp)
        name = cp.get("name")
        stage = str(cp.get("stage") or "-")
        meta = f"{ev.STAGE_CN.get(stage, stage)} 阶段 · 开出于 {_fmt_ts(cp.get('opened_at'))} · 已等 {_cp_waited(cp)}"
        out.append(
            f"<div class='cp-card{' final' if final else ''}'><div class='cp-head'><span class='cp-title'>{esc(rp.checkpoint_title(name, cp))}</span>"
            f" <code>{esc(str(cp.get('id') or '-'))}</code> {_pill('最终评审' if final else '中途检查点', 'gate' if final else 'warn')}"
            f" <span class='muted small'>{esc(meta)}</span></div>"
        )
        out.append(f"<p><strong>原因</strong>：{esc(str(cp.get('reason') or '内核没有写原因'))}</p>")
        out.append("<div class='tbl-scroll'><table><tr><th>选项</th><th>含义</th><th>放行命令</th></tr>")
        for option in rp.checkpoint_options(name, cp):
            command = rp.option_command(report_id, name, cp.get("id"), option["key"])
            out.append(
                f"<tr><td class='nowrap'><code>{esc(option['key'])}</code></td><td>{esc(option['label'])}</td>"
                f"<td><code class='cmd'>{esc(command)}</code></td></tr>"
            )
        out.append("</table></div>")
        code = (
            f" · 放行短码 <code>{esc(str(cp['code']))}</code> <span class='muted'>在自己的终端执行放行命令时要输入；没有它的放行会记为自述</span>"
            if cp.get("code")
            else ""
        )
        out.append(f"<p>审阅包：{_pack_link(root, report_id, cp)}{code}</p></div>")
    out.append("</section>")
    return out


def _checkpoint_log(state: dict[str, Any]) -> list[str]:
    """检查点记录：人处理过的（谁放行、凭什么）与按策略自动放行的分开列。"""
    items = checkpoints(state)
    decided = [c for c in items if not rp.is_auto(c) and c.get("status") != "pending"]
    auto = [c for c in items if rp.is_auto(c)]
    if not decided and not auto:
        return []

    def decision(cp: dict[str, Any]) -> dict[str, Any]:
        return cp["decision"] if isinstance(cp.get("decision"), dict) else {}

    out = ["<section><h2>检查点记录</h2>"]
    if decided:
        out.append("<h3>已处理</h3>")
        self_reported = sum(1 for c in decided if decision(c).get("credential") == "self_report")
        if self_reported:
            out.append(
                "<div class='note' style='border-left-color:var(--fail);background:var(--fail-wash)'>"
                f"<strong>有 {self_reported} 次放行是自述级</strong>：既没有钩子记录的用户原话，也没有人在终端输入短码，只有代理自己的说法。</div>"
            )
        out.append("<div class='tbl-scroll'><table><tr><th>时间</th><th>名称</th><th>选择</th><th>原话</th><th>凭据等级</th><th>谁放行</th></tr>")
        for cp in decided:
            d = decision(cp)
            credential = str(d.get("credential") or "-")
            by = str(d.get("by") or "-")
            note = f" <span class='muted'>（{esc(str(d['note']))}）</span>" if d.get("note") else ""
            row_attr = " class='f-row'" if credential == "self_report" else ""  # 自述级整行标红
            out.append(
                f"<tr{row_attr}>"
                f"<td class='nowrap muted'>{esc(_fmt_ts(d.get('at')))}</td><td class='nowrap'>{esc(_cp_label(cp))}</td>"
                f"<td><code>{esc(str(d.get('choice') or '-'))}</code></td><td class='detail'>{esc(str(d.get('quote') or ''))}{note}</td>"
                f"<td>{_pill(rp.credential_cn(d.get('credential')), CREDENTIAL_PILL.get(credential, 'dim'))}</td>"
                f"<td class='nowrap'>{esc(BY_CN.get(by, by))}</td></tr>"
            )
        out.append("</table></div>")
    if auto:
        out.append("<h3>按策略自动放行</h3><p class='muted'>这些检查点不停下来等人，只留痕。</p>")
        out.append("<div class='tbl-scroll'><table><tr><th>时间</th><th>名称</th><th>阶段</th><th>原因</th></tr>")
        for cp in auto:
            stage = str(cp.get("stage") or "-")
            out.append(
                f"<tr><td class='nowrap muted'>{esc(_fmt_ts(cp.get('opened_at')))}</td><td class='nowrap'>{esc(_cp_label(cp))}</td>"
                f"<td class='nowrap'>{esc(ev.STAGE_CN.get(stage, stage))}</td><td class='detail'>{esc(str(cp.get('reason') or ''))}</td></tr>"
            )
        out.append("</table></div>")
    out.append("</section>")
    return out


def _counter_item(key: str, count: Any) -> str:
    """计数器里的一项。重派计数里 gate:<阶段> 这种键记的是这个阶段的门禁修了几轮。"""
    if key.startswith("gate:"):
        stage = key.split(":", 1)[1]
        return f"{ev.STAGE_CN.get(stage, stage)}门禁修复 {count} 轮"
    return f"{key} {count} 次"


def _counter_text(state: dict[str, Any]) -> str:
    """重派、复审、表外派发、假 FAIL 复跑的累计次数，写成一句。"""
    counters = state.get("counters") if isinstance(state.get("counters"), dict) else {}
    parts: list[str] = []
    for key, label in (("redispatch", "重派"), ("review_rounds", "复审轮数"), ("false_fail", "假 FAIL 复跑")):
        value = counters.get(key)
        if isinstance(value, dict) and value:
            parts.append(f"{label}：" + "、".join(_counter_item(str(k), v) for k, v in value.items()))
    if _int(counters.get("adhoc")):
        parts.append(f"表外派发 {counters['adhoc']} 次")
    return "；".join(parts)


def _steps_section(state: dict[str, Any]) -> list[str]:
    """内核派出的步骤，以及返工（同一步派了不止一次）与表外派发的清单。旧案例不出现。"""
    records = step_records(state)
    marks = kernel_marks(state)
    adhoc = [a for a in _flow(state).get("adhoc") or [] if isinstance(a, dict)]
    if not records and not marks and not adhoc:
        return []

    def status_pill(value: Any) -> str:
        return _pill(STEP_STATUS_CN.get(str(value), str(value or "-")), STEP_PILL.get(str(value), "dim"))

    flying = [sid for sid, rec in records if rec.get("status") == "inflight"]
    out = ["<section><h2>步骤</h2>"]
    out.append(f"<p class='muted'>内核派出的步骤共 {len(records)} 个" + (f"，在途 {len(flying)} 个：{esc('、'.join(flying))}" if flying else "，眼下没有在途的") + "。</p>")
    if records:
        out.append("<div class='tbl-scroll'><table><tr><th>步骤</th><th>角色</th><th>第几次派发</th><th>状态</th><th>任务文件大小</th><th>派发时间</th><th>完成时间</th><th>原因</th></tr>")
        for sid, rec in records:
            kind = STEP_KIND_CN.get(str(rec.get("kind")), str(rec.get("kind") or ""))
            out.append(
                f"<tr><td class='nowrap'><code>{esc(sid)}</code></td>"
                f"<td class='nowrap'>{esc(str(rec.get('role') or '-'))}" + (f" <span class='muted'>{esc(kind)}</span>" if kind else "") + "</td>"
                f"<td class='num'>{_int(rec.get('attempt')) or '-'}</td><td>{status_pill(rec.get('status'))}</td>"
                f"<td class='num'>{esc(_fmt_bytes(rec.get('task_bytes')))}</td><td class='nowrap'>{esc(_fmt_ts(rec.get('issued_at')))}</td>"
                f"<td class='nowrap'>{esc(_fmt_ts(rec.get('done_at')))}</td><td class='detail'>{esc(str(rec.get('reason') or ''))}</td></tr>"
            )
        out.append("</table></div>")
    if marks:  # 内核自己做完的机器步骤没有派发对象，折叠起来，免得淹没上面的表
        out.append(f"<details><summary>内核自己做完的机器步骤 {len(marks)} 个（没有派发对象）</summary><div><div class='tbl-scroll'><table>")
        out.append("<tr><th>步骤</th><th>状态</th><th>完成时间</th></tr>")
        for sid, rec in marks:
            out.append(
                f"<tr><td class='nowrap'><code>{esc(sid)}</code></td><td>{status_pill(rec.get('status'))}</td>"
                f"<td class='nowrap'>{esc(_fmt_ts(rec.get('done_at')))}</td></tr>"
            )
        out.append("</table></div></div></details>")

    out.append("<h3>返工与表外派发清单</h3>")
    rework = [(sid, rec) for sid, rec in records if _int(rec.get("attempt")) > 1]
    if rework or adhoc:
        out.append("<div class='tbl-scroll'><table><tr><th>类别</th><th>步骤</th><th>角色</th><th>第几次派发</th><th>状态</th><th>时间</th><th>原因</th></tr>")
        for sid, rec in rework:
            out.append(
                f"<tr><td class='nowrap'>返工</td><td class='nowrap'><code>{esc(sid)}</code></td><td class='nowrap'>{esc(str(rec.get('role') or '-'))}</td>"
                f"<td class='num'>{_int(rec.get('attempt'))}</td><td>{status_pill(rec.get('status'))}</td>"
                f"<td class='nowrap'>{esc(_fmt_ts(rec.get('issued_at')))}</td><td class='detail'>{esc(str(rec.get('reason') or ''))}</td></tr>"
            )
        for entry in adhoc:
            out.append(
                f"<tr><td class='nowrap'>表外派发</td><td class='nowrap'><code>{esc(str(entry.get('id') or '-'))}</code></td>"
                f"<td class='nowrap'>{esc(str(entry.get('role') or '-'))}</td><td class='num'>-</td><td>{status_pill(entry.get('status'))}</td>"
                f"<td class='nowrap'>{esc(_fmt_ts(entry.get('at')))}</td><td class='detail'>{esc(str(entry.get('reason') or ''))}</td></tr>"
            )
        out.append("</table></div>")
    else:
        out.append("<p class='muted'>没有返工，也没有表外派发。</p>")
    counters = _counter_text(state)
    if counters:
        out.append(f"<p class='muted'>累计：{esc(counters)}。</p>")
    out.append("</section>")
    return out


def _streak_block(state: dict[str, Any]) -> str:
    """连败计数（counters.gate_fail_streak 里不为零的项）；到熔断线的标红。旧案例不出现。"""
    raw = state.get("counters", {}).get("gate_fail_streak") if st.is_v2(state) and isinstance(state.get("counters"), dict) else None
    items = sorted(((str(k), _int(n)) for k, n in raw.items() if _int(n) > 0), key=lambda item: (-item[1], item[0])) if isinstance(raw, dict) else []
    if not items:
        return ""
    threshold = int(getattr(st, "BREAKER_THRESHOLD", 3))
    chips: list[str] = []
    for key, n in items:
        stage, _sep, check = key.partition(":")
        tripped = n >= threshold
        chips.append(_pill(f"{ev.STAGE_CN.get(stage, stage)} {check} 连续 {n} 次未过" + ("，已到熔断线" if tripped else ""), "fail" if tripped else "warn"))
    return (
        f"<p><strong>连败计数</strong> <span class='muted'>同一检查项连续未过满 {threshold} 次就熔断，停下来等人决定</span></p>"
        f"<div class='chips'>{''.join(chips)}</div>"
    )


def _pending_section(state: dict[str, Any]) -> list[str]:
    blockers = state.get("blockers") or []
    question = state.get("pending_question")
    # 检查点开出时会把自己的原因写进 pending_question；上面的卡片已经写了，这里不重复
    reasons = [str(c.get("reason")) for c in pending_checkpoints(state) if c.get("reason")]
    if isinstance(question, str) and any(reason in question for reason in reasons):
        question = None
    if not (blockers or question):
        return []
    out = ["<section><h2>待处理</h2>"]
    if question:
        text = question if isinstance(question, str) else json.dumps(question, ensure_ascii=False, indent=1)
        label = "等你回答" if state.get("status") == "paused_blocked" else "状态里留着一条没有清掉的提问（案例已不在暂停状态）"
        out.append(f"<div class='note'><strong>{label}</strong>：{esc(text)}</div>")
    if blockers:
        out.append("<div class='tbl-scroll'><table><tr><th>阶段</th><th>阻断</th><th>说明</th><th>证据</th></tr>")
        for b in blockers:
            if isinstance(b, dict):
                out.append(
                    f"<tr><td class='nowrap'>{esc(ev.STAGE_CN.get(str(b.get('stage')), str(b.get('stage') or '-')))}</td>"
                    f"<td><code>{esc(str(b.get('code') or '-'))}</code></td><td>{esc(str(b.get('message') or ''))}</td>"
                    f"<td class='detail'>{esc(str(b.get('evidence') or ''))}</td></tr>"
                )
            else:
                out.append(f"<tr><td>-</td><td>-</td><td colspan='2'>{esc(str(b))}</td></tr>")
        out.append("</table></div>")
    out.append("</section>")
    return out


def _gate_section(state: dict[str, Any], history: dict[str, list[dict[str, Any]]]) -> list[str]:
    streak_block = _streak_block(state)
    if not history:
        return [f"<section><h2>门禁明细</h2><p class='muted'>还没有门禁记录。</p>{streak_block}</section>"]
    latest_detail = state.get("gate_latest") or {}
    streaks = fail_streaks(history)
    rows: list[str] = []
    for stage in st.STAGE_ORDER:
        records = history.get(stage)
        if not records:
            continue
        last = records[-1]
        details = {f.get("id"): f.get("detail") for f in (latest_detail.get(stage) or {}).get("failed") or [] if isinstance(f, dict)}
        for check in last["checks"]:
            if not isinstance(check, dict):
                continue
            passed = check.get("result") == "PASS"
            cid = str(check.get("id"))
            streak = streaks.get(f"{stage}:{cid}", 0)
            note = check.get("detail") or details.get(cid) or ""
            if streak >= 2:
                note = f"已连续 {streak} 次未过。" + str(note)
            row_attrs = "data-s='pass'" if passed else "data-s='fail' class='f-row'"
            rows.append(
                f"<tr {row_attrs}>"
                f"<td class='nowrap'>{esc(ev.STAGE_CN.get(stage, stage))}</td><td class='nowrap'><code>{esc(cid)}</code></td>"
                f"<td>{_pill('通过' if passed else '未过', 'pass' if passed else 'fail')}</td>"
                f"<td>{esc(str(check.get('desc') or ''))}</td><td class='detail'>{esc(str(note))}</td>"
                f"<td class='nowrap muted'>{esc(_fmt_ts(last['ts']))}</td></tr>"
            )
    total = sum(len(v) for v in history.values())
    return [
        f"<section><h2>门禁明细</h2><p class='muted'>各阶段最近一次门禁的逐项结果（全部门禁记录共 {total} 次）。</p>",
        streak_block,
        "<div class='filter-bar'>筛选：<button class='on' onclick=\"fl('all',this)\">全部</button>"
        "<button onclick=\"fl('fail',this)\">仅未过</button><button onclick=\"fl('pass',this)\">仅通过</button></div>",
        "<div class='tbl-scroll'><table id='cmp'><thead><tr><th>阶段</th><th>检查项</th><th>结果</th><th>内容</th><th>明细</th><th>时间</th></tr></thead><tbody>",
        *rows,
        "</tbody></table></div></section>",
    ]


def _review_section(state: dict[str, Any]) -> list[str]:
    reviews = state.get("external_reviews") or []
    if not reviews:
        return []
    out = [
        "<section><h2>外审台账</h2><div class='tbl-scroll'><table>",
        "<tr><th>审查点</th><th>引擎</th><th>结论</th><th>critical</th><th>major</th><th>minor</th><th>备注</th></tr>",
    ]
    for r in reviews:
        if not isinstance(r, dict):
            continue
        engine = str(r.get("engine"))
        tone = "warn" if "fallback" in engine or engine == "skipped" else "dim"
        out.append(
            f"<tr><td class='nowrap'>{esc(rr._cn(rr.CHECKPOINT_CN, r.get('checkpoint')))}</td><td>{_pill(rr._cn(rr.ENGINE_CN, engine), tone)}</td>"
            f"<td>{esc(rr._cn(rr.REVIEW_VERDICT_CN, r.get('verdict')))}</td>"
            f"<td class='num'>{esc(str(r.get('critical', '-')))}</td><td class='num'>{esc(str(r.get('major', '-')))}</td>"
            f"<td class='num'>{esc(str(r.get('minor', '-')))}</td><td class='detail'>{esc(str(r.get('note') or ''))}</td></tr>"
        )
    out.append("</table></div></section>")
    return out


def _rework_section(state: dict[str, Any]) -> list[str]:
    retried = [(s, e) for s, e in (state.get("stages") or {}).items() if isinstance(e, dict) and int(e.get("attempts") or 0) > 1]
    history = (state.get("iteration") or {}).get("history") or []
    if not retried and not history:
        return []
    out = ["<section><h2>返工与迭代</h2>"]
    if retried:
        items = "、".join(f"{ev.STAGE_CN.get(s, s)} {e['attempts']} 次" for s, e in retried)
        out.append(f"<p>重复进入的阶段：{esc(items)}。</p>")
    if not st.is_v2(state):
        out.append("<p class='muted'>旧流程不记录每一次派发，返工派发的明细在这里看不到；改由内核派发之后会逐条列出。</p>")
    if history:
        out.append("<div class='tbl-scroll'><table><tr><th>轮次</th><th>触发</th><th>结果</th><th>摘要</th></tr>")
        for h in history:
            if isinstance(h, dict):
                out.append(
                    f"<tr><td class='num'>{esc(str(h.get('iteration', '-')))}</td><td>{esc(str(h.get('trigger') or ''))}</td>"
                    f"<td>{esc(str(h.get('status') or ''))}</td><td class='detail'>{esc(str(h.get('summary') or ''))}</td></tr>"
                )
        out.append("</table></div>")
    out.append("</section>")
    return out


def _usage_section(usage: Optional[dict[str, Any]], scanned: bool) -> list[str]:
    out = ["<section><h2>用量</h2>"]
    if not scanned:
        out.append("<p class='muted'>本次没有读取宿主的会话记录。</p></section>")
        return out
    if not usage:
        out.append("<p class='muted'>在宿主的会话记录里没有找到与这个案例对得上的会话（记录可能已被清理，或这个案例跑在别的宿主上）。</p></section>")
        return out
    total = usage["total"]
    out.append(
        f"<p>从宿主会话记录里找到 {usage['sessions']} 个相关会话。累计输入 {esc(_fmt_tokens(total['total_input']))} token，"
        f"其中未缓存 {esc(_fmt_tokens(total['uncached_input']))}、缓存写入 {esc(_fmt_tokens(total['cache_write']))}、"
        f"缓存读取 {esc(_fmt_tokens(total['cache_read']))}；输出 {esc(_fmt_tokens(total['output']))}。</p>"
    )
    out.append("<div class='tbl-scroll'><table><tr><th>宿主 / 角色</th><th>会话数</th><th>模型调用</th><th>工具调用</th><th>未缓存输入</th><th>缓存写入</th><th>缓存读取</th><th>输出</th><th>上下文峰值</th><th>起止跨度</th></tr>")
    for key, g in usage["groups"].items():
        out.append(
            f"<tr><td>{esc(key)}</td><td class='num'>{g['sessions']}</td><td class='num'>{g['calls']}</td><td class='num'>{g['tool_calls']}</td>"
            f"<td class='num'>{esc(_fmt_tokens(g['uncached_input']))}</td><td class='num'>{esc(_fmt_tokens(g['cache_write']))}</td>"
            f"<td class='num'>{esc(_fmt_tokens(g['cache_read']))}</td><td class='num'>{esc(_fmt_tokens(g['output']))}</td>"
            f"<td class='num'>{esc(_fmt_tokens(g['peak_context']))}</td><td class='num'>{esc(ev.fmt_duration(g['seconds'] / 3600))}</td></tr>"
        )
    out.append(
        "</table></div><p class='muted'>这是给旧案例的估计：取案例从第一条到最后一条状态事件之间（前后各一小时）、"
        "工作目录相同、且提到本案例的行数比提到其他任何案例都多的会话，只算这段时间内的调用；子代理跟随父会话。"
        "同一个会话在同一段时间里同时推进两个案例时分不开；宿主已经清理掉的记录（Claude Code 会定期清理）不在其中。"
        "「起止跨度」是会话在这段时间里第一条到最后一条记录相隔多久，不是实际工作时长。</p></section>"
    )
    return out


def _events_section(timeline: list[dict[str, Any]], recent: int = 30) -> list[str]:
    if not timeline:
        return []

    def row(item: dict[str, Any]) -> str:
        return (
            f"<tr><td class='nowrap muted'>{esc(_fmt_ts(item.get('ts')))}</td>"
            f"<td>{esc(ev.describe(str(item.get('event')), item.get('payload')))}</td></tr>"
        )

    out = [f"<section><h2>事件</h2><p class='muted'>最近 {min(recent, len(timeline))} 条，新的在上（共 {len(timeline)} 条）。</p>"]
    out.append("<div class='tbl-scroll'><table><tr><th>时间</th><th>事件</th></tr>")
    out.extend(row(item) for item in reversed(timeline[-recent:]))
    out.append("</table></div>")
    if len(timeline) > recent:
        out.append(f"<details><summary>更早的 {len(timeline) - recent} 条</summary><div><div class='tbl-scroll'><table>")
        out.extend(row(item) for item in reversed(timeline[:-recent]))
        out.append("</table></div></div></details>")
    out.append("</section>")
    return out


def render_case(root: Path, report_id: str, with_usage: bool = True, stall_hours: float = ev.DEFAULT_STALL_HOURS) -> str:
    state = st.load_state(root, report_id)
    timeline = ev.timeline(root, report_id, state)
    history = gate_history(timeline)
    status = str(state.get("status"))
    board_dir = st.workspace_dir(root, report_id)

    body: list[str] = ["<header>", "<div class='eyebrow'>复现看板 · quant-report-reproduce</div>", f"<h1>{esc(report_id)}</h1>", "<div class='hero-meta'>"]
    body.append(_pill(ev.TOP_STATUS_CN.get(status, status), STATUS_PILL.get(status, "dim")))
    if state.get("type"):
        diff = state.get("difficulty")
        body.append(_pill(rr._cn(rr.TYPE_CN, state.get("type")) + (f" · 难度：{rr.DIFFICULTY_CN.get(str(diff), str(diff))}" if diff else ""), "dim"))
    body.append(_pill(f"{MODE_CN.get(str(state.get('mode')), str(state.get('mode')))}模式", "dim"))
    if state.get("reproduction_mode") == "experimental":
        body.append(_pill("实验模式 · 市场迁移", "warn"))
    if state.get("feasibility") and state.get("feasibility") != "feasible":
        body.append(_pill(f"可行性：{state.get('feasibility')}", "warn"))
    body.append(_pill(f"状态文件 v{state.get('schema_version')}", "dim"))
    body.append("</div>")
    body.append(_status_bar(state, timeline, stall_hours, root))
    body.append(_kpis(state))
    body.append("</header>")

    if st.is_v2(state):
        chain = st.verify_event_chain(root, report_id, state)
        if not chain["ok"]:
            body.append(f"<div class='note' style='border-left-color:var(--fail);background:var(--fail-wash)'><strong>事件流校验未通过</strong>：{esc('；'.join(chain['errors']))}</div>")

    body += _checkpoint_cards(root, report_id, state)
    body += _pending_section(state)
    body += _stage_table(state, history)
    body += _steps_section(state)
    body += _gate_section(state, history)
    body += _checkpoint_log(state)
    body += _review_section(state)
    body += _rework_section(state)
    body += _usage_section(collect_usage(root, report_id, state, timeline) if with_usage else None, with_usage)

    links = case_links(root, report_id)
    if links:
        body.append("<section><h2>产物</h2><ul class='links'>")
        body.extend(f"<li><a href='{esc(_rel(path, board_dir))}'>{esc(label)}</a></li>" for label, path in links)
        body.append("</ul></section>")
    body += _events_section(timeline)
    body.append(
        f"<footer><span>{esc(_generated_at())}</span>"
        f"<span>数据来自 {esc(_rel(st.state_path(root, report_id), board_dir))}</span>"
        f"<span><a href='../{BOARD_NAME}'>全部案例</a></span>"
        + ("<span>案例运行中，本页每分钟自动刷新</span>" if status == "running" else "")
        + "</footer>"
    )
    return _page(f"{report_id} · 复现看板", body, refresh=status == "running", script=rr.FILTER_JS)


def write_case(root: Path, report_id: str, with_usage: bool = True) -> Path:
    target = st.workspace_dir(root, report_id) / BOARD_NAME
    _atomic_write(target, render_case(root, report_id, with_usage=with_usage))
    return target


# ---------------------------------------------------------------------------
# 总览
# ---------------------------------------------------------------------------


def render_index(root: Path, stall_hours: float = ev.DEFAULT_STALL_HOURS) -> str:
    cases: list[dict[str, Any]] = []
    infos: dict[str, dict[str, Any]] = {}
    broken: list[tuple[str, str]] = []
    for report_id in st.list_case_ids(root):
        try:
            state = st.load_state(root, report_id)
            infos[report_id] = ev.stall_info(state, threshold_hours=stall_hours, timeline=ev.timeline(root, report_id, state))
            cases.append(state)
        except (ValueError, OSError) as exc:
            broken.append((report_id, str(exc)))
    cases.sort(key=lambda s: (ACTIVE_ORDER.get(str(s.get("status")), 9), str(s.get("report_id"))))

    counts: dict[str, int] = {}
    for s in cases:
        counts[str(s.get("status"))] = counts.get(str(s.get("status")), 0) + 1
    stalled = [s for s in cases if infos[str(s.get("report_id"))]["stalled"]]

    body: list[str] = ["<header>", "<div class='eyebrow'>复现看板 · quant-report-reproduce</div>", "<h1>全部案例</h1>", "<div class='kpis'>"]
    cards = [("案例数", str(len(cases)), "")]
    cards += [(ev.TOP_STATUS_CN.get(k, k), str(counts[k]), "") for k in sorted(counts, key=lambda k: ACTIVE_ORDER.get(k, 9))]
    if stalled:
        cards.append(("疑似停滞", str(len(stalled)), f"运行中但超过 {stall_hours:g} 小时没有新事件"))
    body.extend(
        f"<div class='kpi'><div class='k-label'>{esc(label)}</div><div class='k-value'>{esc(value)}</div><div class='k-sub'>{esc(sub)}</div></div>"
        for label, value, sub in cards
    )
    body.append("</div></header>")
    body.append("<section><h2>案例</h2><div class='tbl-scroll'><table>")
    body.append("<tr><th>案例</th><th>类型</th><th>状态</th><th>停在</th><th>停在哪个检查点</th><th>等了多久</th><th>指标达标</th><th>结论</th><th>最近更新</th></tr>")
    for s in cases:
        rid = str(s.get("report_id"))
        status = str(s.get("status"))
        info = infos[rid]
        verdict = s.get("verdict") or {}
        metrics = f"{verdict.get('metrics_pass', 0)}/{verdict['metrics_total']}" if verdict.get("metrics_total") else "-"
        waited = "-"
        if status in ev.WAITING_STATUSES:
            waited = ev.fmt_duration(info["waiting_hours"])
        elif status == "running":
            waited = f"距上次事件 {ev.fmt_duration(info['idle_hours'])}"
        if info["stalled"]:
            waited += " " + _pill("疑似停滞", "fail")
        board = st.workspace_dir(root, rid) / BOARD_NAME
        name = f"<a href='{esc(rid)}/{BOARD_NAME}'>{esc(rid)}</a>" if board.is_file() else esc(rid)
        pending = pending_checkpoints(s)
        stopped = "-"
        if pending:
            stopped = esc(_cp_label(pending[0])) + (f" <span class='muted'>另有 {len(pending) - 1} 个</span>" if len(pending) > 1 else "")
        body.append(
            f"<tr><td>{name}</td><td class='nowrap'>{esc(rr.TYPE_CN.get(str(s.get('type')), str(s.get('type') or '-')))}</td>"
            f"<td>{_pill(ev.TOP_STATUS_CN.get(status, status), STATUS_PILL.get(status, 'dim'))}</td>"
            f"<td class='nowrap'>{esc(ev.STAGE_CN.get(str(s.get('current_stage')), str(s.get('current_stage'))))}</td>"
            f"<td class='nowrap'>{stopped}</td>"
            f"<td class='nowrap'>{waited}</td><td class='num'>{esc(metrics)}</td>"
            f"<td class='nowrap'>{esc(rr.VERDICT_CN.get(str(verdict.get('result')), '-'))}</td>"
            f"<td class='nowrap muted'>{esc(_fmt_ts(s.get('updated_at')))}</td></tr>"
        )
    body.append("</table></div></section>")
    if broken:
        body.append("<section><h2>读不了的案例</h2><ul>")
        body.extend(f"<li><code>{esc(rid)}</code>：{esc(msg[:200])}</li>" for rid, msg in broken)
        body.append("</ul></section>")
    body.append(f"<footer><span>{esc(_generated_at())}</span></footer>")
    return _page("复现看板 · 全部案例", body, refresh=any(str(s.get("status")) == "running" for s in cases))


def write_index(root: Path) -> Path:
    target = root / "workspace" / BOARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, render_index(root))
    return target


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="复现看板（静态页）")
    parser.add_argument("report_id", nargs="?")
    parser.add_argument("--index", action="store_true", help="只生成全案例总览")
    parser.add_argument("--all", action="store_true", help="生成全部案例的看板和总览")
    parser.add_argument("--no-usage", action="store_true", help="不读宿主的会话记录")
    args = parser.parse_args(argv)
    root = st.default_root()
    try:
        if args.all:
            for report_id in st.list_case_ids(root):
                print(write_case(root, report_id, with_usage=not args.no_usage))
            print(write_index(root))
        elif args.index:
            print(write_index(root))
        elif args.report_id:
            print(write_case(root, st.resolve_case_id(root, args.report_id), with_usage=not args.no_usage))
        else:
            parser.error("给出 report_id，或用 --index / --all")
    except (ValueError, FileNotFoundError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
