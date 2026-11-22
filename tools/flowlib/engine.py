"""推进引擎：flow next / done / fail / adhoc / exec / wait 背后的循环。

一次推进（advance）反复做同一件事，直到必须停下来等人或等子 agent：
读状态 → 该停就停 → 找到当前阶段 → 问步骤表现在该做什么 → 内核自己能做的就地做，
要派出去的写任务文件并返回工单，都做完了就跑门禁收口。

状态的每次改动都在一个事务里完成（tools/state.py 的 transaction），事件与状态一起提交。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from tools import check_gates as cg
from tools import state as st

from . import checkpoints as cps
from . import events as ev
from . import kernelsteps as ks
from . import receipts as rc
from . import steps as sp
from . import tasks as tk
from .core import (
    ADHOC_LIMIT,
    DONE,
    FAILED,
    INFLIGHT,
    REDO,
    Ctx,
    FlowError,
    Step,
    external_engine,
    make_ctx,
    read_json,
    src_fingerprint,
    step_key,
    write_json,
    write_text,
)
from .events import STAGE_CN

MAX_LOOP = 80


def _extreview():
    from . import extreview

    return extreview


class Engine:
    def __init__(self, root: Path, report_id: str, host: Optional[str] = None) -> None:
        self.root = root
        self.report_id = report_id
        self._host = host
        self.notes: list[str] = []  # 这次调用里值得告诉主会话的话（门禁结论、重派原因等）

    # ------------------------------------------------------------------ 基础
    def ctx(self, state: Optional[dict[str, Any]] = None) -> Ctx:
        return make_ctx(self.root, self.report_id, state, self._host)

    def txn(self, actor: str = "flow") -> Any:
        return st.transaction(self.root, self.report_id, actor=actor)

    def note(self, text: str) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    @staticmethod
    def _steps(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return state["flow"].setdefault("steps", {})

    def _mark_kernel(self, txn: st.Txn, key: Optional[str], result: Optional[dict[str, Any]] = None) -> None:
        if not key:
            return
        self._steps(txn.state)[key] = {"status": DONE, "kind": "kernel", "done_at": st.now_iso(), "result": result or {}}
        txn.log(f"step:{key}:done", {"kind": "kernel", **({"result": result} if result else {})})

    def redo(
        self,
        txn: st.Txn,
        ctx: Ctx,
        step_id: str,
        reason: str,
        detail: str = "",
        *,
        count: bool = True,
        stage: Optional[str] = None,
        role: Optional[str] = None,
        hint: str = "",
    ) -> bool:
        """把一步标成「要重派」。count=True 时计入重派次数，超过上限改开检查点并返回 False。

        hint 是写给接手者的一句话（比如「活不用重做，只改回执」），不给时任务文件里用通用的那句。
        """
        steps = self._steps(txn.state)
        rec = steps.get(step_id)
        counters = txn.state["counters"].setdefault("redispatch", {})
        if count:
            used = int(counters.get(step_id) or 0)
            if used >= ctx.redispatch_limit(step_id):
                cps.open_human(
                    txn,
                    ctx,
                    "redispatch_exhausted",
                    reason=f"步骤 {step_id} 已经重派 {used} 次仍没过：{reason}",
                    stage=stage or (rec or {}).get("stage"),
                    payload={"step": step_id, "reason": reason, "detail": detail[:2000]},
                )
                return False
            counters[step_id] = used + 1
            cps.record_auto(txn, "redispatch", reason=f"{step_id}：{reason}", stage=stage or (rec or {}).get("stage"), payload={"step": step_id, "n": used + 1})
        if rec is None:
            rec = {"attempt": 0, "stage": stage, "role": role, "kind": "dispatch"}
            steps[step_id] = rec
        rec["status"] = REDO
        rec["redo"] = {"reason": reason, "detail": detail[:6000], **({"hint": hint} if hint else {})}
        if step_id in txn.state["flow"]["inflight"]:
            txn.state["flow"]["inflight"].remove(step_id)
        txn.log(f"step:{step_id}:redo", {"reason": reason, "counted": count})
        self.note(f"{step_id} 要重派：{reason}")
        return True

    # ------------------------------------------------------------------ 派发
    def _issue(self, txn: st.Txn, ctx: Ctx, step: Step) -> dict[str, Any]:
        steps = self._steps(txn.state)
        rec = steps.get(step.id) or {}
        attempt = int(rec.get("attempt") or 0) + 1
        redo = rec.get("redo") if rec.get("status") == REDO else None
        reopen = ctx.flow.get("reopen") or {}
        notes = None
        if reopen.get("gen") == ctx.generation and reopen.get("notes_file") and step.kind == "dispatch":
            notes = ctx.read(reopen["notes_file"]) or None
        body: Optional[str] = None
        extra: dict[str, Any] = {}

        if step.kind == "exec":
            extra, body = self._prepare_exec(ctx, step, attempt)
        elif step.kind == "judge":
            body = self._judge_question(ctx, step)
        elif step.extra.get("fallback_of"):
            body, outputs = self._fallback_body(ctx, step)
            step.outputs = outputs

        written = tk.write_task(ctx, step, attempt, redo=redo, notes=notes, body=body, prior_reserved=list(rec.get("reserved") or []) if redo else None)
        record: dict[str, Any] = {
            "status": INFLIGHT,
            "attempt": attempt,
            "kind": step.kind,
            "role": step.role,
            "stage": step.stage,
            "milestone": step.milestone,
            "issued_at": st.now_iso(),
            "done_at": None,
            "task_bytes": written["task_bytes"],
            "manifest": written["manifest"],
            "receipt": written["receipt"],
            "receipt_mode": step.receipt,
            "reserved": written["reserved"],
            "reason": (redo or {}).get("reason") or "首派",
            **extra,
        }
        if step.extra.get("fallback_of"):
            record["fallback_of"] = step.extra["fallback_of"]
        if step.id == "oos.main":
            # 样本外分析的基线：它开工时的代码与对比结果。之后任一个变了（结果审计的修复），它的产物就过期了
            record["baseline"] = {"src": src_fingerprint(self.root, self.report_id), "comparison": ks.comparison_digest(ctx)}
        if step.role in ("quant-verifier", "quant-auditor") and step.kind == "dispatch":
            # 这一步看的是哪一版代码：之后代码再变，它的结论就过期了
            if step.milestone and step.milestone != "all":
                record["src_files"] = ks.milestone_src_files(ctx, step.milestone)
            else:
                record["src_sha"] = src_fingerprint(self.root, self.report_id)
        steps[step.id] = record
        if written["reserved"]:  # 重派沿用旧区间时不能把水位往回拨，否则会和并行工单拿到的区间撞上
            txn.state["flow"]["as_reserved"] = max(int(txn.state["flow"].get("as_reserved") or 0), int(written["reserved"][-1][2:]))
        if step.id not in txn.state["flow"]["inflight"]:
            txn.state["flow"]["inflight"].append(step.id)
        txn.log(
            f"step:{step.id}:issued",
            {"attempt": attempt, "kind": step.kind, "role": step.role, "task_bytes": written["task_bytes"], "reason": record["reason"]},
        )
        return written["order"]

    def _prepare_exec(self, ctx: Ctx, step: Step, attempt: int) -> tuple[dict[str, Any], str]:
        """外审步骤：渲染提示词与输入包。准备失败（模块缺失、模板问题）记在记录里，由 exec 时走降级。"""
        kind, rnd = step.extra["review_kind"], int(step.extra.get("round") or 1)
        engine, engine_state = external_engine(ctx.host, ctx.config)
        try:
            job = _extreview().prepare(
                self.root,
                self.report_id,
                kind,
                rnd,
                engine=engine,
                host=ctx.host,
                config=ctx.config,
                iteration=step.extra.get("iteration"),
            )
        except Exception as exc:  # noqa: BLE001 - 准备不出来就按外审不可用处理
            return {"job_id": None, "engine": engine, "prepare_error": str(exc)[:500]}, f"外审任务没有准备出来：{exc}\n"
        body = (
            f"# 外审任务 {job.get('job_id')}\n\n由内核在后台调用 {engine} 执行，不派子 agent。\n\n"
            f"- 方式：{job.get('mode')}；输入包 {int(job.get('input_bytes') or 0) / 1024:.0f}KB\n"
            f"- 提示词与输入包在外审任务目录里，原件只由外审模块写\n"
        )
        return {"job_id": job.get("job_id"), "engine": engine, "engine_state": engine_state, "task_bytes_input": job.get("input_bytes")}, body

    def _fallback_body(self, ctx: Ctx, step: Step) -> tuple[str, list[str]]:
        ext_rec = ctx.rec(step.extra["fallback_of"]) or {}
        info = _extreview().fallback_task(self.root, self.report_id, ext_rec.get("job_id"))
        body = (
            f"# 任务：{step.title}\n\n"
            f"外部审查引擎这一轮不可用（{(ext_rec.get('result') or {}).get('reason')}）。请你作为独立审查方完成同一份审查：\n\n"
            f"1. 读取 `{info['prompt_file']}`，严格按其中的要求审查（只读，不改任何被审文件）；\n"
            f"2. 把结论按其中规定的输出格式写到 `{info['output']}`；\n"
            "3. 不要读主会话的对话历史，不要采信任何完成汇报；\n"
            "4. 做完后只回一行：`DONE`，或 `BLOCKED: <原因>`。\n"
        )
        return body, [info["output"]]

    def _judge_question(self, ctx: Ctx, step: Step) -> str:
        kind, rnd, stage = step.extra["review_kind"], step.extra["round"], step.stage
        data = read_json(ctx.path(f"{ctx.ws}/flow/answers/{stage}.findings.r{rnd}.json")) or {}
        owners = sp.REVIEW_OWNERS[kind]
        lines = [
            f"# 请逐条裁决：{STAGE_CN.get(stage, stage)}意见（第 {rnd} 轮）",
            "",
            "下面是外审与内审提出、还没有处置的意见。每条给出处置；这是你作为编排者的判断，被审方与内审方都不宜自裁。",
            "",
            "规则：",
            "- 处置取 `accepted`（接受并修复）、`rejected`（拒绝，须给技术理由）或 `deferred`（搁置，须说明何时处理）；",
            "- **critical 不得 rejected 或 deferred**。确有争议就照实填，内核会开检查点交给人裁决；",
            f"- accepted 的意见写明交给谁修：owner 取 {' / '.join(owners)}，不需要改任何文件时写 `none`；",
            "- `回应` 写修复计划或技术理由，一两句话。",
            "",
            "## 待裁决的意见",
            "",
        ]
        for item in data.get("findings") or []:
            if item.get("id") not in (data.get("unruled") or []):
                continue
            lines.append(f"### {item.get('id')}（{item.get('severity')}）{item.get('title', '')}")
            if item.get("location"):
                lines.append(f"- 位置：{item['location']}")
            if item.get("detail"):
                lines.append(f"- 说明：{str(item['detail'])[:900]}")
            lines.append("")
        diffs = [d for d in data.get("diffs") or [] if d.get("id") in (data.get("unruled_diffs") or [])]
        if diffs:
            lines += ["## 待裁决的提取差异（DIF）", "", "裁决取 `adopted`（采纳盲提取的说法）、`dismissed`（不采纳）或 `corrected`（两边都不对，已另行更正）；要改 spec 或 plan 时写 owner。", ""]
            for item in diffs:
                lines.append(f"- **{item.get('id')}**（{item.get('类别', '')}，{item.get('页码', '')}）{item.get('描述', '')}")
            lines.append("")
        example = {
            "findings": {"CDX-X-01": {"处置": "accepted", "回应": "……", "owner": owners[0]}},
            "diffs": {"DIF-01": {"裁决": "adopted", "依据": "……", "owner": "none"}},
        }
        import json as _json

        lines += [
            "## 答卷",
            "",
            f"把答卷写到 `{step.extra['answer_file']}`，格式如下（没有 DIF 时省略 diffs）：",
            "",
            "```json",
            _json.dumps(example, ensure_ascii=False, indent=2),
            "```",
            "",
            f"原件：`{ctx.ws}/audit/{kind}_audit_external.md`；回应表：`{ctx.ws}/audit/audit_responses.md`。只在需要核对细节时才打开原件。",
        ]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ 推进循环
    def advance(self) -> dict[str, Any]:
        out: dict[str, Any] = {"report_id": self.report_id, "status": None, "orders": [], "wait": [], "halt": None}
        checked = False
        for _ in range(MAX_LOOP):
            ctx = self.ctx()
            state = ctx.state
            out["status"] = state.get("status")
            if not st.is_v2(state):
                legacy = sp.plan_next(state)
                legacy["notes"] = ["这是 v1 案例，仍由执行卡驱动；检查点与内核推进要先迁移状态文件（flow migrate，需经用户同意）。"]
                return legacy
            if state.get("status") in st.WAITING_STATUSES and not st.pending_checkpoints(state):
                with self.txn() as txn:
                    cps.ensure_wait_checkpoint(txn, self.ctx(txn.state))
                continue
            halt = sp.halt_for(state)
            if halt:
                out["halt"] = halt
                break
            if not checked:
                checked = True  # 事件流校验、停滞与预算一次调用只查一遍
                if self._integrity(ctx):
                    continue
            stage = sp.current_stage(state)
            if stage is None:
                with self.txn() as txn:
                    st.set_stage_in(txn, "review", "running")
                continue
            if sp.stage_driver(state, stage) == "card":
                out["orders"].append(sp.legacy_order(state, stage))
                break
            if ctx.stage_status(stage) in ("pending", "failed", "blocked"):
                with self.txn() as txn:
                    st.set_stage_in(txn, stage, "running")
                continue
            if stage == "init":
                out["halt"] = {"reason": "init_incomplete", "message": "初始化没有完成；用 flow init 重新开始，或检查 PDF 是否能解析"}
                break

            special = self._pending_special(ctx, stage)
            plan = sp.Plan(steps=special) if special else sp.PLANNERS[stage](ctx)
            if plan.skip:
                with self.txn() as txn:
                    st.set_stage_in(txn, stage, "skipped")
                    txn.log(f"{stage}_skipped", {"reason": plan.skip})
                self.note(f"{STAGE_CN.get(stage, stage)}阶段跳过：{plan.skip}")
                continue
            if plan.checkpoint and not plan.steps and not plan.actions:
                with self.txn() as txn:
                    cp = plan.checkpoint
                    cps.open_human(txn, self.ctx(txn.state), cp["name"], reason=cp["reason"], stage=stage, payload=cp.get("payload"))
                continue
            pending = [s for s in plan.steps if ctx.status_of(s.id) in (None, REDO, FAILED)]
            if pending:
                with self.txn() as txn:
                    inner = self.ctx(txn.state)
                    for step in pending:
                        self._issue(txn, inner, step)
                continue
            if plan.actions:
                name, args = plan.actions[0]
                with self.txn() as txn:
                    ACTIONS[name](self, txn, self.ctx(txn.state), **args)
                continue
            if any(ctx.status_of(s.id) == INFLIGHT for s in plan.steps) or self._inflight(ctx):
                break
            if plan.close:
                self._close_stage(stage)
                continue
            with self.txn() as txn:
                cps.open_human(txn, self.ctx(txn.state), "stuck", reason=f"{STAGE_CN.get(stage, stage)}阶段既没有可派的步骤也收不了口", stage=stage)
        else:
            out["halt"] = {"reason": "loop_guard", "message": "内核连续推进了太多轮没有停下，已中止；请把这次的输出反馈给维护者"}

        ctx = self.ctx()
        out["status"] = ctx.state.get("status")
        if out["halt"] is None and st.is_v2(ctx.state):
            out["halt"] = sp.halt_for(ctx.state)
        waiting = bool(out["halt"]) and out["halt"].get("reason") in st.WAITING_STATUSES
        if st.is_v2(ctx.state) and (not out["halt"] or waiting):
            for sid in self._inflight(ctx):
                rec = ctx.rec(sid) or {}
                order = (read_json(ctx.path(rec.get("manifest") or "")) or {}).get("order") or {"step_id": sid, "kind": rec.get("kind")}
                if rec.get("kind") == "exec" and rec.get("launched_at"):
                    out["wait"].append({"step_id": order.get("step_id"), "kind": "exec", "launched_at": rec["launched_at"], "how": f"flow wait {self.report_id}"})
                else:
                    out["orders"].append(order)
            if waiting and (out["orders"] or out["wait"]):
                out["halt"]["inflight_note"] = "检查点待决期间这些步骤仍在途：做完照常 flow done 点收，但不会再派新的步骤。"
        if self.notes:
            out["notes"] = list(self.notes)
        return out

    @staticmethod
    def _inflight(ctx: Ctx) -> list[str]:
        return [sid for sid, rec in ctx.steps.items() if rec.get("status") == INFLIGHT]

    def _pending_special(self, ctx: Ctx, stage: str) -> list[Step]:
        """门禁修复、检查点「修改后继续」这两类不在步骤表里的工单，优先于步骤表处理。"""
        out: list[Step] = []
        for suffix in ("gatefix", "modify"):
            sid = f"{stage}.{suffix}"
            rec = ctx.rec(sid)
            if not rec or rec.get("status") not in (REDO, INFLIGHT, FAILED):
                continue
            if suffix == "gatefix":
                step = sp.gatefix_step(ctx, stage)
                if rec.get("role") and step is not None and rec["role"] != step.role:
                    step.role = rec["role"]
                    step.pack = ("verifier", "final") if step.role == "quant-verifier" else None
            else:
                step = Step(
                    id=sid,
                    stage=stage,
                    role=str(rec.get("role") or "general-purpose"),
                    title=f"按评审意见修改（{STAGE_CN.get(stage, stage)}）",
                    instruction="人在检查点提出了修改要求（见下面的重派原因）。只按要求修改你负责的文件，改完写回执。",
                    milestone=rec.get("milestone") or "all",
                )
            if step is not None:
                out.append(step)
        return out

    def _integrity(self, ctx: Ctx) -> bool:
        """事件流校验、停滞、预算。任何一项开了检查点就返回 True（下一轮循环会停下）。"""
        state = ctx.state
        chain = st.verify_event_chain(self.root, self.report_id, state)
        signature = "；".join(chain.get("errors") or [])
        if not chain.get("ok") and (ctx.ext.get("tamper_ack") or {}).get("signature") != signature:
            with self.txn() as txn:
                cps.open_human(txn, self.ctx(txn.state), "tamper", reason="事件流与状态文件对不上：" + signature[:300], payload={"signature": signature})
            return True
        timeline = ev.timeline(self.root, self.report_id, state)
        stall = cps.stalled(ctx, timeline)
        if stall:
            with self.txn() as txn:
                cps.open_human(
                    txn,
                    self.ctx(txn.state),
                    "stall",
                    reason=f"在途步骤 {'、'.join(stall['steps'])} 已经 {stall['idle_hours']} 小时没有新事件（阈值 {stall['threshold']:g} 小时），会话可能中断了",
                    payload=stall,
                )
            return True
        over = cps.budget_exceeded(ctx, timeline)
        if over and (ctx.ext.get("budget_ack") or {}) != over:
            with self.txn() as txn:
                unit = "小时" if over["kind"] == "hours" else " token"
                cps.open_human(txn, self.ctx(txn.state), "budget", reason=f"已用 {over['used']}{unit}，超过预算 {over['cap']}{unit}", payload=over)
            return True
        return False

    # ------------------------------------------------------------------ 门禁收口
    def _close_stage(self, stage: str) -> None:
        evaluation = cg.evaluate(self.root, self.report_id, stage)
        failed = [c.id for c in evaluation.failed()]
        with self.txn() as txn:
            ctx = self.ctx(txn.state)
            breaker = st.gate_in(txn, stage, evaluation.verdict, evaluation.to_record(with_detail=True))
            txn.state["stages"][stage]["issues"] = len(failed)
            if breaker is not None:
                breaker["pack"] = cps._write_pack(ctx, breaker, txn.state)  # 熔断是状态层开的，审阅包在这里补
            if evaluation.passed:
                self.note(f"{STAGE_CN.get(stage, stage)}门禁通过")
            else:
                detail = "\n".join(cg.format_check(c) for c in evaluation.failed())
                hint = _explain_inline(failed)
                self.note(f"{STAGE_CN.get(stage, stage)}门禁未过：\n{detail}" + (f"\n\n处理说明（内核已按此处置，写着交给人的才需要你停下）：\n{hint}" if hint else ""))
            CLOSERS.get(stage, _close_default)(self, txn, ctx, stage, evaluation, failed, breaker)

    def finish_stage(self, txn: st.Txn, ctx: Ctx, stage: str) -> None:
        """门禁通过后的收口：阶段置为完成，并按模式开中途检查点。"""
        st.set_stage_in(txn, stage, "done")
        txn.state["counters"].setdefault("redispatch", {}).pop(f"gate:{stage}", None)
        policy = txn.state.get("policy") or {}
        name = {"extract": "spec_final", "spec_audit": "plan_final", "verify": "verify_done"}.get(stage)
        modify = (txn.state["flow"].get("modify") or {}).get("stage") == stage
        if policy.get("until") == stage:
            policy["until"] = None
            cps.open_human(txn, ctx, "until", reason=f"已到达你指定的停点：{STAGE_CN.get(stage, stage)}阶段收口", stage=stage)
        elif name and (ctx.mode == "interactive" or modify):
            cps.open_human(txn, ctx, name, reason=f"{STAGE_CN.get(stage, stage)}阶段已收口，请确认后继续", stage=stage)

    def gate_remedy(self, txn: st.Txn, ctx: Ctx, stage: str, failed: list[str], detail: str, plan: list[tuple[str, dict[str, Any]]]) -> None:
        """门禁未过后的处置：plan 里每项是（动作, 参数）。同一阶段的门禁修复次数有上限。"""
        counters = txn.state["counters"].setdefault("redispatch", {})
        key = f"gate:{stage}"
        used = int(counters.get(key) or 0)
        limit = max(ctx.redispatch_limit(key), 1)
        if used >= limit:
            cps.open_human(
                txn,
                ctx,
                "redispatch_exhausted",
                reason=f"{STAGE_CN.get(stage, stage)}门禁修了 {used} 轮仍未过：{'、'.join(failed)}",
                stage=stage,
                payload={"stage": stage, "failed": failed, "detail": detail[:2000]},
            )
            return
        counters[key] = used + 1
        reason = f"{STAGE_CN.get(stage, stage)}门禁未过（{'、'.join(failed)}）"
        for action, args in plan:
            if action == "redo":
                self.redo(txn, ctx, args["step"], reason, detail, count=False, stage=stage, role=args.get("role"))
            elif action == "invalidate":
                steps = self._steps(txn.state)
                for sid in [s for s in steps if s.startswith(args["prefix"]) and steps[s].get("kind") == "kernel"]:
                    del steps[sid]
            elif action == "checkpoint":
                cps.open_human(txn, ctx, args["name"], reason=args.get("reason") or reason, stage=stage, payload=args.get("payload"))

    # ------------------------------------------------------------------ done / fail
    def done(self, raw_ids: list[str], collect_usage: bool = True) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self.txn("flow:done") as txn:
            for raw in raw_ids:
                results.append(self._done_one(txn, step_key(raw), collect_usage))
            policy = txn.state.get("policy") or {}
            if policy.get("step") and any(r.get("ok") for r in results) and txn.state.get("status") == "running":
                cps.open_human(txn, self.ctx(txn.state), "step", reason="单步模式：" + "、".join(r["step"] for r in results if r.get("ok")) + " 已点收")
        self._ingest_guard_log()
        return results

    def _done_one(self, txn: st.Txn, sid: str, collect_usage: bool) -> dict[str, Any]:
        ctx = self.ctx(txn.state)
        steps = self._steps(txn.state)
        rec = steps.get(sid)
        if rec is None:
            raise FlowError(f"没有步骤 {sid}；用 flow next 看当前的工单")
        if rec.get("status") == DONE:
            return {"step": sid, "ok": True, "already": True}
        if rec.get("status") != INFLIGHT:
            raise FlowError(f"步骤 {sid} 不在途（当前 {rec.get('status')}），不能点收；用 flow next 重新取工单")
        manifest = read_json(ctx.path(rec.get("manifest") or "")) or {}
        if rec.get("kind") == "exec":
            raise FlowError(f"{sid} 是后台外审步骤，用 flow wait {self.report_id} 等它结束")
        if rec.get("kind") == "judge":
            return self._done_judge(txn, ctx, sid, rec, manifest)

        missing = [p for p in manifest.get("outputs") or [] if not ctx.path(p).is_file() or ctx.path(p).stat().st_size == 0]
        try:
            receipt = rc.load(ctx.path(rec["receipt"])) if rec.get("receipt") else None
        except rc.ReceiptError as exc:
            self.redo(txn, ctx, sid, "回执读不出来", "\n".join(exc.reasons), hint=_receipt_only_hint(rec))
            return {"step": sid, "ok": False, "class": "receipt_rejected", "reasons": exc.reasons}
        if receipt and str(receipt.get("status")) == "blocked":
            return self._fail_one(txn, ctx, sid, "blocked", str(receipt.get("summary") or "子 agent 报告受阻"))
        skip = isinstance((receipt or {}).get("skip"), dict)
        if skip:
            missing = []
        if rec.get("receipt_mode") == "required" and receipt is None:
            missing.append(str(rec.get("receipt")))
        if missing and rec.get("fallback_of") and int(rec.get("attempt") or 1) >= 2:
            # 外审替身重派一次仍交不出东西：不为它惊动人，这一轮外审记为不可用
            rec.update(status=FAILED, done_at=st.now_iso())
            if sid in txn.state["flow"]["inflight"]:
                txn.state["flow"]["inflight"].remove(sid)
            txn.log(f"step:{sid}:failed", {"class": "incomplete", "attempt": rec.get("attempt")})
            self.note(f"{sid} 两次都没有交出审查结果，这一轮外审记为不可用")
            return {"step": sid, "ok": False, "class": "degraded", "missing": missing}
        if missing:
            self.redo(txn, ctx, sid, "交回的东西不全", "缺少：\n" + "\n".join(missing), count=not rec.get("fallback_of"))
            return {"step": sid, "ok": False, "class": "incomplete", "missing": missing}
        try:
            merge = rc.apply(ctx, rec, receipt, allowed_ids=rc.step_element_ids(ctx, rec.get("milestone")))
        except rc.ReceiptError as exc:
            self.redo(txn, ctx, sid, "回执被拒收", "\n".join(exc.reasons), hint=_receipt_only_hint(rec))
            return {"step": sid, "ok": False, "class": "receipt_rejected", "reasons": exc.reasons}
        problem = _post_check(ctx, sid, rec)
        if problem:
            self.redo(txn, ctx, sid, problem[0], problem[1])
            return {"step": sid, "ok": False, "class": "incomplete", "reasons": [problem[0]]}

        now = st.now_iso()
        rec.update(status=DONE, done_at=now, result=dict(merge.result), summary=merge.summary)
        rec.pop("redo", None)
        if sid in txn.state["flow"]["inflight"]:
            txn.state["flow"]["inflight"].remove(sid)
        payload: dict[str, Any] = {"attempt": rec.get("attempt"), "role": rec.get("role"), "merged": {k: v for k, v in merge.to_dict().items() if k not in ("result", "status", "summary")}}
        seconds = ev.hours_since(rec.get("issued_at"))
        if seconds is not None:
            payload["seconds"] = round(seconds * 3600)
        usage, violations = _step_usage(ctx, sid, rec, manifest) if collect_usage else (None, [])
        if usage:
            payload["usage"] = usage
        if violations:
            # 事后核对：这一步的会话记录里，工具调用碰过禁读清单上的路径
            rec["forbidden_reads"] = violations[:20]
            txn.log("guard:violation", {"step": sid, "role": rec.get("role"), "paths": violations[:20]})
            self.note(f"{sid} 读了不该读的路径：{'、'.join(violations[:5])}（已记入事件流，看板会标出）")
        drift = ks.pack_drift(self.ctx(txn.state), manifest)
        if drift:
            # 到货即过期：这一步在途期间，它消费过的片被改了。只留痕并提示，是否重做由人看过期报告后决定
            rec["stale_on_arrival"] = drift[:30]
            payload["stale_on_arrival"] = drift[:30]
            self.note(f"{sid} 做的时候依据的内容在途中变了（{'、'.join(drift[:5])}{' 等' if len(drift) > 5 else ''}）；用 flow stale {self.report_id} 看过期范围")
        txn.log(f"step:{sid}:done", payload)
        _on_done(self, txn, self.ctx(txn.state), sid, rec, merge)
        return {"step": sid, "ok": True, "merged": payload["merged"]}

    def _done_judge(self, txn: st.Txn, ctx: Ctx, sid: str, rec: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
        order = manifest.get("order") or {}
        answer = read_json(ctx.path(order.get("answer_file") or ""))
        if not isinstance(answer, dict):
            return {"step": sid, "ok": False, "class": "incomplete", "reasons": [f"答卷 {order.get('answer_file')} 不存在或不是合法的 JSON"]}
        problems, result = _apply_ruling(self, txn, ctx, sid, rec, answer)
        if problems:
            return {"step": sid, "ok": False, "class": "answer_rejected", "reasons": problems}
        rec.update(status=DONE, done_at=st.now_iso(), result=result)
        if sid in txn.state["flow"]["inflight"]:
            txn.state["flow"]["inflight"].remove(sid)
        txn.log(f"step:{sid}:done", {"kind": "judge", "ruled": result.get("ruled"), "fix_owners": sorted((result.get("fixes") or {}).keys())})
        return {"step": sid, "ok": True}

    def fail(self, raw: str, klass: str, note: str = "") -> dict[str, Any]:
        with self.txn("flow:fail") as txn:
            return self._fail_one(txn, self.ctx(txn.state), step_key(raw), klass, note)

    def _fail_one(self, txn: st.Txn, ctx: Ctx, sid: str, klass: str, note: str) -> dict[str, Any]:
        rec = self._steps(txn.state).get(sid)
        if rec is None or rec.get("status") != INFLIGHT:
            raise FlowError(f"步骤 {sid} 不在途，不能记失败")
        txn.log(f"step:{sid}:failed", {"class": klass, "note": note[:500], "attempt": rec.get("attempt")})
        if klass == "blocked":
            rec["status"] = FAILED
            if sid in txn.state["flow"]["inflight"]:
                txn.state["flow"]["inflight"].remove(sid)
            if rec.get("fallback_of"):
                self.note(f"{sid} 受阻，外审降级到不可用")
                return {"step": sid, "ok": False, "class": klass}
            cps.open_human(txn, ctx, "step_blocked", reason=f"{sid} 报告受阻：{note or '未说明'}", stage=rec.get("stage"), payload={"step": sid, "note": note[:1000]})
            return {"step": sid, "ok": False, "class": klass, "checkpoint": True}
        if rec.get("fallback_of"):
            rec["status"] = FAILED
            if sid in txn.state["flow"]["inflight"]:
                txn.state["flow"]["inflight"].remove(sid)
            return {"step": sid, "ok": False, "class": klass}
        ok = self.redo(txn, ctx, sid, {"incomplete": "上一次没有做完", "crashed": "上一次中途中断"}.get(klass, klass), note)
        return {"step": sid, "ok": False, "class": klass, "redispatch": ok}

    # ------------------------------------------------------------------ 表外派发
    def adhoc(self, role: str, reason: str, instruction: str, writes: list[str]) -> dict[str, Any]:
        with self.txn("flow:adhoc") as txn:
            ctx = self.ctx(txn.state)
            if txn.state.get("status") != "running":
                raise FlowError("案例不在运行中，不能临时派发")
            if not (reason or "").strip() or not (instruction or "").strip():
                raise FlowError("表外派发要写明原因（--reason）和任务说明（--instruction <文件>）")
            if not role.startswith("quant-") and role != "general-purpose":
                raise FlowError(f"不认识的角色 {role}；用 quant-* 角色或 general-purpose")
            used = int(txn.state["counters"].get("adhoc") or 0)
            limit = int((ctx.config.get("flow") or {}).get("adhoc_limit") or ADHOC_LIMIT)
            if used >= limit:
                raise FlowError(f"表外派发已经用了 {used} 次，达到上限 {limit}；确有需要请让人决定（flow pin 把阶段退回执行卡，或调高 .reproduce.json 的 flow.adhoc_limit）")
            txn.state["counters"]["adhoc"] = used + 1
            step = Step(
                id=f"adhoc.{used + 1:02d}",
                stage=str(txn.state.get("current_stage")),
                role=role,
                title=f"临时派发：{reason[:40]}",
                instruction=instruction,
                writes=writes,
                milestone="all",
            )
            order = self._issue(txn, ctx, step)
            txn.state["flow"].setdefault("adhoc", []).append({"id": step.id, "role": role, "reason": reason, "at": st.now_iso(), "status": INFLIGHT})
            txn.log(f"adhoc:{step.id}", {"role": role, "reason": reason, "writes": writes})
            return order

    # ------------------------------------------------------------------ 外审：exec / wait
    def exec_step(self, raw: str, detach: bool) -> dict[str, Any]:
        sid = step_key(raw)
        ctx = self.ctx()
        rec = ctx.rec(sid) or {}
        if rec.get("kind") != "exec" or rec.get("status") != INFLIGHT:
            raise FlowError(f"{sid} 不是在途的外审步骤")
        if not rec.get("job_id"):
            return self._finish_exec(sid, {"state": "failed", "reason": "unavailable", "detail": rec.get("prepare_error")})
        try:
            started = _extreview().launch(self.root, self.report_id, rec["job_id"], detach=detach)
        except Exception as exc:  # noqa: BLE001
            return self._finish_exec(sid, {"state": "failed", "reason": "unavailable", "detail": str(exc)[:300]})
        with self.txn("flow:exec") as txn:
            live = self._steps(txn.state)[sid]
            if not live.get("launched_at"):
                live["launched_at"] = started.get("started_at") or st.now_iso()
                txn.log(f"step:{sid}:launched", {"job_id": rec["job_id"], "pid": started.get("pid"), "detach": detach})
        if not detach:
            return self._finish_exec(sid, _extreview().status(self.root, self.report_id, rec["job_id"]))
        return {"step": sid, "launched": True, "job_id": rec["job_id"], "pid": started.get("pid")}

    def _finish_exec(self, sid: str, status: dict[str, Any]) -> dict[str, Any]:
        with self.txn("flow:exec") as txn:
            ctx = self.ctx(txn.state)
            rec = self._steps(txn.state)[sid]
            if rec.get("status") == DONE:
                return {"step": sid, "state": (rec.get("result") or {}).get("state")}
            result = {k: status.get(k) for k in ("state", "reason", "engine", "mode", "seconds", "subsessions", "input_bytes", "blind_read_spec") if status.get(k) is not None}
            if status.get("state") != "success" and status.get("message"):
                result["message"] = str(status["message"])[:200]
            rec.update(status=DONE, done_at=st.now_iso(), result=result)
            if "context_overflow" in str(status.get("message") or status.get("reason") or ""):
                self.note(f"{sid}：输入包超出了外审引擎的上下文窗口。把 .reproduce.json 的 external_review.input_budget_kb 调小（当前这一轮 {int(result.get('input_bytes') or 0) / 1024:.0f}KB），下一次外审按新预算打包")
            if result.get("blind_read_spec"):
                # 盲提取的第一次调用读了 spec：这一轮的「盲」不成立。不作废（意见仍有用），但要留痕并让人知道
                txn.log("review:blind_violation", {"step": sid, "job_id": rec.get("job_id")})
                self.note(f"{sid}：外审的盲提取调用读过 spec（从它的会话记录里查到的），这一轮的盲提取不算独立，已记入事件流")
            if int(result.get("subsessions") or 0) > 0:
                self.note(f"{sid}：外审引擎分出了 {result['subsessions']} 个子会话（应为 0，已在调用时关闭多代理），用量会偏高")
            if sid in txn.state["flow"]["inflight"]:
                txn.state["flow"]["inflight"].remove(sid)
            payload = dict(result, attempts=status.get("attempts"))
            if isinstance(status.get("usage"), dict):
                payload["usage"] = status["usage"]
            txn.log(f"step:{sid}:done", payload)
            if result.get("state") != "success":
                second = sid.startswith("iterate.")
                how = "本轮没有第二意见，诊断照常进行" if second else "转同宿主替身"
                cps.record_auto(txn, "external_degraded", reason=f"{sid} 外审失败（{result.get('reason')}），{how}", stage=rec.get("stage"), payload={"step": sid, "reason": result.get("reason")})
                self.note(f"{sid} 外审失败（{result.get('reason')}），{how}")
        return {"step": sid, "state": status.get("state"), "reason": status.get("reason")}

    def wait(self, timeout: float = 600.0, interval: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        finished: list[dict[str, Any]] = []
        while True:
            ctx = self.ctx()
            running = [(sid, rec) for sid, rec in ctx.steps.items() if rec.get("kind") == "exec" and rec.get("status") == INFLIGHT]
            launched = [(sid, rec) for sid, rec in running if rec.get("launched_at") and rec.get("job_id")]
            for sid, rec in launched:
                status = _extreview().status(self.root, self.report_id, rec["job_id"])
                if status.get("state") in ("success", "failed"):
                    finished.append(self._finish_exec(sid, status))
            if finished or not launched or time.monotonic() >= deadline:
                not_started = [sid for sid, rec in running if not rec.get("launched_at")]
                return {"finished": finished, "running": [sid for sid, _r in launched if sid not in {f["step"] for f in finished}], "not_started": not_started}
            time.sleep(interval)

    # ------------------------------------------------------------------ 杂项
    def _ingest_guard_log(self) -> None:
        """把禁读护栏的拦截记录并进事件流（钩子自己不碰状态文件）。"""
        path = self.root / "workspace" / self.report_id / "flow" / "guard.log"
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            path.unlink()
        except OSError:
            return
        import json as _json

        items = []
        for line in lines:
            try:
                items.append(_json.loads(line))
            except ValueError:
                continue
        if not items:
            return
        with self.txn("flow:guard") as txn:
            for item in items[:50]:
                txn.log("guard:denied", {k: item.get(k) for k in ("path", "tool", "agent_type", "steps", "ts")})


# ---------------------------------------------------------------------------
# 点收时的附加检查与路由
# ---------------------------------------------------------------------------


def _post_check(ctx: Ctx, sid: str, rec: dict[str, Any]) -> Optional[tuple[str, str]]:
    """个别步骤在产物齐、回执合并之后还要核一件事；有问题返回（原因, 明细）。"""
    if rec.get("role") == "quant-coder" and rec.get("stage") == "implement" and sid.endswith(".code"):
        rows = cg.load_matrix_rows(ctx.path(f"{ctx.ws}/spec/coverage_matrix.md"))
        allowed = rc.step_element_ids(ctx, rec.get("milestone"))
        missing = [
            cg._row_get(r, "要素ID")
            for r in rows
            if (allowed is None or cg._row_get(r, "要素ID") in allowed)
            and cg._row_get(r, "状态") not in ("skipped", "infeasible")
            and not cg._row_get(r, "实现位置")
        ]
        if missing:
            return ("本步要素的矩阵「实现位置」还有空的", "这些要素没有实现位置：" + "、".join(missing) + "\n在回执的 matrix 里补上（确实不做的改 skipped / infeasible 并给状态理由）。")
        src = ctx.path(ctx.src)
        if not src.is_dir() or not any(src.rglob("*.py")):
            return ("src 目录里没有代码", f"{ctx.src}/ 下没有任何 .py 文件")
    return None


def _all_milestone_ids(ctx: Ctx, rec: dict[str, Any]) -> list[str]:
    mid = rec.get("milestone")
    return [str(m["id"]) for m in ctx.milestones] if mid in (None, "all") else [str(mid)]


def _on_done(engine: Engine, txn: st.Txn, ctx: Ctx, sid: str, rec: dict[str, Any], merge: rc.Merge) -> None:
    stage, role = rec.get("stage"), rec.get("role")
    steps = engine._steps(txn.state)
    for entry in txn.state["flow"].get("adhoc") or []:
        if entry.get("id") == sid:
            entry["status"] = DONE
    if rec.get("fallback_of"):
        ext = steps.get(rec["fallback_of"]) or {}
        try:
            status = _extreview().accept_fallback(engine.root, engine.report_id, ext.get("job_id"))
            ok = status.get("state") == "success"
        except Exception as exc:  # noqa: BLE001
            ok = False
            engine.note(f"替身的输出没有通过校验：{exc}")
        rec["result"] = {"accepted": ok}
        if not ok:
            rec["status"] = FAILED
        return

    if stage == "implement" and sid.endswith(".code"):
        for mid in _all_milestone_ids(ctx, rec):
            st.milestone_in(txn, mid, "implement", "done")
            if ctx.difficulty == "easy" and not ctx.is_ml:
                st.milestone_in(txn, mid, "verify", "skipped")
        rec["src_sha"] = src_fingerprint(engine.root, engine.report_id)
    elif stage == "implement" and sid.endswith(".verify"):
        mid = str(rec.get("milestone"))
        verdict = (merge.result.get("verify") or {}).get("verdict")
        if verdict == "pass":
            st.milestone_in(txn, mid, "verify", "done")
            _milestone_checkpoint(txn, ctx, mid)
        else:
            failures = "\n".join(f"- {f}" for f in (merge.result.get("verify") or {}).get("failures") or []) or "（验证回执没有给出失败明细）"
            if engine.redo(txn, ctx, f"implement.{mid}.code", f"{mid} 的 milestone 级验证没过", failures):
                st.milestone_in(txn, mid, "implement", "running")
                engine.redo(txn, ctx, sid, "代码修复后重新验证", count=False)
    elif sid.endswith(".audit") or sid == "code_audit.internal":
        audit = merge.result.get("audit") or {}
        bad = int(audit.get("critical") or 0) > 0 or bool(audit.get("not_found"))
        targets = _all_milestone_ids(ctx, rec)
        if not bad:
            for mid in targets:
                st.milestone_in(txn, mid, "code_review", "done")
                if stage == "implement":
                    _milestone_checkpoint(txn, ctx, mid)
        elif stage == "implement":
            mid = targets[0]
            detail = f"内审文件：{ctx.ws}/audit/impl_audit_{mid}.md；critical {audit.get('critical')} 条，空壳实现 {audit.get('not_found') or '无'}"
            if engine.redo(txn, ctx, f"implement.{mid}.code", f"{mid} 的实现内审有 critical 或空壳实现", detail):
                st.milestone_in(txn, mid, "implement", "running")
                engine.redo(txn, ctx, sid, "代码修复后重新内审", count=False)
                if steps.get(f"implement.{mid}.verify"):
                    engine.redo(txn, ctx, f"implement.{mid}.verify", "代码修复后重新验证", count=False)
                    st.milestone_in(txn, mid, "verify", "pending")
        else:
            detail = f"内审文件在 {ctx.ws}/audit/impl_audit_m*.md；critical {audit.get('critical')} 条，空壳实现 {audit.get('not_found') or '无'}。逐条修复。"
            if engine.redo(txn, ctx, "code_audit.gatefix", "实现内审有 critical 或空壳实现", detail, stage="code_audit", role="quant-coder"):
                engine.redo(txn, ctx, sid, "代码修复后重新内审", count=False)
    if sid.endswith(".modify") and role == "quant-planner":
        ks.seed_plan(txn, ctx)


def _milestone_checkpoint(txn: st.Txn, ctx: Ctx, mid: str) -> None:
    """interactive 模式下 milestone 做完停一次。hard 难度要等实现内审也有了结论，人确认时才看得到内审怎么说。"""
    if ctx.mode != "interactive":
        return
    m = next((m for m in txn.state.get("milestones") or [] if str(m.get("id")) == mid), None)
    if m is None or m.get("verify") != "done" or (ctx.difficulty == "hard" and m.get("code_review") != "done"):
        return
    audited = "和实现内审" if ctx.difficulty == "hard" else ""
    cps.open_human(txn, ctx, "milestone_done", reason=f"{mid} 已实现并通过 milestone 级验证{audited}", stage="implement", payload={"milestone": mid})


def _apply_ruling(engine: Engine, txn: st.Txn, ctx: Ctx, sid: str, rec: dict[str, Any], answer: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """核对主会话的裁决答卷并落到回应表。返回（问题清单, 路由结果）。"""
    manifest = read_json(ctx.path(rec.get("manifest") or "")) or {}
    order = manifest.get("order") or {}
    stage = str(rec.get("stage"))
    kind = sp.REVIEW_KIND[stage]
    rnd = int(str(order.get("step_id", sid)).split(".r")[-1].split("#")[0])
    data = read_json(ctx.path(f"{ctx.ws}/flow/answers/{stage}.findings.r{rnd}.json")) or {}
    by_id = {f.get("id"): f for f in data.get("findings") or []}
    owners = set(sp.REVIEW_OWNERS[kind]) | {"none"}
    problems: list[str] = []
    rulings: dict[str, dict[str, str]] = {}
    fixes: dict[str, list[dict[str, Any]]] = {}
    recheck: list[str] = []
    disputes: list[dict[str, Any]] = []
    given = answer.get("findings") if isinstance(answer.get("findings"), dict) else {}
    for fid in data.get("unruled") or []:
        item, finding = given.get(fid), by_id.get(fid) or {}
        if not isinstance(item, dict):
            problems.append(f"{fid}：答卷里没有这一条")
            continue
        choice, reply, owner = str(item.get("处置") or ""), str(item.get("回应") or "").strip(), str(item.get("owner") or "")
        severity = str(finding.get("severity") or "").lower()
        if choice not in ("accepted", "rejected", "deferred"):
            problems.append(f"{fid}：处置只能是 accepted / rejected / deferred")
            continue
        if severity in ("critical", "major") and not reply:
            problems.append(f"{fid}：{severity} 级意见必须写回应")
            continue
        if choice == "accepted" and owner not in owners:
            problems.append(f"{fid}：accepted 的意见要写 owner（{' / '.join(sorted(owners))}）")
            continue
        if severity == "critical" and choice != "accepted":
            disputes.append({"id": fid, "choice": choice, "reply": reply, "title": finding.get("title"), "location": finding.get("location"), "owner": owner if owner in sp.REVIEW_OWNERS[kind] else None})
            continue
        rulings[fid] = {"处置": choice, "回应": reply}
        if choice == "accepted" and owner != "none":
            fixes.setdefault(owner, []).append({**{k: finding.get(k) for k in ("id", "severity", "title", "location", "detail")}, "reply": reply})
        if choice == "accepted" and severity == "critical":
            recheck.append(fid)
    diff_rulings: dict[str, dict[str, str]] = {}
    given_diffs = answer.get("diffs") if isinstance(answer.get("diffs"), dict) else {}
    diffs_by_id = {d.get("id"): d for d in data.get("diffs") or []}
    for did in data.get("unruled_diffs") or []:
        item = given_diffs.get(did)
        if not isinstance(item, dict) or str(item.get("裁决") or "") not in ("adopted", "dismissed", "corrected"):
            problems.append(f"{did}：裁决只能是 adopted / dismissed / corrected")
            continue
        diff_rulings[did] = {"裁决": str(item["裁决"]), "依据": str(item.get("依据") or "").strip() or "主会话裁决"}
        owner = str(item.get("owner") or "none")
        if owner in sp.REVIEW_OWNERS[kind]:
            row = diffs_by_id.get(did) or {}
            fixes.setdefault(owner, []).append({"id": did, "severity": "diff", "title": row.get("描述"), "location": row.get("页码"), "detail": f"裁决 {item['裁决']}：{diff_rulings[did]['依据']}"})
    if problems:
        return problems, {}
    review = _extreview()
    if rulings:
        review.write_responses(engine.root, engine.report_id, kind, rulings)
    if diff_rulings:
        review.write_extract_diff(engine.root, engine.report_id, diff_rulings)
    for dispute in disputes:
        cps.open_human(
            txn,
            ctx,
            "critical_dispute",
            reason=f"{dispute['id']} 是 critical，编排者认为应当 {dispute['choice']}：{dispute['reply'][:200]}",
            stage=stage,
            payload={"kind": kind, "step": sid, **dispute},
        )
    return [], {"ruled": len(rulings) + len(diff_rulings), "fixes": fixes, "recheck": recheck, "disputed": [d["id"] for d in disputes]}


def _receipt_only_hint(rec: dict[str, Any]) -> str:
    """回执有毛病而活已经干完时写给接手者的话：重干一遍是这类重派里最贵、也最没必要的事。"""
    return (
        f"**交回的文件和代码不用重做。** 上一次的回执在 `{rec.get('receipt')}`：以它为底稿，只把上面指出的地方改对，"
        "写到这次的回执路径（见下面「回执」一节）；其余内容原样照抄。"
    )


def _step_usage(ctx: Ctx, sid: str, rec: dict[str, Any], manifest: Optional[dict[str, Any]] = None) -> tuple[Optional[dict[str, Any]], list[str]]:
    """从宿主的会话记录里找这一步对应的子 agent（派发描述等于步骤编号），读出用量，并核对它有没有碰禁读清单。

    返回（用量, 碰过的禁读路径）。找不到会话记录就都是空的。
    """
    if os.environ.get("REPRODUCE_NO_USAGE"):
        return None, []
    try:
        from . import usage as us

        since = ev.parse_ts(rec.get("issued_at"))
        if since is None:
            return None, []
        # 派发描述等于步骤编号只在一个案例里唯一：同一个工作区并行跑两个案例时两边都有 extract.main。
        # 所以还要求会话里出现过这一步自己的任务文件路径（派发提示词和读文件调用里都有它）。
        task_file = str((manifest or {}).get("task_file") or "")
        needle = task_file or sid

        def wanted(label: Optional[str]) -> bool:
            return bool(label) and step_key(str(label)) == sid

        found = None
        if ctx.host in ("claude_code", "generic"):
            paths = sorted(us.find_claude_transcripts(ctx.root), key=lambda p: p.stat().st_mtime, reverse=True)[:60]
            for path in paths:
                stat = path.stat()
                if stat.st_mtime < since.timestamp() - 5 or stat.st_size > 40 * 1024 * 1024:
                    continue
                if not wanted(us.claude_transcript_label(path)):
                    continue  # 派发描述在元数据文件里，对不上的不必打开会话记录
                parsed = us.parse_claude_transcript(path, needle=needle)
                if not task_file or parsed.mentions:
                    found = parsed
                    break
        if found is None and ctx.host in ("codex", "generic"):
            for path in us.find_codex_sessions(since, None):
                parsed = us.parse_codex_session(path, needle=needle, only_label=wanted)
                if wanted(parsed.label) and (not task_file or parsed.mentions):
                    found = parsed
                    break
        if found is None:
            return None, []
        usage = found.usage.to_dict()
        usage["tool_calls"] = sum(found.tools.values())
        usage["model"] = found.model
        forbid = [f for f in (manifest or {}).get("forbid") or [] if not f.endswith("/flow/tasks/") and not f.endswith("/flow/receipts/")]
        allowed = [p for p in ((manifest or {}).get("task_file"), rec.get("receipt")) if p]
        violations = us.forbidden_reads(Path(found.path), found.host, forbid, allowed)
        return usage, violations
    except Exception:  # noqa: BLE001 - 计量只是增强，出任何问题都不该影响点收
        return None, []


# ---------------------------------------------------------------------------
# 各阶段的门禁收口
# ---------------------------------------------------------------------------


def _explain_inline(failed: list[str]) -> str:
    """未过检查项各自的处理说明（没有单独成段的不附）。说明只是辅助，取不到不影响推进。"""
    try:
        from . import explain

        return explain.inline(failed)
    except Exception:  # noqa: BLE001
        return ""


def _detail(evaluation: cg.GateEvaluation) -> str:
    return "\n".join(cg.format_check(c) for c in evaluation.failed())


def _close_default(engine: Engine, txn: st.Txn, ctx: Ctx, stage: str, evaluation: cg.GateEvaluation, failed: list[str], breaker: Any) -> None:
    if evaluation.passed:
        engine.finish_stage(txn, ctx, stage)
        return
    if breaker is not None:
        return
    detail = _detail(evaluation)
    remedy = GATE_REMEDIES.get(stage)
    plan = remedy(ctx, set(failed)) if remedy else [("redo", {"step": f"{stage}.gatefix", "role": sp.GATEFIX_ROLE.get(stage)})]
    engine.gate_remedy(txn, ctx, stage, failed, detail, plan)


def _close_verify(engine: Engine, txn: st.Txn, ctx: Ctx, stage: str, evaluation: cg.GateEvaluation, failed: list[str], breaker: Any) -> None:
    stats = ks.recalc(ctx)
    if evaluation.passed:
        ks.set_verdict(txn, ctx, "pass", stats)
        engine.finish_stage(txn, ctx, "verify")
        if ctx.stage_status("iterate") not in ("done", "skipped"):
            st.set_stage_in(txn, "iterate", "skipped")
        return
    if set(failed) == {"G-VF-3"}:
        # 只有指标超差：这是进入迭代的设计路径，验证阶段本身算做完
        ks.set_verdict(txn, ctx, "partial", stats)
        engine.finish_stage(txn, ctx, "verify")
        return
    if breaker is None:
        _close_default(engine, txn, ctx, stage, evaluation, failed, breaker)


def _close_report(engine: Engine, txn: st.Txn, ctx: Ctx, stage: str, evaluation: cg.GateEvaluation, failed: list[str], breaker: Any) -> None:
    if not evaluation.passed:
        _close_default(engine, txn, ctx, stage, evaluation, failed, breaker)
        return
    st.set_stage_in(txn, "report", "done")
    st.set_stage_in(txn, "review", "running")
    cps.open_human(txn, ctx, "final_review", reason="报告已出，等你评审：通过、修改假设后重跑，或回退", stage="review")


def _close_code_audit(engine: Engine, txn: st.Txn, ctx: Ctx, stage: str, evaluation: cg.GateEvaluation, failed: list[str], breaker: Any) -> None:
    if evaluation.passed:
        for m in ctx.milestones:
            if m.get("code_review") == "pending":
                st.milestone_in(txn, str(m["id"]), "code_review", "done" if ctx.difficulty != "easy" or ctx.is_ml else "skipped")
    _close_default(engine, txn, ctx, stage, evaluation, failed, breaker)


CLOSERS: dict[str, Callable[..., None]] = {"verify": _close_verify, "report": _close_report, "code_audit": _close_code_audit}


def _remedy_extract(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
    return [("redo", {"step": "extract.main"})]


def _remedy_plan(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
    if "G-PL-9" in failed:
        return [("checkpoint", {"name": "feasibility_blocked", "reason": "plan 判定可行性为 blocked：核心数据缺失或核心方法无法确定"})]
    if "G-PL-8" in failed:
        return [("checkpoint", {"name": "blocking_ambiguity", "reason": "还有 blocking 级歧义没有裁决，见 spec/ambiguities.md"})]
    if failed <= {"G-PL-10", "G-PL-11"}:
        return [("invalidate", {"prefix": "plan.datacheck@"})]
    return [("redo", {"step": "plan.main"})]


def _remedy_review(stage: str) -> Callable[[Ctx, set[str]], list[tuple[str, dict[str, Any]]]]:
    def remedy(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
        rnd = sp.review_round(ctx, sp.REVIEW_KIND[stage])
        plan: list[tuple[str, dict[str, Any]]] = []
        if stage == "spec_audit" and "G-SA-2" in failed:
            plan.append(("redo", {"step": "spec_audit.internal", "role": "quant-auditor"}))
        if stage == "code_audit" and failed & {"G-CA-2", "G-CA-3"}:
            plan += [("redo", {"step": "code_audit.gatefix", "role": "quant-coder"}), ("redo", {"step": "code_audit.internal", "role": "quant-auditor"})]
        if stage == "result_audit" and "G-RA-3" in failed:
            plan.append(("redo", {"step": "result_audit.gatefix", "role": "quant-diagnoser"}))
        if stage == "result_audit" and "G-RA-4" in failed:
            plan.append(("redo", {"step": "result_audit.gatefix", "role": "quant-verifier"}))
        plan.append(("invalidate", {"prefix": f"{stage}.collect.r{rnd}@"}))
        return plan

    return remedy


def _remedy_verify(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
    plan: list[tuple[str, dict[str, Any]]] = []
    if failed & {"G-VF-1", "G-VF-2"}:
        plan.append(("redo", {"step": "verify.gatefix", "role": "quant-coder"}))
    plan.append(("redo", {"step": "verify.main", "role": "quant-verifier"}))
    return plan


def _remedy_oos(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
    return [("redo", {"step": "oos.main", "role": "quant-oos-analyst"})]


def _remedy_report(ctx: Ctx, failed: set[str]) -> list[tuple[str, dict[str, Any]]]:
    if failed <= {"G-FN-7", "G-FN-6"}:
        return [("invalidate", {"prefix": "report.assemble@"}), ("invalidate", {"prefix": "report.stats@"})]
    if failed & {"G-FN-3", "G-FN-4"}:
        return [("invalidate", {"prefix": "report.precheck@"})]
    return [("redo", {"step": "report.main", "role": "quant-reporter"})]


GATE_REMEDIES: dict[str, Callable[[Ctx, set[str]], list[tuple[str, dict[str, Any]]]]] = {
    "extract": _remedy_extract,
    "plan": _remedy_plan,
    "spec_audit": _remedy_review("spec_audit"),
    "code_audit": _remedy_review("code_audit"),
    "result_audit": _remedy_review("result_audit"),
    "verify": _remedy_verify,
    "oos": _remedy_oos,
    "report": _remedy_report,
}


# ---------------------------------------------------------------------------
# 内核动作（步骤表里以名字引用）
# ---------------------------------------------------------------------------


def _act_plan_seed(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    engine._mark_kernel(txn, key, ks.seed_plan(txn, ctx))


def _act_plan_datacheck(engine: Engine, txn: st.Txn, ctx: Ctx, key: str, stage: str = "plan") -> None:
    """数据需求体检。plan 阶段做一次；implement 入口发现数据需求在体检之后改过，再做一次。"""
    from . import datacheck

    if stage != "plan":
        current = datacheck.load_check(engine.root, engine.report_id) or {}
        if current.get("plan_hash") == datacheck.plan_requirements_hash(engine.root, engine.report_id) and not datacheck.open_gaps(current):
            engine._mark_kernel(txn, key, {"fresh": True})
            return
    try:
        result = datacheck.check_requirements(engine.root, engine.report_id)
        datacheck.save_check(engine.root, engine.report_id, result)
        result = _carry_drop(engine, result)
    except Exception as exc:  # noqa: BLE001 - 体检本身出错不该把案例卡死，记下来继续（门禁会如实判未过）
        engine._mark_kernel(txn, key, {"error": str(exc)[:300]})
        engine.note(f"数据需求体检没有跑成：{exc}")
        return
    gaps = datacheck.open_gaps(result)
    summary = dict(result.get("summary") or {})
    bounce = [g for g in gaps if g.get("status_plan") in ("available", "derive")] if stage == "plan" else []
    counters = txn.state["counters"].setdefault("redispatch", {})
    if bounce and not counters.get("plan.main:datacheck"):
        counters["plan.main:datacheck"] = 1
        engine._mark_kernel(txn, key, {**summary, "bounced": [g.get("name") for g in bounce]})
        engine.redo(
            txn,
            ctx,
            "plan.main",
            "有数据需求标了可得，但机器体检不满足",
            datacheck.render_gap_report(result, only_open=True) + "\n\n按实测结果修改 data_requirements 的 status 与可行性判定；确实缺的如实标 missing。",
            count=False,
        )
        return
    engine._mark_kernel(txn, key, summary)
    if gaps:
        cp = cps.open_human(
            txn,
            ctx,
            "data_gap",
            reason=f"复现要用的数据有 {len(gaps)} 处缺口，需要你决定怎么处置",
            stage=stage,
            payload={"gaps": [g.get("name") for g in gaps], "gap_report": datacheck.render_gap_report(result, only_open=True), "on_missing": ctx.policy.get("on_missing")},
        )
        if ctx.policy.get("on_missing") == "mock" and not ctx.trial:
            # 启动时预先声明过「数据缺口先用 mock 试跑」：照办并留痕，凭据等级记为预先声明
            from . import decisions

            quote = "启动时预先声明：数据缺口先用 mock 试跑（--on-missing mock）"
            st.resolve_checkpoint_in(txn, cp, choice="mock", quote=quote, credential="policy", by="policy", resume_status="running")
            engine.note(decisions._decide_data_gap(engine, txn, ctx, cp, "mock", quote))


def _carry_drop(engine: Engine, result: dict[str, Any]) -> dict[str, Any]:
    """人已经决定「砍掉相关要素」的需求，planner 按决定把它改标成 missing 之后缺口的样子变了，决定照样延续，不再问一遍。

    其余处置（替代、缩小范围）改完之后若还有缺口，那是新的缺口，要重新问。
    """
    from . import datacheck

    carried = [
        e
        for e in result.get("requirements") or []
        if e.get("result") in datacheck.GAP_RESULTS and not e.get("disposition") and (e.get("cleared_disposition") or {}).get("choice") == "drop"
    ]
    for entry in carried:
        old = entry["cleared_disposition"]
        result = datacheck.set_disposition(engine.root, engine.report_id, [entry["name"]], "drop", checkpoint=str(old.get("checkpoint") or ""), note=str(old.get("note") or ""))
    return result


def _act_mock_generate(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    result = generate_mock(ctx)
    engine._mark_kernel(txn, key, result)
    if result.get("errors"):
        engine.redo(txn, ctx, "plan.mock_spec", "mock 规格不合法", "\n".join(result["errors"]))
        return
    cp = cps.open_human(
        txn,
        ctx,
        "mock_spec",
        reason="mock 数据已按规格生成，请确认规格后开始试跑（试跑不出结论）",
        stage="plan",
        payload={"spec": f"{ctx.ws}/data_mock/spec.yaml", "manifest": f"{ctx.ws}/data_mock/manifest.json", "tables": result.get("tables")},
    )
    if ctx.policy.get("on_missing") == "mock":
        # 预先声明过用 mock：规格不停下等确认，试跑做完再一并给人看（试跑不出结论）
        st.resolve_checkpoint_in(txn, cp, choice="approve", quote="启动时预先声明：数据缺口先用 mock 试跑（--on-missing mock）", credential="policy", by="policy", resume_status="running")


def generate_mock(ctx: Ctx) -> dict[str, Any]:
    """按 data_mock/spec.yaml 生成模拟数据并打开试跑标记。"""
    from tools import mockdata

    from . import datacheck

    base = ctx.path(f"{ctx.ws}/data_mock")
    spec_path = base / "spec.yaml"
    try:
        spec = mockdata.load_spec(spec_path)
        errors = mockdata.validate_spec(spec)
    except Exception as exc:  # noqa: BLE001
        return {"errors": [f"规格读不出来：{exc}"]}
    if errors:
        return {"errors": errors}
    try:
        manifest = mockdata.generate(spec, base / "files", datacheck.resolve_data_root(ctx.root), root=ctx.root, spec_path=spec_path, report_id=ctx.report_id)
    except Exception as exc:  # noqa: BLE001
        return {"errors": [f"生成失败：{exc}"]}
    write_text(base / "ACTIVE", f"mock 试跑中（{st.now_iso()}）。删除本文件即回到真实数据。\n")
    tables = [t.get("name") for t in manifest.get("tables") or [] if isinstance(t, dict)] if isinstance(manifest, dict) else []
    return {"tables": tables}


def _review_engine_state(ctx: Ctx, stage: str, rnd: int) -> tuple[str, str]:
    """这一轮外审最终是谁做的：（引擎状态, 说明）。"""
    ext = ctx.rec(f"{stage}.ext.r{rnd}") or {}
    result = ext.get("result") or {}
    if result.get("state") == "success":
        return str(ext.get("engine_state") or "codex_external"), ""
    if not ext.get("job_id"):
        return "skipped", f"外审任务没有准备出来（{str(ext.get('prepare_error') or result.get('reason'))[:200]}），这一轮外审记为跳过"
    fallback = ctx.rec(f"{stage}.ext.r{rnd}.fallback") or {}
    if fallback.get("status") == DONE and (fallback.get("result") or {}).get("accepted"):
        return "same_host_fallback", f"外部引擎失败（{result.get('reason')}），由同宿主替身完成"
    return "skipped", f"外部引擎失败（{result.get('reason')}），替身也没有完成"


def _act_review_collect(engine: Engine, txn: st.Txn, ctx: Ctx, kind: str, stage: str, round: int, key: str, skipped: bool = False, reason: str = "") -> None:
    review = _extreview()
    if skipped:
        res = review.skip(engine.root, engine.report_id, kind, reason or "按审计档位不触发")
        engine_state = "skipped"
    else:
        engine_state, why = _review_engine_state(ctx, stage, round)
        if engine_state == "skipped":
            res = review.skip(engine.root, engine.report_id, kind, why)
        else:
            res = review.collect(engine.root, engine.report_id, kind, engine_state=engine_state)
        if why:
            engine.note(why)
    ledger = dict(res.get("ledger") or {}, rounds=res.get("rounds"))
    if ((ctx.rec(f"{stage}.ext.r{round}") or {}).get("result") or {}).get("blind_read_spec"):
        ledger["blind_read_spec"] = True
    reviews = [r for r in txn.state.get("external_reviews") or [] if not (isinstance(r, dict) and r.get("checkpoint") == kind)]
    st.set_in(txn, "external_reviews", reviews + [ledger])
    diffs: dict[str, Any] = {"rows": [], "unruled": []}
    if kind == "spec":
        diffs = review.write_extract_diff(engine.root, engine.report_id)
    responses = review.write_responses(engine.root, engine.report_id, kind)
    findings = res.get("findings") or []
    # 上一轮接受过、这一轮仍未闭环的 critical：沿用上一轮的属主继续修
    carry: dict[str, list[dict[str, Any]]] = {}
    previous = ctx.result_of(f"{stage}.rule.r{round - 1}") if round > 1 else {}
    owner_of = {item.get("id"): role for role, items in (previous.get("fixes") or {}).items() for item in items}
    by_id = {f.get("id"): f for f in findings}
    for fid in responses.get("open_critical") or []:
        if fid in (responses.get("unruled") or []):
            continue
        role = owner_of.get(fid) or sp.REVIEW_OWNERS[kind][0]
        finding = by_id.get(fid) or {"id": fid}
        carry.setdefault(role, []).append({**{k: finding.get(k) for k in ("id", "severity", "title", "location", "detail")}, "reply": "上一轮已接受，复审认为仍未闭环"})
    write_json(
        ctx.path(f"{ctx.ws}/flow/answers/{stage}.findings.r{round}.json"),
        {"findings": findings, "unruled": responses.get("unruled") or [], "diffs": diffs.get("rows") or [], "unruled_diffs": diffs.get("unruled") or []},
    )
    result = {
        "engine_state": engine_state,
        "verdict": res.get("verdict"),
        "counts": res.get("counts"),
        "findings": len(findings),
        "unruled": responses.get("unruled") or [],
        "unruled_diffs": diffs.get("unruled") or [],
        "open_critical": responses.get("open_critical") or [],
        "carry_fixes": carry,
    }
    txn.state["stages"][stage]["issues"] = len(findings)
    engine._mark_kernel(txn, key, result)
    txn.log(f"review:{kind}:collected", {"round": round, "engine": engine_state, "verdict": res.get("verdict"), "counts": res.get("counts")})


def _act_review_responses(engine: Engine, txn: st.Txn, ctx: Ctx, kind: str, stage: str, round: int, key: str) -> None:
    """修复做完后，把修复回执的说明补进回应表的「回应」列。"""
    ruling = ctx.result_of(f"{stage}.rule.r{round}")
    updates: dict[str, dict[str, str]] = {}
    for role, items in (ruling.get("fixes") or {}).items():
        fix = ctx.rec(f"{stage}.fix.{sp.OWNER_SHORT[role]}.r{round}") or {}
        summary = str(fix.get("summary") or "").strip()
        for item in items:
            fid = str(item.get("id"))
            if summary and fid.startswith("CDX-"):
                updates[fid] = {"回应": f"{item.get('reply') or ''}；修复：{summary}"[:600]}
    if updates:
        _extreview().write_responses(engine.root, engine.report_id, kind, updates)
    engine._mark_kernel(txn, key, {"updated": sorted(updates)})


def _act_review_next_round(engine: Engine, txn: st.Txn, ctx: Ctx, kind: str, stage: str, round: int, key: str) -> None:
    txn.state["counters"].setdefault("review_rounds", {})[kind] = round + 1
    engine._mark_kernel(txn, key, {"next": round + 1})
    engine.note(f"{STAGE_CN.get(stage, stage)}进入第 {round + 1} 轮（差量复审）")


def _act_code_audit_prep(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    signatures = ks.write_common_signatures(ctx)
    engine._mark_kernel(txn, key, {"signatures": signatures, **ks.static_prescreen(ctx)})


def _act_verify_fresh(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    """验证派出去之后代码有没有再改（与代码审计并行的预跑最容易遇到）；改过就作废重跑。"""
    rec = ctx.rec("verify.main") or {}
    current = src_fingerprint(engine.root, engine.report_id)
    if rec.get("src_sha") and current and rec["src_sha"] != current:
        engine.redo(txn, ctx, "verify.main", "验证派出之后代码又改过，之前的验证产物作废", "整批重出结果目录的全部产物。", count=False)
        return
    engine._mark_kernel(txn, key, {"src_sha": current})


def _act_oos_fresh(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    """样本外分析（常与结果审计并行）开工之后，代码或对比结果有没有再变；变了就作废重做。"""
    rec = ctx.rec("oos.main") or {}
    base = rec.get("baseline") or {}
    now = {"src": src_fingerprint(engine.root, engine.report_id), "comparison": ks.comparison_digest(ctx)}
    changed = [name for name in ("src", "comparison") if base.get(name) and now.get(name) and base[name] != now[name]]
    if changed:
        what = "、".join({"src": "策略代码", "comparison": "对比结果"}[c] for c in changed)
        engine.redo(txn, ctx, "oos.main", f"样本外分析开工之后{what}又改过，之前的样本外产物作废", "在当前的代码与对比结果上整批重做样本外分析。", count=False)
        return
    engine._mark_kernel(txn, key, now)


def _act_verify_trial(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    result = ks.trial_check(ctx)
    engine._mark_kernel(txn, key, result)
    if not result["ok"]:
        problems = []
        if not result["ran"]:
            problems.append("run_log.md 里没有 exit=0")
        if result["missing"]:
            problems.append("产物不全：" + "、".join(result["missing"]))
        if result["empty_metrics"]:
            problems.append("这些指标算不出来：" + "、".join(result["empty_metrics"][:20]))
        del engine._steps(txn.state)[key]
        engine.redo(txn, ctx, "verify.main", "试跑没有通过三项检查", "\n".join(problems))


def _act_verify_blocks(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    """把机器生成的对比总表与产物清单嵌进 verify_report.md（只对 v3 新建案例做）。"""
    info: dict[str, Any] = {}
    path = ctx.path(f"{ctx.out}/verify_report.md")
    if ctx.created_by_kernel and path.is_file():
        try:
            from . import precheck

            text = path.read_text(encoding="utf-8")
            text = ks.upsert_block(text, "comparison_table", ks.comparison_block(ctx))
            text = ks.upsert_block(text, "artifacts", precheck.artifacts_table(engine.root, engine.report_id))
            fragments = sorted(ctx.path(f"{ctx.out}/verify_fragments").glob("*.md")) if ctx.path(f"{ctx.out}/verify_fragments").is_dir() else []
            if fragments:
                body = "\n\n".join(f"### {p.stem}\n\n{p.read_text(encoding='utf-8').strip()}" for p in fragments)
                text = ks.upsert_block(text, "milestone_fragments", "## milestone 级验证记录\n\n" + body)
            write_text(path, text)
            info["blocks"] = True
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)[:300]
    engine._mark_kernel(txn, key, info)


def _act_iterate_open(engine: Engine, txn: st.Txn, ctx: Ctx, round: int, key: str) -> None:
    st.set_in(txn, "iteration.current", round)
    ctx.path(ks.iter_dir(ctx, round)).mkdir(parents=True, exist_ok=True)
    ks.snapshot_comparison(ctx, round, before=True)
    digest = None
    if ctx.iterate_digest != "off":
        try:
            digest = ks.write_iterate_digest(ctx, round)
        except Exception as exc:  # noqa: BLE001 - 摘要只是辅助，生成不了就照旧整读历史
            engine.note(f"第 {round} 轮的诊断摘要没有生成：{exc}")
    engine._mark_kernel(txn, key, {"round": round, "before": ks.recalc(ctx)["pass"], "digest": digest})


def _act_iterate_close(engine: Engine, txn: st.Txn, ctx: Ctx, round: int, mode: str, key: str) -> None:
    gen = ctx.generation
    before = ctx.result_of(f"iterate.open.r{round}@g{gen}").get("before")
    diagnose = ctx.rec(f"iterate.r{round}.diagnose") or {}
    fix = ctx.rec(f"iterate.r{round}.fix") or {}
    if mode == "stop":
        stats = ks.recalc(ctx)
        ks.append_iteration_log(ctx, round, {"trigger": "验证超差", "fails": "、".join(stats["fails"][:6]), "hypothesis": diagnose.get("summary", ""), "changes": "（未改代码）", "result": f"达标 {stats['pass']}/{stats['total']}", "status": "stop_partial"})
        _history(txn, round, "stop_partial", before, stats)
        ks.set_verdict(txn, ctx, "partial", stats)
        engine._mark_kernel(txn, key, {"outcome": "partial"})
        return
    ks.snapshot_comparison(ctx, round)
    evaluation = cg.evaluate(engine.root, engine.report_id, "verify")
    failed = {c.id for c in evaluation.failed()}
    breaker = st.gate_in(txn, "verify", evaluation.verdict, evaluation.to_record(with_detail=True))
    stats = ks.recalc(ctx)
    structural = failed - {"G-VF-3"}
    if structural:
        if breaker is None:
            detail = _detail(evaluation)
            if structural & {"G-VF-1", "G-VF-2"}:
                engine.redo(txn, ctx, f"iterate.r{round}.fix", "重跑验证时程序没有跑通", detail)
            engine.redo(txn, ctx, f"iterate.r{round}.verify", "验证产物没有过结构性检查", detail, count=not (structural & {"G-VF-1", "G-VF-2"}))
        return
    max_iter = int((txn.state.get("iteration") or {}).get("max") or 0) or 3
    outcome = "pass" if evaluation.passed else ("next" if round < max_iter else "exhausted")
    ks.append_iteration_log(
        ctx,
        round,
        {
            "trigger": "验证超差",
            "fails": "、".join(stats["fails"][:6]) or "无",
            "hypothesis": diagnose.get("summary", ""),
            "changes": fix.get("summary", ""),
            "result": f"达标 {before}→{stats['pass']}/{stats['total']}",
            "status": {"pass": "达标", "next": "继续下一轮", "exhausted": "到达轮数上限"}[outcome],
        },
    )
    _history(txn, round, "continue", before, stats)
    if outcome == "pass":
        ks.set_verdict(txn, ctx, "pass", stats)
    else:
        ks.set_verdict(txn, ctx, "partial", stats)
    engine._mark_kernel(txn, key, {"outcome": outcome, "pass": stats["pass"], "total": stats["total"]})
    engine.note(f"迭代第 {round} 轮：达标 {before}→{stats['pass']}/{stats['total']}，{'已达标' if outcome == 'pass' else ('进入下一轮' if outcome == 'next' else '到达轮数上限，转收尾归因')}")
    if txn.state.get("policy", {}).get("step") or ctx.mode == "interactive" and outcome == "next":
        cps.open_human(txn, ctx, "iterate_round", reason=f"迭代第 {round} 轮结束：达标 {before}→{stats['pass']}/{stats['total']}", stage="iterate", payload={"round": round})


def _history(txn: st.Txn, round: int, conclusion: str, before: Any, stats: dict[str, Any]) -> None:
    history = list((txn.state.get("iteration") or {}).get("history") or [])
    history = [h for h in history if not (isinstance(h, dict) and h.get("round") == round and h.get("trigger") != "revise")]
    history.append({"round": round, "trigger": "verify", "conclusion": conclusion, "pass_before": before, "pass_after": stats["pass"], "total": stats["total"], "at": st.now_iso()})
    st.set_in(txn, "iteration.history", history, log=False)
    txn.log("set:iteration.history", {"round": round, "conclusion": conclusion})


def _act_iterate_finish(engine: Engine, txn: st.Txn, ctx: Ctx, result: str, key: str) -> None:
    ks.set_verdict(txn, ctx, result, ks.recalc(ctx))
    engine._mark_kernel(txn, key, {"result": result})


def _act_step_redo(engine: Engine, txn: st.Txn, ctx: Ctx, step: str, reason: str, key: Optional[str] = None) -> None:
    engine.redo(txn, ctx, step, reason)


def _act_result_precheck(engine: Engine, txn: st.Txn, ctx: Ctx, fix_step: str, key: str) -> None:
    from . import precheck

    try:
        result = precheck.run_precheck(engine.root, engine.report_id, stage="result")
    except Exception as exc:  # noqa: BLE001
        engine._mark_kernel(txn, key, {"error": str(exc)[:300]})
        return
    summary = {"blocked": result.blocked, "block": result.stats.get("block"), "warn": result.stats.get("warn"), "file": ks.save_precheck(ctx, result)}
    txn.log("precheck:result", summary)
    if result.blocked:
        if engine.redo(txn, ctx, fix_step, "结果一致性预检没过（文书与机器结果对不上）", result.render(), stage="result_audit", role="quant-verifier"):
            return
    elif result.findings and not _attempts(ctx, fix_step):
        # 只有提示（多半是旧轮残留的数）：让验证者清一轮，改掉或标注为历史记录；清不清得干净都不挡外审
        detail = result.render() + "\n\n这些只是提示：确认是旧数的改掉或在同一行标注为历史记录；核对后确实没问题的不用改，在回执里说明。"
        if engine.redo(txn, ctx, fix_step, "结果一致性预检有提示（疑似旧数值残留）", detail, count=False, stage="result_audit", role="quant-verifier"):
            return
    engine._mark_kernel(txn, key, summary)


def _attempts(ctx: Ctx, step_id: str) -> int:
    return int((ctx.rec(step_id) or {}).get("attempt") or 0)


def _act_report_consistency(engine: Engine, txn: st.Txn, ctx: Ctx, main: str, fix_step: str, key: str) -> None:
    """报告写完、生成块嵌入之后：两份文书里手写的计数和数值与机器结果再核一遍。

    报告里的问题退回报告者改；验证文书或对比表的问题退回验证者改，改完报告的生成块重新嵌入。提示只留痕。
    """
    from . import precheck

    try:
        result = precheck.run_precheck(engine.root, engine.report_id, stage="report")
    except Exception as exc:  # noqa: BLE001
        engine._mark_kernel(txn, key, {"error": str(exc)[:300]})
        return
    summary = {"blocked": result.blocked, "block": result.stats.get("block"), "warn": result.stats.get("warn"), "file": ks.save_precheck(ctx, result)}
    txn.log("precheck:report", summary)

    def listing(items: list[Any]) -> str:
        return "\n".join(f"- {f.check} {f.message}" + (f"（{f.where}）" if f.where else "") for f in items)

    blocks = [f for f in result.findings if f.level == "block"]
    report_rel = f"{ctx.ws}/final_report.md"
    elsewhere = [f for f in blocks if not str(f.where).startswith(report_rel)]
    if elsewhere:
        if engine.redo(txn, ctx, fix_step, "写完报告后的一致性预检没过（验证文书或对比表与机器结果对不上）", listing(elsewhere), stage="report", role="quant-verifier"):
            steps = engine._steps(txn.state)
            for sid in [s for s in steps if s.startswith("report.assemble@") and steps[s].get("kind") == "kernel"]:
                del steps[sid]
            return
    elif blocks:
        detail = listing(blocks) + "\n\n计数和指标数值以内核嵌入的对比块为准：正文里引用指标编号，不要另写一套数。"
        if engine.redo(txn, ctx, main, "报告里手写的计数或数值与机器结果对不上", detail):
            return
    if result.findings and not blocks:
        engine.note(f"报告的一致性预检有 {len(result.findings)} 条提示，见 {summary['file']}")
    engine._mark_kernel(txn, key, summary)


def _act_report_stats(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    stats = ks.coverage_stats(ctx)
    st.set_in(txn, "coverage_stats", stats)
    engine._mark_kernel(txn, key, stats)


def _act_report_precheck(engine: Engine, txn: st.Txn, ctx: Ctx, fix_step: str, key: str) -> None:
    """G-FN 输入侧的条件先由机器核一遍，全绿才派 reporter。"""
    rows = cg.load_matrix_rows(ctx.path(f"{ctx.ws}/spec/coverage_matrix.md"))
    pending = [cg._row_get(r, "要素ID") for r in rows if cg._row_get(r, "状态") in ("pending", "in_progress")]
    placeholders = [b.id for b in cg.parse_id_blocks(ctx.read(f"{ctx.ws}/assumptions.md")) if rc.PLACEHOLDER in str(b.fields.get("验证后回看") or "")]
    problems = []
    if pending:
        problems.append("覆盖矩阵里还没到终态的要素：" + "、".join(pending) + "（做完的填验证结果并改 done，确实不做的改 skipped / infeasible 并给状态理由）")
    if placeholders:
        problems.append("假设登记簿里「验证后回看」还是占位符的条目：" + "、".join(placeholders) + "（用 comparison.json 的实际数值各写一句回看）")
    if problems and engine.redo(txn, ctx, fix_step, "写报告前的预检没过", "\n".join(problems), stage="report", role="quant-verifier"):
        return
    engine._mark_kernel(txn, key, {"pending": pending, "placeholders": placeholders})


def _act_report_pre_checkpoint(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    engine._mark_kernel(txn, key)
    cps.open_human(txn, ctx, "pre_report", reason="验证与审计都做完了，写报告之前请你过目", stage="report")


def _act_report_digest(engine: Engine, txn: st.Txn, ctx: Ctx, key: str) -> None:
    nbytes = write_text(ctx.path(f"{ctx.ws}/flow/report_digest.md"), ks.report_digest(ctx))
    engine._mark_kernel(txn, key, {"bytes": nbytes})


def _act_report_assemble(engine: Engine, txn: st.Txn, ctx: Ctx, main: str, key: str) -> None:
    result = ks.assemble_report(ctx)
    st.set_in(txn, "assumptions", result["assumptions"])
    for note in result["notes"]:
        engine.note(note)
    engine._mark_kernel(txn, key, result)  # 嵌入之后的一致性预检是下一个动作（report.consistency）


ACTIONS: dict[str, Callable[..., None]] = {
    "plan.seed": _act_plan_seed,
    "implement.datacheck": _act_plan_datacheck,
    "plan.datacheck": _act_plan_datacheck,
    "plan.mock_generate": _act_mock_generate,
    "review.collect": _act_review_collect,
    "review.responses": _act_review_responses,
    "review.next_round": _act_review_next_round,
    "code_audit.prep": _act_code_audit_prep,
    "verify.fresh": _act_verify_fresh,
    "oos.fresh": _act_oos_fresh,
    "report.consistency": _act_report_consistency,
    "verify.trial": _act_verify_trial,
    "verify.blocks": _act_verify_blocks,
    "iterate.open": _act_iterate_open,
    "iterate.close": _act_iterate_close,
    "iterate.finish": _act_iterate_finish,
    "step.redo": _act_step_redo,
    "result_audit.precheck": _act_result_precheck,
    "report.stats": _act_report_stats,
    "report.precheck": _act_report_precheck,
    "report.pre_checkpoint": _act_report_pre_checkpoint,
    "report.digest": _act_report_digest,
    "report.assemble": _act_report_assemble,
}
