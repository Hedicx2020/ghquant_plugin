#!/usr/bin/env python3
"""研报复现 v3 内核入口。

推进（主会话只和内核说这几句话）：
    flow init <pdf> --slug <短名>            新建案例：编号、骨架、PDF 转文本、撞库检查、过 G-IN，零派发
    flow next <id>                           下一步：{orders 工单, wait 在途的后台步骤, halt 停在哪}
    flow done <id> <step…>                   点收：产物 → 回执 → 状态 → 门禁 → 事件 → 看板，并给出下一步
    flow fail <id> <step> --class …          记失败（incomplete / blocked / crashed）
    flow adhoc <id> --role … --reason …      步骤表之外的临时派发（有限额、入账）
    flow exec <id> <step> [--detach]         启动后台外审；flow wait <id> 等它结束
人工出口（都要带上人的原话）：
    flow decide <id> <检查点> --choice … --quote "…"
    flow accept <id> --quote "…"             最终评审通过并收尾
    flow revise <id> --assumption AS3 --new-text "…" | --from-excel [--dry-run]
    flow reopen <id> --from <阶段|mN> --reason "…" --quote "…" [--dry-run]
工具层（可单独调用，执行卡驱动的阶段也能用）：
    flow gate / precheck / review / merge / pack / data probe|check|recheck / get
只读与维护：
    flow status [id] / board / cost / explain <键> / stale <id> / migrate / fork / pin / rerun

调用方式：REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/flow.py" ...
只依赖标准库与 pyyaml（数据体检另需 pyarrow）。子 agent 只允许调用 flow get。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

from tools import check_gates as cg  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import checkpoints as cps  # noqa: E402
from tools.flowlib import datacheck, decisions, packs, steps  # noqa: E402
from tools.flowlib import events as ev  # noqa: E402
from tools.flowlib import usage as us  # noqa: E402
from tools.flowlib.core import PLUGIN_ROOT, FlowError  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402
from tools.flowlib.receipts import ReceiptError  # noqa: E402

TYPE_CN = {"factor": "选股因子", "timing": "择时", "allocation": "资产配置", "fixed_income": "固定收益", "ml": "机器学习"}
VERDICT_CN = {"pass": "达标", "partial": "部分达标", "fail": "未达标"}


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _resolve(root: Path, query: str) -> str:
    return st.resolve_case_id(root, query)


def _targets(root: Path, queries: list[str]) -> list[str]:
    return [_resolve(root, q) for q in queries] if queries else st.list_case_ids(root)


def _kb(n: Optional[int]) -> str:
    return "-" if n is None else f"{n / 1024:.0f}KB"


def _tokens(n: Optional[float]) -> str:
    if n is None:
        return "-"
    if n >= 1e8:
        return f"{n / 1e8:.2f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return str(int(n))


def _width(text: str) -> int:
    """终端显示宽度：中日韩字符算两格。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(width - _width(text), 0)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(_width(str(h)), *(_width(str(r[i])) for r in rows)) if rows else _width(str(h)) for i, h in enumerate(headers)]
    lines = ["  ".join(_pad(str(h), widths[i]) for i, h in enumerate(headers)).rstrip()]
    lines += ["  ".join(_pad(str(cell), widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# status / next
# ---------------------------------------------------------------------------


def _gate_summary(state: dict[str, Any], timeline: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """每个阶段的门禁：次数、未过次数、最近一次的结论与未过项。"""
    out: dict[str, dict[str, Any]] = {}
    for item in timeline:
        event = str(item.get("event") or "")
        if not event.startswith("gate:"):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        slot = out.setdefault(event.split(":", 1)[1], {"count": 0, "fails": 0})
        slot["count"] += 1
        slot["fails"] += payload.get("verdict") != "PASS"
        slot["verdict"] = payload.get("verdict")
        slot["ts"] = item.get("ts")
        slot["failed"] = [c for c in payload.get("checks") or [] if isinstance(c, dict) and c.get("result") == "FAIL"]
    details = state.get("gate_latest") or {}
    for stage, slot in out.items():
        by_id = {f.get("id"): f.get("detail") for f in (details.get(stage) or {}).get("failed") or [] if isinstance(f, dict)}
        for check in slot.get("failed") or []:
            if not check.get("detail") and by_id.get(check.get("id")):
                check["detail"] = by_id[check.get("id")]
    return out


def case_status(root: Path, report_id: str) -> dict[str, Any]:
    """一个案例的进度摘要（status 的 JSON 形态，看板之外的机器接口）。"""
    state = st.load_state(root, report_id)
    timeline = ev.timeline(root, report_id, state)
    gates = _gate_summary(state, timeline)
    info = ev.stall_info(state, timeline=timeline)
    data: dict[str, Any] = {
        "report_id": report_id,
        "schema_version": state.get("schema_version"),
        "status": state.get("status"),
        "current_stage": state.get("current_stage"),
        "type": state.get("type"),
        "difficulty": state.get("difficulty"),
        "mode": state.get("mode"),
        "reproduction_mode": state.get("reproduction_mode"),
        "idle_hours": info["idle_hours"],
        "waiting_hours": info["waiting_hours"],
        "stalled": info["stalled"],
        "waiting_for": info["waiting_for"],
        "stages": {
            stage: {
                "status": (state["stages"].get(stage) or {}).get("status"),
                "attempts": (state["stages"].get(stage) or {}).get("attempts", 0),
                "gate": gates.get(stage),
            }
            for stage in st.STAGE_ORDER
        },
        "milestones": state.get("milestones") or [],
        "verdict": state.get("verdict"),
        "blockers": state.get("blockers") or [],
        "pending_question": state.get("pending_question"),
        "external_reviews": state.get("external_reviews") or [],
        "events": len(timeline),
        "next": steps.plan_next(state),
    }
    if st.is_v2(state):
        data["event_chain"] = st.verify_event_chain(root, report_id, state)
        flow = state.get("flow") or {}
        data["checkpoints"] = [
            {k: c.get(k) for k in ("id", "name", "stage", "reason", "pack", "code", "opened_at", "options")}
            for c in st.pending_checkpoints(state)
        ]
        data["inflight"] = [
            {"step": sid, "role": rec.get("role"), "attempt": rec.get("attempt"), "issued_at": rec.get("issued_at"), "kind": rec.get("kind")}
            for sid, rec in (flow.get("steps") or {}).items()
            if rec.get("status") == "inflight"
        ]
        data["pinned"] = flow.get("pinned") or {}
        data["generation"] = flow.get("generation")
        data["trial"] = bool(((state.get("ext") or {}).get("trial") or {}).get("active"))
        data["fail_streak"] = {k: v for k, v in ((state.get("counters") or {}).get("gate_fail_streak") or {}).items() if v}
    return data


def _render_status(data: dict[str, Any]) -> str:
    status = str(data["status"])
    head = f"{data['report_id']}  {ev.TOP_STATUS_CN.get(status, status)}"
    if data["waiting_hours"] is not None:
        head += f"（等{data['waiting_for']}，已等 {ev.fmt_duration(data['waiting_hours'])}）"
    elif status == "running":
        head += f"（距上次事件 {ev.fmt_duration(data['idle_hours'])}）"
    lines = [head]
    if data["stalled"]:
        lines.append(f"注意：运行中但已超过 {ev.DEFAULT_STALL_HOURS:g} 小时没有新事件，可能是会话中断了。")
    meta = [TYPE_CN.get(str(data["type"]), str(data["type"] or "类型未定")), f"难度 {data['difficulty'] or '未定'}", f"{data['mode']} 模式"]
    if data["reproduction_mode"] == "experimental":
        meta.append("实验模式")
    meta.append(f"状态文件 v{data['schema_version']}")
    lines.append(" · ".join(meta))
    chain = data.get("event_chain")
    if chain and not chain["ok"]:
        lines.append("事件流校验未通过：" + "；".join(chain["errors"]))

    rows = []
    for stage in st.STAGE_ORDER:
        entry = data["stages"][stage]
        gate = entry["gate"]
        if gate:
            gate_text = "通过" if gate["verdict"] == "PASS" else "未过 " + "、".join(str(c.get("id")) for c in gate["failed"])
            if gate["count"] > 1:
                gate_text += f"（共 {gate['count']} 次，未过 {gate['fails']} 次）"
        else:
            gate_text = "-"
        mark = " ←" if stage == data["current_stage"] else ""
        rows.append([ev.STAGE_CN.get(stage, stage) + mark, ev.STAGE_STATUS_CN.get(str(entry["status"]), str(entry["status"])), str(entry["attempts"]), gate_text])
    lines += ["", _table(["阶段", "状态", "尝试", "最近一次门禁"], rows)]

    failed_now = [
        (stage, check)
        for stage in st.STAGE_ORDER
        for check in ((data["stages"][stage]["gate"] or {}).get("failed") or [])
        if (data["stages"][stage]["gate"] or {}).get("verdict") != "PASS"
    ]
    if failed_now:
        lines += ["", "未过的检查项："]
        for stage, check in failed_now:
            detail = f"（{str(check['detail'])[:160]}）" if check.get("detail") else ""
            lines.append(f"  {ev.STAGE_CN.get(stage, stage)} {check.get('id')} {check.get('desc', '')}{detail}")

    if data["milestones"]:
        ms_rows = [
            [str(m.get("id")), str(m.get("name") or "")[:28]]
            + [ev.STAGE_STATUS_CN.get(str(m.get(k)), str(m.get(k))) for k in ("implement", "code_review", "verify")]
            for m in data["milestones"]
        ]
        lines += ["", _table(["milestone", "名称", "编码", "内审", "验证"], ms_rows)]

    verdict = data.get("verdict") or {}
    if verdict.get("metrics_total"):
        lines += ["", f"指标达标 {verdict.get('metrics_pass', 0)}/{verdict['metrics_total']}，结论：{VERDICT_CN.get(str(verdict.get('result')), '尚无')}"]
    for b in data["blockers"]:
        lines.append(f"阻断：{b.get('code', '')} {b.get('message', '')}" if isinstance(b, dict) else f"阻断：{b}")
    if data["pending_question"]:
        label = "等你回答" if status == "paused_blocked" else "状态里留着一条没有清掉的提问（案例已不在暂停状态）"
        lines.append(f"{label}：{data['pending_question']}")

    if data.get("trial"):
        lines.append("本案例处于 mock 试跑：结果只用来确认流水线跑得通，不出结论。")
    for cp in data.get("checkpoints") or []:
        lines += [
            "",
            f"停在检查点 {cp['id']}「{cps.cn(str(cp['name']))}」：{cp.get('reason') or ''}",
            f"  审阅包：{cp.get('pack') or '（无）'}",
            f"  选项：{'、'.join(str(o.get('key')) for o in cp.get('options') or [])}",
            f"  放行：flow decide {data['report_id']} {cp['id']} --choice <选项> --quote \"<人的原话>\"",
        ]
    for item in data.get("inflight") or []:
        lines.append(f"在途：{item['step']}（{item.get('role')}，第 {item.get('attempt')} 次，{ev.fmt_duration(ev.hours_since(item.get('issued_at')))}前派出）")
    for stage, pin in (data.get("pinned") or {}).items():
        if isinstance(pin, dict) and pin.get("mode") == "card":
            lines.append(f"{ev.STAGE_CN.get(stage, stage)}阶段钉在执行卡上：{pin.get('reason', '')}")
    for key, count in (data.get("fail_streak") or {}).items():
        lines.append(f"连败计数：{key} 已连续 {count} 次未过" + ("（已到熔断阈值）" if count >= st.BREAKER_THRESHOLD else ""))

    nxt = data["next"]
    lines.append("")
    if nxt["orders"]:
        order = nxt["orders"][0]
        if order.get("kind") == "legacy_card":
            lines.append(f"下一步：{order['stage_name']}阶段，按执行卡推进（{order['card']}）")
        else:
            lines.append(f"下一步：{order['stage_name']}阶段，由内核推进（flow next {data['report_id']}）")
    else:
        lines.append(f"下一步：停。{(nxt['halt'] or {}).get('message', '')}")
    return "\n".join(lines)


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    if args.report_id:
        data = case_status(root, _resolve(root, args.report_id))
        _print_json(data) if args.json else print(_render_status(data))
        return 0
    rows: list[list[str]] = []
    summary: list[dict[str, Any]] = []
    for report_id in st.list_case_ids(root):
        try:
            state = st.load_state(root, report_id)
        except (ValueError, OSError) as exc:
            rows.append([report_id, "读取失败", "-", "-", "-", str(exc)[:40]])
            continue
        info = ev.stall_info(state, timeline=ev.timeline(root, report_id, state))
        verdict = state.get("verdict") or {}
        status = str(state.get("status"))
        waited = "-"
        if status in ev.WAITING_STATUSES:
            waited = "已等 " + ev.fmt_duration(info["waiting_hours"])
        elif status == "running":
            waited = "距上次事件 " + ev.fmt_duration(info["idle_hours"])
        summary.append({"report_id": report_id, "status": status, "current_stage": state.get("current_stage"), "idle_hours": info["idle_hours"], "waiting_hours": info["waiting_hours"], "stalled": info["stalled"], "verdict": verdict.get("result")})
        rows.append(
            [
                report_id,
                ev.TOP_STATUS_CN.get(status, status) + ("（疑似停滞）" if info["stalled"] else ""),
                ev.STAGE_CN.get(str(state.get("current_stage")), str(state.get("current_stage"))),
                waited,
                f"{verdict.get('metrics_pass', 0)}/{verdict['metrics_total']}" if verdict.get("metrics_total") else "-",
                VERDICT_CN.get(str(verdict.get("result")), "-"),
            ]
        )
    if args.json:
        _print_json(summary)
    elif rows:
        print(_table(["案例", "状态", "停在", "等了多久", "指标达标", "结论"], rows))
    else:
        print("还没有任何案例。")
    return 0


def _engine(root: Path, args: argparse.Namespace) -> Engine:
    return Engine(root, _resolve(root, args.report_id), getattr(args, "host", None))


def _refresh_board(root: Path, report_id: str) -> None:
    """推进类命令之后顺手刷新看板和钩子用的索引；这两样出任何问题都不影响主流程。"""
    from tools.flowlib import guardindex

    guardindex.sync(root, report_id)
    try:
        from tools import board

        board.write_case(root, report_id, with_usage=False)
        board.write_index(root)
    except Exception:  # noqa: BLE001
        pass


def _emit_next(engine: Engine, text: bool = False, head: Optional[dict[str, Any]] = None, lines: Optional[list[str]] = None) -> None:
    """推进一步并输出。默认整段输出是一个 JSON 对象（head 里的回报并在前面）；--text 时逐行打印。"""
    result = engine.advance()
    if st.is_v2(st.load_state(engine.root, engine.report_id)):  # v1 案例的 next 是只读的，不动任何文件
        _refresh_board(engine.root, engine.report_id)
    if not text:
        _print_json({**(head or {}), **result})
        return
    for line in lines or []:
        print(line)
    for order in result["orders"]:
        print(f"{order['step_id']}  {order.get('prompt_inline', '')}")
    for item in result["wait"]:
        print(f"等待 {item['step_id']}：{item.get('how', '')}")
    if result.get("halt"):
        print(f"停：{result['halt'].get('message', '')}")
    for note in result.get("notes") or []:
        print(f"说明：{note}")


def cmd_next(root: Path, args: argparse.Namespace) -> int:
    _emit_next(_engine(root, args), args.text)
    return 0


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    policy = {
        "on_no_answer": args.on_no_answer,
        "on_missing": args.on_missing,
        "until": args.until,
        "step": True if args.step else None,
        "budget_tokens": args.budget_tokens,
        "budget_hours": args.budget_hours,
        "stall_hours": args.stall_hours,
    }
    summary = decisions.init_case(
        root,
        args.pdf,
        slug=args.slug,
        report_id=args.id,
        mode=args.mode,
        max_iter=args.max_iter,
        difficulty=args.difficulty,
        experimental=args.experimental,
        policy=policy,
        host=args.host,
    )
    _refresh_board(root, summary["report_id"])
    if args.json:
        _print_json(summary)
    else:
        print(f"已建立案例 {summary['report_id']}：{summary.get('pages')} 页，识别出 {summary.get('tables')} 张表，初始化门禁{'通过' if summary.get('gate') == 'PASS' else '未过'}。")
        if summary.get("duplicates"):
            print(f"注意：这份 PDF 与已有案例 {'、'.join(summary['duplicates'])} 完全相同，已停在检查点等你决定。")
        if summary.get("gate_detail"):
            print(summary["gate_detail"])
        print(f"下一步：flow next {summary['report_id']}")
    return 0 if summary.get("gate") == "PASS" else 1


def cmd_done(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    results = engine.done(args.steps, collect_usage=not args.no_usage)
    lines = []
    for item in results:
        if item.get("ok"):
            lines.append(f"{item['step']}：已点收" + ("（之前已点收过）" if item.get("already") else ""))
        else:
            reasons = item.get("missing") or item.get("reasons") or []
            lines.append(f"{item['step']}：未点收（{item.get('class')}）" + ("：" + "；".join(str(r) for r in reasons) if reasons else ""))
    if not args.no_next:
        _emit_next(engine, args.text, head={"collected": results}, lines=lines)
    else:
        _refresh_board(root, engine.report_id)
        print("\n".join(lines)) if args.text else _print_json({"collected": results})
    return 0 if all(item.get("ok") for item in results) else 1


def cmd_fail(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    result = engine.fail(args.step, args.klass, args.note or "")
    _emit_next(engine, args.text, head={"failed": result}, lines=[f"{result['step']}：已记失败（{result['class']}）"])
    return 0


def cmd_adhoc(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    instruction = Path(args.instruction).read_text(encoding="utf-8")
    order = engine.adhoc(args.role, args.reason, instruction, args.writes or [])
    _refresh_board(root, engine.report_id)
    _print_json({"orders": [order]})
    return 0


def cmd_exec(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    result = engine.exec_step(args.step, detach=args.detach)
    if result.get("launched"):
        line = f"{result['step']}：外审已在后台启动（{result.get('job_id')}）。用 flow wait {engine.report_id} 等结果。"
        print(line) if args.text else _print_json({"exec": result, "how": f"flow wait {engine.report_id}"})
        return 0
    line = f"{result['step']}：外审结束，{result.get('state')}" + (f"（{result.get('reason')}）" if result.get("reason") else "")
    _emit_next(engine, args.text, head={"exec": result}, lines=[line])
    return 0


def cmd_wait(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    result = engine.wait(timeout=args.timeout, interval=args.interval)
    lines = [f"{item['step']}：外审结束，{item.get('state')}" + (f"（{item.get('reason')}）" if item.get("reason") else "") for item in result["finished"]]
    lines += [f"{sid}：还没有启动，先执行 flow exec {engine.report_id} {sid} --detach" for sid in result["not_started"]]
    if result["running"] and not result["finished"]:
        lines.append(f"还在跑：{'、'.join(result['running'])}。稍后再执行 flow wait {engine.report_id}。")
        print("\n".join(lines)) if args.text else _print_json({"waited": result, "how": f"还在跑，稍后再执行 flow wait {engine.report_id}"})
        return 0
    _emit_next(engine, args.text, head={"waited": result}, lines=lines)
    return 0


def _typed_code(args: argparse.Namespace, root: Path, report_id: str, key: Optional[str]) -> Optional[str]:
    """放行短码只认人在交互终端里当场输入的；没有命令行参数可传，免得编排会话替人填。"""
    state = st.load_state(root, report_id)
    pending = st.pending_checkpoints(state) if st.is_v2(state) else []
    cp = st.find_checkpoint(state, key) if key else (pending[0] if pending else None)
    return cps.ask_code_on_tty(cp) if cp else None


def cmd_decide(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    code = None if args.by == "policy" else _typed_code(args, root, engine.report_id, args.checkpoint)
    result = decisions.decide(
        engine,
        args.checkpoint,
        args.choice,
        args.quote or "",
        by=args.by,
        typed_code=code,
        to=args.to,
        budget_tokens=args.budget_tokens,
        budget_hours=args.budget_hours,
    )
    line = f"检查点 {result['checkpoint']}（{cps.cn(result['name'])}）：{result['choice']}。{result['message']}。凭据：{cps.CREDENTIAL_CN.get(result['credential'], result['credential'])}。"
    _emit_next(engine, args.text, head={"decision": result}, lines=[line])
    return 0


def cmd_accept(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    result = decisions.accept(engine, args.quote or "", _typed_code(args, root, engine.report_id, None))
    _refresh_board(root, engine.report_id)
    line = f"{engine.report_id} 已收尾：{ev.TOP_STATUS_CN.get(result['status'], result['status'])}。凭据：{cps.CREDENTIAL_CN.get(result['credential'], result['credential'])}。"
    print(line) if getattr(args, "text", False) else _print_json({"accepted": result, "report_id": engine.report_id, "message": line})
    return 0


def cmd_revise(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    if args.each:
        card = steps.card_path("review")
        print(f"逐条敏感性模式（--each）仍按执行卡做：读取 {card} 的「--each」一节。")
        return 0
    code = None if args.dry_run else _typed_code(args, root, engine.report_id, None)
    result = decisions.revise(
        engine,
        assumption=args.assumption,
        text=args.text_value,
        from_excel=args.from_excel,
        xlsx=args.xlsx,
        dry_run=args.dry_run,
        quote=args.quote or "",
        typed_code=code,
    )
    if args.dry_run:
        _print_json(result)
        return 0
    _emit_next(engine, args.text, head={"revise": result}, lines=[f"{result['message']}。影响面 {result['scope']}，第 {result['round']} 轮 revise。"])
    return 0


def cmd_reopen(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    code = None if args.dry_run else _typed_code(args, root, engine.report_id, None)
    result = decisions.reopen(engine, args.start, args.reason or "", args.quote or "", code, dry_run=args.dry_run)
    if args.dry_run:
        _print_json(result)
        return 0
    _emit_next(engine, args.text, head={"reopen": result}, lines=[result["message"] + "。"])
    return 0


def cmd_stale(root: Path, args: argparse.Namespace) -> int:
    report = decisions.stale_report(_engine(root, args))
    if args.json:
        _print_json(report)
        return 0
    if not report["stale"]:
        print("没有过期的步骤：已完成步骤消费过的内容都没有变。")
        return 0
    print(f"{len(report['stale'])} 个已完成的步骤消费过的内容后来变了：")
    for item in report["stale"]:
        more = f"……另有 {item['more']} 处" if item["more"] else ""
        print(f"  {item['step']}：{'、'.join(item['changed'])}{more}")
    print(f"建议的重入点：flow reopen {args.report_id} --from {report['reopen_from']} --reason \"…\" --quote \"…\"（只是建议，不会自动执行）")
    return 0


def cmd_pin(root: Path, args: argparse.Namespace) -> int:
    result = decisions.pin(_engine(root, args), args.stage, args.mode, args.reason)
    print(f"{ev.STAGE_CN.get(result['stage'], result['stage'])}阶段现在由{'执行卡' if result['mode'] == 'card' else '内核'}驱动。")
    return 0


def cmd_rerun(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    result = decisions.rerun_false_fail(engine, args.step, args.reason)
    line = f"{result['step']}：按假 FAIL 复跑，不计重派次数（验证期间在编码的步骤：{'、'.join(result['overlapping'])}）。"
    _emit_next(engine, args.text, head={"rerun": result}, lines=[line])
    return 0


def cmd_get(root: Path, args: argparse.Namespace) -> int:
    sys.stdout.write(decisions.get_block(_engine(root, args), args.kind, args.key, args.step))
    return 0


def cmd_fork(root: Path, args: argparse.Namespace) -> int:
    result = decisions.fork(root, _resolve(root, args.report_id), args.new_id, args.start, getattr(args, "host", None))
    _print_json(result) if args.json else print(f"已把 {result['from']} 复制为 {result['report_id']}，回退到{ev.STAGE_CN.get(result['start'], result['start'])}阶段的起点。源案例没有改动。")
    return 0


def cmd_explain(root: Path, args: argparse.Namespace) -> int:
    from tools.flowlib import explain

    text = explain.lookup(args.key)
    if text is not None:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0
    print(f"没有 {args.key} 的处理说明。可用的键见 flow explain index：{'、'.join(explain.available()) or '（说明目录不存在）'}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# 工具层：gate / precheck / review / merge / data check
# ---------------------------------------------------------------------------


def cmd_gate(root: Path, args: argparse.Namespace) -> int:
    report_id = _resolve(root, args.report_id)
    evaluation = cg.evaluate(root, report_id, args.stage)
    state = st.load_state(root, report_id)
    if not args.no_record:
        st.record_gate(root, report_id, args.stage, evaluation.verdict, evaluation.to_record(with_detail=st.is_v2(state)))
    if evaluation.passed:
        print(f"{ev.STAGE_CN.get(args.stage, args.stage)}门禁通过（{len(evaluation.checks)} 项）")
        return 0
    print(f"{ev.STAGE_CN.get(args.stage, args.stage)}门禁未过：")
    for check in evaluation.failed():
        print("  " + cg.format_check(check))
    print(f"处理说明：flow explain {args.stage}")
    return 1


def cmd_precheck(root: Path, args: argparse.Namespace) -> int:
    from tools.flowlib import precheck

    result = precheck.run_precheck(root, _resolve(root, args.report_id), stage=args.stage)
    _print_json(result.to_dict()) if args.json else print(result.render())
    return 1 if result.blocked else 0


def cmd_review(root: Path, args: argparse.Namespace) -> int:
    """工具层的外审：准备、执行、合并、生成回应表，一条命令做完（执行卡驱动的阶段用）。台账条目由调用方按输出入账。"""
    from tools.flowlib import extreview
    from tools.flowlib.core import external_engine, make_ctx

    report_id = _resolve(root, args.report_id)
    ctx = make_ctx(root, report_id, host=getattr(args, "host", None))
    engine_name, engine_state = external_engine(ctx.host, ctx.config)
    job = extreview.prepare(root, report_id, args.kind, args.round, engine=engine_name, host=ctx.host, config=ctx.config, iteration=args.iteration, force_full=args.full)
    status = extreview.launch(root, report_id, job["job_id"], detach=False)
    if status.get("state") != "success":
        print(f"外审失败：{status.get('reason')}。同宿主替身的提示词：{extreview.fallback_task(root, report_id, job['job_id'])}")
        return 1
    if args.kind == "second_opinion":
        _print_json({"job": job["job_id"], "status": status})
        return 0
    result = extreview.collect(root, report_id, args.kind, engine_state=engine_state)
    responses = extreview.write_responses(root, report_id, args.kind)
    diffs = extreview.write_extract_diff(root, report_id) if args.kind == "spec" else {}
    _print_json({"ledger": result.get("ledger"), "verdict": result.get("verdict"), "counts": result.get("counts"), "unruled": responses.get("unruled"), "unruled_diffs": diffs.get("unruled"), "seconds": status.get("seconds")})
    return 0


def cmd_merge(root: Path, args: argparse.Namespace) -> int:
    """工具层的回执合并：核对一张回执并并进覆盖矩阵与假设登记簿。"""
    from tools.flowlib import receipts as rc
    from tools.flowlib.core import make_ctx

    report_id = _resolve(root, args.report_id)
    ctx = make_ctx(root, report_id)
    record = {"role": args.role, "stage": args.stage, "milestone": args.milestone, "reserved": args.reserved or []}
    merge = rc.apply(ctx, record, rc.load(Path(args.receipt)), allowed_ids=rc.step_element_ids(ctx, args.milestone))
    _print_json(merge.to_dict())
    return 0


def cmd_data_check(root: Path, args: argparse.Namespace) -> int:
    report_id = _resolve(root, args.report_id)
    result = datacheck.check_requirements(root, report_id, run_smoke=args.smoke)
    if not args.no_save:
        datacheck.save_check(root, report_id, result)
    if args.json:
        _print_json(result)
    else:
        summary = result.get("summary") or {}
        print(f"{report_id}：{summary.get('total', 0)} 条数据需求，通过 {summary.get('ok', 0)}、部分满足 {summary.get('partial', 0)}、缺失 {summary.get('missing', 0)}、未机检 {summary.get('unchecked', 0)}。")
        print(datacheck.render_gap_report(result))
    return 0


def cmd_data_recheck(root: Path, args: argparse.Namespace) -> int:
    engine = _engine(root, args)
    state = st.load_state(root, engine.report_id)
    waiting = [c for c in (st.pending_checkpoints(state) if st.is_v2(state) else []) if c.get("name") == "data_wait"]
    if not waiting:
        return cmd_data_check(root, argparse.Namespace(report_id=args.report_id, smoke=False, no_save=False, json=args.json))
    code = _typed_code(args, root, engine.report_id, waiting[0]["id"])
    result = decisions.decide(engine, waiting[0]["id"], "recheck", args.quote or "数据已补齐，重新体检", typed_code=code)
    _emit_next(engine, False, head={"decision": result})
    return 0


# ---------------------------------------------------------------------------
# board / cost
# ---------------------------------------------------------------------------


def cmd_board(root: Path, args: argparse.Namespace) -> int:
    from tools import board  # 延迟导入：看板会带上结果页的样式模块

    if args.index:
        print(board.write_index(root))
        return 0
    targets = st.list_case_ids(root) if args.all or not args.report_id else [_resolve(root, args.report_id)]
    for report_id in targets:
        print(board.write_case(root, report_id, with_usage=not args.no_usage))
    print(board.write_index(root))
    return 0


def _print_ledger(report_id: str, ledger: dict[str, Any], steps: bool) -> None:
    totals = ledger["totals"]
    have = totals["with_usage"]
    print(
        f"{report_id}：共派发 {totals['dispatches']} 次（其中重派 {totals['redispatches']} 次），任务文件与外审输入包合计 {totals['task_bytes'] / 1024:.0f}KB，"
        f"各步耗时合计 {ev.fmt_duration(totals['seconds'] / 3600)}。"
    )
    if have:
        print(
            f"其中 {have} 次读到了宿主的会话记录：未缓存输入 {_tokens(totals['uncached_input'])}、缓存写入 {_tokens(totals['cache_write'])}、"
            f"缓存读取 {_tokens(totals['cache_read'])}、输出 {_tokens(totals['output'])}，模型调用 {totals['calls']} 次、工具调用 {totals['tool_calls']} 次。"
        )
    else:
        print("没有读到宿主的会话记录，下面只有输入侧的账（任务文件大小与耗时）。")

    def rows_of(groups: dict[str, dict[str, Any]], order: list[str]) -> list[list[str]]:
        keys = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
        return [
            [
                ev.STAGE_CN.get(k, k),
                str(groups[k]["dispatches"]),
                str(groups[k]["redispatches"]),
                f"{groups[k]['task_bytes'] / 1024:.0f}KB",
                ev.fmt_duration(groups[k]["seconds"] / 3600),
                _tokens(groups[k]["uncached_input"]) if groups[k]["with_usage"] else "-",
                _tokens(groups[k]["cache_read"]) if groups[k]["with_usage"] else "-",
                _tokens(groups[k]["output"]) if groups[k]["with_usage"] else "-",
                str(groups[k]["tool_calls"]) if groups[k]["with_usage"] else "-",
            ]
            for k in keys
        ]

    head = ["派发", "重派", "输入包", "耗时", "未缓存输入", "缓存读取", "输出", "工具调用"]
    print()
    print(_table(["阶段", *head], rows_of(ledger["by_stage"], st.STAGE_ORDER)))
    print()
    print(_table(["角色", *head], rows_of(ledger["by_role"], [])))
    calls = ledger["kernel_calls"]
    if calls.get("total"):
        print()
        per = totals["dispatches"] and calls["total"] / totals["dispatches"]
        print(
            f"主会话调用内核 {calls['total']} 次（平均每次派发 {per:.1f} 次），内核一共输出 {calls['out_bytes'] / 1024:.0f}KB："
            + "、".join(f"{k} {v}" for k, v in sorted(calls["by_command"].items(), key=lambda kv: -kv[1]))
        )
    if steps:
        print()
        detail = [
            [
                f"{r['step']}#{r['attempt']}",
                str(r["role"]),
                f"{(r['task_bytes'] + int(r.get('input_bytes') or 0)) / 1024:.0f}KB",
                ev.fmt_duration((r["seconds"] or 0) / 3600) if r["seconds"] is not None else "在途",
                str(r["outcome"]),
                _tokens((r["usage"] or {}).get("total_input", 0)) if r.get("usage") else "-",
                _tokens((r["usage"] or {}).get("peak_context", 0)) if r.get("usage") else "-",
            ]
            for r in ledger["rows"]
        ]
        print(_table(["步骤", "角色", "输入包", "耗时", "结果", "累计输入", "上下文峰值"], detail))


def cmd_cost(root: Path, args: argparse.Namespace) -> int:
    report_id = _resolve(root, args.report_id)
    state = st.load_state(root, report_id)
    ledger = us.step_ledger(st.read_event_records(root, report_id), us.read_calls(root, report_id)) if st.is_v2(state) else None
    if ledger and ledger["rows"] and not args.sessions:
        # 内核推进的案例：用内核自己记的账，任何宿主都有；宿主会话记录只作补充（--sessions 时再去扫）
        if args.json:
            _print_json({"report_id": report_id, "source": "ledger", **ledger})
        else:
            _print_ledger(report_id, ledger, args.steps)
        return 0
    hosts = ("claude_code", "codex") if args.host == "auto" else (args.host,)
    span = us.span_interval(*ev.activity_span(state, ev.timeline(root, report_id, state)))
    sessions = us.collect_case_usage(
        root, report_id, state, hosts=hosts, intervals=[span] if span else None, other_ids=st.list_case_ids(root)
    )
    summary = us.summarize(sessions)
    if args.json:
        _print_json({"report_id": report_id, **summary, "sessions_detail": [s.to_dict() for s in sessions] if args.sessions else None})
        return 0
    if not sessions:
        print(f"{report_id}：在宿主的会话记录里没有找到对得上的会话（记录可能已被清理，或案例跑在别的宿主上）。")
        return 0
    total = summary["total"]
    print(
        f"{report_id}：{summary['sessions']} 个相关会话，累计输入 {_tokens(total['total_input'])}"
        f"（未缓存 {_tokens(total['uncached_input'])}、缓存写入 {_tokens(total['cache_write'])}、缓存读取 {_tokens(total['cache_read'])}），"
        f"输出 {_tokens(total['output'])}。"
    )
    rows = [
        [
            key,
            str(g["sessions"]),
            str(g["calls"]),
            str(g["tool_calls"]),
            _tokens(g["uncached_input"]),
            _tokens(g["cache_write"]),
            _tokens(g["cache_read"]),
            _tokens(g["output"]),
            _tokens(g["peak_context"]),
            ev.fmt_duration(g["seconds"] / 3600),
        ]
        for key, g in summary["groups"].items()
    ]
    print(_table(["宿主/角色", "会话", "调用", "工具", "未缓存输入", "缓存写入", "缓存读取", "输出", "上下文峰值", "起止跨度"], rows))
    if args.sessions:
        print()
        srows = [
            [
                (s.started_at or "")[:16],
                f"{s.host}/{s.role or '?'}",
                (s.label or "")[:30],
                str(s.usage.calls),
                _tokens(s.usage.total_input),
                _tokens(s.usage.output),
                _tokens(s.usage.peak_context),
                f"{s.model or '-'}{'/' + s.effort if s.effort else ''}",
            ]
            for s in sorted(sessions, key=lambda x: x.started_at or "")
        ]
        print(_table(["开始", "宿主/角色", "标签", "调用", "累计输入", "输出", "上下文峰值", "模型/强度"], srows))
    print(
        "这是给旧案例的估计：取案例从第一条到最后一条状态事件之间（前后各一小时）、工作目录相同、"
        "且提到本案例的行数比提到其他任何案例都多的会话，只算这段时间内的调用；子代理跟随父会话。"
        "宿主已经清理掉的记录不在其中。"
    )
    return 0


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------


def cmd_pack_build(root: Path, args: argparse.Namespace) -> int:
    report_id = _resolve(root, args.report_id)
    docs = packs.CaseDocs.load(root, report_id)
    pack = packs.build_pack(docs, args.role, args.step)
    problems = packs.verify_pack(docs, pack)
    if problems:
        print("错误: 包里有片不是原文的逐字节子串：\n" + "\n".join(problems), file=sys.stderr)
        return 1
    if args.manifest:
        _print_json(pack.manifest())
    elif args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(pack.render(), encoding="utf-8")
        print(f"{out}  {_kb(pack.nbytes)}（现行合同全量 {_kb(pack.full_bytes)}，{pack.nbytes / pack.full_bytes:.0%}）")
    else:
        sys.stdout.write(pack.render())
    for warning in pack.warnings:
        print(f"注意: {warning}", file=sys.stderr)
    return 0


def cmd_pack_stats(root: Path, args: argparse.Namespace) -> int:
    all_stats = [packs.shadow_stats(root, report_id) for report_id in _targets(root, args.report_ids)]
    if args.json:
        _print_json({"cases": all_stats, "summary": packs.summarize_ratios(all_stats)})
        return 0
    rows: list[list[str]] = []
    skipped: list[str] = []
    for case in all_stats:
        if not case["packs"]:
            skipped.append(f"{case['report_id']}（{'；'.join(case['errors'])[:80] or '文书不全'}）")
            continue
        for row in case["packs"]:
            rows.append(
                [
                    case["report_id"],
                    row["role"],
                    row["step"],
                    _kb(row["bytes"]),
                    _kb(row["full_bytes"]),
                    f"{row['ratio']:.0%}" if row["ratio"] is not None else "-",
                    "是" if row["substring_ok"] else "否",
                ]
            )
    if rows:
        print(_table(["案例", "角色", "步骤", "包", "现行合同全量", "比例", "片都是原文子串"], rows))
    summary = packs.summarize_ratios(all_stats)
    if summary:
        print()
        srows = [
            [role, str(v["n"]), f"{v['ratio_min']:.0%}", f"{v['ratio_median']:.0%}", f"{v['ratio_max']:.0%}", _kb(v["bytes_min"]), _kb(v["bytes_median"]), _kb(v["bytes_max"])]
            for role, v in summary.items()
        ]
        print(_table(["角色", "包数", "比例最小", "比例中位", "比例最大", "包最小", "包中位", "包最大"], srows))
    for item in skipped:
        print(f"跳过 {item}")
    print("\n影子包：只拼出来量大小，没有投喂给任何 agent，也没有写入任何文件。")
    return 0


def cmd_pack_lint(root: Path, args: argparse.Namespace) -> int:
    result: dict[str, list[dict[str, str]]] = {}
    for report_id in _targets(root, args.report_ids):
        findings = packs.lint(packs.CaseDocs.load(root, report_id))
        result[report_id] = [{"level": f.level, "code": f.code, "message": f.message} for f in findings]
    if args.json:
        _print_json(result)
        return 0
    for report_id, findings in result.items():
        warns = [f for f in findings if f["level"] == "warn"]
        if not findings:
            print(f"{report_id}: 没有问题")
            continue
        print(f"{report_id}: {len(warns)} 条告警，{len(findings) - len(warns)} 条提示")
        for f in findings:
            print(f"  [{'告警' if f['level'] == 'warn' else '提示'}] {f['message']}")
    return 0


# ---------------------------------------------------------------------------
# data probe
# ---------------------------------------------------------------------------


def cmd_data_probe(root: Path, args: argparse.Namespace) -> int:
    data_root = Path(args.data_root).expanduser() if args.data_root else None
    probe = datacheck.run_probe(root, data_root, yearly=not args.no_yearly, use_cache=not args.no_cache)
    catalog = root / "templates" / "data_catalog.md"
    findings = datacheck.compare_with_catalog(probe, catalog.read_text(encoding="utf-8")) if catalog.is_file() and not probe.get("error") else None
    if args.json:
        _print_json({**probe, "catalog_findings": findings})
    if probe.get("error"):
        print(f"错误: {probe['error']}", file=sys.stderr)
        return 1
    json_path, md_path = datacheck.save_probe(root, probe, findings)
    if args.json:
        return 0
    stats = probe["stats"]
    print(
        f"数据目录 {probe['data_root']}：{stats['files']} 个文件，{stats['bytes'] / 1e9:.1f} GB；"
        f"本次实测 {stats['probed']} 个，其余 {stats['from_cache']} 个沿用缓存，用时 {stats['seconds']} 秒。"
    )
    if not probe.get("pyarrow"):
        print("注意：没有安装 pyarrow，parquet 文件只记了大小，没有读字段和日期。")
    if stats["errors"]:
        print(f"{stats['errors']} 个文件读取失败，详见 {json_path}。")
    flagged = [(rel, e) for rel, e in probe["files"].items() if e.get("flags")]
    if flagged:
        print(f"\n{len(flagged)} 个文件有需要留意的情况：")
        for rel, entry in flagged[: args.limit]:
            print(f"  {rel}：" + "；".join(f["detail"] for f in entry["flags"]))
        if len(flagged) > args.limit:
            print(f"  …另有 {len(flagged) - args.limit} 个，见 {md_path}")
    if findings:
        warns = [f for f in findings if f["level"] == "warn"]
        print(f"\n与 templates/data_catalog.md 对不上的地方 {len(warns)} 处：")
        for f in warns[: args.limit]:
            print(f"  {f['file']}：{f['detail']}")
        if len(warns) > args.limit:
            print(f"  …另有 {len(warns) - args.limit} 处，见 {md_path}")
    print(f"\n数据实况表：{md_path}\n逐文件明细：{json_path}")
    return 0


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


def cmd_migrate(root: Path, args: argparse.Namespace) -> int:
    if not args.report_id and not args.all:
        print("错误: 给出要迁移的案例，或用 --all", file=sys.stderr)
        return 1
    targets = st.list_case_ids(root) if args.all else [_resolve(root, args.report_id)]
    failed = 0
    for report_id in targets:
        try:
            summary = st.migrate_to_v2(root, report_id, dry_run=args.dry_run)
        except (st.StateValidationError, ValueError, OSError) as exc:
            failed += 1
            print(f"{report_id}: 迁移失败——{str(exc).splitlines()[0]}")
            continue
        if summary.get("reason") == "already_v2":
            print(f"{report_id}: 已是 v2，未改动")
            continue
        verb = "将会" if args.dry_run else "已"
        print(
            f"{report_id}: {verb}把 {summary['events']} 条事件和 {summary['gates']} 条门禁记录移入 events.jsonl，"
            f"state 留最近 {summary['state_events_kept']} 条事件、{summary['state_gates_kept']} 个阶段的最新门禁"
            + ("" if args.dry_run else f"；原文件备份为 {summary['backup']}")
        )
    if not args.dry_run and failed < len(targets):
        print("提示：v2 的状态文件旧版本工具（v2.12 及更早）读不了；如需退回，用 state.v1.json 覆盖 state.json 并删除 events.jsonl。")
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flow", description="研报复现 v3 内核")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="进度；不给 id 时列出全部案例")
    p.add_argument("report_id", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    def _common(p: argparse.ArgumentParser, text: bool = True) -> argparse.ArgumentParser:
        p.add_argument("--host", choices=["claude_code", "codex", "generic"], help="当前宿主（不给时自动识别）")
        if text:
            p.add_argument("--text", action="store_true", help="给人看的文字（默认输出 JSON）")
        return p

    def _human(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--quote", help="人的原话（必填：放行必须引用人说过的话）")
        return p

    p = _common(sub.add_parser("init", help="新建由内核推进的案例"), text=False)
    p.add_argument("pdf")
    p.add_argument("--slug", help="案例英文短名（小写加下划线），内核据此分配编号 rNNN_<slug>")
    p.add_argument("--id", help="直接指定案例编号（一般不用）")
    p.add_argument("--mode", choices=sorted(st.MODE_VALUES))
    p.add_argument("--max-iter", type=int, dest="max_iter")
    p.add_argument("--difficulty", choices=sorted(st.DIFFICULTY_VALUES), help="人工指定难度（覆盖 planner 的判定）")
    p.add_argument("--experimental", action="store_true", help="实验模式：市场迁移复现")
    p.add_argument("--until", choices=st.STAGE_ORDER, help="到这个阶段收口时停一次")
    p.add_argument("--step", action="store_true", help="每步点收后都停")
    p.add_argument("--on-missing", choices=["ask", "mock", "stop"], dest="on_missing", help="数据缺口无人应答时怎么办（默认 ask：停下等人）")
    p.add_argument("--on-no-answer", choices=["stop"], dest="on_no_answer", help="其余检查点无人应答时一律停下")
    p.add_argument("--budget-tokens", type=float, dest="budget_tokens")
    p.add_argument("--budget-hours", type=float, dest="budget_hours")
    p.add_argument("--stall-hours", type=float, dest="stall_hours")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_init)

    p = _common(sub.add_parser("next", help="下一步的工单"))
    p.add_argument("report_id")
    p.set_defaults(func=cmd_next)

    p = _common(sub.add_parser("done", help="点收步骤并给出下一步"))
    p.add_argument("report_id")
    p.add_argument("steps", nargs="+")
    p.add_argument("--no-next", action="store_true", help="只点收，不推进")
    p.add_argument("--no-usage", action="store_true", help="不读宿主的会话记录")
    p.set_defaults(func=cmd_done)

    p = _common(sub.add_parser("fail", help="记一步失败"))
    p.add_argument("report_id")
    p.add_argument("step")
    p.add_argument("--class", dest="klass", required=True, choices=["incomplete", "blocked", "crashed"])
    p.add_argument("--note")
    p.set_defaults(func=cmd_fail)

    p = _common(sub.add_parser("adhoc", help="步骤表之外的临时派发"), text=False)
    p.add_argument("report_id")
    p.add_argument("--role", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--instruction", required=True, help="写着要做什么的文件")
    p.add_argument("--writes", nargs="*", help="允许改动的路径")
    p.set_defaults(func=cmd_adhoc)

    p = _common(sub.add_parser("exec", help="启动外审步骤"))
    p.add_argument("report_id")
    p.add_argument("step")
    p.add_argument("--detach", action="store_true", help="后台执行，立即返回")
    p.set_defaults(func=cmd_exec)

    p = _common(sub.add_parser("wait", help="等后台外审结束"))
    p.add_argument("report_id")
    p.add_argument("--timeout", type=float, default=540.0, help="最多等多少秒（默认 540，留在常见的命令超时之内）")
    p.add_argument("--interval", type=float, default=5.0)
    p.set_defaults(func=cmd_wait)

    p = _human(_common(sub.add_parser("decide", help="人对检查点的决定")))
    p.add_argument("report_id")
    p.add_argument("checkpoint", help="检查点编号（cp_03 / 3）、短码或名称")
    p.add_argument("--choice", required=True)
    p.add_argument("--by", choices=["human", "policy"], default="human", help="policy 仅用于启动时预先声明过的自动处置")
    p.add_argument("--to", help="choice=rollback 时从哪里重做（阶段名或 milestone 编号）")
    p.add_argument("--budget-tokens", type=float, dest="budget_tokens")
    p.add_argument("--budget-hours", type=float, dest="budget_hours")
    p.set_defaults(func=cmd_decide)

    p = _human(_common(sub.add_parser("accept", help="最终评审通过并收尾"), text=False))
    p.add_argument("report_id")
    p.set_defaults(func=cmd_accept)

    p = _human(_common(sub.add_parser("revise", help="按假设修订定向重跑")))
    p.add_argument("report_id")
    p.add_argument("--assumption", help="假设编号（单条修订）")
    p.add_argument("--text-value", "--new-text", dest="text_value", help="新口径（单条修订）")
    p.add_argument("--from-excel", action="store_true", help="读回 assumptions.xlsx 批量修订")
    p.add_argument("--xlsx")
    p.add_argument("--each", action="store_true", help="逐条敏感性模式（仍按执行卡做）")
    p.add_argument("--dry-run", action="store_true", help="只输出重跑计划")
    p.set_defaults(func=cmd_revise)

    p = _human(_common(sub.add_parser("reopen", help="回退到某个阶段或 milestone 重做")))
    p.add_argument("report_id")
    p.add_argument("--from", dest="start", required=True, help="阶段名或 milestone 编号")
    p.add_argument("--reason")
    p.add_argument("--dry-run", action="store_true", help="只报告过期范围，不执行")
    p.set_defaults(func=cmd_reopen)

    p = _common(sub.add_parser("stale", help="哪些已完成步骤消费过的内容后来变了（只报告）"), text=False)
    p.add_argument("report_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stale)

    p = _common(sub.add_parser("pin", help="把一个阶段退回执行卡驱动或交还内核"), text=False)
    p.add_argument("report_id")
    p.add_argument("stage", choices=st.STAGE_ORDER)
    p.add_argument("--mode", required=True, choices=["card", "kernel"])
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_pin)

    p = _common(sub.add_parser("rerun", help="按假 FAIL 重跑一次 milestone 级验证"))
    p.add_argument("report_id")
    p.add_argument("step")
    p.add_argument("--false-fail", action="store_true", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_rerun)

    p = sub.add_parser("get", help="取一个要素块、一条假设或一行矩阵的原文（子 agent 的逃生门）")
    p.add_argument("report_id")
    p.add_argument("kind", choices=["element", "assumption", "matrix-row"])
    p.add_argument("key")
    p.add_argument("--step")
    p.set_defaults(func=cmd_get)

    p = _common(sub.add_parser("fork", help="把案例复制成新编号并回退到某阶段起点"), text=False)
    p.add_argument("report_id")
    p.add_argument("new_id")
    p.add_argument("--from", dest="start", required=True, choices=st.STAGE_ORDER)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_fork)

    p = sub.add_parser("explain", help="某个阶段、步骤或检查项的异常处理说明")
    p.add_argument("key")
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("gate", help="跑一个阶段的门禁并入账（工具层）")
    p.add_argument("report_id")
    p.add_argument("stage", choices=st.STAGE_ORDER)
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("precheck", help="结果一致性预检（工具层）")
    p.add_argument("report_id")
    p.add_argument("--stage", choices=["result", "report"], default="result")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_precheck)

    p = _common(sub.add_parser("review", help="发起一次外审并合并结果（工具层）"), text=False)
    p.add_argument("report_id")
    p.add_argument("kind", choices=["spec", "code", "result", "second_opinion"])
    p.add_argument("--round", type=int, default=1)
    p.add_argument("--iteration", type=int)
    p.add_argument("--full", action="store_true", help="第二轮起也整体重审")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("merge", help="核对并合并一张回执（工具层）")
    p.add_argument("report_id")
    p.add_argument("receipt")
    p.add_argument("--role", required=True)
    p.add_argument("--stage", required=True, choices=st.STAGE_ORDER)
    p.add_argument("--milestone")
    p.add_argument("--reserved", nargs="*", help="预留给这张回执的新假设编号")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("board", help="生成看板")
    p.add_argument("report_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--index", action="store_true", help="只生成全案例总览")
    p.add_argument("--no-usage", action="store_true", help="不读宿主的会话记录")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("cost", help="用量汇总：内核推进的案例用内核自己记的账，旧案例从宿主会话记录估计")
    p.add_argument("report_id")
    p.add_argument("--host", choices=["auto", "claude_code", "codex"], default="auto")
    p.add_argument("--sessions", action="store_true", help="改为扫描宿主的会话记录并逐会话列出（旧案例只有这一种）")
    p.add_argument("--steps", action="store_true", help="逐次派发列出")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cost)

    pack = sub.add_parser("pack", help="上下文包（影子包）").add_subparsers(dest="pack_command", required=True)
    p = pack.add_parser("build", help="拼一个包")
    p.add_argument("report_id")
    p.add_argument("role", choices=sorted(set(packs.MILESTONE_ROLES) | set(packs.FINAL_ROLES)))
    p.add_argument("step", help="milestone 编号（m1、m2…）或 final")
    p.add_argument("--out", help="写到这个文件（默认打印到标准输出）")
    p.add_argument("--manifest", action="store_true", help="只输出清单（片的来源与哈希）")
    p.set_defaults(func=cmd_pack_build)
    p = pack.add_parser("stats", help="影子包大小统计")
    p.add_argument("report_ids", nargs="*")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pack_stats)
    p = pack.add_parser("lint", help="检查文书里会影响切片的问题")
    p.add_argument("report_ids", nargs="*")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pack_lint)

    data = sub.add_parser("data", help="数据体检").add_subparsers(dest="data_command", required=True)
    p = data.add_parser("probe", help="体检数据目录")
    p.add_argument("--data-root", help="数据根目录（默认取 .reproduce.json 的 data_root，再不然 ~/local_data）")
    p.add_argument("--no-yearly", action="store_true", help="不算每年的标的数与交易日数（只读元数据，最快）")
    p.add_argument("--no-cache", action="store_true", help="忽略缓存，全部重测")
    p.add_argument("--limit", type=int, default=15, help="终端里最多列出多少条提示")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_data_probe)
    p = data.add_parser("check", help="核对一个案例的数据需求")
    p.add_argument("report_id")
    p.add_argument("--smoke", action="store_true", help="执行非文件来源的取数冒烟命令")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_data_check)
    p = _human(_common(data.add_parser("recheck", help="数据补齐后重检；在等数据的检查点上会顺带放行"), text=False))
    p.add_argument("report_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_data_recheck)

    p = sub.add_parser("migrate", help="把状态文件升级到 v2")
    p.add_argument("report_id", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="只说明会怎么改，不写任何文件")
    p.set_defaults(func=cmd_migrate)
    return parser


class _Counting:
    """包一层标准输出，数一数这条命令吐了多少字节（主会话开销的代理指标）。"""

    def __init__(self, stream: Any) -> None:
        self._stream, self.count = stream, 0

    def write(self, text: str) -> int:
        self.count += len(text.encode("utf-8", errors="replace"))
        return self._stream.write(text)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


# 推进与放行类命令才记调用次数；只读查询（status / board / cost / pack / explain / get）不算主循环的往返
_COUNTED_COMMANDS = {"next", "done", "fail", "adhoc", "exec", "wait", "decide", "accept", "revise", "reopen", "pin", "rerun", "gate", "review", "merge", "precheck"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = st.default_root()
    counter = _Counting(sys.stdout)
    sys.stdout = counter
    code = 1
    try:
        code = args.func(root, args)
    except ReceiptError as exc:
        print("错误: 回执被拒收：\n" + "\n".join(f"  - {r}" for r in exc.reasons), file=sys.stderr)
    except (packs.PackError, FlowError, st.StateValidationError, st.StateLockTimeout, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
    finally:
        sys.stdout = counter._stream
    report_id = getattr(args, "report_id", None)
    if args.command in _COUNTED_COMMANDS and report_id:
        try:
            resolved = _resolve(root, report_id)
            if st.is_v2(st.load_state(root, resolved)):  # v1 案例的命令是只读的，不留任何文件
                us.log_call(root, resolved, args.command, int(code or 0), counter.count)
        except Exception:  # noqa: BLE001 - 记账出问题不影响命令本身
            pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
