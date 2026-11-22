"""真实案例回放（本地可选）：在历史案例的副本上跑内核，不派 agent、不调外审、不花 token。

这组测试依赖本机才有的东西——`workspace/` 下的历史案例（部分未入库）、`output/`（不入库）和
数据根目录——缺哪样就跳过哪样，所以在干净的检出或公开快照里它们全部跳过。副本放在 pytest
的临时目录里，真实 workspace 一个字节都不动（每个用例结束前核对）。

覆盖四件事：
1. 每个案例从每个阶段的起点 fork 一次、推进一步：步骤表、任务文件、外审输入包在真实文书上不出错；
2. r009 当时的两次 revise（AS18+AS19、AS41）算出的重跑范围是 m2–m5；
3. r010 的数据需求补上机器可查字段后，体检报出港股行情的截面塌陷；
4. 三个审查点的外审提示词在真实案例上渲染后没有占位符残留，输入包不超预算。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import state as st  # noqa: E402
from tools.flowlib import datacheck, decisions, extreview, packs  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402

# 设计文档第十节第 3 项点名的六个案例：三个走完全程的新案例、三个文件时间被检出重置过的旧案例
REPLAY_CASES = (
    "r008_inflection_trend_size_rotation",
    "r009_industry_rotation",
    "r010_breakout_ratio_timing",
    "r001_signature_transformer_allocation",
    "r003_equity_factor_timing_cn",
    "ssrn_6115073",
)
SKIP_DIRS = {"checkpoints", "data_cache", "data_mock", "__pycache__", "flow", "reviews"}
SKIP_SUFFIXES = {".parquet", ".pkl", ".ndjson", ".npy", ".npz", ".pt", ".pth", ".h5", ".zip", ".feather", ".bin", ".ckpt", ".joblib"}
MAX_FILE_BYTES = 5_000_000
FORK_STAGES = tuple(s for s in st.STAGE_ORDER if s not in ("init", "review"))


def _ignore(directory: str, names: list[str]) -> list[str]:
    """副本里不带运行缓存、训练检查点和大文件：回放只读文书、代码和小的结果文件。"""
    dropped = []
    for name in names:
        path = Path(directory) / name
        if name in SKIP_DIRS or name.startswith(("perturbation_", ".state.lock")) or name == "board.html":
            dropped.append(name)
        elif path.is_file() and (path.suffix in SKIP_SUFFIXES or path.stat().st_size > MAX_FILE_BYTES):
            dropped.append(name)
    return dropped


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_case(case: str, *, need_output: bool = True) -> None:
    if not (REPO_ROOT / "workspace" / case / "state.json").is_file():
        pytest.skip(f"本机没有案例 {case}（workspace 不入库或未检出）")
    if need_output and not (REPO_ROOT / "output" / case).is_dir():
        pytest.skip(f"本机没有 {case} 的 output/（不入库）")


def _copy_case(tmp_path: Path, case: str, monkeypatch: pytest.MonkeyPatch, config: dict[str, Any] | None = None) -> Path:
    """把一个真实案例的文书、代码、小结果文件拷到临时工作区根。"""
    monkeypatch.setenv("REPRODUCE_NO_USAGE", "1")
    monkeypatch.setenv("REPRODUCE_NO_TTY", "1")
    root = tmp_path / "wsroot"
    root.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "templates", root / "templates")
    (root / "data").mkdir()
    cfg = {"data_root": str(root / "data"), "audit_level": "strict", **(config or {})}
    (root / ".reproduce.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    for top in ("workspace", "src", "output"):
        source = REPO_ROOT / top / case
        if source.is_dir():
            shutil.copytree(source, root / top / case, ignore=_ignore)
    return root


@pytest.mark.parametrize("case", REPLAY_CASES)
def test_fork_from_every_stage_plans_a_first_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    _require_case(case)
    real_state = _digest(REPO_ROOT / "workspace" / case / "state.json")
    root = _copy_case(tmp_path, case, monkeypatch)
    copy_state = _digest(root / "workspace" / case / "state.json")
    old = json.loads((root / "workspace" / case / "state.json").read_text(encoding="utf-8"))
    first_milestone = (old.get("milestones") or [{}])[0].get("id")
    pdf_name = Path(str(old.get("pdf_path") or "")).name or "\0"
    expected_first = {
        "extract": {"extract.main"},
        "plan": {"plan.main"},
        "spec_audit": {"spec_audit.ext.r1", "spec_audit.internal"},
        "implement": {f"implement.{first_milestone}.code"},
        "code_audit": {"code_audit.ext.r1"},
        "verify": {"verify.main"},
        "iterate": {"iterate.r1.diagnose"},
        "result_audit": {"result_audit.ext.r1"},
    }
    seen: dict[str, list[str]] = {}
    for index, stage in enumerate(FORK_STAGES):
        new_id = f"r9{index:02d}_fork_{stage}"
        result = decisions.fork(root, case, new_id, stage, host="claude_code")
        assert result["report_id"] == new_id
        out = Engine(root, new_id, host="claude_code").advance()
        orders = out.get("orders") or []
        steps = [str(o["step_id"]).split("#")[0] for o in orders]
        seen[stage] = steps
        assert orders and not out.get("halt"), (stage, out.get("halt"), out.get("notes"))
        if stage in expected_first:
            assert expected_first[stage] <= set(steps), (stage, steps)
        else:  # oos / report：样本外要不要做、报告前要不要先修文书，取决于这个案例的结论与产物
            assert set(steps) <= {"oos.main", "report.main", "report.docfix"}, (stage, steps)
        state = st.load_state(root, new_id)
        assert state["current_stage"] in st.STAGE_ORDER and state["ext"]["forked_from"] == case
        for order in orders:
            if order["kind"] == "dispatch":
                task = root / order["prompt_file"]
                text = task.read_text(encoding="utf-8")
                assert task.is_file() and len(text) > 500 and order["prompt_file"] in order["prompt_inline"]
                assert f"步骤：`{str(order['step_id']).split('#')[0]}`" in text
                # PDF 文件名里本来就带着源案例的编号（fork 沿用同一份 PDF），除此之外不该再出现
                assert case not in text.replace(pdf_name, ""), f"{order['step_id']} 的任务文件里还留着源案例的编号"
            elif order["kind"] == "exec":
                # 外审步骤：提示词与输入包已经渲染出来，没有启动任何外部进程
                record = state["flow"]["steps"][str(order["step_id"]).split("#")[0]]
                assert record.get("job_id"), (stage, record.get("prepare_error"))
                status = extreview.status(root, new_id, record["job_id"])
                assert status["state"] in ("prepared", "pending", "idle", "created"), status["state"]
    # coder 的任务文件明显小于整份文书；整读全量的角色（提取、计划首派）任务文件只是一张清单
    assert seen["implement"] and seen["verify"]
    assert _digest(root / "workspace" / case / "state.json") == copy_state  # fork 不动源案例
    assert _digest(REPO_ROOT / "workspace" / case / "state.json") == real_state  # 更不动真实案例


def test_r009_revise_replay_reruns_m2_to_m5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """r009 在 2026-08-26 做过两次 revise（聚源中观指标扩展替代池、海关表补拉），当时都是重跑 m2–m5。"""
    case = "r009_industry_rotation"
    _require_case(case)
    real_state = _digest(REPO_ROOT / "workspace" / case / "state.json")
    root = _copy_case(tmp_path, case, monkeypatch)
    summary = st.migrate_to_v2(root, case)
    assert (root / "workspace" / case / summary["backup"].split("/")[-1]).is_file() if summary.get("backup") else True
    assert st.load_state(root, case)["schema_version"] == st.SCHEMA_VERSION_V2
    docs = packs.CaseDocs.load(root, case)
    engine = Engine(root, case, host="claude_code")
    for assumption in ("AS18", "AS19", "AS41"):
        block = docs.assumption(assumption)
        assert block is not None and block.field("影响面").value.strip() == "data"
        plan = decisions.revise(engine, assumption=assumption, text="回放：口径改动", dry_run=True)
        assert plan["dry_run"] is True and plan["scope"] == "data"
        assert plan["milestones"] == ["m2", "m3", "m4", "m5"], (assumption, plan["milestones"])
        assert plan["stages"][0] == "implement" and "plan" not in plan["stages"] and plan["stages"][-1] == "review"
    # 只算不做：状态没有被推进
    state = st.load_state(root, case)
    assert state["status"] == "awaiting_review" and state["current_stage"] == "report"
    assert _digest(REPO_ROOT / "workspace" / case / "state.json") == real_state


def test_r010_data_requirements_replay_flags_hk_cross_section_collapse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """r010 的 plan 照手写目录把港股个股行情标成 available，缺口到 m1 编码时才被发现；机器查只要一瞬间。"""
    case = "r010_breakout_ratio_timing"
    _require_case(case, need_output=False)
    data_root = datacheck.resolve_data_root(REPO_ROOT)
    if not (data_root / "hkshare_stock_quote.parquet").is_file():
        pytest.skip("本机数据根里没有 hkshare_stock_quote.parquet")
    pytest.importorskip("pyarrow")
    root = _copy_case(tmp_path, case, monkeypatch)

    legacy = datacheck.check_requirements(root, case, data_root=data_root)
    assert legacy["summary"]["total"] == 10 and legacy["summary"]["gaps"] == 0  # 旧 plan 没有可查字段，只查文件在不在

    plan = root / "workspace" / case / "plan.md"
    text = plan.read_text(encoding="utf-8")
    old = "  - name: H股个股日行情（H股平行实证）\n    source: hkshare_stock_quote.parquet\n    status: available\n"
    assert text.count(old) == 1
    fields = "    files: [hkshare_stock_quote.parquet]\n    period: [2014-01-01, 2025-06-30]\n    freq: D\n    min_codes: 200\n    core: false\n"
    plan.write_text(text.replace(old, old + fields), encoding="utf-8")

    result = datacheck.check_requirements(root, case, data_root=data_root)
    item = next(r for r in result["requirements"] if r["name"].startswith("H股个股日行情"))
    codes = {p["code"] for p in item["problems"]}
    assert item["result"] == "partial" and item["plan_mismatch"] is True and "cross_section_collapse" in codes, (item["result"], codes)
    collapse = next(p for p in item["problems"] if p["code"] == "cross_section_collapse")
    yearly = collapse["evidence"]["yearly_codes"]
    assert max(yearly[str(year)] for year in range(2014, 2025)) < 200 <= yearly["2025"]
    assert result["summary"]["open_gaps"] == 1 and result["summary"]["ok"] == 9
    report = datacheck.render_gap_report(result, only_open=True)
    assert "hkshare_stock_quote.parquet" in report and "plan 没把它当缺口" in report


@pytest.mark.parametrize("case", ("r009_industry_rotation", "r010_breakout_ratio_timing"))
def test_review_prompts_render_cleanly_on_real_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    _require_case(case)
    root = _copy_case(tmp_path, case, monkeypatch)
    known = extreview.KNOWN_PLACEHOLDERS
    for kind in ("spec", "code", "result"):
        job = extreview.prepare(root, case, kind, 1, engine="codex", host="claude_code", config={}, force_full=True)
        job_dir = root / job["dir"]
        prompts = sorted(job_dir.glob("prompt_*.md"))
        assert prompts, (kind, job["dir"])
        for prompt in prompts:
            text = prompt.read_text(encoding="utf-8")
            left = [m.group(0) for m in extreview._TOKEN_RE.finditer(text) if (m.group(1) or m.group(2)) in known]
            assert not left, (kind, prompt.name, left[:5])
            assert case in text  # 提示词确实是给这个案例填的
        # 预算按每次调用算：当场拼好的输入包不超预算；要等上一次调用产出的（规格审查的第二次调用）先记下预算，执行时再按它拼
        budget = extreview.settings({}, kind, "codex")["budget_bytes"]
        assert job["budget_bytes"] == budget
        for call in job["calls"]:
            if call.get("deferred_input"):
                assert 0 < int(call["budget_bytes"]) <= budget and not (job_dir / call["input"]).exists()
            else:
                assert 0 < (job_dir / call["input"]).stat().st_size <= budget, (kind, call["name"])
        assert [c["name"] for c in job["calls"]] == (["blind", "review"] if kind == "spec" else ["main"])
        if kind == "spec":
            # 盲提取那一次调用的输入包里不能有 spec 的内容
            blind = (job_dir / "input_blind.md").read_text(encoding="utf-8")
            assert "spec/spec.md" not in blind and "report_text.md" in blind
