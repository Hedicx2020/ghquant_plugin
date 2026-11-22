"""案例的入口与人工出口：init、decide、accept、revise、reopen、pin、fork，以及失效标注。

等待态只有这里的几个函数能解除；它们都要求带上人的原话，并记下凭据等级。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from tools import check_gates as cg
from tools import state as st

from . import checkpoints as cps
from . import kernelsteps as ks
from . import mdslice as ms
from . import packs
from . import steps as sp
from .core import DONE, INFLIGHT, MODIFY_ROUND_LIMIT, PLUGIN_ROOT, REDO, REVISE_ROUND_LIMIT, Ctx, FlowError, read_json, sha256_file, src_fingerprint, write_json, write_text
from .engine import Engine, generate_mock
from .events import STAGE_CN

REVIEW_TYPE = {"spec_final", "plan_final", "milestone_done", "verify_done", "iterate_round", "pre_report", "until", "step"}
MODIFY_ROLE = {
    "spec_final": "quant-extractor",
    "plan_final": "quant-planner",
    "milestone_done": "quant-coder",
    "verify_done": "quant-verifier",
    "iterate_round": "quant-diagnoser",
    "pre_report": "quant-verifier",
}
STAGE_OWNER = {
    "extract": "quant-extractor",
    "plan": "quant-planner",
    "spec_audit": "quant-planner",
    "implement": "quant-coder",
    "code_audit": "quant-coder",
    "verify": "quant-verifier",
    "iterate": "quant-diagnoser",
    "result_audit": "quant-verifier",
    "report": "quant-reporter",
}
# revise 的影响面 → 要重跑的阶段
REVISE_STAGES = {
    "data": ["implement", "code_audit", "verify", "result_audit", "oos", "report", "review"],
    "method": ["implement", "code_audit", "verify", "result_audit", "oos", "report", "review"],
    "param": ["implement", "verify", "result_audit", "oos", "report", "review"],
    "trading": ["implement", "verify", "result_audit", "oos", "report", "review"],
    "output": ["verify", "report", "review"],
}
IMPACT_RANK = {"data": 4, "method": 3, "param": 2, "trading": 1, "output": 0}


def impact_scope(impact: str) -> str:
    """一条假设改口径后的重跑档位。跨几个面的（「method、data」）取最重的一面；认不出的写法取最重一档。"""
    from . import receipts as rc

    parts = rc.impact_parts(impact)
    return max(parts, key=IMPACT_RANK.__getitem__) if parts and all(part in IMPACT_RANK for part in parts) else "data"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def init_case(
    root: Path,
    pdf: str,
    *,
    slug: Optional[str] = None,
    report_id: Optional[str] = None,
    mode: Optional[str] = None,
    max_iter: Optional[int] = None,
    difficulty: Optional[str] = None,
    experimental: bool = False,
    policy: Optional[dict[str, Any]] = None,
    host: Optional[str] = None,
) -> dict[str, Any]:
    """新建一个由内核推进的案例：编号、骨架、PDF 转文本、撞库检查、数据目录体检、过 G-IN。零派发。"""
    from tools import pdf_extract

    from .core import detect_host, load_config

    config = load_config(root)
    pdf_path = Path(pdf).expanduser()
    pdf_path = pdf_path if pdf_path.is_absolute() else root / pdf_path
    if not pdf_path.is_file():
        raise FlowError(f"PDF 不存在：{pdf_path}")
    if not report_id:
        if not slug:
            raise FlowError("新建案例要给 --slug（英文短名，小写加下划线）或 --id")
        report_id = st.next_numbered_id(root, slug)
    if st.state_path(root, report_id).exists():
        raise FlowError(f"案例 {report_id} 已经存在；续跑用 flow next {report_id}")
    mode = mode or config.get("default_mode") or "auto"
    max_iter = max_iter if max_iter is not None else config.get("default_max_iter")
    st.init_state(
        root,
        report_id,
        str(pdf_path),
        mode=mode,
        max_iter=int(max_iter) if max_iter else None,
        reproduction_mode="experimental" if experimental else "strict",
        schema_version=st.SCHEMA_VERSION_V2,
    )
    engine = Engine(root, report_id, host)
    with engine.txn("flow:init") as txn:
        state = txn.state
        state["flow"]["driver"] = "kernel"
        state["ext"].update({"created_by": "flow", "host": detect_host(host, state), "kernel": "v3"})
        # 策略的取值顺序：建案命令行参数 > .reproduce.json 里的默认值 > 内核默认
        defaults = {"on_missing": config.get("default_on_missing"), "budget_hours": config.get("default_budget_hours"), "budget_tokens": config.get("default_budget_tokens")}
        for key, value in {**{k: v for k, v in defaults.items() if v is not None}, **{k: v for k, v in (policy or {}).items() if v is not None}}.items():
            if key in state["policy"]:
                state["policy"][key] = value
        if difficulty:
            st.set_in(txn, "difficulty_override", difficulty)
        st.set_stage_in(txn, "init", "running")
        txn.log("flow:init", {"pdf": state.get("pdf_path"), "mode": mode, "policy": state["policy"]})

    summary: dict[str, Any] = {"report_id": report_id, "mode": mode}
    try:
        extracted = pdf_extract.run_extract(pdf_path, root / "workspace" / report_id / "spec")
    except pdf_extract.PdfUnparseableError as exc:
        with engine.txn("flow:init") as txn:
            st.set_stage_in(txn, "init", "failed")
            txn.state["status"] = "aborted"
            txn.log("pdf_unparseable", {"error": str(exc)[:300]})
        raise FlowError(f"PDF 无法解析，案例已终止：{exc}") from exc
    sha = sha256_file(pdf_path)
    with engine.txn("flow:init") as txn:
        st.set_in(txn, "pdf_pages", extracted.n_pages)
        txn.state["ext"]["pdf_sha256"] = sha
        txn.touch()
    summary.update(pages=extracted.n_pages, tables=extracted.table_count, text_engine=extracted.engine)

    try:  # 数据目录体检：只读元数据，有缓存；失败不影响建案
        from . import datacheck

        probe = datacheck.run_probe(root, None)
        if not probe.get("error"):
            catalog = root / "templates" / "data_catalog.md"
            findings = datacheck.compare_with_catalog(probe, catalog.read_text(encoding="utf-8")) if catalog.is_file() else None
            datacheck.save_probe(root, probe, findings)
            summary["data_probe"] = {"files": probe["stats"]["files"], "seconds": probe["stats"]["seconds"]}
    except Exception as exc:  # noqa: BLE001
        summary["data_probe"] = {"error": str(exc)[:200]}

    evaluation = cg.evaluate(root, report_id, "init")
    duplicates = ks.pdf_duplicates(root, report_id, sha)
    with engine.txn("flow:init") as txn:
        ctx = engine.ctx(txn.state)
        st.gate_in(txn, "init", evaluation.verdict, evaluation.to_record(with_detail=True))
        if evaluation.passed:
            st.set_stage_in(txn, "init", "done")
            if duplicates:
                cps.open_human(
                    txn,
                    ctx,
                    "pdf_duplicate",
                    reason=f"这份 PDF 与已有案例 {'、'.join(duplicates)} 内容完全相同；通常应当续跑已有案例而不是重做",
                    stage="init",
                    payload={"duplicates": duplicates},
                )
        else:
            st.set_stage_in(txn, "init", "failed")
            txn.state["status"] = "aborted"
            txn.log("pdf_unparseable", {"failed": [c.id for c in evaluation.failed()]})
    summary.update(gate=evaluation.verdict, duplicates=duplicates)
    if not evaluation.passed:
        summary["gate_detail"] = evaluation.render()
    return summary


# ---------------------------------------------------------------------------
# 放行的公共部分
# ---------------------------------------------------------------------------


def _credential(root: Path, cp: dict[str, Any], quote: str, typed_code: Optional[str], by: str) -> str:
    if by == "policy":
        return "policy"
    if not (quote or "").strip():
        raise FlowError("放行要带上人的原话（--quote \"…\"）。没有人说过话就不要放行。")
    return cps.credential_for(root, cp, quote, typed_code)


def _pin(txn: st.Txn, stage: str, mode: str, reason: str) -> None:
    if stage not in st.STAGE_ORDER:
        raise FlowError(f"未知阶段: {stage}")
    txn.state["flow"]["pinned"][stage] = {"mode": mode, "reason": reason, "at": st.now_iso()}
    txn.log(f"pin:{stage}:{mode}", {"reason": reason})


def pin(engine: Engine, stage: str, mode: str, reason: str) -> dict[str, Any]:
    """把一个阶段退回执行卡驱动，或交还内核。要写原因，入事件流。"""
    if mode not in ("card", "kernel"):
        raise FlowError("mode 只能是 card 或 kernel")
    if not reason.strip():
        raise FlowError("要写原因（--reason）")
    with engine.txn("flow:pin") as txn:
        if not st.is_v2(txn.state):
            raise FlowError("v1 案例本来就由执行卡驱动")
        _pin(txn, stage, mode, reason)
    return {"stage": stage, "mode": mode}


def _reset_stage(txn: st.Txn, stage: str) -> None:
    entry = txn.state["stages"][stage]
    entry["status"] = "pending"
    entry["updated_at"] = st.now_iso()


def _abort(txn: st.Txn) -> None:
    txn.state["status"] = "aborted"
    txn.log("set:status", {"value": "aborted", "by": "decide"})


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def decide(
    engine: Engine,
    key: str,
    choice: str,
    quote: str,
    *,
    by: str = "human",
    typed_code: Optional[str] = None,
    to: Optional[str] = None,
    budget_tokens: Optional[float] = None,
    budget_hours: Optional[float] = None,
) -> dict[str, Any]:
    with engine.txn("flow:decide") as txn:
        state = txn.state
        if not st.is_v2(state):
            raise FlowError("v1 案例没有检查点；先迁移状态文件（flow migrate，需经用户同意）")
        cps.ensure_wait_checkpoint(txn, engine.ctx(state))
        cp = st.find_checkpoint(state, key)
        if cp is None:
            raise FlowError(f"没有检查点 {key}；用 flow status 看待决的检查点")
        if cp.get("status") != st.CHECKPOINT_PENDING or cp.get("kind") != "human":
            raise FlowError(f"检查点 {cp.get('id')} 不在待决状态")
        options = [o.get("key") for o in cp.get("options") or []]
        if choice not in options:
            raise FlowError(f"检查点 {cp['id']}（{cps.cn(cp['name'])}）的选项只有：{'、'.join(str(o) for o in options)}")
        name = cp["name"]
        if name == "final_review" and choice in ("accept", "revise", "reopen"):
            raise FlowError({"accept": "收尾用 flow accept", "revise": "定向重跑用 flow revise", "reopen": "回退用 flow reopen"}[choice])
        if by == "policy":
            allowed = name == "data_gap" and choice == "mock" and (state.get("policy") or {}).get("on_missing") == "mock"
            if not allowed:
                raise FlowError("这个检查点只能由人放行；启动时没有预先声明可以这样自动处理")
        credential = _credential(engine.root, cp, quote, typed_code, by)
        st.resolve_checkpoint_in(txn, cp, choice=choice, quote=quote, credential=credential, by=by, resume_status="running")
        ctx = engine.ctx(state)
        message = _effect(engine, txn, ctx, cp, choice, quote, to, {"budget_tokens": budget_tokens, "budget_hours": budget_hours})
        return {"checkpoint": cp["id"], "name": name, "choice": choice, "credential": credential, "status": state.get("status"), "message": message}


def _effect(engine: Engine, txn: st.Txn, ctx: Ctx, cp: dict[str, Any], choice: str, quote: str, to: Optional[str], budgets: dict[str, Any]) -> str:
    name, stage = cp["name"], cp.get("stage") or txn.state.get("current_stage")
    state = txn.state
    payload = cp.get("payload") if isinstance(cp.get("payload"), dict) else {}
    steps = engine._steps(state)
    if choice == "abort":
        _abort(txn)
        return "案例已终止"
    if choice == "pin_card":
        _pin(txn, stage, "card", f"检查点 {cp['id']} 上由人决定退回执行卡")
        return f"{STAGE_CN.get(stage, stage)}阶段已退回执行卡驱动"
    if choice == "retry":
        counters = state["counters"].setdefault("redispatch", {})
        for k in [k for k in counters if k == f"gate:{stage}" or k.startswith(f"{stage}.") or k == payload.get("step")]:
            counters.pop(k, None)
        target = payload.get("step")
        if target and target in steps and steps[target].get("status") != DONE:
            engine.redo(txn, ctx, target, "人决定再试一次", str(payload.get("detail") or payload.get("note") or ""), count=False)
        if name == "review_rounds_exhausted" and payload.get("kind"):
            kind, rnd = payload["kind"], int(payload.get("round") or 1)
            state["flow"].setdefault("round_base", {})[kind] = rnd
            state["counters"].setdefault("review_rounds", {})[kind] = rnd + 1
        return "计数已清零，继续"
    if name in REVIEW_TYPE:
        if choice == "approve":
            state["flow"].pop("modify", None)
            return "已通过，继续"
        if choice == "rollback":
            if not to:
                raise FlowError("回退要指明从哪里重做：--to <阶段或 milestone>")
            return _reopen(engine, txn, ctx, to, f"检查点 {cp['id']} 上决定回退：{quote}", kind="reopen")["message"]
        return _modify(engine, txn, ctx, cp, choice, quote)
    if name == "data_gap":
        return _decide_data_gap(engine, txn, ctx, cp, choice, quote)
    if name == "data_wait":
        if choice == "change":
            return _change_disposition(engine, txn, ctx, "改用别的处置方式")
        return _data_recheck(engine, txn, ctx, payload)
    if name == "mock_spec":
        if choice == "change":
            return _change_disposition(engine, txn, ctx, "不用 mock，改用别的处置方式")
        if choice == "edited":
            result = generate_mock(ctx)
            if result.get("errors"):
                cps.open_human(txn, ctx, "mock_spec", reason="改后的规格不合法：" + "；".join(result["errors"])[:300], stage="plan", payload=payload)
                return "规格不合法，仍在等待确认"
        return "开始 mock 试跑（这一轮不出结论）"
    if name == "trial_done":
        if choice == "wait_real":
            cps.open_human(txn, ctx, "data_wait", reason="试跑完成，等真实数据到位", stage="verify", payload={"after_trial": True, **_gap_payload(ctx)})
            return "等真实数据：补齐后执行 flow data recheck"
        return _change_disposition(engine, txn, ctx, "试跑完成后改用别的处置方式")
    if name == "feasibility_blocked":
        if choice == "experimental":
            st.set_in(txn, "reproduction_mode", "experimental")
        text = {
            "supply": "用户已补数据，按最新的数据实况重新分诊。",
            "experimental": f"用户同意切换到实验模式（市场迁移复现）：{quote}\n用本地等价数据替代缺失的数据，在 data_requirements 里标 substitute 并写明替代理由，逐条登记假设；数值不与原文对齐。",
            "degrade": f"用户接受降级复现：{quote}\n把 feasibility 改为 degraded，受影响的要素如实标注并登记假设。",
        }[choice]
        engine.redo(txn, ctx, "plan.main", "可行性阻断经人处置", text, count=False, stage="plan", role="quant-planner")
        _reset_stage_running(txn, "plan")
        return "已回派 planner 重新分诊" + ("（已切换到实验模式）" if choice == "experimental" else "")
    if name == "blocking_ambiguity":
        engine.redo(txn, ctx, "plan.main", "阻断级歧义已由人裁决", f"用户的裁决：{quote}\n据此把对应歧义的状态改为 resolved，并登记假设（来源写「人工裁决」）。", count=False, stage="plan", role="quant-planner")
        _reset_stage_running(txn, "plan")
        return "已回派 planner 落实裁决"
    if name == "iterate_blocked":
        n = int(payload.get("round") or (state.get("iteration") or {}).get("current") or 0)
        outcome = "next" if choice == "continue" else "exhausted"
        engine._mark_kernel(txn, f"iterate.close.r{n}@g{ctx.generation}", {"outcome": outcome, "by": "human"})
        return "继续下一轮" if choice == "continue" else "按部分达标收尾（先补归因）"
    if name == "critical_dispute":
        return _decide_dispute(engine, txn, ctx, cp, choice, quote)
    if name == "tamper":
        state["ext"]["tamper_ack"] = {"signature": payload.get("signature"), "at": st.now_iso(), "checkpoint": cp["id"]}
        return "已记录，继续"
    if name == "budget":
        if choice == "raise":
            if not budgets.get("budget_tokens") and not budgets.get("budget_hours"):
                raise FlowError("提高预算要给出新值：--budget-tokens 或 --budget-hours")
            for k, v in budgets.items():
                if v:
                    state["policy"][k] = v
        else:
            state["policy"]["budget_tokens"] = None
            state["policy"]["budget_hours"] = None
        state["ext"].pop("budget_ack", None)
        return "预算已更新，继续"
    if name == "stall":
        txn.log("stall:resumed", {"steps": payload.get("steps")})
    return "继续"


def _reset_stage_running(txn: st.Txn, stage: str) -> None:
    if txn.state["stages"][stage]["status"] in ("done", "skipped", "failed", "blocked"):
        st.set_stage_in(txn, stage, "running")


def _modify(engine: Engine, txn: st.Txn, ctx: Ctx, cp: dict[str, Any], choice: str, quote: str) -> str:
    """检查点上的「修改后继续」：口述的交给属主角色去改；人自己改了文件的重新核对。之后重跑所属阶段的门禁，并回到同一个检查点。"""
    name, stage = cp["name"], str(cp.get("stage"))
    payload = cp.get("payload") if isinstance(cp.get("payload"), dict) else {}
    rounds = txn.state["counters"].setdefault("modify", {})
    key = f"{name}:{stage}:{payload.get('milestone') or ''}"
    if int(rounds.get(key) or 0) >= MODIFY_ROUND_LIMIT:
        raise FlowError(f"这个检查点已经修改过 {MODIFY_ROUND_LIMIT} 轮；请选择通过、回退或终止")
    rounds[key] = int(rounds.get(key) or 0) + 1
    txn.state["flow"]["modify"] = {"stage": stage, "checkpoint": name, "milestone": payload.get("milestone")}
    _reset_stage_running(txn, stage)
    if stage in ("plan", "spec_audit") and ctx.exists(f"{ctx.ws}/plan.md"):
        ks.seed_plan(txn, ctx)
    mid = payload.get("milestone")
    if choice == "modify":
        role = MODIFY_ROLE.get(name) or STAGE_OWNER.get(stage, "general-purpose")
        engine.redo(txn, ctx, f"{stage}.modify", "人在检查点要求修改", quote, count=False, stage=stage, role=role)
        engine._steps(txn.state)[f"{stage}.modify"]["milestone"] = mid or "all"
    if name == "milestone_done" and mid:
        st.milestone_in(txn, mid, "verify", "pending")
        if engine._steps(txn.state).get(f"implement.{mid}.verify"):
            engine.redo(txn, ctx, f"implement.{mid}.verify", "修改后重新验证", count=False)
    if name == "verify_done":
        engine.redo(txn, ctx, "verify.main", "修改后重新验证", quote if choice == "modify" else "人直接改了文件，整批重出验证产物。", count=False, stage="verify", role="quant-verifier")
        engine._steps(txn.state).pop(f"{stage}.modify", None)
    return "已交给负责的角色修改；改完会重跑门禁并回到这个检查点" if choice == "modify" else "将重新核对你改过的文件；过门禁后回到这个检查点"


def _change_disposition(engine: Engine, txn: st.Txn, ctx: Ctx, reason: str) -> str:
    """换一种处置方式：正在试跑的先结束试跑、回到 plan 起点（试跑的编码与结果归档），再回到缺口处置检查点。"""
    was_trial = ctx.trial
    _trial_off(txn, ctx)
    if was_trial and txn.state["stages"]["plan"]["status"] == "done":
        _reopen(engine, txn, ctx, "plan", reason, kind="reopen", keep_status=True)
    else:
        _reset_stage_running(txn, "plan")
    _reopen_gaps(engine, txn, ctx)
    cps.open_human(txn, ctx, "data_gap", reason=reason, stage="plan", payload=_gap_payload(ctx))
    return "请重新选择处置方式" if not was_trial else "已结束试跑，请重新选择处置方式"


def _reopen_gaps(engine: Engine, txn: st.Txn, ctx: Ctx) -> None:
    """把缺口上已有的处置决定清掉（人要重新选）。"""
    from . import datacheck

    datacheck.clear_dispositions(engine.root, engine.report_id, reason="人决定改用别的处置方式")


def _gap_payload(ctx: Ctx) -> dict[str, Any]:
    from . import datacheck

    result = datacheck.load_check(ctx.root, ctx.report_id) or {}
    gaps = [r for r in result.get("requirements") or [] if r.get("result") in ("partial", "missing")]
    return {"gaps": [g.get("name") for g in gaps], "gap_report": datacheck.render_gap_report(result) if result else ""}


def _trial_off(txn: st.Txn, ctx: Ctx) -> None:
    marker = ctx.path(f"{ctx.ws}/data_mock/ACTIVE")
    if marker.is_file():
        marker.unlink()
    trial = txn.state["ext"].get("trial") or {}
    if trial.get("active"):
        trial.update(active=False, ended_at=st.now_iso())
        txn.state["ext"]["trial"] = trial
        txn.log("trial:off", None)


def _decide_data_gap(engine: Engine, txn: st.Txn, ctx: Ctx, cp: dict[str, Any], choice: str, quote: str) -> str:
    from . import datacheck

    state = txn.state
    payload = cp.get("payload") if isinstance(cp.get("payload"), dict) else {}
    names = payload.get("gaps")
    result = datacheck.set_disposition(engine.root, engine.report_id, names, choice, checkpoint=cp["id"], note=quote)
    txn.log(f"data:disposition:{choice}", {"gaps": names, "checkpoint": cp["id"]})
    report = payload.get("gap_report") or datacheck.render_gap_report(result)
    if choice == "supply":
        cps.open_human(txn, ctx, "data_wait", reason="等你把数据补齐", stage="plan", payload={"gaps": names, "gap_report": report})
        return "已暂停等数据；补齐后执行 flow data recheck"
    if choice == "mock":
        state["ext"]["trial"] = {"active": True, "since": st.now_iso(), "checkpoint": cp["id"], "gaps": names}
        txn.log("trial:on", {"gaps": names})
        _reset_stage_running(txn, "plan")
        if "plan.mock_spec" in engine._steps(state):  # 之前起草过又取消了：按现在的缺口重新起草
            engine.redo(txn, ctx, "plan.mock_spec", "重新进入 mock 试跑", "按最新的数据体检结果重新核对规格；已有的 spec.yaml 可以在原基础上改。", count=False)
        return "转入 mock 试跑：先由 planner 起草 mock 规格，这一轮不出结论"
    instructions = {
        "substitute": "用户决定用本地等价数据替代缺失的数据。在 data_requirements 里把对应条目改为 substitute 并写明替代文件与理由，登记假设（影响面 data）。",
        "narrow": "用户决定缩小范围：只在有数据的区间或标的上复现。相应修改回测区间或标的池，登记假设（影响面 data），受影响的指标如实说明。",
        "drop": "用户决定砍掉依赖缺失数据的要素：把这些要素在覆盖矩阵里标为 infeasible，状态理由写 data_missing: <一句话>；core 级要素同时登记假设。"
        "data_requirements 里对应的条目保留、名称不要改，status 改为 missing 并在 note 里写明「已决定砍掉相关要素」。",
    }
    if choice == "substitute" and state.get("reproduction_mode") != "experimental":
        st.set_in(txn, "reproduction_mode", "experimental")
        engine.note("等价替代在 strict 模式下不成立，已随这次决定切换到实验模式（数值判定豁免，报告显著声明）")
    engine.redo(txn, ctx, "plan.main", f"数据缺口处置：{dict(cps.HUMAN['data_gap'][2])[choice].split('：')[0]}", f"{instructions[choice]}\n\n用户原话：{quote}\n\n{report}", count=False, stage="plan", role="quant-planner")
    _reset_stage_running(txn, "plan")
    return "已回派 planner 按处置决定修订计划"


def _data_recheck(engine: Engine, txn: st.Txn, ctx: Ctx, payload: dict[str, Any]) -> str:
    """数据补齐后的重检。通过就继续；试跑之后的重检还要把验证标为过期。"""
    from . import datacheck

    probe = datacheck.run_probe(engine.root, None, use_cache=False)
    if not probe.get("error"):
        datacheck.save_probe(engine.root, probe)
    result = datacheck.check_requirements(engine.root, engine.report_id, probe=None if probe.get("error") else probe)
    names = set(payload.get("gaps") or [])
    still = [r for r in result.get("requirements") or [] if r.get("result") in ("partial", "missing") and (not names or r.get("name") in names) and r.get("status_plan") != "substitute"]
    if still:
        report = datacheck.render_gap_report(result, only_open=False)
        cps.open_human(txn, ctx, "data_wait", reason=f"重检后仍有 {len(still)} 处缺口", stage=str(payload.get("stage") or "plan"), payload={**payload, "gap_report": report})
        return "重检未通过，仍在等数据"
    datacheck.save_check(engine.root, engine.report_id, result)
    txn.log("data:recheck", {"ok": True, "gaps": sorted(names)})
    if payload.get("after_trial") or ctx.trial:
        stale = _schema_drift(ctx, probe)
        _trial_off(txn, ctx)
        if stale:
            _reopen(engine, txn, ctx, "implement", "真实数据的结构与 mock 规格不一致：" + "；".join(stale)[:300], kind="reopen", keep_status=True)
            return "真实数据到位，但结构与 mock 不一致，编码一并重做"
        _reopen(engine, txn, ctx, "verify", "真实数据到位，重跑验证", kind="reopen", keep_status=True)
        return "真实数据到位，结构与 mock 一致，只重跑验证"
    _reset_stage_running(txn, "plan")
    for key in [k for k in engine._steps(txn.state) if k.startswith("plan.datacheck@")]:
        del engine._steps(txn.state)[key]
    return "数据已齐，继续"


def _schema_drift(ctx: Ctx, probe: Optional[dict[str, Any]] = None) -> list[str]:
    """真实文件与 mock 的列是否一致（只比列名：mock 有而真实文件没有的列）。"""
    from . import datacheck

    manifest = read_json(ctx.path(f"{ctx.ws}/data_mock/manifest.json")) or {}
    probe = probe or datacheck.load_probe(ctx.root) or {}
    out: list[str] = []
    for table in manifest.get("tables") or []:
        if not isinstance(table, dict):
            continue
        entry = (probe.get("files") or {}).get(str(table.get("name"))) or {}
        real = {c.get("name") if isinstance(c, dict) else c for c in entry.get("columns") or []}
        mock = set(table.get("columns") or [])
        if real and mock - real:
            out.append(f"{table.get('name')} 缺列 {sorted(mock - real)}")
    return out


def _decide_dispute(engine: Engine, txn: st.Txn, ctx: Ctx, cp: dict[str, Any], choice: str, quote: str) -> str:
    from . import extreview

    payload = cp.get("payload") or {}
    kind, fid, stage = payload.get("kind"), payload.get("id"), str(cp.get("stage"))
    rnd = sp.review_round(ctx, kind)
    if choice == "waive":
        extreview.write_responses(engine.root, engine.report_id, kind, {fid: {"处置": "rejected", "回应": f"人工裁定意见不成立（{cp['id']}）：{quote}"[:500], "复核": "pass"}})
        return f"{fid} 经人工裁定不成立"
    extreview.write_responses(engine.root, engine.report_id, kind, {fid: {"处置": "accepted", "回应": f"人工裁定意见成立（{cp['id']}），须修复"}})
    owner = payload.get("owner") if payload.get("owner") in sp.REVIEW_OWNERS[kind] else sp.REVIEW_OWNERS[kind][0]  # 答卷里写了合法属主就用它
    bucket = txn.state["flow"].setdefault("dispute_fixes", {}).setdefault(f"{stage}.r{rnd}", {})
    bucket.setdefault(owner, []).append({"id": fid, "severity": "critical", "title": payload.get("title"), "location": payload.get("location"), "detail": "", "reply": f"人工裁定成立：{quote}"[:300]})
    return f"{fid} 维持，交给 {owner} 修复"


# ---------------------------------------------------------------------------
# accept
# ---------------------------------------------------------------------------


def accept(engine: Engine, quote: str, typed_code: Optional[str] = None) -> dict[str, Any]:
    with engine.txn("flow:accept") as txn:
        state = txn.state
        if not st.is_v2(state):
            raise FlowError("v1 案例的收尾仍按执行卡做；要用 flow accept 请先迁移状态文件")
        cps.ensure_wait_checkpoint(txn, engine.ctx(state))
        cp = next((c for c in st.pending_checkpoints(state) if c.get("name") == "final_review"), None)
        if state.get("status") != "awaiting_review" or cp is None:
            raise FlowError("案例不在最终评审；只有报告出完、等待评审时才能收尾")
        credential = _credential(engine.root, cp, quote, typed_code, "human")
        st.resolve_checkpoint_in(txn, cp, choice="accept", quote=quote, credential=credential, by="human", resume_status=None)
        st.set_stage_in(txn, "review", "done")
        final = "done_partial" if (state.get("verdict") or {}).get("result") == "partial" else "done"
        state["status"] = final
        state["pending_question"] = None
        txn.log("accept", {"status": final, "credential": credential})
        return {"status": final, "credential": credential}


# ---------------------------------------------------------------------------
# reopen / revise
# ---------------------------------------------------------------------------


def _dependents(ctx: Ctx, roots: list[str]) -> list[str]:
    """这些 milestone 以及依赖它们的 milestone（沿 deps 传递）。"""
    wanted = set(roots)
    changed = True
    while changed:
        changed = False
        for m in ctx.milestones:
            if m["id"] not in wanted and wanted & set(m.get("deps") or []):
                wanted.add(m["id"])
                changed = True
    return [m["id"] for m in ctx.milestones if m["id"] in wanted]


def _reopen(
    engine: Engine,
    txn: st.Txn,
    ctx: Ctx,
    start: str,
    reason: str,
    *,
    kind: str = "reopen",
    stages: Optional[list[str]] = None,
    milestones: Optional[list[str]] = None,
    extra: Optional[dict[str, Any]] = None,
    notes: Optional[str] = None,
    keep_status: bool = False,
) -> dict[str, Any]:
    """从某个阶段或 milestone 起重做：重开代次加一，受影响阶段回到未开始，旧的步骤记录与产物归档不删。"""
    state = txn.state
    flow = state["flow"]
    if re.fullmatch(r"m\d+", start):
        if ctx.milestone(start) is None:
            raise FlowError(f"没有 milestone {start}")
        milestones = _dependents(ctx, [start])
        start_stage = "implement"
    elif start in st.STAGE_ORDER and start != "init":
        start_stage = start
    else:
        raise FlowError(f"不能从 {start} 重开；给阶段名（extract 之后的任一阶段）或 milestone 编号")
    index = st.STAGE_ORDER.index(start_stage)
    stages = stages or [s for s in st.STAGE_ORDER[index:]]
    if "implement" in stages and milestones is None:
        milestones = [m["id"] for m in ctx.milestones]  # 从编码或更早的阶段重开：全部 milestone 重做
    milestones = milestones or []
    old_gen = int(flow.get("generation") or 0)
    steps = engine._steps(state)
    affected = {sid: rec for sid, rec in steps.items() if rec.get("stage") in stages or sid.split(".")[0] in stages}
    archive_dir = ctx.path(f"{ctx.ws}/flow/archive/gen_{old_gen}")
    write_json(archive_dir / "steps.json", {"reason": reason, "kind": kind, "at": st.now_iso(), "stages": stages, "milestones": milestones, "steps": affected})
    for rel in (f"output/{ctx.report_id}/results/comparison.json", f"output/{ctx.report_id}/results/metrics.json", f"output/{ctx.report_id}/verify_report.md", f"{ctx.ws}/final_report.md"):
        source = ctx.path(rel)
        if source.is_file():
            shutil.copy2(source, archive_dir / Path(rel).name)
    for sid in affected:
        del steps[sid]
    flow["inflight"] = [sid for sid in flow.get("inflight") or [] if sid not in affected]
    for stage in stages:
        _reset_stage(txn, stage)
    for mid in milestones:
        m = ctx.milestone(mid)
        if m is not None:
            m.update(implement="pending", code_review="pending", verify="pending")
    if "iterate" in stages:
        iterations = ctx.path(f"{ctx.ws}/iterations")
        if iterations.is_dir() and any(iterations.iterdir()):
            shutil.move(str(iterations), str(archive_dir / "iterations"))
            iterations.mkdir(parents=True, exist_ok=True)
        state["iteration"]["current"] = 0
    counters = state["counters"]
    for k in [k for k in counters.get("redispatch") or {} if k.split(":")[-1].split(".")[0] in stages or k.split(".")[0] in stages]:
        counters["redispatch"].pop(k, None)
    counters["modify"] = {}
    rounds = counters.setdefault("review_rounds", {})
    base: dict[str, int] = {}
    for stage, review_kind in sp.REVIEW_KIND.items():
        if stage in stages and ctx.exists(f"{ctx.ws}/audit/{review_kind}_audit_external.md"):
            base[review_kind] = int(rounds.get(review_kind) or 1)
            rounds[review_kind] = base[review_kind] + 1  # 重开后的外审从下一轮续编，走差量复审
    flow["round_base"] = {**(flow.get("round_base") or {}), **base}
    flow["generation"] = old_gen + 1
    notes_file = None
    if notes:
        notes_file = f"{ctx.ws}/flow/reopen/gen_{old_gen + 1}.md"
        write_text(ctx.path(notes_file), notes)
    flow["reopen"] = {"gen": old_gen + 1, "kind": kind, "reason": reason, "from": start, "stages": stages, "milestones": milestones, "notes_file": notes_file, "round_base": base, **(extra or {})}
    flow.pop("modify", None)
    state["current_stage"] = stages[0]
    if not keep_status:
        state["status"] = "running"
        state["pending_question"] = None
    txn.log(f"reopen:{kind}", {"from": start, "stages": stages, "milestones": milestones, "generation": old_gen + 1, "reason": reason[:300]})
    message = f"已重开：从{STAGE_CN.get(start_stage, start_stage)}起重做" + (f"（milestone {'、'.join(milestones)}）" if milestones and start_stage == "implement" else "") + f"，共 {len(stages)} 个阶段，重开代次 {old_gen + 1}"
    return {"message": message, "stages": stages, "milestones": milestones, "generation": old_gen + 1}


def _resolve_review_for(engine: Engine, txn: st.Txn, choice: str, quote: str, typed_code: Optional[str]) -> str:
    """revise / reopen 作为等待态的出口：把待决的检查点按这次决定关掉。运行中的案例不需要。"""
    state = txn.state
    cps.ensure_wait_checkpoint(txn, engine.ctx(state))
    pending = st.pending_checkpoints(state)
    if state.get("status") in st.TERMINAL_STATUSES:
        if not (quote or "").strip():
            raise FlowError("重开已收尾的案例要带上人的原话（--quote）")
        txn.log("reopen:from_terminal", {"status": state.get("status"), "quote": quote[:300]})
        return "self_report"
    credential = "self_report"
    for cp in pending:
        credential = _credential(engine.root, cp, quote, typed_code, "human")
        st.resolve_checkpoint_in(txn, cp, choice=choice, quote=quote, credential=credential, by="human", resume_status=None)
    if pending or state.get("status") in st.WAITING_STATUSES:
        return credential
    if not (quote or "").strip():
        raise FlowError("回退重开是人的决定，要带上人的原话（--quote）")
    return credential


def reopen(engine: Engine, start: str, reason: str, quote: str, typed_code: Optional[str] = None, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "stale": stale_report(engine), "note": "只报告，不执行；去掉 --dry-run 才会重开"}
    with engine.txn("flow:reopen") as txn:
        if not st.is_v2(txn.state):
            raise FlowError("v1 案例不支持回退重开；先迁移状态文件")
        credential = _resolve_review_for(engine, txn, "reopen", quote, typed_code)
        result = _reopen(engine, txn, engine.ctx(txn.state), start, reason or quote, kind="reopen")
        return {**result, "credential": credential}


def _excel_plan(engine: Engine, xlsx: Optional[str], dry_run: bool) -> dict[str, Any]:
    args = [sys.executable, str(PLUGIN_ROOT / "tools" / "assumptions_xlsx.py"), "apply", engine.report_id]
    args += ["--xlsx", xlsx] if xlsx else []
    args += ["--dry-run"] if dry_run else []
    proc = subprocess.run(args, capture_output=True, text=True, env=dict(os.environ, REPORT_REPRODUCE_ROOT=str(engine.root)), cwd=str(engine.root))
    try:
        plan = json.loads(proc.stdout)
    except ValueError as exc:
        raise FlowError(f"读不出 Excel 回改的计划：{(proc.stderr or proc.stdout).strip()[:400]}") from exc
    if not isinstance(plan, dict) or plan.get("error"):
        raise FlowError(str((plan or {}).get("error") or "Excel 回改失败"))
    return plan


def revise(
    engine: Engine,
    *,
    assumption: Optional[str] = None,
    text: Optional[str] = None,
    from_excel: bool = False,
    xlsx: Optional[str] = None,
    dry_run: bool = False,
    quote: str = "",
    typed_code: Optional[str] = None,
) -> dict[str, Any]:
    """按假设修订定向重跑。单条：给假设编号和新口径；批量：读回 Excel。不占迭代轮数，最多 3 轮。"""
    ctx = engine.ctx()
    if not st.is_v2(ctx.state):
        raise FlowError("v1 案例的 revise 仍按执行卡做；要用 flow revise 请先迁移状态文件")
    revisions: list[dict[str, Any]] = []
    config_edits: list[dict[str, Any]] = []
    if from_excel:
        plan = _excel_plan(engine, xlsx, dry_run=True)
        revisions = list(plan.get("text_revisions") or [])
        config_edits = list(plan.get("config_edits") or [])
        scope = plan.get("merged_impact_scope") or "data"
        milestones = list(plan.get("milestones_affected") or [])
        rejected = plan.get("rejected") or []
        if not revisions and not config_edits:
            raise FlowError("工作表里没有生效的修订（「操作」列要选 revise，且新值或新口径至少填一个）" + (f"；被拒的行：{rejected}" if rejected else ""))
    else:
        if not assumption or not (text or "").strip():
            raise FlowError("单条修订要给 --assumption <编号> 和 --new-text \"<新口径>\"；批量修订用 --from-excel")
        docs = packs.CaseDocs.load(engine.root, engine.report_id)
        block = docs.assumption(assumption)
        if block is None:
            raise FlowError(f"假设登记簿里没有 {assumption}")
        impact = (block.field("影响面").value.strip() if block.field("影响面") else "")
        scope = impact_scope(impact)
        fld = block.field("影响 milestone")
        milestones = ms.extract_milestones(fld.value) if fld else []
        revisions = [{"as_id": assumption, "title": block.title, "new_text": text.strip(), "impact": scope, "milestones": milestones}]
        rejected = []
    if scope not in REVISE_STAGES:
        scope = "data"
    all_ids = [m["id"] for m in ctx.milestones]
    targets = _dependents(ctx, [m for m in milestones if m in all_ids]) if scope in ("data", "method") else []
    if scope in ("data", "method") and not targets:
        targets = all_ids  # 归属不明时全部重做，宁多勿漏
    stages = REVISE_STAGES[scope]
    preview = {
        "scope": scope,
        "stages": stages,
        "milestones": targets,
        "text_revisions": [{"as_id": r["as_id"], "new_text": r["new_text"]} for r in revisions],
        "config_edits": config_edits,
        "rejected": rejected,
    }
    if dry_run:
        return {"dry_run": True, **preview}

    used = int(((ctx.state.get("counters") or {}).get("revise")) or 0)
    if used >= REVISE_ROUND_LIMIT:
        raise FlowError(f"这个案例已经 revise 过 {used} 轮（上限 {REVISE_ROUND_LIMIT}）；还要改请用 flow reopen 回退重做")
    applied: dict[str, Any] = {}
    if from_excel:
        applied = _excel_plan(engine, xlsx, dry_run=False)  # 参数直改由工具确定性落地（注入 config.py 并追记登记簿）
        revisions = list(applied.get("text_revisions") or [])
    notes = ["这一轮是按假设修订的定向重跑，只处理下面列出的修订，其余口径保持不变。", ""]
    notes += [f"- **{r['as_id']}**（{r.get('title', '')}）新口径：{r['new_text']}" for r in revisions]
    notes += [f"- **{e['as_id']}** 参数 `{e['field']}`：{e['old']} → {e['new']}（已由工具写入 config.py）" for e in applied.get("applied_config_edits") or []]
    notes += [f"- 以下条目工具写入失败，需要手工落实：{json.dumps(applied['config_edits_degraded'], ensure_ascii=False)}"] if applied.get("config_edits_degraded") else []
    with engine.txn("flow:revise") as txn:
        credential = _resolve_review_for(engine, txn, "revise", quote, typed_code)
        inner = engine.ctx(txn.state)
        txn.state["counters"]["revise"] = used + 1
        result = _reopen(
            engine,
            txn,
            inner,
            stages[0],
            f"revise：{'、'.join(sorted({r['as_id'] for r in revisions} | {e['as_id'] for e in config_edits}))}",
            kind="revise",
            stages=stages,
            milestones=targets,
            notes="\n".join(notes) + "\n",
            extra={"scope": scope, "text_revisions": bool(revisions), "needs_coder": bool(revisions) and scope in ("param", "trading")},
        )
        history = list((txn.state.get("iteration") or {}).get("history") or [])
        history.append({"round": used + 1, "trigger": "revise", "scope": scope, "assumptions": sorted({r["as_id"] for r in revisions} | {e["as_id"] for e in config_edits}), "at": st.now_iso()})
        st.set_in(txn, "iteration.history", history, log=False)
        txn.log("revise", {"scope": scope, "milestones": targets, "round": used + 1, "credential": credential})
    return {**preview, **result, "credential": credential, "round": used + 1}


# ---------------------------------------------------------------------------
# 失效标注
# ---------------------------------------------------------------------------


def stale_report(engine: Engine) -> dict[str, Any]:
    """哪些已完成的步骤消费过的内容后来变了。只报告，不改任何东西。

    依据：每步派发时写下的清单（消费了哪些片、各片的哈希）。现在按同样的角色与步骤重新切一次，逐片比哈希；
    另外比对验证、内审步骤做完时记下的 src 指纹。
    """
    ctx = engine.ctx()
    try:
        docs = packs.CaseDocs.load(engine.root, engine.report_id)
    except packs.PackError:
        docs = None
    current_src = src_fingerprint(engine.root, engine.report_id)
    stale: list[dict[str, Any]] = []
    for sid, rec in ctx.steps.items():
        if rec.get("status") != DONE or rec.get("kind") == "kernel":
            continue
        manifest = read_json(ctx.path(rec.get("manifest") or "")) or {}
        changed = ks.pack_drift(ctx, manifest, docs) if docs is not None else []
        if rec.get("src_sha") and current_src and rec["src_sha"] != current_src:
            changed.append("src（代码在这一步派出之后改过）")
        changed += [f"{rel}（代码在这一步派出之后改过）" for rel in ks.src_files_drift(ctx, rec.get("src_files"))]
        if changed:
            own = [c for c in changed if _own_change(docs, rec.get("milestone"), c)]
            stale.append(
                {
                    "step": sid,
                    "stage": rec.get("stage"),
                    "milestone": rec.get("milestone"),
                    "changed": changed[:20],
                    "more": max(len(changed) - 20, 0),
                    # 只有对照用的上下文变了（比如内审带着全部因子定义，变的是别的 milestone 的因子）
                    "context_only": not own,
                }
            )
    order = {s: i for i, s in enumerate(st.STAGE_ORDER)}
    stale.sort(key=lambda item: (order.get(str(item["stage"]), 99), str(item["step"])))
    suggestion = None
    direct = [item for item in stale if not item["context_only"]] or stale
    if direct:
        first = direct[0]
        suggestion = first["milestone"] if first["stage"] == "implement" and first.get("milestone") not in (None, "all") else first["stage"]
    return {"stale": stale, "reopen_from": suggestion, "src_fingerprint": current_src}


def _own_change(docs: Any, milestone: Any, change: str) -> bool:
    """这处变更是不是这一步自己交付的内容，而不是为了对照才带上的全量上下文。

    内审的包里带着全部因子定义和全部假设：别的 milestone 的要素变了，它的清单也会对不上，
    但那不是重做这个 milestone 的理由。重入点的建议只看「自己的」变更。
    """
    if docs is None or milestone in (None, "all"):
        return True
    kind, _, name = change.partition(":")
    name = name.split("（")[0]
    try:
        if kind.startswith("element"):
            return name in docs.step_elements(str(milestone))
        if kind.startswith("assumption"):
            block = docs.assumption(name)
            owners = docs.assumption_owners(block) if block is not None else []
            return not owners or str(milestone) in owners
    except Exception:  # noqa: BLE001 - 归属算不出来就按自己的算，宁多勿漏
        return True
    return True


# ---------------------------------------------------------------------------
# 假 FAIL 复跑 / 取块 / fork
# ---------------------------------------------------------------------------


def rerun_false_fail(engine: Engine, raw_step: str, reason: str) -> dict[str, Any]:
    """流水线干扰造成的假 FAIL：验证期间确有别的 milestone 在编码时，允许不计次数地重跑一次验证。"""
    from .core import step_key

    sid = step_key(raw_step)
    with engine.txn("flow:rerun") as txn:
        ctx = engine.ctx(txn.state)
        steps = engine._steps(txn.state)
        rec = steps.get(sid) or {}
        mid = rec.get("milestone")
        if not (sid.startswith("implement.") and sid.endswith(".verify")) or not mid:
            raise FlowError("只有 milestone 级验证可以按假 FAIL 复跑")
        used = txn.state["counters"].setdefault("false_fail", {})
        if int(used.get(mid) or 0) >= 1:
            raise FlowError(f"{mid} 已经按假 FAIL 复跑过一次；这次按真实失败处理")
        records = st.read_event_records(engine.root, engine.report_id)
        mine = _step_spans(records, sid)
        window = mine[-1] if mine else None
        overlapping = sorted(
            other
            for other, orec in steps.items()
            if window is not None and other.endswith(".code") and orec.get("milestone") != mid
            and any(a < window[1] and b > window[0] for a, b in _step_spans(records, other))
        )
        if not overlapping:
            raise FlowError(f"{sid} 验证期间没有别的 milestone 在编码，不符合假 FAIL 的条件；按真实失败处理")
        code = steps.get(f"implement.{mid}.code") or {}
        if code.get("status") in (REDO, INFLIGHT) and (code.get("redo") or code.get("reason")):
            code.update(status=DONE)
            code.pop("redo", None)
            if f"implement.{mid}.code" in txn.state["flow"]["inflight"]:
                txn.state["flow"]["inflight"].remove(f"implement.{mid}.code")
            txn.state["counters"].setdefault("redispatch", {}).pop(f"implement.{mid}.code", None)
            st.milestone_in(txn, mid, "implement", "done")
        used[mid] = 1
        engine.redo(txn, ctx, sid, "按假 FAIL 复跑（验证期间有别的 milestone 在改代码）", reason, count=False)
        cps.record_auto(txn, "false_fail_rerun", reason=f"{sid}：{reason}", stage="implement", payload={"step": sid, "overlapping": overlapping})
        return {"step": sid, "overlapping": overlapping}


def _step_spans(records: list[dict[str, Any]], sid: str) -> list[tuple[int, int]]:
    """一个步骤每次派发在事件流里占的区间（派出那条事件的序号, 收回那条的序号）；还在途的右端取事件流末尾。"""
    spans: list[tuple[int, int]] = []
    start: Optional[int] = None
    for index, record in enumerate(records):
        event = record.get("event")
        if event == f"step:{sid}:issued":
            start = index
        elif start is not None and event in (f"step:{sid}:done", f"step:{sid}:failed", f"step:{sid}:redo"):
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(records)))
    return spans


def get_block(engine: Engine, kind: str, key: str, step: Optional[str]) -> str:
    """子 agent 的逃生门：取一个要素块、一条假设或一行矩阵的原文。每次调用记事件。"""
    docs = packs.CaseDocs.load(engine.root, engine.report_id)
    segment = packs.get_block(docs, kind, key)
    try:
        with engine.txn("flow:get") as txn:
            if st.is_v2(txn.state):
                txn.log("pack:get", {"kind": kind, "key": key, "step": step, "bytes": segment.nbytes})
    except (st.StateLockTimeout, st.StateValidationError):
        pass  # 记不上事件不该让子 agent 拿不到内容
    return segment.text


_FORK_TEXT_SUFFIXES = {".md", ".json", ".py", ".yaml", ".yml", ".txt"}


def fork(root: Path, source: str, new_id: str, start: str, host: Optional[str] = None) -> dict[str, Any]:
    """把一个案例复制成新编号，并回退到指定阶段的起点（对照回归用）。源案例不动。

    从 implement 起点 fork 时，把终态文书退回编码前的样子：清空矩阵的实现位置与验证结果、
    去掉编码与迭代阶段追加的假设、把「验证后回看」复位成占位符，src 清空。这样的起点带着首跑的
    后见之明，对比派发次数会偏乐观。
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", new_id):
        raise FlowError("新编号要用小写字母开头，只含小写字母、数字和下划线")
    if st.state_path(root, new_id).exists() or (root / "workspace" / new_id).exists():
        raise FlowError(f"{new_id} 已经存在")
    if start not in st.STAGE_ORDER or start in ("init", "review"):
        raise FlowError("起点要给阶段名（extract … report）")
    src_ws, dst_ws = root / "workspace" / source, root / "workspace" / new_id
    if not (src_ws / "state.json").is_file():
        raise FlowError(f"没有案例 {source}")
    ignore = shutil.ignore_patterns("flow", "reviews", "board.html", "events.jsonl", "state.v1.json", ".state.lock", "checkpoints", "__pycache__", "*.pkl", "*.parquet", "*.ndjson")
    shutil.copytree(src_ws, dst_ws, ignore=ignore)
    for path in dst_ws.rglob("*"):
        if path.is_file() and path.suffix in _FORK_TEXT_SUFFIXES and path.name != "state.json":
            text = path.read_text(encoding="utf-8", errors="replace")
            if source in text:
                path.write_text(text.replace(source, new_id), encoding="utf-8")
    old = json.loads((src_ws / "state.json").read_text(encoding="utf-8"))
    (dst_ws / "state.json").unlink()
    st.init_state(root, new_id, str(old.get("pdf_path")), mode=str(old.get("mode") or "auto"), max_iter=old.get("max_iter"), reproduction_mode=str(old.get("reproduction_mode") or "strict"), schema_version=st.SCHEMA_VERSION_V2)
    index = st.STAGE_ORDER.index(start)
    engine = Engine(root, new_id, host)
    with engine.txn("flow:fork") as txn:
        state = txn.state
        state["flow"]["driver"] = "kernel"
        state["ext"].update({"created_by": "fork", "forked_from": source, "fork_start": start})
        for key in ("type", "tags", "difficulty", "difficulty_override", "feasibility", "pdf_pages"):
            state[key] = old.get(key)
        for stage in st.STAGE_ORDER[:index]:
            state["stages"][stage].update(status="done" if (old.get("stages") or {}).get(stage, {}).get("status") != "skipped" else "skipped", updated_at=st.now_iso())
        state["current_stage"] = start
        state["external_reviews"] = [r for r in old.get("external_reviews") or [] if isinstance(r, dict) and st.STAGE_ORDER.index({"spec": "spec_audit", "code": "code_audit", "result": "result_audit"}.get(str(r.get("checkpoint")), "review")) < index]
        after_implement = index > st.STAGE_ORDER.index("implement")
        if index > st.STAGE_ORDER.index("plan"):
            state["milestones"] = [
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "deps": m.get("deps") or [],
                    **({k: m.get(k) or "pending" for k in ("implement", "code_review", "verify")} if after_implement else {"implement": "pending", "code_review": "pending", "verify": "pending"}),
                }
                for m in old.get("milestones") or []
                if isinstance(m, dict)
            ]
            max_iter = (old.get("iteration") or {}).get("max")
            state["iteration"]["max"] = max_iter
        if index > st.STAGE_ORDER.index("iterate"):
            # 验证与迭代都不重做：结论、迭代记录照搬
            state["verdict"] = old.get("verdict") or state["verdict"]
            state["iteration"] = old.get("iteration") or state["iteration"]
        txn.log("fork", {"from": source, "start": start})
    cleaned: dict[str, Any] = {}
    if start == "implement":
        cleaned = _rewind_docs_to_implement(root, new_id)
    copied: list[str] = []
    if index > st.STAGE_ORDER.index("implement"):
        copied += _fork_tree(root / "src" / source, root / "src" / new_id, source, new_id)
    if index > st.STAGE_ORDER.index("verify"):
        copied += _fork_tree(root / "output" / source, root / "output" / new_id, source, new_id)
    (root / "src" / new_id).mkdir(parents=True, exist_ok=True)
    return {"report_id": new_id, "from": source, "start": start, "cleaned": cleaned, "copied": copied}


