"""内核推进引擎的端到端测试：玩具案例 + 桩 agent + 真实门禁，从建案走到收尾。全程不花 token。

覆盖主路径（easy / medium / hard）、迭代的三个出口、外审的审裁修循环与降级链、
重派与受阻、门禁未过后的处置与连败熔断、各模式下的中途检查点。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_harness as fh  # noqa: E402
from tools import check_gates as cg  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import decisions  # noqa: E402
from tools.flowlib.core import FlowError  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: fh.Scenario | None = None, config: dict | None = None, **init) -> tuple[Path, str, fh.Stub]:
    root = fh.make_root(tmp_path, config)
    rid = fh.new_case(root, monkeypatch, **init)
    stub = fh.Stub(root, rid, scenario or fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    return root, rid, stub


def _stages(root: Path, rid: str) -> dict[str, str]:
    return {k: v["status"] for k, v in st.load_state(root, rid)["stages"].items()}


def _steps(stub: fh.Stub) -> list[str]:
    return [c.split("#")[0] for c in stub.calls]


# ---------------------------------------------------------------------------
# 主路径
# ---------------------------------------------------------------------------


def test_easy_case_runs_from_init_to_accept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch)
    out = fh.drive(root, rid, stub)

    # 走到最终评审就停：等待态下 next 只返回停机说明，不再派任何东西
    assert out["status"] == "awaiting_review" and out["orders"] == [] and out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert _steps(stub) == ["extract.main", "plan.main", "implement.m1.code", "verify.main", "result_audit.internal", "oos.main", "report.main"]
    stages = _stages(root, rid)
    assert stages["iterate"] == "skipped" and stages["review"] == "running"
    assert all(stages[s] == "done" for s in st.STAGE_ORDER if s not in ("iterate", "review"))
    state = st.load_state(root, rid)
    assert state["verdict"]["result"] == "pass" and state["verdict"]["metrics_pass"] == 2 and state["verdict"]["metrics_total"] == 2
    assert state["coverage_stats"]["total"] == 6 and state["ext"]["created_by"] == "flow"
    # 每个阶段的门禁都由内核在收口处跑过并入账，结论与现在直接重跑一致
    for stage in ("init", "extract", "plan", "spec_audit", "implement", "code_audit", "verify", "result_audit", "oos", "report"):
        assert state["gate_latest"][stage]["verdict"] == "PASS", stage
        assert cg.evaluate(root, rid, stage).passed, stage
    assert st.verify_event_chain(root, rid, state)["ok"]

    # 机器生成的内容嵌进了文书；报告里的假设登记簿是内核拼的
    report = (root / "workspace" / rid / "final_report.md").read_text(encoding="utf-8")
    assert "flow:generated comparison_table BEGIN" in report and "rank_ic_mean_mom" in report
    assert "flow:generated assumptions_register BEGIN" in report and "AS1" in report
    verify_report = (root / "output" / rid / "verify_report.md").read_text(encoding="utf-8")
    assert "flow:generated comparison_table BEGIN" in verify_report and "flow:generated artifacts BEGIN" in verify_report
    assert (root / "output" / rid / "final_report.html").stat().st_size > 5 * 1024
    # 回执里的回填由内核合并进了矩阵与登记簿
    matrix = (root / "workspace" / rid / "spec" / "coverage_matrix.md").read_text(encoding="utf-8")
    assert "strategy.py:momentum" in matrix and "与研报对上" in matrix and "| pending |" not in matrix
    assert "[verify 后填]" not in (root / "workspace" / rid / "assumptions.md").read_text(encoding="utf-8")

    # 收尾只能经 flow accept，并且要带人的原话
    engine = Engine(root, rid, host="claude_code")
    with pytest.raises(FlowError, match="原话"):
        decisions.accept(engine, "")
    result = decisions.accept(engine, "结果可以，收尾吧")
    assert result == {"status": "done", "credential": "self_report"}
    state = st.load_state(root, rid)
    assert state["status"] == "done" and state["stages"]["review"]["status"] == "done"
    assert state["checkpoints"][-1]["decision"]["quote"] == "结果可以，收尾吧"
    assert fh.drive(root, rid, stub)["halt"]["reason"] == "terminal"


def test_next_is_idempotent_and_orders_carry_the_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, _stub = _case(tmp_path, monkeypatch)
    engine = Engine(root, rid, host="claude_code")
    first = engine.advance()
    again = Engine(root, rid, host="claude_code").advance()
    assert first["orders"] == again["orders"] and len(first["orders"]) == 1
    order = first["orders"][0]
    assert order["step_id"] == "extract.main#1" and order["description"] == "extract.main" and order["role"] == "quant-extractor"
    assert order["kind"] == "dispatch" and order["contract"]["sha"] and "只回一行" in order["prompt_inline"]
    assert [e for e in fh.events(root, rid) if e.startswith("step:extract.main")] == ["step:extract.main:issued"]  # 没有重复派发
    task = (root / order["prompt_file"]).read_text(encoding="utf-8")
    assert "flow-task v1" in task and "spec/spec.md" in task and "## 回执" in task
    assert "不要读：`workspace/r001_toy/state.json`" in task
    assert "report_text.md" in task and "不要读：`workspace/r001_toy/spec/report_text.md`" not in task  # 提取角色可以读原文转写
    # 自己这一步的任务文件与回执不在禁读之列；没有上下文包的角色不提「取块命令」
    assert "不要读：`workspace/r001_toy/flow/tasks/`" not in task and "除你自己这一步以外的文件" in task
    assert "取块命令" not in task and "不要调用 `tools/` 下的任何脚本" in task
    state = st.load_state(root, rid)
    record = state["flow"]["steps"]["extract.main"]
    assert record["status"] == "inflight" and record["attempt"] == 1 and record["task_bytes"] == len(task.encode("utf-8"))
    manifest = json.loads((root / record["manifest"]).read_text(encoding="utf-8"))
    assert manifest["outputs"] == order["outputs"] and manifest["order"]["step_id"] == "extract.main#1"
    # 步骤编号带不带派发次数都能点收；没在途的步骤点收会被拒
    with pytest.raises(FlowError, match="没有步骤"):
        engine.done(["plan.main"])


def test_medium_case_pipelines_milestones_and_prerun_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)]))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps[:3] == ["extract.main", "plan.main", "spec_audit.internal"]  # medium 起有规格内审
    # 流水线深度 1：m1 写完就写 m2，m1 的验证与 m2 的编码同批
    assert steps.index("implement.m2.code") < steps.index("implement.m2.verify")
    assert steps.index("implement.m1.code") < steps.index("implement.m1.verify") < steps.index("code_audit.internal")
    assert steps.count("verify.main") == 1 and "result_audit.internal" not in steps  # 偏差不是全都小于 0.5%，不触发结果内审
    events = fh.events(root, rid)
    assert events.index("step:implement.m1.verify:issued") < events.index("step:implement.m2.code:done")
    # 最终验证是和代码内审一起预跑的：代码审计阶段就派出，验证阶段不再派
    assert events.index("step:verify.main:issued") < events.index("stage:code_audit:done") < events.index("stage:verify:running")
    state = st.load_state(root, rid)
    assert [(m["implement"], m["code_review"], m["verify"]) for m in state["milestones"]] == [("done", "done", "done")] * 2
    assert sorted(p.name for p in (root / "workspace" / rid / "audit").glob("impl_audit_m*.md")) == ["impl_audit_m1.md", "impl_audit_m2.md"]


def test_hard_case_audits_each_milestone_and_requires_perturbation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)]))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    for mid in ("m1", "m2", "m3"):
        assert {f"implement.{mid}.code", f"implement.{mid}.verify", f"implement.{mid}.audit"} <= set(steps)
    assert "code_audit.internal" not in steps and "result_audit.internal" in steps  # hard：内审逐 milestone 做过了，结果内审必做
    assert st.load_state(root, rid)["iteration"]["max"] == 6
    kinds = [(r["kind"], r["call"]) for r in stub.review_log]
    assert ("code", "main") in kinds and ("result", "main") in kinds and ("spec", "blind") in kinds and ("spec", "review") in kinds
    assert all(r["effort"] for r in stub.review_log)  # 每次外审都显式指定了推理强度


def test_parallel_orders_can_be_collected_in_any_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)]))
    out = fh.drive(root, rid, stub, until=lambda o: len([x for x in o["orders"] if x["kind"] == "dispatch"]) >= 2)
    orders = [o for o in out["orders"] if o["kind"] == "dispatch"]
    assert len({o["parallel_group"] for o in orders}) >= 1 and len(orders) >= 2
    engine = Engine(root, rid, host="claude_code")
    for order in reversed(orders):  # 倒着点收
        stub.run(order)
    results = engine.done([o["step_id"] for o in reversed(orders)], collect_usage=False)
    assert all(r["ok"] for r in results)
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"


# ---------------------------------------------------------------------------
# 迭代
# ---------------------------------------------------------------------------


def test_metric_gap_goes_through_iterate_until_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(verify_values=[(0.02, 0.04), (0.03, 0.04), (0.052, 0.041)], diagnose=["continue", "continue"])
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps[steps.index("verify.main") + 1 :][:6] == ["iterate.r1.diagnose", "iterate.r1.fix", "iterate.r1.verify", "iterate.r2.diagnose", "iterate.r2.fix", "iterate.r2.verify"]
    state = st.load_state(root, rid)
    assert state["iteration"]["current"] == 2 and state["verdict"]["result"] == "pass" and state["stages"]["iterate"]["status"] == "done"
    assert [(h["round"], h["pass_before"], h["pass_after"]) for h in state["iteration"]["history"]] == [(1, 1, 1), (2, 1, 2)]
    # 只有指标超差（G-VF-3 独败）是进入迭代的设计路径：不计连败、不熔断
    assert state["counters"]["gate_fail_streak"] == {} and not [c for c in state["checkpoints"] if c["name"] == "circuit_breaker"]
    log = (root / "workspace" / rid / "iterations" / "iteration_log.md").read_text(encoding="utf-8")
    assert "达标 1→1/2" in log and "达标 1→2/2" in log
    assert (root / "workspace" / rid / "iterations" / "iter_02" / "comparison.json").is_file()
    assert "已排除假设" in (root / "workspace" / rid / "iterations" / "iter_02" / "diagnosis.md").read_text(encoding="utf-8")
    # 第 2 轮起有异构第二意见（后台外审步骤，不是子 agent）
    assert any(r["kind"] == "second_opinion" for r in stub.review_log)
    assert fh.decide if True else None
    assert decisions.accept(Engine(root, rid, host="claude_code"), "通过")["status"] == "done"


def test_iterate_exhausted_ends_partial_with_attribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(verify_values=[(0.02, 0.04)]), max_iter=2)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps.count("iterate.r1.verify") == 1 and steps.count("iterate.r2.verify") == 1 and "iterate.r3.diagnose" not in steps
    assert "iterate.final.attribution" in steps
    state = st.load_state(root, rid)
    assert state["verdict"]["result"] == "partial" and state["iteration"]["current"] == 2
    comparison = json.loads((root / "output" / rid / "results" / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["metrics"][0]["attribution_status"] == "accepted"
    # 部分达标的案例照样做样本外，收尾状态是「部分达标」
    assert state["stages"]["oos"]["status"] == "done"
    assert decisions.accept(Engine(root, rid, host="claude_code"), "接受部分达标")["status"] == "done_partial"


def test_diagnoser_stop_partial_and_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(verify_values=[(0.02, 0.04)], diagnose=["stop_partial"]))
    fh.drive(root, rid, stub)
    steps = _steps(stub)
    assert "iterate.r1.diagnose" in steps and "iterate.r1.fix" not in steps  # 不再改代码
    state = st.load_state(root, rid)
    assert state["verdict"]["result"] == "partial" and state["stages"]["iterate"]["status"] == "done"
    assert state["iteration"]["history"][0]["conclusion"] == "stop_partial"

    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, fh.Scenario(verify_values=[(0.02, 0.04)], diagnose=["blocked", "stop_partial"]))
    out = fh.drive(root2, rid2, stub2)
    cp = out["halt"]["checkpoints"][0]
    assert out["status"] == "paused_blocked" and cp["name"] == "iterate_blocked"
    assert fh.drive(root2, rid2, stub2)["halt"]["checkpoints"][0]["id"] == cp["id"]  # 没人决定就一直停着
    result = fh.decide(root2, rid2, cp["id"], "continue", "缺的参数我补到 plan 里了，继续")
    assert result["status"] == "running"
    fh.drive(root2, rid2, stub2)
    assert "iterate.r2.diagnose" in _steps(stub2) and st.load_state(root2, rid2)["verdict"]["result"] == "partial"


# ---------------------------------------------------------------------------
# 外审：审 → 裁 → 修 → 复审，降级链
# ---------------------------------------------------------------------------


def test_review_findings_are_ruled_fixed_and_rechecked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(
        verify_values=[(0.052, 0.041)],
        reviews={
            "result": [
                [{"severity": "critical", "description": "verify_report 里的达标数与 comparison.json 不符"}, {"severity": "major", "description": "归因缺量级分解"}, {"severity": "minor", "description": "图注缺单位"}],
                [],
            ]
        },
        rulings={"CDX-R-02": {"处置": "rejected", "回应": "研报本身没有给分解口径", "owner": "none"}},
    )
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    i = steps.index("result_audit.rule.r1")
    assert steps[i + 1] == "result_audit.fix.verifier.r1"  # 主会话裁决之后，接受的意见交给属主角色修
    state = st.load_state(root, rid)
    assert state["counters"]["review_rounds"]["result"] == 2  # critical 修完要复审
    rounds = [(r["round"], r["call"]) for r in stub.review_log if r["kind"] == "result"]
    assert [r for r, _call in rounds] == [1, 2]
    responses = (root / "workspace" / rid / "audit" / "audit_responses.md").read_text(encoding="utf-8")
    rows = {row["意见ID"]: row for row in cg.parse_markdown_table_rows(responses) if row.get("意见ID", "").startswith("CDX-R-")}
    assert len(rows) == 3
    assert cg._row_get(rows["CDX-R-01"], "处置") == "accepted" and cg._row_get(rows["CDX-R-01"], "复核") == "pass"
    assert cg._row_get(rows["CDX-R-02"], "处置") == "rejected" and "分解口径" in cg._row_get(rows["CDX-R-02"], "回应")
    assert "桩 agent 完成" in cg._row_get(rows["CDX-R-01"], "回应")  # 修复回执的说明回填进了回应列
    ledger = [r for r in state["external_reviews"] if r["checkpoint"] == "result"]
    assert len(ledger) == 1 and ledger[0]["rounds"] == 2
    # rejected 的意见必须出现在报告里（G-FN-5）
    assert "CDX-R-02" in (root / "workspace" / rid / "final_report.md").read_text(encoding="utf-8")
    task = (root / "workspace" / rid / "flow" / "tasks" / "result_audit.fix.verifier.r1.1.md").read_text(encoding="utf-8")
    assert "CDX-R-01" in task and "CDX-R-03" in task and "CDX-R-02" not in task


def test_judge_answer_is_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(verify_values=[(0.052, 0.041)], reviews={"result": [[{"severity": "major", "description": "归因缺量级分解"}], []]})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    out = fh.drive(root, rid, stub, until=lambda o: any(x["kind"] == "judge" for x in o["orders"]))
    order = next(o for o in out["orders"] if o["kind"] == "judge")
    engine = Engine(root, rid, host="claude_code")
    assert engine.done([order["step_id"]])[0]["class"] == "incomplete"  # 没写答卷
    answer = root / order["answer_file"]
    answer.parent.mkdir(parents=True, exist_ok=True)
    answer.write_text(json.dumps({"findings": {"CDX-R-01": {"处置": "accepted", "回应": "", "owner": "quant-verifier"}}}), encoding="utf-8")
    assert "必须写回应" in engine.done([order["step_id"]])[0]["reasons"][0]
    answer.write_text(json.dumps({"findings": {"CDX-R-01": {"处置": "accepted", "回应": "补分解", "owner": "quant-reporter"}}}, ensure_ascii=False), encoding="utf-8")
    assert "owner" in engine.done([order["step_id"]])[0]["reasons"][0]
    answer.write_text(json.dumps({"findings": {"CDX-R-01": {"处置": "accepted", "回应": "补分解", "owner": "quant-verifier"}}}, ensure_ascii=False), encoding="utf-8")
    assert engine.done([order["step_id"]])[0]["ok"]
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    assert st.load_state(root, rid)["counters"]["review_rounds"].get("result", 1) == 1  # 没有 critical，不复审


def test_rejecting_a_critical_goes_to_a_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def scenario() -> fh.Scenario:
        return fh.Scenario(
            verify_values=[(0.052, 0.041)],
            reviews={"result": [[{"severity": "critical", "description": "核心指标缺对比条目"}], []]},
            rulings={"CDX-R-01": {"处置": "rejected", "回应": "该指标研报只有定性描述", "owner": "none"}},
        )

    root, rid, stub = _case(tmp_path, monkeypatch, scenario())
    out = fh.drive(root, rid, stub)
    cp = out["halt"]["checkpoints"][0]
    assert cp["name"] == "critical_dispute" and "CDX-R-01" in cp["reason"] and out["status"] == "paused_blocked"
    result = fh.decide(root, rid, cp["id"], "waive", "这条确实只有定性描述，意见不成立")
    assert "不成立" in result["message"]
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    responses = (root / "workspace" / rid / "audit" / "audit_responses.md").read_text(encoding="utf-8")
    assert "人工裁定意见不成立" in responses and "result_audit.fix.verifier.r1" not in _steps(stub)

    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, scenario())
    cp2 = fh.drive(root2, rid2, stub2)["halt"]["checkpoints"][0]
    fh.decide(root2, rid2, cp2["id"], "uphold", "意见成立，补上")
    assert fh.drive(root2, rid2, stub2)["halt"]["checkpoints"][0]["name"] == "final_review"
    assert "result_audit.fix.coder.r1" in _steps(stub2)  # 维持的 critical 交给属主修，并复审
    assert st.load_state(root2, rid2)["counters"]["review_rounds"]["result"] == 2


def test_review_rounds_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    critical = [{"id": "CDX-R-01", "severity": "critical", "description": "数值与机器结果不符"}]
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(verify_values=[(0.052, 0.041)], reviews={"result": [critical, critical, critical, critical, []]}))
    out = fh.drive(root, rid, stub)
    cp = out["halt"]["checkpoints"][0]
    assert cp["name"] == "review_rounds_exhausted" and st.load_state(root, rid)["counters"]["review_rounds"]["result"] == 3
    assert [r["round"] for r in stub.review_log if r["kind"] == "result"] == [1, 2, 3]
    fh.decide(root, rid, cp["id"], "retry", "再给它一轮")
    out = fh.drive(root, rid, stub)
    assert [r["round"] for r in stub.review_log if r["kind"] == "result"] == [1, 2, 3, 4, 5]
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"


def test_external_review_failure_falls_back_then_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(verify_values=[(0.052, 0.041)], review_fail={"result": ["timeout", "timeout"]}))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert "result_audit.ext.r1.fallback" in _steps(stub)
    efforts = [r["effort"] for r in stub.review_log if r["kind"] == "result"]
    assert len(efforts) == 2 and efforts[0] != efforts[1]  # 超时后降一档推理强度、原输入重试一次
    state = st.load_state(root, rid)
    ledger = next(r for r in state["external_reviews"] if r["checkpoint"] == "result")
    assert ledger["engine"] == "same_host_fallback"
    auto = [c for c in state["checkpoints"] if c["name"] == "external_degraded"]
    assert len(auto) == 1 and auto[0]["kind"] == "auto" and auto[0]["status"] == "resolved"  # 降级按策略自动放行，只留痕

    # 替身也做不了（报告受阻，或重派一次仍不交东西）：记为 skipped，流程继续，不为它惊动人
    for name, knobs in (("b", {"blocked": {"result_audit.ext.r1.fallback": 1}}), ("c", {"omit": {"result_audit.ext.r1.fallback": 9}})):
        scenario = fh.Scenario(verify_values=[(0.052, 0.041)], review_fail={"result": ["timeout", "timeout"]}, **knobs)
        root2, rid2, stub2 = _case(tmp_path / name, monkeypatch, scenario)
        assert fh.drive(root2, rid2, stub2)["halt"]["checkpoints"][0]["name"] == "final_review"
        state2 = st.load_state(root2, rid2)
        assert next(r for r in state2["external_reviews"] if r["checkpoint"] == "result")["engine"] == "skipped"
        assert not [c for c in state2["checkpoints"] if c["kind"] == "human" and c["name"] != "final_review"]
        assert cg.evaluate(root2, rid2, "result_audit").passed


# ---------------------------------------------------------------------------
# 重派、受阻、门禁未过、熔断
# ---------------------------------------------------------------------------


def test_missing_outputs_are_redispatched_within_a_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(omit={"plan.main": 1}))
    out = fh.drive(root, rid, stub, until=lambda o: any(x["step_id"] == "plan.main#2" for x in o["orders"]))
    task = (root / out["orders"][0]["prompt_file"]).read_text(encoding="utf-8")
    assert "这是重派" in task and "交回的东西不全" in task and "plan.md" in task
    state = st.load_state(root, rid)
    assert state["counters"]["redispatch"]["plan.main"] == 1
    assert [c["name"] for c in state["checkpoints"]] == ["redispatch"]  # 限额内的重派自动放行，但留痕
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"

    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, fh.Scenario(omit={"plan.main": 9}))
    out = fh.drive(root2, rid2, stub2)
    cp = out["halt"]["checkpoints"][0]
    assert cp["name"] == "redispatch_exhausted" and _steps(stub2).count("plan.main") == 3  # 首派 + 重派 2 次
    stub2.sc.omit = {}
    fh.decide(root2, rid2, cp["id"], "retry", "再派一次")
    assert fh.drive(root2, rid2, stub2)["halt"]["checkpoints"][0]["name"] == "final_review"


def test_blocked_step_waits_for_a_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(blocked={"implement.m1.code": 1}))
    out = fh.drive(root, rid, stub)
    cp = out["halt"]["checkpoints"][0]
    assert cp["name"] == "step_blocked" and "缺少外部输入" in cp["reason"]
    fh.decide(root, rid, cp["id"], "retry", "数据已经放好了，重试")
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    assert _steps(stub).count("implement.m1.code") == 2


def test_gate_failure_is_sent_back_with_the_gate_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def break_spec(stub: fh.Stub, order: dict) -> None:
        if stub.counts["extract.main"] == 1:  # 第一次交的 spec 少一个要素块，三方计数对不上
            path = stub.ws / "spec" / "spec.md"
            path.write_text(path.read_text(encoding="utf-8").replace("### [F2] 反转因子", "#### F2 反转因子"), encoding="utf-8")

    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(hooks={"extract.main": break_spec}))
    out = fh.drive(root, rid, stub, until=lambda o: any(x["step_id"] == "extract.main#2" for x in o["orders"]))
    task = (root / out["orders"][0]["prompt_file"]).read_text(encoding="utf-8")
    assert "提取门禁未过（G-EX-4）" in task and "正则=5 frontmatter=6 矩阵=6" in task
    state = st.load_state(root, rid)
    assert state["gate_latest"]["extract"]["verdict"] == "FAIL" and state["stages"]["extract"]["status"] == "running"
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    gates = [r["payload"]["verdict"] for r in st.read_event_records(root, rid) if r["event"] == "gate:extract"]
    assert gates == ["FAIL", "PASS"]


def test_three_consecutive_gate_failures_trip_the_breaker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def always_break(stub: fh.Stub, order: dict) -> None:
        path = stub.ws / "spec" / "spec.md"
        path.write_text(path.read_text(encoding="utf-8").replace("### [F2] 反转因子", "#### F2 反转因子"), encoding="utf-8")

    config = {"flow": {"redispatch_limit": {"gate:extract": 5}}}
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(hooks={"extract.main": always_break}), config=config)
    out = fh.drive(root, rid, stub)
    cp = out["halt"]["checkpoints"][0]
    assert cp["name"] == "circuit_breaker" and "G-EX-4 连续 3 次" in cp["reason"] and cp["pack"]
    assert _steps(stub).count("extract.main") == 3
    state = st.load_state(root, rid)
    assert state["counters"]["gate_fail_streak"] == {"extract:G-EX-4": 3} and state["status"] == "paused_blocked"
    # 熔断之后门禁即使转绿也不会自动放行：只有人能解除
    stub.sc.hooks = {}
    stub.extract({"description": "extract.main", "receipt": None}, 4)
    assert cg.evaluate(root, rid, "extract").passed
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["id"] == cp["id"]
    fh.decide(root, rid, cp["id"], "retry", "我看过了，spec 已经改好，继续")
    assert st.load_state(root, rid)["counters"]["gate_fail_streak"] == {}
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"


def test_milestone_verify_failure_sends_the_coder_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)], milestone_verify_fail={"m1": 1})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps.count("implement.m1.code") == 2 and steps.count("implement.m1.verify") == 2
    task = (root / "workspace" / rid / "flow" / "tasks" / "implement.m1.code.2.md").read_text(encoding="utf-8")
    assert "milestone 级验证没过" in task and "输出列缺失" in task


def test_internal_audit_critical_sends_the_coder_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)], audit_critical={"implement.m2.audit": 1})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps.count("implement.m2.code") == 2 and steps.count("implement.m2.audit") == 2 and steps.count("implement.m2.verify") == 2
    assert steps.count("implement.m1.code") == 1


# ---------------------------------------------------------------------------
# 中途检查点：interactive / --until / --step
# ---------------------------------------------------------------------------


def test_interactive_mode_stops_at_each_review_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)])
    root, rid, stub = _case(tmp_path, monkeypatch, scenario, mode="interactive")
    seen: list[str] = []
    for _ in range(12):
        out = fh.drive(root, rid, stub)
        cp = out["halt"]["checkpoints"][0]
        seen.append(cp["name"])
        if cp["name"] == "final_review":
            break
        assert out["status"] == "awaiting_review" and (root / cp["pack"]).is_file()
        fh.decide(root, rid, cp["id"], "approve", "看过了，没问题")
    assert seen == ["spec_final", "plan_final", "milestone_done", "milestone_done", "verify_done", "final_review"]
    decisions_made = [c["decision"]["credential"] for c in st.load_state(root, rid)["checkpoints"] if c["kind"] == "human" and c["decision"]]
    assert decisions_made == ["self_report"] * 5  # 没有钩子也没有终端短码时，放行记为自述级


def test_checkpoint_modify_dispatches_the_owner_and_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), mode="interactive")
    cp = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    assert cp["name"] == "spec_final"
    result = fh.decide(root, rid, cp["id"], "modify", "R2 的页码应该是 p3 不是 p2，改一下")
    assert result["status"] == "running"
    out = fh.drive(root, rid, stub)
    assert "extract.modify" in _steps(stub)
    task = (root / "workspace" / rid / "flow" / "tasks" / "extract.modify.1.md").read_text(encoding="utf-8")
    assert "R2 的页码应该是 p3 不是 p2" in task
    again = out["halt"]["checkpoints"][0]
    assert again["name"] == "spec_final" and again["id"] != cp["id"]  # 改完重跑门禁，回到同一个检查点
    gates = [r for r in st.read_event_records(root, rid) if r["event"] == "gate:extract"]
    assert len(gates) == 2

    # 人直接改了文件：不派人，重新核对后回到同一个检查点
    fh.decide(root, rid, again["id"], "edited", "我自己改好了")
    third = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    assert third["name"] == "spec_final" and _steps(stub).count("extract.modify") == 1
    for _ in range(MODIFY_LEFT := 1):
        fh.decide(root, rid, third["id"], "modify", "再改一处")
        third = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    with pytest.raises(FlowError, match="已经修改过 3 轮"):
        fh.decide(root, rid, third["id"], "modify", "还要改")
    fh.decide(root, rid, third["id"], "approve", "可以了")
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "plan_final"


def test_until_and_step_policies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"until": "plan"})
    cp = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    assert cp["name"] == "until" and _stages(root, rid)["plan"] == "done" and _stages(root, rid)["spec_audit"] == "pending"
    fh.decide(root, rid, cp["id"], "approve", "继续")
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"  # 一次性的停点，过了就不再停

    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, fh.Scenario(), policy={"step": True})
    names = []
    for _ in range(40):
        out = fh.drive(root2, rid2, stub2)
        cp = out["halt"]["checkpoints"][0]
        names.append(cp["name"])
        if cp["name"] == "final_review":
            break
        fh.decide(root2, rid2, cp["id"], "approve", "继续")
    # 每点收一步停一次（并行的两步一起点收时共用一个停点），写报告前另停一次
    assert names.count("step") == len(stub2.calls) - 1 and names[-2:] == ["step", "final_review"] and "pre_report" in names


def test_abort_is_available_at_every_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), mode="interactive")
    cp = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    with pytest.raises(FlowError, match="选项只有"):
        fh.decide(root, rid, cp["id"], "accept", "x")
    with pytest.raises(FlowError, match="原话"):
        fh.decide(root, rid, cp["id"], "approve", "  ")
    assert fh.decide(root, rid, cp["id"], "abort", "这份不做了")["status"] == "aborted"
    assert fh.drive(root, rid, stub)["halt"]["reason"] == "terminal"
    with pytest.raises(FlowError, match="不在待决状态"):
        fh.decide(root, rid, cp["id"], "approve", "反悔")


# ---------------------------------------------------------------------------
# 迭代诊断摘要
# ---------------------------------------------------------------------------


def test_iterate_digest_gives_trend_stall_warning_and_excluded_hypotheses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # R1 的偏差：60% → 58% → 57% → 达标；连续两轮改善都不到一成
    scenario = fh.Scenario(verify_values=[(0.02, 0.04), (0.021, 0.04), (0.0215, 0.04), (0.052, 0.041)], diagnose=["continue", "continue", "continue"])
    root, rid, stub = _case(tmp_path, monkeypatch, scenario, max_iter=4)
    assert fh.drive(root, rid, stub)["halt"]["checkpoints"][0]["name"] == "final_review"
    ws = root / "workspace" / rid
    assert not (ws / "iterations" / "iter_01" / "digest.md").exists()  # 第 1 轮没有历史
    second = (ws / "iterations" / "iter_02" / "digest.md").read_text(encoding="utf-8")
    assert "| 基线 | 第 1 轮后 |" in second and "60.0% | 58.0%" in second and "没有（没有指标连续两轮改善不足）" in second
    assert "此前各轮的诊断里没有「已排除假设」一节" in second
    third = (ws / "iterations" / "iter_03" / "digest.md").read_text(encoding="utf-8")
    assert "| 基线 | 第 1 轮后 | 第 2 轮后 |" in third and "60.0% | 58.0% | 57.0%" in third
    assert "`rank_ic_mean_mom`：连续两轮偏差缩小都不到 10%（60.0% → 58.0% → 57.0%）" in third
    assert "### 第 2 轮诊断里写的" in third and "调仓日对齐：已核对无误。" in third  # 原文逐字摘录
    assert "rank_ic_mean_rev" not in third  # 一直达标的指标不进表
    assert (ws / "iterations" / "iter_01" / "comparison_before.json").is_file()

    # 默认是灰度：摘要与全部历史一起给，摘要排在最前
    task2 = (ws / "flow" / "tasks" / "iterate.r2.diagnose.1.md").read_text(encoding="utf-8")
    task3 = (ws / "flow" / "tasks" / "iterate.r3.diagnose.1.md").read_text(encoding="utf-8")
    assert task2.index("iter_02/digest.md") < task2.index("iterations/iter_01/") and "以原文为准" in task2
    assert "iterations/iter_01/" in task3 and "iterations/iter_02/" in task3

    # 切到 on：第 2 轮只给摘要和上一轮诊断全文；第 3 轮起恢复全部历史
    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, scenario, config={"flow": {"iterate_digest": "on"}}, max_iter=4)
    fh.drive(root2, rid2, stub2)
    ws2 = root2 / "workspace" / rid2
    task2 = (ws2 / "flow" / "tasks" / "iterate.r2.diagnose.1.md").read_text(encoding="utf-8")
    assert "iter_01/diagnosis.md" in task2 and f"workspace/{rid2}/iterations/iter_01/`" not in task2
    task3 = (ws2 / "flow" / "tasks" / "iterate.r3.diagnose.1.md").read_text(encoding="utf-8")
    assert f"workspace/{rid2}/iterations/iter_01/" in task3 and f"workspace/{rid2}/iterations/iter_02/" in task3

    # 关掉：不生成
    root3, rid3, stub3 = _case(tmp_path / "c", monkeypatch, scenario, config={"flow": {"iterate_digest": "off"}}, max_iter=4)
    fh.drive(root3, rid3, stub3)
    assert not list((root3 / "workspace" / rid3 / "iterations").glob("*/digest.md"))


# ---------------------------------------------------------------------------
# 结果一致性预检接进流程
# ---------------------------------------------------------------------------


def _precheck_events(root: Path, rid: str, name: str) -> list[dict]:
    return [r["payload"] for r in st.read_event_records(root, rid) if r["event"] == f"precheck:{name}"]


def test_report_with_a_handwritten_count_that_disagrees_is_sent_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def spoil(stub: fh.Stub, order: dict) -> None:
        if stub.counts["report.main"] == 1:  # 第一稿里手写了一个与重算对不上的达标计数
            path = stub.ws / "final_report.md"
            path.write_text(path.read_text(encoding="utf-8").replace("## 指标对比\n", "## 指标对比\n\n指标对比总表：达标 1/2 项。\n", 1), encoding="utf-8")

    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(hooks={"report.main": spoil}))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert stub.counts["report.main"] == 2 and "report.docfix" not in stub.counts
    seen = _precheck_events(root, rid, "report")
    assert [e["blocked"] for e in seen] == [True, False] and seen[0]["block"] >= 1
    task = (root / "workspace" / rid / "flow" / "tasks" / "report.main.2.md").read_text(encoding="utf-8")
    assert "报告里手写的计数或数值与机器结果对不上" in task and "final_report.md" in task and "1/2" in task
    report = (root / "workspace" / rid / "final_report.md").read_text(encoding="utf-8")
    assert "达标 2 / 2（数值 2/2）" in report and "flow:generated comparison_table BEGIN" in report  # 计数由内核写在生成块里
    assert (root / "workspace" / rid / "audit" / "precheck_report.md").is_file()
    assert cg.evaluate(root, rid, "report").passed


def test_stale_numbers_get_one_cleanup_round_and_never_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def leftover(stub: fh.Stub, order: dict) -> None:  # 第 2 轮重出的验证文书里留着上一轮的旧数
        path = stub.out / "verify_report.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nrank_ic_mean_mom 复现值为 0.0210，与研报仍有差距。\n", encoding="utf-8")

    scenario = fh.Scenario(verify_values=[(0.02, 0.04), (0.021, 0.04), (0.052, 0.041)], diagnose=["continue", "continue"], hooks={"iterate.r2.verify": leftover})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert stub.counts["result_audit.docfix"] == 1  # 只清一轮：桩没有改掉，流程照样往下走
    seen = _precheck_events(root, rid, "result")
    assert [e["blocked"] for e in seen] == [False, False] and seen[0]["warn"] >= 1
    task = (root / "workspace" / rid / "flow" / "tasks" / "result_audit.docfix.1.md").read_text(encoding="utf-8")
    assert "疑似旧数值残留" in task and "0.0210" in task and "标注为历史记录" in task
    counters = st.load_state(root, rid)["counters"].get("redispatch") or {}
    assert "result_audit.docfix" not in counters  # 不计入重派次数
    assert "旧数值" in (root / "workspace" / rid / "audit" / "precheck_result.md").read_text(encoding="utf-8")


def test_hard_milestone_checkpoint_waits_for_the_internal_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(difficulty="hard", milestones=3), mode="interactive")
    seen: list[str] = []
    for _ in range(12):
        out = fh.drive(root, rid, stub)
        cp = out["halt"]["checkpoints"][0]
        if cp["name"] == "milestone_done":
            state = st.load_state(root, rid)
            mid = next(c for c in state["checkpoints"] if c["id"] == cp["id"])["payload"]["milestone"]
            m = next(m for m in state["milestones"] if m["id"] == mid)
            # 人看到这个检查点时，这个 milestone 的验证和实现内审都已经有结论
            assert m["verify"] == "done" and m["code_review"] == "done", (mid, m)
            assert (root / "workspace" / rid / "audit" / f"impl_audit_{mid}.md").is_file()
            assert "实现内审" in cp["reason"]
            seen.append(mid)
        if cp["name"] == "final_review":
            break
        fh.decide(root, rid, cp["id"], "approve", "看过了，继续")
    assert sorted(seen) == ["m1", "m2", "m3"]


def test_final_review_pack_carries_the_precheck_conclusion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch)
    cp = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    assert cp["name"] == "final_review" and cp["code"]
    pack = (root / cp["pack"]).read_text(encoding="utf-8")
    assert "一致性预检通过（report）" in pack and "audit/precheck_report.md" in pack


def test_oos_run_in_parallel_is_redone_when_the_result_review_changes_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    critical = [{"severity": "critical", "description": "回测用了未来数据"}]
    # 结果外审第 1 轮的 critical 交给 coder 修：代码改了、验证整批重出（数值也变了），并行做的样本外分析基线已经变了
    scenario = fh.Scenario(verify_values=[(0.0501, 0.0401), (0.0502, 0.0402)], reviews={"result": [critical, []]}, rulings={"CDX-R-01": {"owner": "quant-coder"}})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert steps.count("oos.main") == 2 and "result_audit.fix.coder.r1" in steps and "result_audit.reverify.r1" in steps
    assert steps.index("oos.main") < steps.index("result_audit.fix.coder.r1") < len(steps) - 1 - steps[::-1].index("oos.main")
    redo = [r["payload"] for r in st.read_event_records(root, rid) if r["event"] == "step:oos.main:redo"]
    assert len(redo) == 1 and "策略代码" in redo[0]["reason"] and "对比结果" in redo[0]["reason"] and redo[0]["counted"] is False
    assert "oos.main" not in (st.load_state(root, rid)["counters"].get("redispatch") or {})
    assert _stages(root, rid)["oos"] == "done"

    # 审计没有引起任何改动：样本外分析只做一次
    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch)
    fh.drive(root2, rid2, stub2)
    assert _steps(stub2).count("oos.main") == 1


def test_review_that_cannot_be_prepared_is_skipped_without_a_stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.flowlib import extreview

    root, rid, stub = _case(tmp_path, monkeypatch, config={"audit_level": "strict"})  # strict：三道外审都跑
    real_prepare = extreview.prepare

    def broken(root_, report_id, kind, *args, **kwargs):
        if kind == "code":
            raise extreview.ExtReviewError("模板缺少占位符")
        return real_prepare(root_, report_id, kind, *args, **kwargs)

    monkeypatch.setattr(extreview, "prepare", broken)
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    steps = _steps(stub)
    assert not any("fallback" in s for s in steps)  # 没有东西可交给替身
    ledger = {r["checkpoint"]: r for r in st.load_state(root, rid)["external_reviews"]}
    assert ledger["code"]["engine"] == "skipped" and ledger["result"]["engine"] == "codex_external"
    assert cg.evaluate(root, rid, "code_audit").passed
    rec = st.load_state(root, rid)["flow"]["steps"]["code_audit.ext.r1"]
    assert rec["job_id"] is None and "模板缺少占位符" in rec["prepare_error"] and rec["result"]["state"] == "failed"


def test_blind_extraction_that_read_the_spec_is_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.flowlib import extreview

    root, rid, stub = _case(tmp_path, monkeypatch)
    real_status = extreview.status

    def peeked(root_, report_id, job_id):
        status = real_status(root_, report_id, job_id)
        return dict(status, blind_read_spec=True, subsessions=2) if str(job_id).startswith("spec") else status

    monkeypatch.setattr(extreview, "status", peeked)
    fh.drive(root, rid, stub)
    state = st.load_state(root, rid)
    assert next(r for r in state["external_reviews"] if r["checkpoint"] == "spec")["blind_read_spec"] is True
    assert "blind_read_spec" not in next(r for r in state["external_reviews"] if r["checkpoint"] == "result")
    records = [r for r in st.read_event_records(root, rid) if r["event"] == "review:blind_violation"]
    assert len(records) == 1 and records[0]["payload"]["step"] == "spec_audit.ext.r1"
    from tools.flowlib import events as ev

    assert "盲提取不算独立" in ev.describe(records[0]["event"], records[0]["payload"])
    assert state["flow"]["steps"]["spec_audit.ext.r1"]["result"]["subsessions"] == 2


def test_report_digest_agrees_with_the_response_table_and_the_iteration_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """给 reporter 的素材摘要要与原件对得上。

    真实的 reporter 按任务文件写 r010 的报告时指出过两处：回应表里的内审意见（SA-A01）没进摘要、
    计数少一条；旧流程跑出来的案例状态里没有逐轮迭代记录，摘要写成「没有进入迭代」。
    """
    from tools.flowlib import kernelsteps as ks

    root, rid, stub = _case(tmp_path, monkeypatch)
    fh.drive(root, rid, stub)
    ws = root / "workspace" / rid
    digest = ks.report_digest(Engine(root, rid, "claude_code").ctx())
    assert "（回应表里没有意见）" in digest and "## 迭代历史（0 轮）" in digest and "（没有进入迭代）" in digest

    (ws / "audit" / "audit_responses.md").write_text(
        "# 审计回应\n\n| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |\n| --- | --- | --- | --- | --- | --- |\n"
        "| CDX-S-01 | minor | 图例没有写进规格 | accepted | 已补 | 通过 |\n"
        "| SA-A01 | minor | 触发词声明与检索不符 | deferred | 留到修订窗口 | 无 |\n"
        "| CDX-C2-03 | major | 复审轮新增的一条 | rejected | 不成立，理由见诊断 | 无 |\n"
        "| CA-A02 | major | 内审认为基准口径不可考 | rejected | 已登记为假设 | 无 |\n",
        encoding="utf-8",
    )
    (ws / "iterations" / "iter_01").mkdir(parents=True, exist_ok=True)
    (ws / "iterations" / "iter_01" / "diagnosis.md").write_text("# 诊断\n\n结论：stop_partial\n", encoding="utf-8")
    digest = ks.report_digest(Engine(root, rid, "claude_code").ctx())
    assert "## 审计回应汇总（共 4 条，其中外审意见 2 条、内审意见 2 条）" in digest
    assert "- SA-A01（minor，deferred）：触发词声明与检索不符" in digest and "- CDX-C2-03（major，rejected）" in digest
    assert "rejected 的意见必须原样出现在报告里：CDX-C2-03、CA-A02" in digest
    assert "状态里记了 0 轮，磁盘上有 1 轮的诊断文书" in digest and f"workspace/{rid}/iterations/iter_01/diagnosis.md" in digest
    assert "（没有进入迭代）" not in digest


def test_step_usage_is_joined_by_dispatch_label_and_the_steps_own_task_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """点收时从宿主的会话记录里取这一步的用量。

    派发描述等于步骤编号只在一个案例里唯一：同一个工作区并行跑两个案例时两边都有 extract.main。
    所以还要看会话里有没有出现这一步自己的任务文件；对不上的同名会话不能算进来，更不能拿它去核对禁读。
    """
    from tools.flowlib import usage as us

    root, rid, stub = _case(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("REPRODUCE_NO_USAGE", raising=False)
    order = Engine(root, rid, "claude_code").advance()["orders"][0]
    assert order["step_id"] == "extract.main#1" and order["prompt_file"] == f"workspace/{rid}/flow/tasks/extract.main.1.md"
    stub.run(order)

    project = us.claude_project_dir(root)
    parsed: list[str] = []
    real_parse = us.parse_claude_transcript
    monkeypatch.setattr(us, "parse_claude_transcript", lambda path, **kw: (parsed.append(path.stem), real_parse(path, **kw))[1])

    def session(name: str, description: str | None, task_file: str, tokens: int, reads: tuple[str, ...] = ()) -> None:
        path = project / "main-1" / "subagents" / f"{name}.jsonl" if description else project / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        blocks = [{"type": "tool_use", "id": f"tu_{name}_{i}", "name": "Read", "input": {"file_path": f"/abs/{rel}"}} for i, rel in enumerate((task_file, *reads))]
        usage = {"input_tokens": tokens, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 7}
        records = [
            {"type": "user", "timestamp": "2026-11-22T01:00:00.000Z", "message": {"role": "user", "content": f"读取任务文件 /abs/{task_file} 并严格按它执行。"}},
            {"type": "assistant", "timestamp": "2026-11-22T01:00:05.000Z", "message": {"id": f"msg_{name}", "model": "claude-opus-5-5", "role": "assistant", "usage": usage, "content": blocks}},
        ]
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        if description:
            path.with_suffix(".meta.json").write_text(json.dumps({"agentType": "quant-extractor", "description": description}), encoding="utf-8")

    mine = order["prompt_file"]
    session("main-1", None, mine, 5)  # 主会话没有派发描述，不必打开
    session("agent-plan", "plan.main#1", mine, 50)  # 别的步骤
    session("agent-mine", "extract.main#1", mine, 123)
    # 另一个案例的同名步骤，而且它读了那个案例里它本可以读的原文转写
    session("agent-other", "extract.main#1", "workspace/r999_other/flow/tasks/extract.main.1.md", 999, reads=(f"workspace/{rid}/state.json",))

    assert Engine(root, rid, "claude_code").done([order["step_id"]])[0]["ok"]
    done = [r for r in st.read_event_records(root, rid) if r["event"] == "step:extract.main:done"][-1]
    assert done["payload"]["usage"]["uncached_input"] == 123 and done["payload"]["usage"]["tool_calls"] == 1
    assert sorted(set(parsed)) == ["agent-mine", "agent-other"]  # 描述对不上的两份没有被解析
    assert "guard:violation" not in fh.events(root, rid)  # 别的案例的会话读了什么，不记到这一步头上

    # 这一步自己的会话真碰了禁读清单：照常记下来
    order = next(o for o in Engine(root, rid, "claude_code").advance()["orders"] if o["step_id"].startswith("plan.main"))
    stub.run(order)
    session("agent-plan2", order["step_id"], order["prompt_file"], 77, reads=(f"workspace/{rid}/state.json",))
    assert Engine(root, rid, "claude_code").done([order["step_id"]])[0]["ok"]
    violation = [r for r in st.read_event_records(root, rid) if r["event"] == "guard:violation"][-1]
    assert violation["payload"]["step"] == "plan.main" and violation["payload"]["paths"] == [f"workspace/{rid}/state.json"]


def test_static_prescreen_matches_literals_exactly_and_stays_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """代码审计前的静态预筛：命中与逐个字面量用正则去搜完全一致，而且在大案例上不拖慢内核。

    r009 的回放里它一度要一分半钟：三百多个字面量 × 一万多行代码，每次都现编一条正则。
    """
    import random
    import re
    import time

    from tools.flowlib import kernelsteps as ks

    root, rid, stub = _case(tmp_path, monkeypatch)
    fh.drive(root, rid, stub)
    spec = root / "workspace" / rid / "spec" / "spec.md"
    rng = random.Random(7)
    values = sorted({f"{rng.uniform(0.01, 99):.{rng.choice((2, 3, 4))}f}" for _ in range(400)} | {"12.34", "0.0512", "100", "2015"})
    extra = "\n".join(f"- 表值 {v}{'%' if i % 3 == 0 else ''}" for i, v in enumerate(values))
    text = spec.read_text(encoding="utf-8")
    marker = "### [R1] 动量 RankIC 均值\n"
    assert text.count(marker) == 1
    spec.write_text(text.replace(marker, marker + extra + "\n- 占比 100%、样本 2015%\n"), encoding="utf-8")

    src = root / "src" / rid
    tricky = [
        "x = 12.34",  # 命中
        "y = 112.34 + 12.345 + a12.34 + 12.34b",  # 都不是独立的 12.34
        "z = [0.0512, 0.05120, 10.0512]  # 12.34 在注释里不算",  # 只命中 0.0512
        "w = 100 + 100.0 + 1100 + 100_000 + v100",  # 只命中第一个 100
        "s = 'RankIC 12.34% 与 0.0512'",  # 字符串里的也算命中（每个字面量每行只记一次）
        "t = 12.34.real if False else 5",  # 后面挨着小数点，不算
        "df = pd.read_parquet(path)  # 直接读数据文件",
        "ok = read_table('a.parquet')",
    ]
    filler = [f"v{i} = {rng.choice(values) if i % 7 == 0 else i} * 2  # {rng.choice(values)}" for i in range(20000)]
    (src / "replay_big.py").write_text("\n".join(tricky + filler) + "\n", encoding="utf-8")

    ctx = Engine(root, rid, host="claude_code").ctx()
    started = time.perf_counter()
    result = ks.static_prescreen(ctx)
    elapsed = time.perf_counter() - started
    assert elapsed < 10, f"静态预筛用了 {elapsed:.1f} 秒"

    # 对照：老办法（每个字面量一条正则逐行搜）算出的命中
    from tools.flowlib import packs

    literals: dict[str, set[str]] = {}
    for block in packs.CaseDocs.load(root, rid).spec_blocks:
        if block.prefix != "R":
            continue
        for number in ks._NUMBER_RE.findall(block.text):
            core = number.rstrip("%").lstrip("-")
            if len(core.replace(".", "")) >= 3:
                literals.setdefault(core, set()).add(block.id)
    assert {"12.34", "0.0512", "100", "2015"} <= set(literals) and len(literals) > 300
    patterns = {literal: re.compile(rf"(?<![\w.]){re.escape(literal)}(?![\w.])") for literal in literals}
    expected = 0
    expected_tricky: list[tuple[int, str]] = []
    for path in sorted(src.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for literal, pattern in patterns.items():
                if pattern.search(code):
                    expected += 1
                    if path.name == "replay_big.py" and lineno <= len(tricky):
                        expected_tricky.append((lineno, literal))
    assert result["literal_hits"] == expected
    assert sorted(expected_tricky) == [(1, "12.34"), (3, "0.0512"), (4, "100"), (5, "0.0512"), (5, "12.34")]
    report = (root / result["file"]).read_text(encoding="utf-8")
    for lineno, literal in expected_tricky:
        assert f"replay_big.py:{lineno}` 出现 `{literal}`" in report
    assert "replay_big.py:6`" not in report and "replay_big.py:2`" not in report
    assert result["direct_reads"] >= 1 and "replay_big.py:7`：`df = pd.read_parquet(path)" in report and "replay_big.py:8`" not in report
