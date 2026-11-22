"""人工出口这一层的端到端测试：数据缺口处置与 mock 试跑、可行性阻断、revise、reopen、fork、
失效标注、退回执行卡、凭据等级、篡改与预算。玩具案例 + 桩 agent + 真实门禁，全程不花 token。
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
from tools.flowlib import checkpoints as cps  # noqa: E402
from tools.flowlib import datacheck, decisions  # noqa: E402
from tools.flowlib.core import FlowError  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: fh.Scenario | None = None, config: dict | None = None, **init) -> tuple[Path, str, fh.Stub]:
    root = fh.make_root(tmp_path, config)
    rid = fh.new_case(root, monkeypatch, **init)
    stub = fh.Stub(root, rid, scenario or fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    return root, rid, stub


def _steps(stub: fh.Stub) -> list[str]:
    return [c.split("#")[0] for c in stub.calls]


def _cp(out: dict) -> dict:
    return out["halt"]["checkpoints"][0]


def _engine(root: Path, rid: str) -> Engine:
    return Engine(root, rid, host="claude_code")


def _gate(root: Path, rid: str, stage: str) -> dict:
    return {c.id: c for c in cg.evaluate(root, rid, stage).checks}


def _gap_scenario(**kwargs) -> fh.Scenario:
    missing = {**fh.GAP_REQUIREMENT, "status": "missing", "note": "已决定砍掉相关要素"}
    return fh.Scenario(data_requirements=[[fh.GAP_REQUIREMENT], [fh.GAP_REQUIREMENT], [missing]], **kwargs)


# ---------------------------------------------------------------------------
# 数据缺口
# ---------------------------------------------------------------------------


def test_data_gap_bounces_the_planner_once_then_asks_a_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario())
    out = fh.drive(root, rid, stub)
    cp = _cp(out)
    assert cp["name"] == "data_gap" and out["status"] == "paused_blocked"
    assert [o["key"] for o in cp["options"]] == ["supply", "substitute", "narrow", "mock", "drop", "abort"]
    # planner 标了 available 而实测没有这个文件：带实测结果退回改一次，仍不过才问人
    assert _steps(stub).count("plan.main") == 2
    task = (root / "workspace" / rid / "flow" / "tasks" / "plan.main.2.md").read_text(encoding="utf-8")
    assert "标了可得，但机器体检不满足" in task and "toy_price.parquet" in task
    state = st.load_state(root, rid)
    assert state["stages"]["plan"]["status"] == "running" and "plan" not in state["gate_latest"]  # 门禁还没跑：缺口没处置
    payload = next(c for c in state["checkpoints"] if c["id"] == cp["id"])["payload"]
    assert payload["gaps"] == ["A股日行情"]
    pack = (root / cp["pack"]).read_text(encoding="utf-8")
    assert "toy_price.parquet" in pack and "A股日行情" in pack
    for element in ("D1", "F1", "F2", "R1", "R2"):  # 缺口顺着 spec 的依赖关系传到因子和结果
        assert element in pack
    check = datacheck.load_check(root, rid)
    assert check["requirements"][0]["result"] == "missing" and check["requirements"][0]["affected_elements"][:1] == ["D1"]
    # 没有预先声明，就不能以「策略」名义替人选 mock
    with pytest.raises(FlowError, match="只能由人放行"):
        fh.decide(root, rid, cp["id"], "mock", "按策略", by="policy")

    # 砍掉相关要素：planner 把需求改标成 missing，缺口的样子变了，但决定延续，不再问一遍
    result = fh.decide(root, rid, cp["id"], "drop", "这份数据不要了，相关要素砍掉")
    assert result["status"] == "running"
    out = fh.drive(root, rid, stub)
    assert _cp(out)["name"] == "final_review" and _steps(stub).count("plan.main") == 3
    task = (root / "workspace" / rid / "flow" / "tasks" / "plan.main.3.md").read_text(encoding="utf-8")
    assert "砍掉依赖缺失数据的要素" in task and "这份数据不要了" in task
    state = st.load_state(root, rid)
    assert [c["name"] for c in state["checkpoints"] if c["kind"] == "human"] == ["data_gap", "final_review"]
    entry = datacheck.load_check(root, rid)["requirements"][0]
    assert entry["result"] == "missing" and entry["disposition"]["choice"] == "drop"
    gate = _gate(root, rid, "plan")
    assert gate["G-PL-10"].passed and gate["G-PL-11"].passed and "A股日行情→drop" in gate["G-PL-11"].detail
    assert state["gate_latest"]["plan"]["verdict"] == "PASS" and "data:disposition:drop" in fh.events(root, rid)


def test_supply_waits_until_the_data_is_really_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario())
    cp = _cp(fh.drive(root, rid, stub))
    assert "补齐后" in fh.decide(root, rid, cp["id"], "supply", "我去补，周一给你")["message"]
    out = fh.drive(root, rid, stub)
    wait = _cp(out)
    assert wait["name"] == "data_wait" and out["status"] == "paused_blocked" and out["orders"] == []
    # 说补好了但其实没补：重检不过，继续等
    assert "仍在等数据" in fh.decide(root, rid, wait["id"], "recheck", "补好了")["message"]
    wait2 = _cp(fh.drive(root, rid, stub))
    assert wait2["name"] == "data_wait" and wait2["id"] != wait["id"]
    assert not cg.evaluate(root, rid, "plan").passed  # 决定补数据但没补齐，门禁也拦着

    fh.write_price(root)
    assert fh.decide(root, rid, wait2["id"], "recheck", "这回真补好了")["message"] == "数据已齐，继续"
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    entry = datacheck.load_check(root, rid)["requirements"][0]
    assert entry["result"] == "ok" and not entry["disposition"]
    assert _steps(stub).count("plan.main") == 2  # 补数据不需要 planner 改计划


def test_substitute_switches_to_experimental_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    substitute = {**fh.GAP_REQUIREMENT, "status": "substitute", "source": "原文 toy_price.parquet → 替代 toy_alt.parquet", "files": ["toy_alt.parquet"]}
    scenario = fh.Scenario(data_requirements=[[fh.GAP_REQUIREMENT], [fh.GAP_REQUIREMENT], [substitute]])
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    fh.write_price(root, name="toy_alt.parquet")
    cp = _cp(fh.drive(root, rid, stub))
    fh.decide(root, rid, cp["id"], "substitute", "用 toy_alt 顶替")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    state = st.load_state(root, rid)
    assert state["reproduction_mode"] == "experimental"  # 等价替代在 strict 下不成立，随决定切到实验模式
    entry = datacheck.load_check(root, rid)["requirements"][0]
    assert entry["result"] == "ok" and entry["substituted"] is True
    assert "市场迁移声明" in (root / "workspace" / rid / "final_report.md").read_text(encoding="utf-8")


def test_mock_trial_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario())
    cp = _cp(fh.drive(root, rid, stub))
    assert "不出结论" in fh.decide(root, rid, cp["id"], "mock", "先用 mock 把流水线跑通")["message"]

    # planner 起草规格 → 内核按规格生成 → 给人看规格
    out = fh.drive(root, rid, stub)
    spec_cp = _cp(out)
    assert spec_cp["name"] == "mock_spec" and "plan.mock_spec" in _steps(stub)
    mock_dir = root / "workspace" / rid / "data_mock"
    assert (mock_dir / "files" / "toy_price.parquet").is_file() and (mock_dir / "ACTIVE").is_file()
    manifest = json.loads((mock_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tables"][0]["name"] == "toy_price.parquet" and manifest["tables"][0]["columns"] == ["stock_code", "date", "close"]
    assert not (root / "data" / "toy_price.parquet").exists()  # mock 从不写进数据根
    fh.decide(root, rid, spec_cp["id"], "approve", "规格可以")

    # 试跑：编码、内审、代码外审照常；验证只查跑得通、产物齐、指标算得出，然后停下
    out = fh.drive(root, rid, stub)
    done_cp = _cp(out)
    assert done_cp["name"] == "trial_done" and out["status"] == "awaiting_review"
    state = st.load_state(root, rid)
    assert state["ext"]["trial"]["active"] is True and state["verdict"]["result"] is None
    assert state["stages"]["verify"]["status"] == "running" and state["stages"]["report"]["status"] == "pending"
    payload = next(c for c in state["checkpoints"] if c["id"] == done_cp["id"])["payload"]
    assert payload["ok"] is True and payload["mock_files"] == ["toy_price.parquet"]
    mock_results = root / "output" / rid / "results_mock"
    assert (mock_results / "metrics.json").is_file() and not (mock_results / "comparison.json").exists()
    real_results = root / "output" / rid / "results"
    assert not [p for p in real_results.rglob("*") if p.is_file()]  # 真实结果目录里什么都没有
    assert not (root / "output" / rid / "verify_report.md").exists()
    assert "iterate.r1.diagnose" not in _steps(stub) and "report.main" not in _steps(stub)
    gate = _gate(root, rid, "plan")
    assert gate["G-PL-11"].passed and "→mock" in gate["G-PL-11"].detail
    assert not cg.evaluate(root, rid, "verify").passed  # 试跑期间验证门禁过不了：这一轮不能出结论

    # 等真实数据：补齐、重检，结构与 mock 一致，只重跑验证
    fh.decide(root, rid, done_cp["id"], "wait_real", "等数据到了再出结论")
    wait = _cp(fh.drive(root, rid, stub))
    assert wait["name"] == "data_wait"
    fh.write_price(root)
    coded = _steps(stub).count("implement.m1.code")
    assert "只重跑验证" in fh.decide(root, rid, wait["id"], "recheck", "真实数据放好了")["message"]
    assert not (mock_dir / "ACTIVE").exists()
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert _steps(stub).count("implement.m1.code") == coded and _steps(stub).count("verify.main") == 2
    state = st.load_state(root, rid)
    assert state["ext"]["trial"]["active"] is False and state["verdict"]["result"] == "pass" and state["flow"]["generation"] == 1
    gate = _gate(root, rid, "verify")
    assert gate["G-VF-8"].passed and "全部来自数据根" in gate["G-VF-8"].detail
    events = fh.events(root, rid)
    assert events.index("trial:on") < events.index("trial:off") < events.index("reopen:reopen")

    # 真实结果的数据清单里混进了 mock 文件：门禁必须拦下；清单没了也拦
    manifest_path = real_results / "data_manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(original.replace('"source": "real"', '"source": "mock"'), encoding="utf-8")
    failed = {c.id: c for c in cg.evaluate(root, rid, "verify").failed()}
    assert "G-VF-8" in failed and "toy_price.parquet" in failed["G-VF-8"].detail
    manifest_path.unlink()
    assert "G-VF-8" in {c.id for c in cg.evaluate(root, rid, "verify").failed()}


def test_real_data_with_different_columns_reopens_coding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = fh.MOCK_SPEC + "      - {name: volume, kind: volume}\n"
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario(mock_spec=spec))
    fh.decide(root, rid, _cp(fh.drive(root, rid, stub))["id"], "mock", "先试跑")
    fh.decide(root, rid, _cp(fh.drive(root, rid, stub))["id"], "approve", "可以")
    fh.decide(root, rid, _cp(fh.drive(root, rid, stub))["id"], "wait_real", "等数据")
    wait = _cp(fh.drive(root, rid, stub))
    fh.write_price(root)  # 真实文件没有 volume 这一列
    message = fh.decide(root, rid, wait["id"], "recheck", "数据到了")["message"]
    assert "结构与 mock 不一致" in message
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert _steps(stub).count("implement.m1.code") == 2  # 编码一并重做


def test_trial_can_be_abandoned_for_another_disposition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario())
    fh.decide(root, rid, _cp(fh.drive(root, rid, stub))["id"], "mock", "先试跑")
    fh.decide(root, rid, _cp(fh.drive(root, rid, stub))["id"], "approve", "可以")
    done_cp = _cp(fh.drive(root, rid, stub))
    assert done_cp["name"] == "trial_done"
    assert "已结束试跑" in fh.decide(root, rid, done_cp["id"], "change", "不等了，砍掉吧")["message"]
    gap = _cp(fh.drive(root, rid, stub))
    assert gap["name"] == "data_gap"
    state = st.load_state(root, rid)
    assert state["ext"]["trial"]["active"] is False and state["stages"]["implement"]["status"] == "pending"
    fh.decide(root, rid, gap["id"], "drop", "砍掉相关要素")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert st.load_state(root, rid)["verdict"]["result"] == "pass"
    # 做过试跑的案例，真实结果必须带数据清单；桩写了，且没有 mock 文件
    assert cg.evaluate(root, rid, "verify").passed


def test_on_missing_mock_is_applied_by_policy_and_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, _gap_scenario(), policy={"on_missing": "mock"})
    out = fh.drive(root, rid, stub)
    assert _cp(out)["name"] == "trial_done"  # 缺口与规格都不停，试跑做完才等人
    state = st.load_state(root, rid)
    decided = [(c["name"], c["decision"]["choice"], c["decision"]["credential"], c["decision"]["by"]) for c in state["checkpoints"] if c["kind"] == "human" and c.get("decision")]
    assert decided == [("data_gap", "mock", "policy", "policy"), ("mock_spec", "approve", "policy", "policy")]
    assert state["verdict"]["result"] is None


def test_feasibility_blocked_needs_a_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(feasibility=["blocked", "degraded"]))
    out = fh.drive(root, rid, stub)
    cp = _cp(out)
    assert cp["name"] == "feasibility_blocked" and out["status"] == "paused_blocked"
    assert _steps(stub).count("plan.main") == 1  # 不会让 planner 自己把 blocked 改掉
    assert [o["key"] for o in cp["options"]] == ["supply", "experimental", "degrade", "abort"]
    result = fh.decide(root, rid, cp["id"], "experimental", "同意用 A 股数据做迁移复现")
    assert "实验模式" in result["message"]
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    state = st.load_state(root, rid)
    assert state["reproduction_mode"] == "experimental" and state["feasibility"] == "degraded"
    task = (root / "workspace" / rid / "flow" / "tasks" / "plan.main.2.md").read_text(encoding="utf-8")
    assert "同意用 A 股数据做迁移复现" in task


def test_blocking_ambiguity_needs_a_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocking = fh.AMBIGUITY_MAJOR.replace("等级: major", "等级: blocking").replace("裁决方式: auto", "裁决方式: human").replace("状态: resolved", "状态: open")

    def resolve(stub: fh.Stub, order: dict) -> None:
        if stub.counts["plan.main"] >= 2:
            path = stub.ws / "spec" / "ambiguities.md"
            path.write_text(path.read_text(encoding="utf-8").replace("状态: open", "状态: resolved"), encoding="utf-8")

    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(ambiguities=blocking, hooks={"plan.main": resolve}))
    cp = _cp(fh.drive(root, rid, stub))
    assert cp["name"] == "blocking_ambiguity"
    fh.decide(root, rid, cp["id"], "answer", "按交易日算")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    task = (root / "workspace" / rid / "flow" / "tasks" / "plan.main.2.md").read_text(encoding="utf-8")
    assert "按交易日算" in task and "人工裁决" in task


# ---------------------------------------------------------------------------
# revise / reopen / fork / 失效标注
# ---------------------------------------------------------------------------


def _finished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: fh.Scenario | None = None, **init) -> tuple[Path, str, fh.Stub]:
    root, rid, stub = _case(tmp_path, monkeypatch, scenario or fh.Scenario(), **init)
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    return root, rid, stub


def test_revise_param_scope_reruns_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _finished(tmp_path, monkeypatch)
    engine = _engine(root, rid)
    before = len(stub.calls)
    # 先看计划：不改任何东西
    preview = decisions.revise(engine, assumption="AS1", text="窗口按自然日计", dry_run=True)
    assert preview["dry_run"] and preview["scope"] == "param" and preview["milestones"] == []
    assert preview["stages"] == ["implement", "verify", "result_audit", "oos", "report", "review"]
    assert st.load_state(root, rid)["status"] == "awaiting_review" and len(stub.calls) == before
    with pytest.raises(FlowError, match="没有 AS9"):
        decisions.revise(engine, assumption="AS9", text="x", quote="改")

    result = decisions.revise(engine, assumption="AS1", text="窗口按自然日计", quote="AS1 改成自然日再跑一遍")
    assert result["round"] == 1 and result["generation"] == 1 and result["credential"] == "self_report"
    state = st.load_state(root, rid)
    assert state["status"] == "running" and state["stages"]["code_audit"]["status"] == "done" and state["stages"]["verify"]["status"] == "pending"
    assert state["checkpoints"][-1]["decision"]["choice"] == "revise"
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    rerun = _steps(stub)[before:]
    # 参数级修订：planner 改登记簿 → coder 只改 config → 整批重出验证 → 结果外审 → 样本外 → 报告；不重做内审
    assert rerun == ["implement.revise_plan", "implement.revise_config", "verify.main", "oos.main", "report.main"]
    assert [r["round"] for r in stub.review_log if r["kind"] == "result"] == [1, 2]
    task = (root / "workspace" / rid / "flow" / "tasks" / "g1.implement.revise_plan.1.md").read_text(encoding="utf-8")
    assert "窗口按自然日计" in task and "AS1" in task
    state = st.load_state(root, rid)
    assert state["counters"]["revise"] == 1 and state["verdict"]["result"] == "pass"
    assert state["iteration"]["history"][-1]["trigger"] == "revise" and state["iteration"]["current"] == 0  # 不占迭代轮数
    archive = root / "workspace" / rid / "flow" / "archive" / "gen_0"
    assert (archive / "steps.json").is_file() and (archive / "comparison.json").is_file() and (archive / "final_report.md").is_file()
    assumptions = (root / "workspace" / rid / "assumptions.md").read_text(encoding="utf-8")
    assert "状态: revised" in assumptions and "[verify 后填]" not in assumptions and "修订记录" in assumptions

    # 上限 3 轮
    for n in (2, 3):
        decisions.revise(_engine(root, rid), assumption="AS1", text=f"第 {n} 版口径", quote="再改")
        fh.drive(root, rid, stub)
    with pytest.raises(FlowError, match="已经 revise 过 3 轮"):
        decisions.revise(_engine(root, rid), assumption="AS1", text="第 4 版", quote="还改")
    assert decisions.accept(_engine(root, rid), "可以了")["status"] == "done"


def test_revise_method_scope_reruns_only_affected_milestones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assumptions = fh.ASSUMPTIONS.replace("影响面: param", "影响面: method").replace("影响 milestone: m1", "影响 milestone: m2（动量因子）")
    scenario = fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)], assumptions=assumptions)
    root, rid, stub = _finished(tmp_path, monkeypatch, scenario)
    before = len(stub.calls)
    result = decisions.revise(_engine(root, rid), assumption="AS1", text="动量改用对数收益", quote="AS1 换成对数收益")
    assert result["scope"] == "method" and result["milestones"] == ["m2", "m3"]  # m2 以及依赖它的 m3；m1 不动
    assert "code_audit" in result["stages"]
    state = st.load_state(root, rid)
    assert [(m["id"], m["implement"]) for m in state["milestones"]] == [("m1", "done"), ("m2", "pending"), ("m3", "pending")]
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    rerun = _steps(stub)[before:]
    assert "implement.m1.code" not in rerun and {"implement.m2.code", "implement.m3.code", "implement.m2.audit", "implement.m3.verify"} <= set(rerun)
    assert rerun[0] == "implement.revise_plan" and "implement.revise_config" not in rerun
    task = (root / "workspace" / rid / "flow" / "tasks" / "g1.implement.m2.code.1.md").read_text(encoding="utf-8")
    assert "动量改用对数收益" in task
    # 重开后的外审续编轮次，走差量复审，不从头再审
    state = st.load_state(root, rid)
    assert state["counters"]["review_rounds"]["code"] == 2 and state["counters"]["review_rounds"]["result"] == 2
    second = {r["kind"]: r for r in stub.review_log if r["round"] == 2}
    assert set(second) == {"code", "result"} and all(r["mode"] == "delta" for r in second.values())
    first = {r["kind"]: r for r in stub.review_log if r["round"] == 1 and r["call"] == "main"}
    assert all(r["mode"] == "full" for r in first.values()) and second["code"]["effort"] != first["code"]["effort"]  # 复审降一档推理强度


def test_reopen_from_a_milestone_and_from_a_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)])
    root, rid, stub = _finished(tmp_path, monkeypatch, scenario)
    engine = _engine(root, rid)
    with pytest.raises(FlowError, match="没有 milestone m9"):
        decisions.reopen(engine, "m9", "x", "回退")
    with pytest.raises(FlowError, match="不能从 init 重开"):
        decisions.reopen(engine, "init", "x", "回退")
    dry = decisions.reopen(engine, "m2", "只看看", "", dry_run=True)
    assert dry["dry_run"] and st.load_state(root, rid)["status"] == "awaiting_review"

    before = len(stub.calls)
    result = decisions.reopen(_engine(root, rid), "m2", "m2 的反转因子口径要重做", "m2 重做")
    assert result["milestones"] == ["m2"] and result["stages"][0] == "implement"
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    rerun = _steps(stub)[before:]
    assert "implement.m1.code" not in rerun and "implement.m2.code" in rerun and "verify.main" in rerun and "extract.main" not in rerun

    # 已收尾的案例也能重开，但要带原话
    decisions.accept(_engine(root, rid), "通过")
    with pytest.raises(FlowError, match="原话"):
        decisions.reopen(_engine(root, rid), "report", "报告要重写", "")
    before = len(stub.calls)
    decisions.reopen(_engine(root, rid), "report", "报告要重写", "报告重写一版")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert _steps(stub)[before:] == ["report.main"]
    assert st.load_state(root, rid)["flow"]["generation"] == 2


def test_checkpoint_rollback_reopens_from_the_named_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"until": "verify"})
    cp = _cp(fh.drive(root, rid, stub))
    assert cp["name"] == "until"
    with pytest.raises(FlowError, match="--to"):
        fh.decide(root, rid, cp["id"], "rollback", "退回去")
    before = len(stub.calls)
    assert "从计划起重做" in fh.decide(root, rid, cp["id"], "rollback", "计划有问题，从 plan 重来", to="plan")["message"]
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert _steps(stub)[before:][:2] == ["plan.main", "implement.m1.code"]


def test_fork_copies_a_case_and_rewinds_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)])
    root, rid, stub = _finished(tmp_path, monkeypatch, scenario)
    source_state = (root / "workspace" / rid / "state.json").read_text(encoding="utf-8")
    result = decisions.fork(root, rid, "r901_toy_fork", "implement", host="claude_code")
    assert result["report_id"] == "r901_toy_fork" and (root / "workspace" / rid / "state.json").read_text(encoding="utf-8") == source_state
    with pytest.raises(FlowError, match="已经存在"):
        decisions.fork(root, rid, "r901_toy_fork", "implement")
    new = "r901_toy_fork"
    state = st.load_state(root, new)
    assert state["ext"]["forked_from"] == rid and state["current_stage"] == "implement"
    assert [state["stages"][s]["status"] for s in ("init", "extract", "plan", "spec_audit", "implement")] == ["done"] * 4 + ["pending"]
    matrix = (root / "workspace" / new / "spec" / "coverage_matrix.md").read_text(encoding="utf-8")
    assert "strategy.py" not in matrix and "与研报对上" not in matrix and "| pending |" in matrix
    assert "[verify 后填]" in (root / "workspace" / new / "assumptions.md").read_text(encoding="utf-8")
    assert not list((root / "src" / new).glob("*.py"))
    stub2 = fh.Stub(root, new, scenario)
    fh.install_fake_review(monkeypatch, stub2)
    assert _cp(fh.drive(root, new, stub2))["name"] == "final_review"
    assert _steps(stub2)[0] == "implement.m1.code" and "plan.main" not in _steps(stub2)

    # 从靠后的阶段 fork：代码与产物照搬，结论沿用
    late = decisions.fork(root, rid, "r902_toy_late", "report", host="claude_code")
    assert len(late["copied"]) == 2 and (root / "src" / "r902_toy_late" / "strategy.py").is_file()
    stub3 = fh.Stub(root, "r902_toy_late", scenario)
    assert _cp(fh.drive(root, "r902_toy_late", stub3))["name"] == "final_review"
    assert _steps(stub3) == ["report.main"] and st.load_state(root, "r902_toy_late")["verdict"]["result"] == "pass"


def test_fork_keeps_plan_stage_assumptions_and_drops_only_later_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """回退到编码起点时只去掉编码之后才登记的假设。

    真实的 coder 按 fork 出来的 r010 干活时指出过：plan 引用的 AS13（来源「数据限制」，planner 登记的）
    被删了，留下悬空的编号。「数据限制」是计划阶段就会用的来源；plan 正文引用到的假设也要留着。
    """
    root, rid, _stub = _finished(tmp_path, monkeypatch)
    ws = root / "workspace" / rid

    def card(as_id: str, title: str, origin: str) -> str:
        return (
            f"\n### [{as_id}] {title}\n- 来源: {origin}\n- 假设内容: 略\n- 行业惯例依据: 略\n- 参数绑定: -\n- 影响面: data\n"
            "- 影响 milestone: m1\n- 影响指标: R1\n- 预期影响: 影响很小\n- 验证后回看: 复现值与研报值一致\n- 状态: assumed\n- 高亮等级: -\n"
        )

    with (ws / "assumptions.md").open("a", encoding="utf-8") as handle:
        handle.write(card("AS2", "交易费率按 0 计", "数据限制"))  # planner 在计划阶段登记的
        handle.write(card("AS3", "等权基准的构造细则", "coder 主动简化"))
        handle.write(card("AS4", "港股行情只有近一年有截面", "数据限制（coder 在 m1 实测发现）"))  # 后来写进了 plan
        handle.write(card("AS5", "仓位分位数的并列处理", "迭代修正（iter_01）"))
        handle.write(card("AS12", "编号是 AS1 的前缀延伸，不能被 plan 里的 AS1 连带保住", "verifier 回看时补登"))
    with (ws / "plan.md").open("a", encoding="utf-8") as handle:
        handle.write("\n| 交易费率 | 0（双边，基线不计费） | B6 + AS2 |\n\n港股区间按 AS4 缩小到有截面的时段。\n")

    result = decisions.fork(root, rid, "r903_toy_fork", "implement", host="claude_code")
    assert result["cleaned"]["assumptions_removed"] == ["AS12", "AS3", "AS5"]
    text = (root / "workspace" / "r903_toy_fork" / "assumptions.md").read_text(encoding="utf-8")
    assert "### [AS2] 交易费率按 0 计" in text and "### [AS4] 港股行情只有近一年有截面" in text and "### [AS1] " in text
    assert "[AS3]" not in text and "[AS5]" not in text and "[AS12]" not in text
    assert text.count("- 验证后回看: [verify 后填]") == 3  # 留下来的三条回看都复位了


def test_stale_report_names_what_changed_without_touching_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)])
    root, rid, stub = _finished(tmp_path, monkeypatch, scenario)
    assert decisions.stale_report(_engine(root, rid))["stale"] == []  # 内核自己合并回执（矩阵回填、假设回看）不算变更
    snapshot = (root / "workspace" / rid / "state.json").read_text(encoding="utf-8")

    spec = root / "workspace" / rid / "spec" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("过去 5 日收益率取负", "过去 10 日收益率取负"), encoding="utf-8")
    report = decisions.stale_report(_engine(root, rid))
    stale = {item["step"]: item for item in report["stale"]}
    assert "implement.m3.code" in stale and any("F2" in c for c in stale["implement.m3.code"]["changed"])  # F2 归 m3
    assert "implement.m1.code" not in stale  # m1 的包里 F2 只有一行索引，公式变了不影响它
    assert stale["implement.m1.audit"]["context_only"] is True  # m1 的内审带着全部因子定义，只是对照用
    assert stale["implement.m3.code"]["context_only"] is False and report["reopen_from"] == "m3"
    assert (root / "workspace" / rid / "state.json").read_text(encoding="utf-8") == snapshot  # 只报告

    # 代码在验证之后改过：验证与内审步骤过期
    strategy = root / "src" / rid / "strategy.py"
    strategy.write_text(strategy.read_text(encoding="utf-8") + "\n# 手工改动\n", encoding="utf-8")
    stale = {item["step"]: item for item in decisions.stale_report(_engine(root, rid))["stale"]}
    assert "verify.main" in stale and any("代码" in c for c in stale["verify.main"]["changed"])


# ---------------------------------------------------------------------------
# 退回执行卡、表外派发、假 FAIL、取块
# ---------------------------------------------------------------------------


def test_pin_hands_a_stage_back_to_its_card_and_gates_still_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"until": "code_audit"})
    cp = _cp(fh.drive(root, rid, stub))
    engine = _engine(root, rid)
    with pytest.raises(FlowError, match="原因"):
        decisions.pin(engine, "verify", "card", "  ")
    decisions.pin(engine, "verify", "card", "步骤表判断不了这个案例的验证分支")
    fh.decide(root, rid, cp["id"], "approve", "继续")
    out = fh.drive(root, rid, stub)
    order = out["orders"][0]
    assert order["kind"] == "legacy_card" and order["stage"] == "verify" and order["card"].endswith("verify.md")
    # 卡驱动的阶段照样只能凭门禁收口：没有产物时 set-stage done 过不了守卫
    assert st.load_state(root, rid)["stages"]["verify"]["status"] in ("pending", "running")
    decisions.pin(_engine(root, rid), "verify", "kernel", "交还内核")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    events = fh.events(root, rid)
    assert "pin:verify:card" in events and "pin:verify:kernel" in events


def test_adhoc_dispatch_is_recorded_and_limited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario())
    fh.drive(root, rid, stub, until=lambda o: any(x["step_id"] == "verify.main#1" for x in o["orders"]))
    engine = _engine(root, rid)
    note = root / "note.md"
    note.write_text("把 strategy.py 里的魔法数字提到 config.py。\n", encoding="utf-8")
    with pytest.raises(FlowError):
        engine.adhoc("quant-coder", "", str(note), [f"src/{rid}/"])  # 必须写原因
    with pytest.raises(FlowError, match="不认识的角色"):
        engine.adhoc("root", "x", "y", [])
    order = engine.adhoc("quant-coder", "步骤表里没有的清理", note.read_text(encoding="utf-8"), [f"src/{rid}/"])
    assert order["step_id"].startswith("adhoc.01#") and order["role"] == "quant-coder"
    task = (root / order["prompt_file"]).read_text(encoding="utf-8")
    assert "魔法数字" in task and "步骤表里没有的清理" in task
    stub.run(order)
    assert engine.done([order["step_id"]], collect_usage=False)[0]["ok"]
    state = st.load_state(root, rid)
    assert state["counters"]["adhoc"] == 1 and "step:adhoc.01:issued" in fh.events(root, rid)
    limit = engine.ctx().config.get("flow", {}).get("adhoc_limit") or 5
    for _ in range(limit - 1):
        extra = engine.adhoc("quant-coder", "再来一次", "同上", [f"src/{rid}/"])
        stub.run(extra)
        engine.done([extra["step_id"]], collect_usage=False)
    with pytest.raises(FlowError, match="上限"):
        engine.adhoc("quant-coder", "超了", "同上", [f"src/{rid}/"])


def test_false_fail_rerun_requires_overlapping_coding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.052, 0.041)], milestone_verify_fail={"m1": 1})
    root, rid, stub = _case(tmp_path, monkeypatch, scenario)
    # 停在「m1 的验证判了 fail、coder 被退回」的那一刻
    out = fh.drive(root, rid, stub, until=lambda o: any(x["step_id"] == "implement.m1.code#2" for x in o["orders"]))
    engine = _engine(root, rid)
    with pytest.raises(FlowError, match="只有 milestone 级验证"):
        decisions.rerun_false_fail(engine, "implement.m1.code", "x")
    result = decisions.rerun_false_fail(engine, "implement.m1.verify", "当时 m2 正在改公共函数，m1 的失败是被它带出来的")
    assert result["overlapping"]  # 验证期间确有别的 milestone 在编码
    state = st.load_state(root, rid)
    assert state["flow"]["steps"]["implement.m1.code"]["status"] == "done" and state["counters"]["false_fail"] == {"m1": 1}
    assert [c["name"] for c in state["checkpoints"] if c["kind"] == "auto"][-1] == "false_fail_rerun"
    with pytest.raises(FlowError, match="已经按假 FAIL 复跑过一次"):
        decisions.rerun_false_fail(_engine(root, rid), "implement.m1.verify", "再来")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"
    assert _steps(stub).count("implement.m1.code") == 1 and _steps(stub).count("implement.m1.verify") == 2

    # easy 案例没有并行编码：不符合条件，按真实失败处理
    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)], milestone_verify_fail={"m2": 1}))
    fh.drive(root2, rid2, stub2, until=lambda o: any(x["step_id"] == "implement.m2.code#2" for x in o["orders"]))
    with pytest.raises(FlowError, match="不符合假 FAIL 的条件"):
        decisions.rerun_false_fail(_engine(root2, rid2), "implement.m2.verify", "x")


def test_get_block_serves_the_source_text_and_logs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"until": "plan"})
    fh.drive(root, rid, stub)
    engine = _engine(root, rid)
    text = decisions.get_block(engine, "element", "F2", "implement.m1.code")
    assert text.startswith("### [F2] 反转因子") and "rev = -(close / close.shift(5) - 1)" in text and "[B1]" not in text
    assert "AS1" in decisions.get_block(engine, "assumption", "AS1", None)
    assert decisions.get_block(engine, "matrix-row", "R1", None).startswith("| R1 |")
    records = [r for r in st.read_event_records(root, rid) if r["event"] == "pack:get"]
    assert [r["payload"]["key"] for r in records] == ["F2", "AS1", "R1"] and records[0]["payload"]["step"] == "implement.m1.code"


# ---------------------------------------------------------------------------
# 凭据、守卫、篡改、停滞、预算
# ---------------------------------------------------------------------------


def test_credential_levels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(difficulty="medium", milestones=2, verify_values=[(0.052, 0.041)]), mode="interactive")
    cp = _cp(fh.drive(root, rid, stub))
    code = next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"])["code"]
    # 终端：当场输入的短码与检查点一致
    assert fh.decide(root, rid, cp["id"], "approve", "可以", typed_code=code.lower())["credential"] == "terminal"

    # 钩子：检查点打开之后，钩子记到了带短码的人的输入
    cp = _cp(fh.drive(root, rid, stub))
    code = next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"])["code"]
    log = root / "workspace" / "_registry" / "presence.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({"ts": st.now_iso(), "source": "prompt", "text": f"plan 看过了，放行 {code}"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert fh.decide(root, rid, cp["id"], "approve", "plan 看过了，放行")["credential"] == "hook"

    # 提问工具的回答只有题面带着这个检查点的短码才算数；别的检查点的回答不能挪用
    cp = _cp(fh.drive(root, rid, stub))
    code = next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"])["code"]
    log.write_text(json.dumps({"ts": st.now_iso(), "source": "ask", "question": "要不要顺便清理缓存？", "text": "通过"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert decisions._credential(root, next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"]), "通过", None, "human") == "self_report"
    log.write_text(json.dumps({"ts": st.now_iso(), "source": "ask", "question": f"[{cp['id']} · {code}] m1 完成，是否继续？", "text": "通过"}, ensure_ascii=False) + "\n", encoding="utf-8")
    assert fh.decide(root, rid, cp["id"], "approve", "通过")["credential"] == "hook"
    # 错的短码不算终端凭据
    cp = _cp(fh.drive(root, rid, stub))
    log.unlink()
    assert fh.decide(root, rid, cp["id"], "approve", "行", typed_code="ZZZZ")["credential"] == "self_report"


def test_orchestrator_cannot_release_a_checkpoint_by_writing_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(blocked={"implement.m1.code": 1}))
    cp = _cp(fh.drive(root, rid, stub))
    assert st.load_state(root, rid)["status"] == "paused_blocked"
    with pytest.raises(st.StateGuardError):
        st.set_field(root, rid, "status", "running")  # 等待态只能经 flow decide 等合法出口解除
    with pytest.raises(st.StateGuardError):
        st.record_event(root, rid, "checkpoint:resolved", {"id": cp["id"]})  # 保留事件名不能手写
    state = st.load_state(root, rid)
    assert state["status"] == "paused_blocked" and st.pending_checkpoints(state)[0]["id"] == cp["id"]
    assert "guard:rejected" in fh.events(root, rid)  # 被拒的尝试留痕
    out = fh.drive(root, rid, stub)
    assert out["orders"] == [] and _cp(out)["id"] == cp["id"]


def test_tampered_event_log_opens_a_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"until": "plan"})
    cp = _cp(fh.drive(root, rid, stub))
    fh.decide(root, rid, cp["id"], "approve", "继续")
    events_path = root / "workspace" / rid / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    lines[5] = lines[5].replace('"gate:', '"gate_x:') if '"gate:' in lines[5] else lines[5].replace('"ts": "2', '"ts": "1', 1)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = fh.drive(root, rid, stub)
    tamper = _cp(out)
    assert tamper["name"] == "tamper" and out["status"] == "paused_blocked"
    fh.decide(root, rid, tamper["id"], "acknowledge", "是我手工改的事件流，已知悉")
    assert _cp(fh.drive(root, rid, stub))["name"] == "final_review"  # 同一处不一致不再反复拦
    assert len([c for c in st.load_state(root, rid)["checkpoints"] if c["name"] == "tamper"]) == 1


def test_stall_and_budget_checkpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    root, rid, stub = _case(tmp_path, monkeypatch, fh.Scenario(), policy={"stall_hours": 1e-7})
    engine = _engine(root, rid)
    first = engine.advance()
    assert first["orders"][0]["step_id"] == "extract.main#1"
    time.sleep(1.2)  # 事件时间戳精确到秒
    out = _engine(root, rid).advance()
    cp = _cp(out)
    assert cp["name"] == "stall" and "extract.main" in cp["reason"]
    assert fh.decide(root, rid, cp["id"], "continue", "会话断过，接着跑")["status"] == "running"
    assert "stall:resumed" in fh.events(root, rid)

    root2, rid2, stub2 = _case(tmp_path / "b", monkeypatch, fh.Scenario(), policy={"budget_hours": 1e-7})
    time.sleep(1.2)
    out = fh.drive(root2, rid2, stub2)
    budget = _cp(out)
    assert budget["name"] == "budget" and "超过预算" in budget["reason"]
    with pytest.raises(FlowError, match="新值"):
        fh.decide(root2, rid2, budget["id"], "raise", "加预算")
    fh.decide(root2, rid2, budget["id"], "raise", "加到 100 小时", budget_hours=100)
    assert _cp(fh.drive(root2, rid2, stub2))["name"] == "final_review"
    assert st.load_state(root2, rid2)["policy"]["budget_hours"] == 100


def test_policy_defaults_come_from_config_and_cli_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = {"default_on_missing": "mock", "default_budget_hours": 8, "flow": {"stall_hours": 1.5}}
    root = fh.make_root(tmp_path, config)
    rid = fh.new_case(root, monkeypatch)
    policy = st.load_state(root, rid)["policy"]
    assert policy["on_missing"] == "mock" and policy["budget_hours"] == 8 and policy["budget_tokens"] is None
    assert cps.stall_hours(Engine(root, rid, host="claude_code").ctx()) == 1.5
    rid2 = fh.new_case(root, monkeypatch, slug="other", policy={"on_missing": "stop", "budget_hours": 2})
    policy = st.load_state(root, rid2)["policy"]
    assert policy["on_missing"] == "stop" and policy["budget_hours"] == 2