def _fork_tree(src: Path, dst: Path, source: str, new_id: str) -> list[str]:
    """把代码或产物目录照搬到新编号下，文本文件里的旧编号一并替换。源目录不存在就什么都不做。"""
    if not src.is_dir() or (dst.is_dir() and any(p.is_file() for p in dst.rglob("*"))):
        return []
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), dirs_exist_ok=True)
    for path in dst.rglob("*"):
        if path.is_file() and path.suffix in _FORK_TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if source in text:
                stamp = path.stat().st_mtime
                path.write_text(text.replace(source, new_id), encoding="utf-8")
                os.utime(path, (stamp, stamp))  # 不动文件时间：验证门禁按时间判断产物是否新于代码
    return [str(dst)]


def _rewind_docs_to_implement(root: Path, report_id: str) -> dict[str, Any]:
    ws = root / "workspace" / report_id
    out: dict[str, Any] = {}
    matrix = ws / "spec" / "coverage_matrix.md"
    if matrix.is_file():
        text = matrix.read_text(encoding="utf-8")
        rows = [r for r in ms.parse_table_rows(text) if ms.row_get(r.cells, "要素ID")]
        cleared = 0
        for row in sorted(rows, key=lambda r: r.start, reverse=True):
            cells = dict(row.cells)
            status_col = next((c for c in cells if c.strip() == "状态"), None)
            if status_col is None or cells[status_col] in ("skipped", "infeasible"):
                continue
            for col in cells:
                if "实现位置" in col or "验证结果" in col:
                    cells[col] = ""
                if "最后更新" in col:
                    cells[col] = "plan"
            cells[status_col] = "pending"
            line = "| " + " | ".join(str(v).replace("|", "\\|") for v in cells.values()) + " |" + ("\n" if row.text.endswith("\n") else "")
            text = text[:row.start] + line + text[row.end:]
            cleared += 1
        matrix.write_text(text, encoding="utf-8")
        out["matrix_rows_reset"] = cleared
    assumptions = ws / "assumptions.md"
    if assumptions.is_file():
        text = assumptions.read_text(encoding="utf-8")
        plan_path = ws / "plan.md"
        plan_text = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        removed, reset = [], 0
        for block in sorted([b for b in ms.parse_blocks(text) if b.prefix == "AS"], key=lambda b: b.start, reverse=True):
            source_field = block.field("来源")
            origin = source_field.value if source_field else ""
            # 编码之后才登记的假设要去掉。只看来源里有没有后段角色的字样：「数据限制」是 planner 在计划阶段
            # 就会用的来源，不能据此删。plan 正文引用到的也留着，删了会留下悬空的编号。
            late = any(word in origin for word in ("coder", "迭代", "diagnoser", "verifier"))
            if late and not re.search(rf"(?<![A-Za-z0-9]){re.escape(block.id)}(?![0-9])", plan_text):
                text = text[:block.start] + text[block.end:]
                removed.append(block.id)
                continue
            look = block.field("验证后回看")
            if look is not None and "[verify 后填]" not in look.value:
                text = text[:look.start] + "- 验证后回看: [verify 后填]\n" + text[look.end:].lstrip("\n")
                reset += 1
        assumptions.write_text(text, encoding="utf-8")
        out.update(assumptions_removed=sorted(removed), lookbacks_reset=reset)
    for rel in ("audit", "iterations"):
        directory = ws / rel
        if directory.is_dir():
            for path in directory.iterdir():
                keep = rel == "audit" and path.name in ("extract_audit.md", "spec_audit_external.md", "spec_audit_codex.md", "external_prompt_spec.md", "audit_responses.md", "external")
                if not keep:
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
    responses = ws / "audit" / "audit_responses.md"
    if responses.is_file():
        lines = [ln for ln in responses.read_text(encoding="utf-8").splitlines(keepends=True) if not re.match(r"^\|\s*CDX-[CR]-", ln)]
        responses.write_text("".join(lines), encoding="utf-8")
    for name in ("final_report.md", "oos_report.md", "assumptions.xlsx"):
        if (ws / name).is_file():
            (ws / name).unlink()
    return out
