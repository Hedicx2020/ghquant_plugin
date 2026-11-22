"""步骤表：每个阶段现在该做哪些步骤。

每个阶段一个规划函数，读案例上下文，返回一份 Plan：
  steps       现在应该在途或待派的步骤（已完成的不必列出）
  actions     内核现在就地该做的确定性动作（名字在 engine.ACTIONS 里登记）
  close       这个阶段的工作都做完了，可以跑门禁收口
  skip        这个阶段按规则跳过（值是原因）
  checkpoint  现在该开的人工检查点

规划函数只读、可重复调用；所有改状态的事都在 engine.py 里做。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from tools import state as st

from . import kernelsteps as ks
from .core import DONE, FAILED, FINISHED, INFLIGHT, PLUGIN_ROOT, REDO, REVIEW_ROUND_LIMIT, Ctx, Step
from .events import STAGE_CN, TERMINAL_STATUSES, TOP_STATUS_CN, WAITING_STATUSES

CARD_DIR = "skills/reproduce/stages"
LEGACY_CARD_DIR = "skills/reproduce/stages/legacy"

REVIEW_KIND = {"spec_audit": "spec", "code_audit": "code", "result_audit": "result"}
REVIEW_PREFIX = {"spec": "CDX-S-", "code": "CDX-C-", "result": "CDX-R-"}
# 外审意见可以交给谁修（按这个顺序依次修）
REVIEW_OWNERS = {
    "spec": ("quant-extractor", "quant-planner"),
    "code": ("quant-coder",),
    "result": ("quant-coder", "quant-verifier", "quant-diagnoser"),
}
OWNER_SHORT = {
    "quant-extractor": "extractor",
    "quant-planner": "planner",
    "quant-coder": "coder",
    "quant-verifier": "verifier",
    "quant-diagnoser": "diagnoser",
}
# 门禁未过时由谁来修（阶段 → 角色）；修完再重新收口
GATEFIX_ROLE = {
    "implement": "quant-coder",
    "code_audit": "quant-coder",
    "verify": "quant-coder",
    "iterate": "quant-diagnoser",
    "result_audit": "quant-verifier",
    "report": "quant-reporter",
}


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    actions: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    close: bool = False
    skip: Optional[str] = None
    checkpoint: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 旧执行卡（v1 案例，以及被钉在执行卡上的阶段）
# ---------------------------------------------------------------------------


def card_path(stage: str) -> Optional[Path]:
    """这个阶段的执行卡：优先取 legacy 目录（阶段入码后旧卡挪到那里），再取原位置。"""
    for directory in (LEGACY_CARD_DIR, CARD_DIR):
        path = PLUGIN_ROOT / directory / f"{stage}.md"
        if path.is_file():
            return path
    return None


def stage_driver(state: dict[str, Any], stage: str) -> str:
    """这个阶段由谁推进：card（执行卡）或 kernel（步骤表）。v1 案例一律是 card。"""
    if not st.is_v2(state):
        return "card"
    flow = state.get("flow") or {}
    entry = (flow.get("pinned") or {}).get(stage)
    if isinstance(entry, dict) and entry.get("mode") in ("card", "kernel"):
        return entry["mode"]
    return "kernel" if flow.get("driver") == "kernel" else "card"


def current_stage(state: dict[str, Any]) -> Optional[str]:
    """下一步该推进的阶段：从头数第一个没收口的。"""
    stages = state.get("stages") or {}
    for stage in st.STAGE_ORDER:
        if (stages.get(stage) or {}).get("status") not in FINISHED:
            return stage
    return None


def legacy_order(state: dict[str, Any], stage: str) -> dict[str, Any]:
    entry = (state.get("stages") or {}).get(stage) or {}
    card = card_path(stage)
    name = STAGE_CN.get(stage, stage)
    return {
        "step_id": f"{stage}#card",
        "kind": "legacy_card",
        "stage": stage,
        "stage_name": name,
        "driver": "card",
        "role": "orchestrator",
        "stage_status": entry.get("status"),
        "attempts": entry.get("attempts", 0),
        "card": str(card) if card else None,
        "prompt_inline": (
            f"{name}阶段仍由执行卡驱动：读取 {card} 并按卡推进，收口时照常跑门禁并记账。"
            f"卡里说的「SKILL.md 第 N 节」与全局协议见同目录的 README.md（v2 主编排原文）。"
            if card
            else f"{name}阶段没有执行卡，按 {PLUGIN_ROOT / LEGACY_CARD_DIR / 'README.md'} 的全局协议处理。"
        ),
    }


def halt_for(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    """终态或等待态时的停机说明；可以继续推进时返回 None。"""
    status = state.get("status")
    if status in TERMINAL_STATUSES:
        return {"reason": "terminal", "message": f"案例{TOP_STATUS_CN.get(str(status), str(status))}，没有可推进的步骤"}
    if status not in WAITING_STATUSES:
        return None
    halt: dict[str, Any] = {
        "reason": status,
        "stage": state.get("current_stage"),
        "message": "等待评审：由人决定通过、修改后继续、回退还是终止"
        if status == "awaiting_review"
        else "已暂停：有阻断要人处理，处理完才能继续",
    }
    if state.get("blockers"):
        halt["blockers"] = state["blockers"]
    if state.get("pending_question"):
        halt["pending_question"] = state["pending_question"]
    pending = st.pending_checkpoints(state) if st.is_v2(state) else []
    if pending:
        halt["checkpoints"] = [
            {k: c.get(k) for k in ("id", "code", "name", "stage", "reason", "options", "pack", "opened_at")} for c in pending
        ]
        halt["how"] = (
            "把审阅包交给人看；向人提问时题面以 [<检查点 id> · <短码 code>] 开头。"
            "人决定后执行 flow decide <案例> <检查点编号> --choice <选项> --quote \"<人的原话>\"。不要替人决定。"
        )
    return halt


def plan_next(state: dict[str, Any]) -> dict[str, Any]:
    """只读的下一步预览（v1 案例与执行卡驱动的阶段用它；内核驱动的阶段由 engine.advance 给出真正的工单）。"""
    out: dict[str, Any] = {"report_id": state.get("report_id"), "status": state.get("status"), "orders": [], "wait": [], "halt": None}
    halt = halt_for(state)
    if halt:
        out["halt"] = halt
        return out
    stage = current_stage(state)
    if stage is None:
        out["halt"] = {"reason": "all_stages_done", "message": "全部阶段已收口，但状态还是运行中；需要进入最终评审或收尾"}
        return out
    if stage_driver(state, stage) == "card":
        out["orders"].append(legacy_order(state, stage))
    else:
        out["orders"].append(
            {"step_id": f"{stage}#kernel", "kind": "kernel", "stage": stage, "stage_name": STAGE_CN.get(stage, stage), "driver": "kernel", "prompt_inline": "由内核推进：执行 flow next 取工单。"}
        )
    return out


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _attempt(ctx: Ctx, step_id: str) -> int:
    return int((ctx.rec(step_id) or {}).get("attempt") or 0)


def _k(ctx: Ctx, name: str, dep: Optional[str] = None) -> str:
    """内核动作的记账编号：挂在所依赖步骤的派发次数和重开代次上，上游重做之后动作会跟着重做。"""
    tag = f"{_attempt(ctx, dep)}" if dep else "0"
    return f"{name}@g{ctx.generation}.{tag}"


def _action(ctx: Ctx, name: str, dep: Optional[str] = None, key_name: Optional[str] = None, **args: Any) -> tuple[str, dict[str, Any]]:
    """一个内核动作：（动作名, 参数）。key_name 给出记账用的名字（同一个动作在不同阶段、轮次各记一笔时用）。"""
    return (name, dict(args, key=_k(ctx, key_name or name, dep)))


def _need(ctx: Ctx, name: str, dep: Optional[str] = None) -> bool:
    return not ctx.is_done(_k(ctx, name, dep))


def _ws(ctx: Ctx, rel: str) -> str:
    return f"{ctx.ws}/{rel}"


def _spec_files(ctx: Ctx) -> list[str]:
    return [_ws(ctx, "spec/spec.md"), _ws(ctx, "spec/coverage_matrix.md"), _ws(ctx, "spec/ambiguities.md")]


def _type_template(ctx: Ctx) -> str:
    rtype = ctx.report_type or (ks.plan_frontmatter(ctx) or {}).get("type") or "factor"
    return ctx.template(f"templates/{rtype}.md")


def _reopen(ctx: Ctx) -> dict[str, Any]:
    info = ctx.flow.get("reopen") or {}
    return info if info.get("gen") == ctx.generation else {}


def _pending_or_done(ctx: Ctx, step: Step) -> Optional[Step]:
    """已完成的步骤不必再列；其余（没派过、在途、要重派）交给引擎处理。"""
    return None if ctx.is_done(step.id) else step


# ---------------------------------------------------------------------------
# extract / plan
# ---------------------------------------------------------------------------


def plan_extract(ctx: Ctx) -> Plan:
    pdf = str(ctx.state.get("pdf_path") or "")
    main = Step(
        id="extract.main",
        stage="extract",
        role="quant-extractor",
        title="从研报提取 spec 三件套",
        instruction=(
            f"研报共 {ctx.state.get('pdf_pages')} 页。按角色合同产出 spec.md、coverage_matrix.md、ambiguities.md，"
            "页码引用制，只陈述研报说了什么，不做复现设计。图表里的数值以 PDF 原页为准，转写文本只作检索用。"
        ),
        reads=[
            pdf,
            _ws(ctx, "spec/report_text.md"),
            _ws(ctx, "spec/tables_extracted.md"),
            ctx.template("templates/_spec_template.md"),
            ctx.template("templates/audit/coverage_matrix.md"),
            ctx.template("templates/audit/ambiguities.md"),
        ],
        outputs=_spec_files(ctx),
        writes=[_ws(ctx, "spec/")],
    )
    return Plan(close=True) if ctx.is_done(main.id) else Plan(steps=[main])


def plan_plan(ctx: Ctx) -> Plan:
    facts = "workspace/_registry/data_probe.md"
    reads = _spec_files(ctx) + [
        ctx.template("templates/_plan_template.md"),
        _type_template(ctx),
        ctx.template("templates/audit/assumptions.md"),
    ]
    reads += [facts] if ctx.exists(facts) else []
    reads.append(ctx.template("templates/data_catalog.md"))
    framework = ctx.config.get("backtest_framework")
    main = Step(
        id="plan.main",
        stage="plan",
        role="quant-planner",
        title="分诊并写复现计划",
        instruction=(
            f"执行模式 {ctx.mode}；复现模式 {ctx.state.get('reproduction_mode')}"
            + (f"；回测框架约定 {framework}" if framework else "")
            + "。只读 spec，不读研报原文。产出 plan.md（frontmatter 分诊 + milestone 拆分）与 assumptions.md，并回填矩阵的 milestone 列与歧义裁决。\n\n"
            "数据可得性以「数据实况表」（机器实测）为准，手写的 data_catalog.md 只作说明；两者不一致时信实况表。"
            "`data_requirements` 的每一条尽量填上机器可查字段（files / fields / period / freq / min_codes / core / elements），"
            "内核会逐条体检：标了 available 而实测不满足的会退回来改。"
            + ("\n\ninteractive 模式：major 级歧义不要自行裁决成结论，按候选方案写清，留给 plan 定稿检查点由人确认。" if ctx.mode == "interactive" else "")
        ),
        reads=reads,
        outputs=[_ws(ctx, "plan.md"), _ws(ctx, "assumptions.md")],
        writes=[_ws(ctx, "plan.md"), _ws(ctx, "assumptions.md"), _ws(ctx, "spec/coverage_matrix.md"), _ws(ctx, "spec/ambiguities.md")],
    )
    if not ctx.is_done(main.id):
        return Plan(steps=[main])
    if _need(ctx, "plan.seed", main.id):
        return Plan(actions=[_action(ctx, "plan.seed", main.id)])
    if _need(ctx, "plan.datacheck", main.id):
        return Plan(actions=[_action(ctx, "plan.datacheck", main.id)])
    if ctx.trial:
        mock = Step(
            id="plan.mock_spec",
            stage="plan",
            role="quant-planner",
            title="起草 mock 数据规格",
            instruction=(
                "这个案例经人确认先用 mock 数据试跑。读数据体检结果，为每一处缺口起草模拟数据规格，写到 data_mock/spec.yaml。"
                "规格格式见 tools/mockdata.py 文件头的模块说明（只读前 140 行，不用读实现）：能借一张结构相近的真实表就用 borrow，实在没有才用 synth；"
                "交易日历与证券代码取本地真实数据，保证与其他表对得上。只写规格，不要生成数据。"
            ),
            reads=[_ws(ctx, "plan.md"), _ws(ctx, "data_check.json"), str(PLUGIN_ROOT / "tools" / "mockdata.py")],
            outputs=[_ws(ctx, "data_mock/spec.yaml")],
            writes=[_ws(ctx, "data_mock/spec.yaml")],
        )
        if not ctx.is_done(mock.id):
            return Plan(steps=[mock])
        if _need(ctx, "plan.mock_generate", mock.id):
            return Plan(actions=[_action(ctx, "plan.mock_generate", mock.id)])
    return Plan(close=True)


# ---------------------------------------------------------------------------
# 外审的「审 → 裁 → 修 → 复审」循环（三个审查点共用）
# ---------------------------------------------------------------------------


def review_round(ctx: Ctx, kind: str) -> int:
    return max(int(((ctx.state.get("counters") or {}).get("review_rounds") or {}).get(kind) or 1), 1)


def _review_base(ctx: Ctx, kind: str) -> int:
    """复审轮数上限从哪一轮起算：重开，或人在「复审超限」检查点上决定再试之后，从那时的轮数起算。"""
    return int((ctx.flow.get("round_base") or {}).get(kind) or 0)


def _fix_instruction(ctx: Ctx, kind: str, role: str, items: list[dict[str, Any]]) -> str:
    lines = [
        f"外审（{kind}）与内审提出了下面这些已被接受的意见，归你修。逐条修复，修完在回执的 summary 里按编号写明改了哪里（文件:行号）。",
        "只处理列出的意见；觉得某条不成立，在回执里写明理由并把 status 写成 blocked，不要自行跳过。",
        "",
    ]
    for item in items:
        lines.append(f"- **{item.get('id')}**（{item.get('severity', '')}）{item.get('title', '')}")
        if item.get("location"):
            lines.append(f"  - 位置：{item['location']}")
        if item.get("detail"):
            lines.append(f"  - 说明：{str(item['detail'])[:600]}")
        if item.get("reply"):
            lines.append(f"  - 处置时的说明：{str(item['reply'])[:300]}")
    return "\n".join(lines)


def _fix_step(ctx: Ctx, stage: str, kind: str, role: str, rnd: int, items: list[dict[str, Any]]) -> Step:
    short = OWNER_SHORT[role]
    writes = {
        "quant-extractor": [_ws(ctx, "spec/")],
        "quant-planner": [_ws(ctx, "plan.md"), _ws(ctx, "assumptions.md"), _ws(ctx, "spec/coverage_matrix.md"), _ws(ctx, "spec/ambiguities.md")],
        "quant-coder": [f"{ctx.src}/", "common/"],
        "quant-verifier": [f"{ctx.results}/", f"{ctx.out}/verify_report.md", _ws(ctx, "audit/evidence_manifest.md")],
        "quant-diagnoser": [f"{ctx.results}/comparison.json", _ws(ctx, "iterations/"), _ws(ctx, "audit/evidence_manifest.md")],
    }[role]
    pack = None
    if role == "quant-verifier":
        pack = ("verifier", "final")
    return Step(
        id=f"{stage}.fix.{short}.r{rnd}",
        stage=stage,
        role=role,
        title=f"修复{STAGE_CN.get(stage, stage)}意见（第 {rnd} 轮）",
        instruction=_fix_instruction(ctx, kind, role, items),
        reads=[_ws(ctx, "audit/audit_responses.md"), _ws(ctx, f"audit/{kind}_audit_external.md")],
        writes=writes,
        pack=pack,
        milestone="all",
    )


def review_cycle(ctx: Ctx, stage: str, *, triggered: bool, parallel: Optional[list[Step]] = None) -> Optional[Plan]:
    """外审循环当前该做什么；循环已经干净收尾时返回 None。

    一轮：外审（后台）→ 汇总入账 → 主会话逐条裁决 → 属主角色修复 →（有 critical 才）下一轮差量复审。
    """
    kind = REVIEW_KIND[stage]
    rnd = review_round(ctx, kind)
    extras = [s for s in (parallel or []) if not ctx.is_done(s.id)]

    if triggered:
        ext = Step(
            id=f"{stage}.ext.r{rnd}",
            stage=stage,
            kind="exec",
            role="external",
            title=f"{STAGE_CN.get(stage, stage)}外审（第 {rnd} 轮）",
            receipt="none",
            parallel_group=f"{stage}.r{rnd}",
            extra={"review_kind": kind, "round": rnd},
        )
        ext_rec = ctx.rec(ext.id) or {}
        if ext_rec.get("status") != DONE:
            return Plan(steps=[ext] + extras)
        outcome = (ext_rec.get("result") or {}).get("state")
        # 外审任务连提示词都没准备出来（job_id 为空）时没有东西可交给替身：这一轮直接记为跳过
        if outcome == "failed" and ext_rec.get("job_id"):
            fb = Step(
                id=f"{stage}.ext.r{rnd}.fallback",
                stage=stage,
                role="general-purpose",
                title=f"{STAGE_CN.get(stage, stage)}外审的同宿主替身（第 {rnd} 轮）",
                instruction="外部审查引擎不可用，由你作为独立审查方完成同一份审查。只读，不改任何被审文件。",
                receipt="none",
                extra={"fallback_of": ext.id, "review_kind": kind, "round": rnd},
            )
            fb_rec = ctx.rec(fb.id) or {}
            if fb_rec.get("status") not in (DONE, "failed"):
                return Plan(steps=[fb] + extras)
    if extras:
        return Plan(steps=extras)

    collect = f"{stage}.collect.r{rnd}"
    if _need(ctx, collect):
        extra_args = {} if triggered else {"skipped": True, "reason": "按审计档位本案例不触发这道外审"}
        return Plan(actions=[_action(ctx, "review.collect", None, key_name=collect, kind=kind, stage=stage, round=rnd, **extra_args)])
    summary = ctx.result_of(_k(ctx, collect))
    unruled = list(summary.get("unruled") or []) + list(summary.get("unruled_diffs") or [])
    rule = Step(
        id=f"{stage}.rule.r{rnd}",
        stage=stage,
        kind="judge",
        role="orchestrator",
        title=f"逐条裁决{STAGE_CN.get(stage, stage)}意见（第 {rnd} 轮）",
        receipt="none",
        extra={"review_kind": kind, "round": rnd, "answer_file": _ws(ctx, f"flow/answers/{stage}.rule.r{rnd}.json")},
    )
    if unruled and not ctx.is_done(rule.id):
        return Plan(steps=[rule])
    ruling = ctx.result_of(rule.id)
    if ruling.get("disputed") and any(
        c.get("name") == "critical_dispute" and c.get("status") == "pending" for c in ctx.state.get("checkpoints") or []
    ):
        return Plan()  # 有 critical 争议在等人裁决
    fixes: dict[str, list[dict[str, Any]]] = {}
    for source in (summary.get("carry_fixes") or {}, ruling.get("fixes") or {}, (ctx.flow.get("dispute_fixes") or {}).get(f"{stage}.r{rnd}") or {}):
        for role, items in source.items():
            fixes.setdefault(role, []).extend(items)
    for role in REVIEW_OWNERS[kind]:
        items = fixes.get(role) or []
        if not items:
            continue
        step = _fix_step(ctx, stage, kind, role, rnd, items)
        if not ctx.is_done(step.id):
            return Plan(steps=[step])
        if role == "quant-planner" and _need(ctx, "plan.seed", step.id):
            return Plan(actions=[_action(ctx, "plan.seed", step.id)])
        if role == "quant-coder" and kind == "result":
            rerun = verify_step(ctx, f"{stage}.reverify.r{rnd}", stage, "代码按外审意见改过了，整批重出验证产物。")
            if not ctx.is_done(rerun.id):
                return Plan(steps=[rerun])
    if fixes and _need(ctx, f"{stage}.responses.r{rnd}"):
        return Plan(actions=[_action(ctx, "review.responses", None, key_name=f"{stage}.responses.r{rnd}", kind=kind, stage=stage, round=rnd)])
    recheck = list(ruling.get("recheck") or []) + [i.get("id") for items in (summary.get("carry_fixes") or {}).values() for i in items]
    recheck += [i.get("id") for items in ((ctx.flow.get("dispute_fixes") or {}).get(f"{stage}.r{rnd}") or {}).values() for i in items]
    needs_recheck = bool(recheck)
    if triggered and needs_recheck:
        if rnd - _review_base(ctx, kind) >= REVIEW_ROUND_LIMIT:
            return Plan(
                checkpoint={
                    "name": "review_rounds_exhausted",
                    "reason": f"{STAGE_CN.get(stage, stage)}已经审了 {rnd - _review_base(ctx, kind)} 轮，仍有 critical 没有闭环",
                    "payload": {"kind": kind, "round": rnd, "open_critical": recheck},
                }
            )
        return Plan(actions=[("review.next_round", {"kind": kind, "stage": stage, "round": rnd, "key": f"{stage}.next.r{rnd}@g{ctx.generation}"})])
    return None


# ---------------------------------------------------------------------------
# spec_audit
# ---------------------------------------------------------------------------


def spec_audit_triggered(ctx: Ctx) -> tuple[bool, str]:
    if ctx.audit_level != "standard":
        return True, "审计档位为 strict，三道外审都跑"
    levels = ks.ambiguity_levels(ctx)
    if levels.get("blocking") or levels.get("major"):
        return True, "歧义清单里有 blocking / major 级条目"
    if ctx.difficulty == "hard":
        return True, "难度为 hard"
    if ks.first_of_type(ctx):
        return True, f"类型 {ctx.report_type} 还没有收尾过的案例"
    return False, "standard 档位下三个触发条件都没有命中"


def plan_spec_audit(ctx: Ctx) -> Plan:
    pdf = str(ctx.state.get("pdf_path") or "")
    internal: list[Step] = []
    if ctx.difficulty != "easy":
        internal.append(
            Step(
                id="spec_audit.internal",
                stage="spec_audit",
                role="quant-auditor",
                title="规格内审（mode=spec）",
                instruction="mode=spec。对照研报原文核对提取与计划（C1–C6），按 templates/audit/extract_audit.md 的骨架写审计记录。只拿文件，不采信任何完成汇报。",
                reads=[pdf, _ws(ctx, "spec/report_text.md"), _ws(ctx, "spec/tables_extracted.md"), *_spec_files(ctx), _ws(ctx, "plan.md"), ctx.template("templates/audit/extract_audit.md")],
                outputs=[_ws(ctx, "audit/extract_audit.md")],
                writes=[_ws(ctx, "audit/extract_audit.md")],
                receipt="required",
                parallel_group="spec_audit.r1",
            )
        )
    triggered, _why = spec_audit_triggered(ctx)
    plan = review_cycle(ctx, "spec_audit", triggered=triggered, parallel=internal)
    return plan if plan is not None else Plan(close=True)


# ---------------------------------------------------------------------------
# implement
# ---------------------------------------------------------------------------


def _coder_instruction(ctx: Ctx, mid: str, name: str) -> str:
    notes = "；".join(
        [
            "只实现本 milestone 的要素，公共逻辑放 common/，策略特有逻辑放 src/",
            "取数一律经 common.data_loader 的 data_path() / read_table()，结果目录用 results_dir()，不要写死路径；"
            f"调用时带上 report_id=\"{ctx.report_id}\"（在 config.py 里定义成常量），否则读不到本案例的覆盖数据、也写不出数据清单",
            "只许冒烟运行，不宣布验证结论",
            "上游 milestone 已实现而尚未验证的代码不要顺手修改，发现问题写进回执",
        ]
    )
    return f"实现 {mid}「{name}」。{notes}。实现位置与矩阵状态写进回执；config 字段定名后把相关假设的参数绑定校正写进回执。"


def code_step(ctx: Ctx, m: dict[str, Any]) -> Step:
    mid = str(m["id"])
    return Step(
        id=f"implement.{mid}.code",
        stage="implement",
        role="quant-coder",
        title=f"编码 {mid} {m.get('name', '')}".strip(),
        milestone=mid,
        instruction=_coder_instruction(ctx, mid, str(m.get("name") or "")),
        pack=("coder", mid),
        writes=[f"{ctx.src}/", "common/"],
        receipt="required",
        parallel_group=f"implement.{mid}",
    )


def milestone_verify_step(ctx: Ctx, m: dict[str, Any]) -> Step:
    mid = str(m["id"])
    return Step(
        id=f"implement.{mid}.verify",
        stage="implement",
        role="quant-verifier",
        title=f"验证 {mid} {m.get('name', '')}".strip(),
        milestone=mid,
        instruction=(
            f"milestone 级验证：只验 {mid} 交付的要素。亲自运行相关代码，把本步的验证记录写成分片文件（不要改 verify_report.md，"
            f"也不要动 {ctx.results}/ 下的正式产物）；对上的指标与矩阵「验证结果」写进回执，结论写进回执的 verify.verdict。"
        ),
        pack=("verifier", mid),
        outputs=[f"{ctx.out}/verify_fragments/{mid}.md"],
        writes=[f"{ctx.out}/verify_fragments/{mid}.md"],
        receipt="required",
        parallel_group=f"implement.{mid}.check",
    )


def milestone_audit_step(ctx: Ctx, m: dict[str, Any], stage: str = "implement") -> Step:
    mid = str(m["id"])
    return Step(
        id=f"{stage}.{mid}.audit",
        stage=stage,
        role="quant-auditor",
        title=f"实现内审 {mid}（mode=code）",
        milestone=mid,
        instruction=(
            f"mode=code，milestone={mid}。按五个维度对本 milestone 全部已实现要素逐条核对，src/ 自己整读。"
            "空壳实现必须单独成行写「判定: not_found」。结论的计数写进回执的 audit。"
        ),
        pack=("auditor_code", mid),
        outputs=[_ws(ctx, f"audit/impl_audit_{mid}.md")],
        writes=[_ws(ctx, f"audit/impl_audit_{mid}.md")],
        receipt="required",
        parallel_group=f"implement.{mid}.check",
    )


def _verified(ctx: Ctx, m: dict[str, Any]) -> bool:
    return m.get("verify") in ("done", "skipped")


def plan_implement(ctx: Ctx) -> Plan:
    milestones = ctx.milestones
    if not milestones:
        return Plan(checkpoint={"name": "stuck", "reason": "状态里没有 milestone，编码阶段无从派发；检查 plan.md 的 frontmatter", "payload": None})
    if ctx.created_by_kernel and _need(ctx, "implement.datacheck"):
        # 入口断言：plan 之后数据需求若被改过（规格外审的修复、人的修改），体检重做一遍
        return Plan(actions=[_action(ctx, "implement.datacheck", stage="implement")])
    reopen = _reopen(ctx)
    todo = [m for m in milestones if m.get("implement") != "done" or not _verified(ctx, m)]
    steps: list[Step] = []

    if reopen.get("kind") == "revise":
        text = Step(
            id="implement.revise_plan",
            stage="implement",
            role="quant-planner",
            title="按修订要求更新假设登记簿与计划",
            instruction=(
                "批量 revise 模式。把下面「本轮的修订要求」逐条落实到 assumptions.md（假设内容改为新口径、状态改 revised、"
                "验证后回看重置为占位符、回看行前插入修订记录）；plan.md 里受影响的段落同步修改。不要改 spec。"
            ),
            reads=[_ws(ctx, "plan.md"), _ws(ctx, "assumptions.md")],
            outputs=[_ws(ctx, "assumptions.md")],
            writes=[_ws(ctx, "plan.md"), _ws(ctx, "assumptions.md")],
        )
        if reopen.get("text_revisions") and not ctx.is_done(text.id):
            return Plan(steps=[text])
        if reopen.get("scope") in ("param", "trading") and reopen.get("needs_coder") and not todo:
            cfg = Step(
                id="implement.revise_config",
                stage="implement",
                role="quant-coder",
                title="按修订要求改参数",
                instruction="只做 config 级改动：按「本轮的修订要求」修改 src 下的参数与受其影响的最小代码，不改方法。改了哪里写进回执。",
                reads=[_ws(ctx, "assumptions.md"), f"{ctx.src}/config.py"],
                writes=[f"{ctx.src}/"],
                milestone="all",
                receipt="required",
            )
            if not ctx.is_done(cfg.id):
                return Plan(steps=[cfg])

    if ctx.difficulty == "easy" and not ctx.is_ml:
        # easy：一个 coder 做完全部 milestone，不做 milestone 级验证
        pending = [m for m in milestones if m.get("implement") != "done"]
        if pending:
            first = pending[0]
            if len(milestones) == 1:
                step = code_step(ctx, first)
            else:
                step = Step(
                    id="implement.all.code",
                    stage="implement",
                    role="quant-coder",
                    title="编码全部 milestone",
                    milestone="all",
                    instruction="easy 难度：一次实现 plan 里的全部 milestone。" + _coder_instruction(ctx, "全部 milestone", "按 plan 顺序"),
                    reads=[*_spec_files(ctx)[:2], _ws(ctx, "plan.md"), _ws(ctx, "assumptions.md"), _type_template(ctx)],
                    writes=[f"{ctx.src}/", "common/"],
                    receipt="required",
                )
            return Plan(steps=[step])
        return Plan(close=True)

    hard = ctx.difficulty == "hard"
    by_id = {str(m["id"]): m for m in milestones}
    for index, m in enumerate(milestones):
        mid = str(m["id"])
        code = code_step(ctx, m)
        if m.get("implement") != "done" or ctx.status_of(code.id) in (INFLIGHT, REDO, FAILED):
            deps_ready = all((by_id.get(d) or {}).get("implement") == "done" for d in m.get("deps") or [])
            if hard:
                ready = deps_ready
            else:
                # medium：按顺序做，流水线深度 1——上一个 milestone 可以还在验证，再往前的必须已验证
                prev_coded = index == 0 or milestones[index - 1].get("implement") == "done"
                earlier_verified = all(_verified(ctx, x) for x in milestones[: max(index - 1, 0)])
                ready = deps_ready and prev_coded and earlier_verified
            if ready or ctx.status_of(code.id) in (INFLIGHT, REDO):
                steps.append(code)
            continue
        if not _verified(ctx, m):
            verify = milestone_verify_step(ctx, m)
            if not ctx.is_done(verify.id):
                steps.append(verify)
        if hard and m.get("code_review") != "done":
            audit = milestone_audit_step(ctx, m)
            if not ctx.is_done(audit.id):
                steps.append(audit)
    if steps:
        return Plan(steps=steps)
    if any(m.get("implement") != "done" or not _verified(ctx, m) or (hard and m.get("code_review") != "done") for m in milestones):
        return Plan(checkpoint={"name": "stuck", "reason": "还有 milestone 没做完，但没有可以派发的步骤（依赖成环，或上一步的结论没有记下来）", "payload": None})
    return Plan(close=True)


# ---------------------------------------------------------------------------
# code_audit / verify
# ---------------------------------------------------------------------------


def verify_step(ctx: Ctx, step_id: str, stage: str, why: str = "") -> Step:
    results = ctx.results
    standards_type = ctx.report_type or ""
    trial = ctx.trial
    outputs = [f"{results}/run_log.md", f"{results}/metrics.json"]
    if not trial:
        outputs += [f"{results}/comparison.json", f"{ctx.out}/verify_report.md", _ws(ctx, "audit/evidence_manifest.md")]
    instruction = (
        "mock 试跑：亲自运行 main.py 把流水线跑通，只确认三件事——跑得通（run_log.md 含 exit=0）、产物齐、指标都算得出。"
        "不做数值对比，不写 comparison.json 和 verify_report.md，不回填矩阵与假设。"
        if trial
        else (
            "最终验证：亲自运行 main.py，整批重出结果目录的全部产物，逐项对数出 comparison.json，写 verify_report.md 与证据清单。"
            "verify_report.md 里不要手抄指标对比表和达标计数：在该放表的位置写一行 `<!-- flow:block comparison_table -->`，"
            "在该放产物清单的位置写一行 `<!-- flow:block artifacts -->`，内核会从机器产物生成后嵌入；正文引用指标时写指标编号。"
            "comparison.json 里每条指标的 source_element 以要素编号开头。矩阵「验证结果」与假设「验证后回看」写进回执。"
            + ("难度为 hard，扰动测试必做一次并记入证据清单。" if ctx.difficulty == "hard" else "全部指标偏差同时小于 0.5% 时做一次扰动测试。")
        )
    )
    return Step(
        id=step_id,
        stage=stage,
        role="quant-verifier",
        title="最终验证" if step_id == "verify.main" else "重跑验证",
        milestone="all",
        instruction=(why + "\n\n" if why else "") + instruction,
        pack=("verifier", "final"),
        reads=[ctx.template("templates/standards.json"), ctx.template(f"templates/{standards_type}.md") if standards_type else _type_template(ctx), ctx.template("templates/audit/evidence_manifest.md")],
        outputs=outputs,
        writes=[f"{results}/", f"{ctx.out}/verify_report.md", _ws(ctx, "audit/evidence_manifest.md")],
        receipt="required",
        parallel_group="verify",
    )


def code_audit_triggered(ctx: Ctx) -> tuple[bool, str]:
    if ctx.audit_level != "standard":
        return True, "审计档位为 strict"
    if ctx.is_ml:
        return True, "含 ml 标签"
    if ctx.difficulty == "hard":
        return True, "难度为 hard"
    critical = [
        sid
        for sid, rec in ctx.steps.items()
        if sid.endswith(".audit") or sid == "code_audit.internal"
        if int(((rec.get("result") or {}).get("audit") or {}).get("critical") or 0) > 0
    ]
    if critical:
        return True, f"内审发现 critical（{', '.join(critical)}）"
    return False, "standard 档位下三个触发条件都没有命中"


def plan_code_audit(ctx: Ctx) -> Plan:
    if _need(ctx, "code_audit.prep"):
        return Plan(actions=[_action(ctx, "code_audit.prep")])
    reopen = _reopen(ctx)
    parallel: list[Step] = []
    needs_internal = (ctx.difficulty == "medium" or (ctx.difficulty == "easy" and ctx.is_ml)) and reopen.get("scope") not in ("param", "trading")
    if needs_internal:
        targets = [m for m in ctx.milestones if not reopen.get("milestones") or m["id"] in reopen["milestones"]]
        parallel.append(
            Step(
                id="code_audit.internal",
                stage="code_audit",
                role="quant-auditor",
                title="实现内审（mode=code，全部 milestone）",
                milestone="all",
                instruction=(
                    "mode=code。对下列 milestone 逐个核对，每个 milestone 各写一份审计文件：" + "、".join(str(m["id"]) for m in targets) + "。"
                    "src/ 自己整读；空壳实现必须单独成行写「判定: not_found」。各 milestone 的计数合计写进回执的 audit。"
                ),
                reads=[*_spec_files(ctx)[:2], _ws(ctx, "assumptions.md"), _ws(ctx, "audit/static_prescreen.md"), _ws(ctx, "audit/common_signatures.md")],
                outputs=[_ws(ctx, f"audit/impl_audit_{m['id']}.md") for m in targets],
                writes=[_ws(ctx, "audit/")],
                receipt="required",
                parallel_group="code_audit.r1",
            )
        )
    # 预跑验证：medium / hard 且非 ml 时，验证与代码审计并行；之后 src 有改动，预跑作废
    if ctx.difficulty in ("medium", "hard") and not ctx.is_ml and not ctx.trial and ctx.status_of("verify.main") is None:
        parallel.append(verify_step(ctx, "verify.main", "verify", "这是与代码审计并行的预跑；之后代码若有改动，内核会让你重跑。"))
    triggered, _why = code_audit_triggered(ctx)
    plan = review_cycle(ctx, "code_audit", triggered=triggered, parallel=parallel)
    return plan if plan is not None else Plan(close=True)


def plan_verify(ctx: Ctx) -> Plan:
    main = verify_step(ctx, "verify.main", "verify")
    rec = ctx.rec(main.id) or {}
    if rec.get("status") == DONE and _need(ctx, "verify.fresh", main.id):
        return Plan(actions=[_action(ctx, "verify.fresh", main.id)])
    if not ctx.is_done(main.id):
        return Plan(steps=[main])
    if ctx.trial:
        if _need(ctx, "verify.trial", main.id):
            return Plan(actions=[_action(ctx, "verify.trial", main.id)])
        return Plan(checkpoint={"name": "trial_done", "reason": "mock 试跑做完了；这一轮不出结论，等你决定下一步", "payload": ctx.result_of(_k(ctx, "verify.trial", main.id))})
    if _need(ctx, "verify.blocks", main.id):
        return Plan(actions=[_action(ctx, "verify.blocks", main.id)])
    return Plan(close=True)


# ---------------------------------------------------------------------------
# iterate
# ---------------------------------------------------------------------------


def plan_iterate(ctx: Ctx) -> Plan:
    verdict = (ctx.state.get("verdict") or {}).get("result")
    iteration = ctx.state.get("iteration") or {}
    n = int(iteration.get("current") or 0)
    max_iter = int(iteration.get("max") or 0) or 3
    if verdict == "pass" and n == 0:
        return Plan(skip="验证已达标，不需要迭代")
    gen = ctx.generation
    outcome = ctx.result_of(f"iterate.close.r{n}@g{gen}").get("outcome") if n else "next"
    if n == 0 or outcome == "next":
        if n >= max_iter:
            outcome = "exhausted"
        else:
            return Plan(actions=[("iterate.open", {"round": n + 1, "key": f"iterate.open.r{n + 1}@g{gen}"})])
    if outcome in ("pass", "partial"):
        return Plan(close=True)
    if outcome == "exhausted":
        closing = Step(
            id="iterate.final.attribution",
            stage="iterate",
            role="quant-diagnoser",
            title="迭代收尾：为残余超差写归因",
            instruction=(
                "收尾模式：迭代已到上限仍有指标超差。只为残余未达标的指标写归因，并回填 comparison.json 里每条的 attribution_status"
                "（accepted 或 assumption_linked）；不给 coder 出新的修改指令，结论不得选 continue。归因追加到最后一轮的 diagnosis.md。"
            ),
            reads=[_ws(ctx, "iterations/iteration_log.md"), f"{ctx.out}/verify_report.md", f"{ctx.results}/comparison.json", _ws(ctx, "assumptions.md")],
            writes=[f"{ctx.results}/comparison.json", _ws(ctx, "iterations/")],
            receipt="required",
        )
        if not ctx.is_done(closing.id):
            return Plan(steps=[closing])
        return Plan(actions=[("iterate.finish", {"result": "partial", "key": f"iterate.finish@g{gen}"})]) if not ctx.is_done(f"iterate.finish@g{gen}") else Plan(close=True)

    directory = ks.iter_dir(ctx, n)
    history = [ks.iter_dir(ctx, i) + "/" for i in range(1, n)]
    digest = f"{directory}/{ks.DIGEST_NAME}"
    has_digest = n >= 2 and ctx.exists(digest)
    digest_note = ""
    if has_digest and ctx.iterate_digest == "on" and n == 2:
        # 摘要代替更早的历史：只在第 2 轮；第 3 轮起恢复全部历史（兜圈的风险随轮次上升）
        history = [f"{ks.iter_dir(ctx, n - 1)}/diagnosis.md"]
        digest_note = f"先读内核生成的摘要 {digest}（趋势表、改善不足预警、已排除假设的原文摘录），再读上一轮诊断全文。"
    elif has_digest:
        digest_note = f"先读内核生成的摘要 {digest}（趋势表、改善不足预警、已排除假设的原文摘录）定位，再读历史轮次的原文；摘要与原文有出入时以原文为准。"
    second = Step(
        id=f"iterate.r{n}.second",
        stage="iterate",
        kind="exec",
        role="external",
        title=f"第二意见（第 {n} 轮）",
        receipt="none",
        extra={"review_kind": "second_opinion", "round": 1, "iteration": n},
    )
    if n >= 2 and ctx.status_of(second.id) != DONE:
        return Plan(steps=[second])
    diagnose = Step(
        id=f"iterate.r{n}.diagnose",
        stage="iterate",
        role="quant-diagnoser",
        title=f"迭代第 {n} 轮：归因",
        instruction=(
            f"本轮目录 {directory}/。{digest_note or '读全部历史轮次再下结论。'}锁定不超过两个修改点；第 2 轮起必须写「## 已排除假设」一节。"
            "末尾写「结论: continue / stop_partial / blocked」三选一，并写进回执的 diagnosis.conclusion。"
            "stop_partial 时为每条未达标指标回填 comparison.json 的 attribution_status。"
            + (f"异构第二意见在 {directory}/second_opinion_external.md，作为独立参考，不必采纳。" if n >= 2 and ctx.exists(f"{directory}/second_opinion_external.md") else "")
        ),
        reads=[*([digest] if has_digest else []), _ws(ctx, "iterations/iteration_log.md"), *history, f"{ctx.out}/verify_report.md", f"{directory}/comparison.json", _ws(ctx, "spec/spec.md"), _ws(ctx, "plan.md"), _ws(ctx, "assumptions.md")],
        outputs=[f"{directory}/diagnosis.md"],
        writes=[f"{directory}/", f"{ctx.results}/comparison.json"],
        receipt="required",
    )
    if not ctx.is_done(diagnose.id):
        return Plan(steps=[diagnose])
    conclusion = ks.diagnosis_conclusion(ctx, n)
    if conclusion == "blocked":
        return Plan(checkpoint={"name": "iterate_blocked", "reason": f"第 {n} 轮诊断结论是 blocked：缺外部输入，见 {directory}/diagnosis.md", "payload": {"round": n}})
    if conclusion == "stop_partial":
        return Plan(actions=[("iterate.close", {"round": n, "mode": "stop", "key": f"iterate.close.r{n}@g{gen}"})])
    if conclusion != "continue":
        return Plan(actions=[("step.redo", {"step": diagnose.id, "reason": "diagnosis.md 里没有找到「结论: continue / stop_partial / blocked」", "key": None})])
    fix = Step(
        id=f"iterate.r{n}.fix",
        stage="iterate",
        role="quant-coder",
        title=f"迭代第 {n} 轮：按诊断修改",
        milestone="all",
        instruction=f"只按 {directory}/diagnosis.md 锁定的修改点和允许的文件范围改代码，改动摘要写到 {directory}/changes.md。不扩大修改面。",
        reads=[f"{directory}/diagnosis.md", _ws(ctx, "assumptions.md")],
        outputs=[f"{directory}/changes.md"],
        writes=[f"{ctx.src}/", "common/", f"{directory}/changes.md"],
        receipt="required",
    )
    if not ctx.is_done(fix.id):
        return Plan(steps=[fix])
    rerun = verify_step(ctx, f"iterate.r{n}.verify", "iterate", f"迭代第 {n} 轮改完代码，整批重出验证产物。")
    if not ctx.is_done(rerun.id):
        return Plan(steps=[rerun])
    return Plan(actions=[("iterate.close", {"round": n, "mode": "verify", "key": f"iterate.close.r{n}@g{gen}"})])


# ---------------------------------------------------------------------------
# result_audit / oos / report / review
# ---------------------------------------------------------------------------


def oos_step(ctx: Ctx) -> Step:
    results = f"{ctx.out}/results"
    return Step(
        id="oos.main",
        stage="oos",
        role="quant-oos-analyst",
        title="样本外表现分析",
        instruction=(
            f"把策略原样延伸到研报回测区间之后的数据上运行，严禁改策略逻辑与参数。数据根目录 {ctx.config.get('data_root') or '~/local_data'}。"
            "本地确实没有区间之后的数据时，不交产物，在回执里写 skip.reason。"
        ),
        reads=[_ws(ctx, "spec/spec.md"), _ws(ctx, "assumptions.md"), f"{results}/comparison.json", ctx.template("templates/data_catalog.md")],
        outputs=[f"{results}/oos_metrics.json", f"{results}/oos_nav.png", f"{results}/oos_summary.xlsx", _ws(ctx, "oos_report.md")],
        writes=[f"{results}/oos_metrics.json", f"{results}/oos_nav.png", f"{results}/oos_summary.xlsx", _ws(ctx, "oos_report.md")],
        receipt="optional",
        parallel_group="result_audit",
    )


def _oos_wanted(ctx: Ctx) -> bool:
    return (ctx.state.get("verdict") or {}).get("result") in ("pass", "partial") and not ctx.trial


def plan_result_audit(ctx: Ctx) -> Plan:
    reopen = _reopen(ctx)
    docfix = Step(
        id="result_audit.docfix",
        stage="result_audit",
        role="quant-verifier",
        title="修正文书与机器结果的不一致",
        instruction="结果一致性预检没过。按下面列出的每一条修正文书（或补 comparison.json 的条目），不要改代码、不要重跑回测。",
        reads=[f"{ctx.out}/verify_report.md", f"{ctx.results}/comparison.json"],
        writes=[f"{ctx.out}/verify_report.md", f"{ctx.results}/comparison.json", _ws(ctx, "audit/evidence_manifest.md")],
        milestone="all",
    )
    if ctx.status_of(docfix.id) in (INFLIGHT, REDO):
        return Plan(steps=[docfix])
    if ctx.created_by_kernel and _need(ctx, "result_audit.precheck", docfix.id):
        return Plan(actions=[_action(ctx, "result_audit.precheck", docfix.id, fix_step=docfix.id)])

    parallel: list[Step] = []
    stats = ks.recalc(ctx)
    k2 = stats["available"] and stats["total"] > 0 and not stats["fails"] and _all_tight(ctx)
    if (ctx.difficulty == "hard" or k2) and reopen.get("scope") not in ("param", "trading", "output"):
        parallel.append(
            Step(
                id="result_audit.internal",
                stage="result_audit",
                role="quant-auditor",
                title="结果内审（mode=result）",
                milestone="all",
                instruction="mode=result。反虚报三查：逐张查看图表、metrics.json 与文书与汇总表三方数值一致、扰动测试触发条件；在证据清单里追加「反虚报复核」一节。结论计数写进回执的 audit。",
                pack=("auditor_result", "final"),
                outputs=[_ws(ctx, "audit/evidence_manifest.md")],
                writes=[_ws(ctx, "audit/evidence_manifest.md")],
                receipt="required",
                parallel_group="result_audit",
            )
        )
    if _oos_wanted(ctx) and ctx.stage_status("oos") not in FINISHED and ctx.status_of("oos.main") is None:
        parallel.append(oos_step(ctx))
    plan = review_cycle(ctx, "result_audit", triggered=True, parallel=parallel)
    return plan if plan is not None else Plan(close=True)


def _all_tight(ctx: Ctx) -> bool:
    """K2：全部数值指标的相对偏差同时小于 0.5%（太准了，要查是不是抄的）。"""
    import json

    path = ctx.path(f"output/{ctx.report_id}/results/comparison.json")
    try:
        metrics = json.loads(path.read_text(encoding="utf-8")).get("metrics") or []
    except (OSError, ValueError):
        return False
    devs = [abs(m["rel_dev"]) for m in metrics if isinstance(m, dict) and isinstance(m.get("rel_dev"), (int, float))]
    return bool(devs) and max(devs) < 0.005


def plan_oos(ctx: Ctx) -> Plan:
    if not _oos_wanted(ctx):
        return Plan(skip="结论不是达标或部分达标（或处于试跑），不做样本外分析")
    step = oos_step(ctx)
    rec = ctx.rec(step.id) or {}
    if rec.get("status") != DONE:
        return Plan(steps=[step])
    skip = (rec.get("result") or {}).get("skip")
    if skip:
        return Plan(skip=f"样本外分析做不了：{skip.get('reason') or '未说明'}")
    if _need(ctx, "oos.fresh", step.id):
        return Plan(actions=[_action(ctx, "oos.fresh", step.id)])
    return Plan(close=True)


def plan_report(ctx: Ctx) -> Plan:
    if _need(ctx, "report.stats"):
        return Plan(actions=[_action(ctx, "report.stats")])
    docfix = Step(
        id="report.docfix",
        stage="report",
        role="quant-verifier",
        title="补齐写报告前还缺的回填",
        instruction="写报告前的机器预检没过：覆盖矩阵里还有没到终态的行，或假设登记簿里还有没回填的「验证后回看」。按下面列出的逐条补齐，写进回执。",
        pack=("verifier", "final"),
        milestone="all",
        receipt="required",
    )
    if ctx.status_of(docfix.id) in (INFLIGHT, REDO):
        return Plan(steps=[docfix])
    if _need(ctx, "report.precheck", docfix.id):
        return Plan(actions=[_action(ctx, "report.precheck", docfix.id, fix_step=docfix.id)])
    if ctx.policy.get("step") and _need(ctx, "report.pre_checkpoint"):
        return Plan(actions=[_action(ctx, "report.pre_checkpoint")])
    if _need(ctx, "report.digest"):
        return Plan(actions=[_action(ctx, "report.digest")])
    digest = _ws(ctx, "flow/report_digest.md")
    n = int((ctx.state.get("iteration") or {}).get("current") or 0)
    reads = [digest, _ws(ctx, "plan.md"), _ws(ctx, "audit/audit_responses.md"), _ws(ctx, "iterations/iteration_log.md")]
    reads += [f"{ks.iter_dir(ctx, n)}/diagnosis.md"] if n else []
    reads += [_ws(ctx, "oos_report.md")] if ctx.stage_status("oos") == "done" else []
    main = Step(
        id="report.main",
        stage="report",
        role="quant-reporter",
        title="汇总最终报告",
        instruction=(
            "按角色合同写 final_report.md，只汇总不新增结论。素材以「报告素材摘要」为准："
            "指标对比总表和假设登记簿全文由内核嵌入——在「指标对比」一节该放总表的位置写一行 `<!-- flow:block comparison_table -->`，"
            "在附录假设清单的位置写一行 `<!-- flow:block assumptions_register -->`，不要自己抄表。"
            "正文引用指标写指标编号；rejected 的意见编号必须原样出现在遗留清单里。"
            + ("本案例是实验模式，必须有「市场迁移」一节并显著声明。" if ctx.experimental else "")
        ),
        reads=reads,
        outputs=[_ws(ctx, "final_report.md")],
        writes=[_ws(ctx, "final_report.md")],
    )
    if not ctx.is_done(main.id):
        return Plan(steps=[main])
    if _need(ctx, "report.assemble", main.id):
        return Plan(actions=[_action(ctx, "report.assemble", main.id, main=main.id)])
    consistency = f"report.consistency.d{_attempt(ctx, docfix.id)}"
    if ctx.created_by_kernel and _need(ctx, consistency, main.id):
        return Plan(actions=[_action(ctx, "report.consistency", main.id, key_name=consistency, main=main.id, fix_step=docfix.id)])
    return Plan(close=True)


def plan_review(ctx: Ctx) -> Plan:
    return Plan(checkpoint={"name": "final_review", "reason": "报告已出，等你评审：通过、修改假设后重跑，或回退", "payload": None})


PLANNERS: dict[str, Callable[[Ctx], Plan]] = {
    "extract": plan_extract,
    "plan": plan_plan,
    "spec_audit": plan_spec_audit,
    "implement": plan_implement,
    "code_audit": plan_code_audit,
    "verify": plan_verify,
    "iterate": plan_iterate,
    "result_audit": plan_result_audit,
    "oos": plan_oos,
    "report": plan_report,
    "review": plan_review,
}


def gatefix_step(ctx: Ctx, stage: str) -> Optional[Step]:
    """门禁未过时的修复工单（原因与门禁原文由引擎写进重派说明）。"""
    role = GATEFIX_ROLE.get(stage)
    if role is None:
        return None
    packs_by_role = {"quant-verifier": ("verifier", "final")}
    writes = {
        "quant-coder": [f"{ctx.src}/", "common/"],
        "quant-verifier": [f"{ctx.results}/", f"{ctx.out}/verify_report.md", _ws(ctx, "audit/evidence_manifest.md")],
        "quant-diagnoser": [_ws(ctx, "iterations/"), f"{ctx.results}/comparison.json"],
        "quant-reporter": [_ws(ctx, "final_report.md")],
    }[role]
    return Step(
        id=f"{stage}.gatefix",
        stage=stage,
        role=role,
        title=f"修复{STAGE_CN.get(stage, stage)}门禁未过项",
        instruction=f"{STAGE_CN.get(stage, stage)}阶段的门禁没过。只修下面「重派原因」里列出的未过项，修完写回执。",
        pack=packs_by_role.get(role),
        writes=writes,
        milestone="all",
    )
