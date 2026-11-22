"""tools/check_gates.py 抽出的四个可复用函数：evaluate / parse_review / recalc_comparison / stale_outputs。

这些函数只是把原有逻辑换了个可调用的形态，判定口径不变；这里断言它们与门禁沿用的入口
给出同样的结论，并检查附加字段（明细、逐条结果、过期文件清单）。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import check_gates as cg  # noqa: E402
from tools import state as st  # noqa: E402

STANDARDS = {
    "factor": {
        "metrics": {
            "rank_ic_mean": {"max_rel_dev": 0.20, "require_same_sign": True, "abs_eps": 0.005},
            "default": {"max_rel_dev": 0.15},
        },
        "required_charts": [],
        "required_excels": [],
    }
}


def _case(tmp_path: Path, schema_version: int = 1) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf", schema_version=schema_version)
    st.set_field(tmp_path, "demo", "type", "factor")
    templates = tmp_path / "templates"
    templates.mkdir(exist_ok=True)
    (templates / "standards.json").write_text(json.dumps(STANDARDS), encoding="utf-8")


def _verify_artifacts(tmp_path: Path, metrics: list[dict], qualitative: list[dict] | None = None) -> None:
    results = tmp_path / "output" / "demo" / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "run_log.md").write_text("exit=0\n", encoding="utf-8")
    (results / "comparison.json").write_text(
        json.dumps({"metrics": metrics, "qualitative": qualitative or []}, ensure_ascii=False), encoding="utf-8"
    )
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text("print('demo')\n", encoding="utf-8")
    later = time.time() + 5
    for name in ("run_log.md", "comparison.json"):
        os.utime(results / name, (later, later))


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


def test_evaluate_matches_run_gate_and_cli_output(tmp_path: Path, monkeypatch, capsys) -> None:
    _case(tmp_path)
    _verify_artifacts(tmp_path, [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": -0.06}])
    result = cg.evaluate(tmp_path, "demo", "verify")
    direct = cg.run_gate(tmp_path, "demo", "verify")
    assert [(c.id, c.passed, c.detail) for c in result.checks] == [(c.id, c.passed, c.detail) for c in direct]
    assert result.verdict == "FAIL" and not result.passed
    failed_ids = [c.id for c in result.failed()]
    assert "G-VF-3" in failed_ids

    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    rc = cg.main(["demo", "--stage", "verify"])
    assert rc == 1
    assert capsys.readouterr().out == result.render() + "\n"


def test_evaluate_assert_done(tmp_path: Path) -> None:
    _case(tmp_path)
    result = cg.evaluate(tmp_path, "demo", "init", assert_done=True)
    assert result.assert_done and result.verdict == "FAIL"
    assert [c.id for c in result.checks] == ["ASSERT-DONE"]
    st.set_stage(tmp_path, "demo", "init", "done")
    assert cg.evaluate(tmp_path, "demo", "init", assert_done=True).passed


def test_evaluate_does_not_write_anything(tmp_path: Path) -> None:
    _case(tmp_path)
    before = st.state_path(tmp_path, "demo").read_bytes()
    cg.evaluate(tmp_path, "demo", "verify")
    cg.evaluate(tmp_path, "demo", "plan", assert_done=True)
    assert st.state_path(tmp_path, "demo").read_bytes() == before


def test_to_record_shapes(tmp_path: Path) -> None:
    _case(tmp_path)
    _verify_artifacts(tmp_path, [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": -0.06}])
    result = cg.evaluate(tmp_path, "demo", "verify")
    plain = result.to_record()
    assert all(set(item) == {"id", "desc", "result"} for item in plain)  # 与旧版入账内容同形
    detailed = {item["id"]: item for item in result.to_record(with_detail=True)}
    assert "rank_ic_mean" in detailed["G-VF-3"]["detail"]
    assert "detail" not in detailed["G-VF-1"]  # 通过项不带明细


def test_cli_record_v1_payload_unchanged_and_v2_keeps_details(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    metrics = [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": -0.06}]

    _case(tmp_path)
    _verify_artifacts(tmp_path, metrics)
    assert cg.main(["demo", "--stage", "verify", "--record"]) == 1
    v1 = st.load_state(tmp_path, "demo")
    assert all(set(c) == {"id", "desc", "result"} for c in v1["gates"][-1]["checks"])

    import shutil

    shutil.rmtree(tmp_path / "workspace")
    _case(tmp_path, schema_version=2)
    assert cg.main(["demo", "--stage", "verify", "--record"]) == 1
    v2 = st.load_state(tmp_path, "demo")
    assert all(set(c) == {"id", "desc", "result"} for c in v2["gates"][-1]["checks"])  # state.gates 形状不变
    failed = {c["id"]: c for c in v2["gate_latest"]["verify"]["failed"]}
    assert "rank_ic_mean" in failed["G-VF-3"]["detail"]
    gate_event = [r for r in st.read_event_records(tmp_path, "demo") if r["event"] == "gate:verify"][-1]
    logged = {c["id"]: c for c in gate_event["payload"]["checks"]}
    assert "rank_ic_mean" in logged["G-VF-3"]["detail"]  # 明细全文在事件流
    capsys.readouterr()


def test_long_gate_detail_is_clipped_in_state_but_full_in_log(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf", schema_version=2)
    long_detail = "超差指标 " * 400
    st.record_gate(
        tmp_path, "demo", "verify", "FAIL", [{"id": "G-VF-3", "desc": "重算", "result": "FAIL", "detail": long_detail}]
    )
    state = st.load_state(tmp_path, "demo")
    kept = state["gate_latest"]["verify"]["failed"][0]["detail"]
    assert len(kept) < len(long_detail) and kept.startswith(long_detail[: st.GATE_DETAIL_KEEP])
    record = st.read_event_records(tmp_path, "demo")[-1]
    assert record["payload"]["checks"][0]["detail"] == long_detail


# ---------------------------------------------------------------------------
# parse_review
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, issues, verdict, source",
    [
        ('{"verdict": "pass", "findings": []}', 0, "pass", "json"),
        ('说明\n```json\n{"verdict": "fail", "findings": [{"id": "CDX-R-01"}, {"id": "CDX-R-02"}]}\n```\n', 2, "fail", "fenced_json"),
        ('<<<SPEC_CODEX>>>\n盲提取内容\n<<<END>>>\n{"verdict": "pass_with_issues", "findings": [{"id": "CDX-S-01"}]}\n', 1, "pass_with_issues", "trailing_json"),
        ("| ID | 严重度 |\n|---|---|\n| CDX-C-01 | major |\n| 汇总 | - |\n\nVERDICT: fail\n", 1, "fail", "table"),
        ("没有任何结构化内容\n", 0, None, "table"),
    ],
)
def test_parse_review_formats(tmp_path: Path, text: str, issues: int, verdict, source: str) -> None:
    path = tmp_path / "review.md"
    path.write_text(text, encoding="utf-8")
    parsed = cg.parse_review(path)
    assert (parsed.issues, parsed.verdict, parsed.source) == (issues, verdict, source)
    assert len(parsed.findings) == issues
    assert cg._parse_codex_output(path) == (issues, verdict)  # 门禁沿用的入口结论一致


def test_parse_review_missing_file(tmp_path: Path) -> None:
    parsed = cg.parse_review(tmp_path / "nope.md")
    assert (parsed.issues, parsed.verdict, parsed.findings, parsed.source) == (None, None, [], None)
    assert cg._parse_codex_output(tmp_path / "nope.md") == (None, None)


# ---------------------------------------------------------------------------
# recalc_comparison
# ---------------------------------------------------------------------------


def test_recalc_comparison_strict_mode_per_metric_results() -> None:
    comparison = {
        "metrics": [
            {"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": False},  # 实际通过
            {"key": "sharpe", "report_value": 1.0, "reproduced_value": 2.0, "pass": True},  # 实际超差
            {"key": "na_metric", "report_value": 1.0, "reproduced_value": None, "verification_level": "unverifiable"},
        ],
        "qualitative": [{"key": "q1", "expect": "up", "observed": "up"}, {"key": "q2", "expect": "up", "observed": "down"}],
    }
    result = cg.recalc_comparison(comparison, STANDARDS, "factor", experimental=False)
    assert result.ok is False and not result.experimental
    assert [m.key for m in result.metrics] == ["rank_ic_mean", "sharpe", "na_metric"]
    by_key = {m.key: m.passed for m in result.metrics}
    assert by_key["rank_ic_mean"] is True and by_key["sharpe"] is False
    assert result.qualitative == [{"key": "q1", "passed": True}, {"key": "q2", "passed": False}]
    assert any(f.startswith("sharpe[") for f in result.fails)
    assert "q2[定性指标 expect!=observed]" in result.fails
    assert result.detail.startswith("未通过: ")
    if by_key["na_metric"] is None:  # unverifiable 的豁免必须透明列出
        assert result.waived == ["na_metric"] and "unverifiable 豁免 1 项" in result.detail


def test_recalc_comparison_experimental_mode() -> None:
    comparison = {
        "metrics": [
            {"key": "a", "report_value": 1.0, "reproduced_value": 9.9},  # 数值不对齐也算在位
            {"key": "b", "report_value": 1.0, "reproduced_value": None},
        ],
        "qualitative": [{"key": "q", "expect": "x", "observed": ""}],
    }
    result = cg.recalc_comparison(comparison, STANDARDS, "factor", experimental=True)
    assert result.ok is False and result.experimental
    assert [(m.key, m.passed) for m in result.metrics] == [("a", True), ("b", False)]
    assert result.fails == ["b[实验模式：迁移市场产出缺失]", "q[实验模式：定性观察缺失]"]

    ok = cg.recalc_comparison({"metrics": [{"key": "a", "reproduced_value": 1}], "qualitative": []}, STANDARDS, "factor", True)
    assert ok.ok and ok.detail.startswith("实验模式（市场迁移）：1 项指标产出完整")


def test_recalc_comparison_missing_file() -> None:
    result = cg.recalc_comparison(None, STANDARDS, "factor", experimental=False)
    assert (result.ok, result.detail, result.metrics) == (False, "comparison.json 不可用，无法重算", [])


def test_recalc_comparison_agrees_with_check_verify(tmp_path: Path) -> None:
    _case(tmp_path)
    metrics = [
        {"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055},
        {"key": "sharpe", "report_value": 1.0, "reproduced_value": 1.5},
    ]
    _verify_artifacts(tmp_path, metrics)
    g3 = {c.id: c for c in cg.check_verify(tmp_path, "demo")}["G-VF-3"]
    direct = cg.recalc_comparison({"metrics": metrics, "qualitative": []}, cg.load_standards(tmp_path), "factor", False)
    assert (g3.passed, g3.detail) == (direct.ok, direct.detail)


# ---------------------------------------------------------------------------
# stale_outputs
# ---------------------------------------------------------------------------


def test_stale_outputs_lists_files_not_newer_than_src(tmp_path: Path) -> None:
    src = tmp_path / "src"
    out = tmp_path / "results"
    src.mkdir()
    out.mkdir()
    (src / "a.py").write_text("x", encoding="utf-8")
    (src / "b.py").write_text("y", encoding="utf-8")
    (out / "old.png").write_bytes(b"1")
    (out / "new.json").write_text("{}", encoding="utf-8")
    cache = src / "__pycache__"
    cache.mkdir()
    (cache / "a.cpython-311.pyc").write_bytes(b"0")
    base = time.time()
    os.utime(src / "a.py", (base, base))
    os.utime(src / "b.py", (base + 10, base + 10))
    os.utime(out / "old.png", (base + 5, base + 5))
    os.utime(out / "new.json", (base + 20, base + 20))
    os.utime(cache / "a.cpython-311.pyc", (base + 99, base + 99))  # 字节码缓存不计入

    fresh = cg.stale_outputs(src, out)
    assert fresh.ok is False
    assert fresh.latest_src == src / "b.py" and fresh.earliest_out == out / "old.png"
    assert fresh.stale == [out / "old.png"]
    assert cg._check_freshness(src, out) == (fresh.ok, fresh.detail)

    os.utime(out / "old.png", (base + 30, base + 30))
    fresh = cg.stale_outputs(src, out)
    assert fresh.ok is True and fresh.stale == []


def test_stale_outputs_missing_dirs(tmp_path: Path) -> None:
    fresh = cg.stale_outputs(tmp_path / "nope", tmp_path / "nope2")
    assert (fresh.ok, fresh.detail, fresh.stale) == (False, "src 或 output/{id}/results 目录不存在", [])
    (tmp_path / "s").mkdir()
    (tmp_path / "o").mkdir()
    assert cg.stale_outputs(tmp_path / "s", tmp_path / "o").detail == "src 或 results 下没有文件可比较"
