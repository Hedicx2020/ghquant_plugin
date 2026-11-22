"""tools/flowlib/precheck.py 的测试：结果一致性预检（P1–P4）、机器生成块、对比总表与计数。

夹具策略：在 tmp_path 下造最小案例（state.json / templates/standards.json / coverage_matrix.md /
comparison.json / metrics.json / verify_report.md / final_report.md），只走公开接口，不依赖真实
案例数据。「8 类夹具」取自 r008–r010 三个真实案例结果外审的 critical 意见形态，每类一个，
断言被报出、且报在对应的检查项上。文末三个真实案例只做冒烟：不抛异常、不写文件，文件不在就跳过。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.flowlib import precheck as pc  # noqa: E402

RID = "demo"

STANDARDS = {
    "timing": {
        "metrics": {"default": {"max_rel_dev": 0.05}},
        "required_charts": [],
        "required_excels": [],
    }
}

MATRIX_HEADER = "| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |"

# (要素ID, 优先级, 状态)：R1 / R2 / R10 / SA1 要求有对比条目；R3、SA2 已放弃；R4 不是 core；D / F / B 类不查
BASE_MATRIX = [
    ("D1", "core", "done"),
    ("F1", "core", "done"),
    ("B1", "core", "done"),
    ("R1", "core", "done"),
    ("R2", "core", "done"),
    ("R3", "core", "skipped"),
    ("R4", "extended", "done"),
    ("R10", "core", "done"),
    ("SA1", "core", "done"),
    ("SA2", "core", "infeasible"),
]

BASE_METRICS_JSON = {
    "strategies": {"core": {"annual_return": 0.10412345, "max_drawdown": -0.23008}},
    "table2": [{"sharpe": 0.52}],
}

BEGIN = "<!-- flow:generated {name} BEGIN（由内核生成，勿手改；改了会被覆盖） -->"
END = "<!-- flow:generated {name} END -->"

# 数值 4 项（重算达标 3、未达标 1）、定性 1 项（达标 1）：合计 5 项，达标 4
BASE_VERIFY = """# demo 验证报告

## 一、运行记录

- 运行时间 2026-11-20 10:21:07，exit=0。
- comparison.json 重算通过，日志第 3/12 页，数据截至 2026/10/31，复核日期 11/20 通过。
- comparison.json 里 R1 分年通过 7/14 年，R2 簇内达标 2/3。

## 二、指标对比

### final.3 核心指标对照

| 指标 | 研报值 | 复现值 | 偏差 |
| --- | --- | --- | --- |
| r1_annual_return | 10.49% | 10.41% | 0.76% |
| R1 最大回撤 | -22.79% | 23.01% | 0.97% |
| r2_sharpe | 0.76 | 0.52 | 31.58% |
| R10 超额年化 | 4.62% | 4.5% | 2.38% |

## 三、结论

comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。
"""

BASE_FINAL = """# demo 最终复现报告

## 结论

- 数值指标：3 / 4 项通过（pass_count 按重算口径）；定性指标：1 / 1 项通过。
- comparison.json 共 5 项验证条目（4 项数值 metrics + 1 项定性 qualitative）。

## 指标对比总表

| 名称 | 研报 | 本次复现 |
| --- | --- | --- |
| R2 夏普比率 | 0.76 | 0.52 |
| R1 策略年化收益 | 0.1049 | 0.1041 |
"""


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


def _metric(key: str, name: str, element: str, report: Any, reproduced: Any, passed: Any, **extra: Any) -> dict:
    entry = {
        "key": key,
        "name": name,
        "source_element": element,
        "report_value": report,
        "reproduced_value": reproduced,
        "pass": passed,
    }
    entry.update(extra)
    return entry


def _base_metrics() -> list[dict]:
    return [
        _metric("r1_annual_return", "R1 策略年化收益", "R1表", 0.1049, 0.1041, True, source_pointer="strategies.core.annual_return"),
        _metric("r1_max_drawdown", "R1 最大回撤", "R1表", -0.2279, -0.2301, True, source_pointer="strategies.core.max_drawdown"),
        _metric("r2_sharpe", "R2 夏普比率", "R2 分年表", 0.76, 0.52, False),
        _metric("r10_excess_return", "R10 超额年化", "R10（图表34）", 0.0462, 0.0451, True),
    ]


def _base_qualitative() -> list[dict]:
    return [{"key": "sa1_direction", "source_element": "SA1 稳健性", "expect": "正收益", "observed": "正收益", "pass": True}]


def _matrix_text(rows: list[tuple[str, str, str]]) -> str:
    lines = ["# 覆盖矩阵", "", MATRIX_HEADER, "|" + "---|" * 11]
    for element_id, priority, status in rows:
        category = "SA" if element_id.startswith("SA") else element_id[0]
        lines.append(
            f"| {element_id} | {category} | {element_id} 的描述 | p1 | {priority} | m1 | {status} | — | src/demo/strategy.py | — | 2026-11-22 |"
        )
    lines += ["", "## 变更日志", "", "| 时间 | 事件 | 来源 | 说明 |", "|---|---|---|---|", "| 2026-11-22 | 初始化 | extract | — |"]
    return "\n".join(lines) + "\n"


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_case(
    root: Path,
    *,
    metrics: Optional[list[dict]] = None,
    qualitative: Optional[list[dict]] = None,
    top: Optional[dict] = None,
    matrix: Optional[list[tuple[str, str, str]]] = None,
    metrics_json: Any = BASE_METRICS_JSON,
    verify: Optional[str] = BASE_VERIFY,
    final: Optional[str] = BASE_FINAL,
    mode: str = "strict",
    previous: Optional[dict] = None,
) -> Path:
    """在 root 下造一个最小案例；默认是文书与机器结果全部一致的那一个。"""
    ws = root / "workspace" / RID
    out = root / "output" / RID
    (ws / "spec").mkdir(parents=True, exist_ok=True)
    (out / "results").mkdir(parents=True, exist_ok=True)
    _dump(ws / "state.json", {"reproduction_mode": mode, "type": "timing", "difficulty": "medium", "stages": {}})
    _dump(root / "templates" / "standards.json", STANDARDS)
    (ws / "spec" / "coverage_matrix.md").write_text(_matrix_text(BASE_MATRIX if matrix is None else matrix), encoding="utf-8")
    comparison = {
        "metrics": _base_metrics() if metrics is None else metrics,
        "qualitative": _base_qualitative() if qualitative is None else qualitative,
    }
    comparison.update(top or {})
    _dump(out / "results" / "comparison.json", comparison)
    if metrics_json is not None:
        _dump(out / "results" / "metrics.json", metrics_json)
    if verify is not None:
        (out / "verify_report.md").write_text(verify, encoding="utf-8")
    if final is not None:
        (ws / "final_report.md").write_text(final, encoding="utf-8")
    if previous is not None:
        _dump(ws / "iterations" / "iter_01" / "comparison.json", previous)
    return root


def _swap(text: str, old: str, new: str) -> str:
    """替换文书里的一段；原文里没有这一段时直接报错，免得夹具悄悄失效。"""
    assert old in text, f"夹具里找不到要替换的原文：{old!r}"
    return text.replace(old, new)


def _line_of(text: str, needle: str) -> int:
    for no, line in enumerate(text.split("\n"), 1):
        if needle in line:
            return no
    raise AssertionError(f"文书里没有这一段：{needle!r}")


def _by(result: pc.PrecheckResult, check: str, level: Optional[str] = None) -> list[pc.Finding]:
    return [f for f in result.findings if f.check == check and (level is None or f.level == level)]


def _previous_with(key: str, reproduced: float) -> dict:
    """上一版 comparison：只有一条指标的复现值与当前不同。"""
    metrics = _base_metrics()
    for entry in metrics:
        if entry["key"] == key:
            entry["reproduced_value"] = reproduced
    return {"metrics": metrics, "qualitative": _base_qualitative()}


# ---------------------------------------------------------------------------
# 全部一致的案例
# ---------------------------------------------------------------------------


def test_consistent_case_passes_with_single_line(tmp_path):
    _make_case(tmp_path)
    for stage in ("result", "report"):
        result = pc.run_precheck(tmp_path, RID, stage=stage)
        assert result.findings == [], result.render()
        assert result.blocked is False
        assert "\n" not in result.render()
        assert "通过" in result.render()

    stats = pc.run_precheck(tmp_path, RID, stage="report").stats
    assert stats["metrics_total"] == 4
    assert stats["metrics_pass"] == 3  # r2_sharpe 偏差 31.6% 超出 5% 容差
    assert stats["qualitative_total"] == 1
    assert stats["core_elements"] == 4
    assert stats["core_element_ids"] == ["R1", "R2", "R10", "SA1"]
    assert stats["pointers_checked"] == 2
    checked = stats["checked_files"]
    assert f"output/{RID}/results/comparison.json" in checked
    assert f"output/{RID}/results/metrics.json" in checked
    assert f"workspace/{RID}/spec/coverage_matrix.md" in checked
    assert f"output/{RID}/verify_report.md" in checked
    assert f"workspace/{RID}/final_report.md" in checked


def test_result_stage_only_reads_verify_report(tmp_path):
    bad_final = _swap(BASE_FINAL, "| R2 夏普比率 | 0.76 | 0.52 |", "| R2 夏普比率 | 0.76 | 0.58 |")
    _make_case(tmp_path, final=bad_final)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.findings == []
    assert f"workspace/{RID}/final_report.md" not in result.stats["checked_files"]
    assert pc.run_precheck(tmp_path, RID, stage="report").blocked is True


def test_to_dict_is_json_serializable(tmp_path):
    _make_case(tmp_path, verify=_swap(BASE_VERIFY, "| r1_annual_return | 10.49% | 10.41% |", "| r1_annual_return | 10.49% | 10.93% |"))
    result = pc.run_precheck(tmp_path, RID, stage="report")
    data = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
    assert data["report_id"] == RID and data["stage"] == "report"
    assert data["blocked"] is True
    assert data["findings"][0].keys() == {"check", "level", "message", "where"}
    assert data["stats"]["block"] == len([f for f in result.findings if f.level == "block"])


def test_invalid_stage_rejected(tmp_path):
    _make_case(tmp_path)
    with pytest.raises(ValueError):
        pc.run_precheck(tmp_path, RID, stage="verify")


# ---------------------------------------------------------------------------
# 8 类 critical 形态
# ---------------------------------------------------------------------------


def test_critical_copied_value_differs_row_matched_by_key(tmp_path):
    """手抄数值与 comparison 不符（形态一，r008 CDX-R-01）：对比表里按指标编号对上的行，复现值抄的是别的口径。"""
    verify = _swap(BASE_VERIFY, "| r1_annual_return | 10.49% | 10.41% |", "| r1_annual_return | 10.49% | 10.93% |")
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is True
    hits = _by(result, "P4", "block")
    assert len(hits) == 1
    assert "r1_annual_return" in hits[0].message
    assert "10.93%" in hits[0].message and "0.1041" in hits[0].message
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '10.93%')}"
    assert _by(result, "P1") == [] and _by(result, "P2") == [] and _by(result, "P3") == []
    assert len(result.render().split("\n")) == 2


def test_critical_copied_value_differs_row_matched_by_name(tmp_path):
    """手抄数值与 comparison 不符（形态二）：报告里按指标名称对上的行，写成小数、位数也不同。"""
    final = _swap(BASE_FINAL, "| R2 夏普比率 | 0.76 | 0.52 |", "| R2 夏普比率 | 0.76 | 0.58 |")
    _make_case(tmp_path, final=final)
    result = pc.run_precheck(tmp_path, RID, stage="report")
    hits = _by(result, "P4", "block")
    assert len(hits) == 1
    assert "r2_sharpe" in hits[0].message and "0.58" in hits[0].message
    assert hits[0].where == f"workspace/{RID}/final_report.md:{_line_of(final, '0.58')}"


# 一行一个要素的宽表，单元格写「复现 vs 研报」：r008 verify_report.md 的要素汇总表就是这个样子
WIDE_TABLE = """
### final.4 要素汇总

| 要素 | 图表 | 策略年化（复现 vs 研报） | 超额年化（复现 vs 研报） | 备注 |
| --- | --- | --- | --- | --- |
| R1 | 图表3 | 10.41% vs 10.49%（偏差 0.76%） | — | 达标 |
| R10 | 图表34 | — | 4.51% vs 4.62%（偏差 2.38%） | 达标 |
"""


def test_critical_copied_value_differs_in_element_wide_table(tmp_path):
    """手抄数值与 comparison 不符（形态三，r008 CDX-R-01 的原样）：要素宽表里的「复现 vs 研报」单元格。"""
    _make_case(tmp_path, verify=BASE_VERIFY + WIDE_TABLE)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    verify = BASE_VERIFY + _swap(WIDE_TABLE, "4.51% vs 4.62%（偏差 2.38%）", "4.73% vs 4.62%（偏差 2.38%）")
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is True
    hits = _by(result, "P4", "block")
    assert len(hits) == 1 and len(result.findings) == 1
    # 说清是哪一栏、写的是什么、对上了哪条指标、机器结果是多少
    assert "超额年化（复现 vs 研报）" in hits[0].message and "4.73%" in hits[0].message
    assert "r10_excess_return" in hits[0].message and "0.0451" in hits[0].message
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '4.73% vs 4.62%')}"


def test_element_wide_table_variants(tmp_path):
    wrong = _swap(WIDE_TABLE, "4.51% vs 4.62%", "4.73% vs 4.62%")

    def check(name: str, table: str, **kwargs: Any) -> list[pc.Finding]:
        _make_case(tmp_path / name, verify=BASE_VERIFY + table, **kwargs)
        return _by(pc.run_precheck(tmp_path / name, RID, stage="result"), "P4")

    # 表头写的是「研报 vs 复现」：两个数换了位置
    flipped = WIDE_TABLE.replace("（复现 vs 研报）", "（研报 vs 复现）")
    flipped = _swap(_swap(flipped, "10.41% vs 10.49%", "10.49% vs 10.41%"), "4.51% vs 4.62%", "4.62% vs 4.51%")
    assert check("flipped", flipped) == []
    hits = check("flipped_wrong", _swap(flipped, "4.62% vs 4.51%", "4.62% vs 4.73%"))
    assert len(hits) == 1 and hits[0].level == "block"

    # 写的是上一版的旧值：按旧值残留提示，旧数值扫描不再重复报这一格
    hits = check("old", wrong, previous=_previous_with("r10_excess_return", 0.04731))
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "这是上一版 comparison 的旧值" in hits[0].message and "逐条改掉或标注为历史记录" in hits[0].message

    # 后文另有一张表里同一指标已是新值：提示
    hits = check("later", wrong + WIDE_TABLE.replace("final.4", "final.5"))
    assert len(hits) == 1 and hits[0].level == "warn" and "同一指标已是新值" in hits[0].message

    # 标了历史字样的章节、标了历史字样的列：不查
    assert check("section", wrong.replace("### final.4 要素汇总", "### final.4 要素汇总（历史记录）")) == []
    assert check("column", wrong.replace("超额年化（复现 vs 研报）", "上一轮超额年化（复现 vs 研报）")) == []


def test_critical_stale_number_from_previous_round_in_prose(tmp_path):
    """旧轮残留（形态一，r008 CDX-R-02）：正文里的统计沿用了上一轮的偏差。"""
    stale_line = "- 扰动测试触发判定：K2 不成立（最大相对偏差 45.96%，来自 R2 夏普比率）。"
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- 运行时间 2026-11-20 10:21:07，exit=0。\n" + stale_line)
    # 上一轮 r2_sharpe 复现 0.410712，偏差 |0.410712 - 0.76| / 0.76 = 45.96%；本轮 0.52，偏差 31.58%
    _make_case(tmp_path, verify=verify, previous=_previous_with("r2_sharpe", 0.410712))
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is False
    hits = _by(result, "P4")
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "45.96%" in hits[0].message and "r2_sharpe" in hits[0].message
    assert "逐条改掉或标注为历史记录" in hits[0].message
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '45.96%')}"
    assert result.stats["previous"] == f"workspace/{RID}/iterations/iter_01/comparison.json"

    scanned = pc.scan_stale_numbers(tmp_path, RID)
    assert scanned == hits
    assert all(f.level == "warn" for f in scanned)
    # 调用方直接给上一版的内容，结果一样
    assert pc.scan_stale_numbers(tmp_path, RID, previous=_previous_with("r2_sharpe", 0.410712)) == hits


def test_critical_stale_count_left_after_revision(tmp_path):
    """旧轮残留（形态二，r009 CDX-R-R1）：修订后终态已是新计数，前文还留着旧的「共 N 项」。"""
    stale_line = "- G-VF-3 处置：comparison.json 该步处置后共 6 项。"
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- 运行时间 2026-11-20 10:21:07，exit=0。\n" + stale_line)
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4")
    assert len(hits) == 1
    assert "共 6 项" in hits[0].message
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '共 6 项')}"
    # 后文的结论已经写了一致的「共 5 项」：按旧计数残留提示
    assert hits[0].level == "warn"
    assert "逐条改掉或标注为历史记录" in hits[0].message

    # 后文没有一致的写法时，这就是文书唯一的说法：阻断
    only = _swap(verify, "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），", "")
    _make_case(tmp_path, verify=only)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4")
    assert len(hits) == 1 and hits[0].level == "block"
    assert result.blocked is True

    # 真实原件的样子：旧计数和终态计数挤在同一行的前后两句里。照样按旧计数残留提示
    conclusion = "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"
    packed = (
        "- 处置记录：10 条胜率条目改为主口径数值，该步处置后共 6 项（5 metrics+1 qualitative）；"
        "随后按结果外审意见调整，终态 comparison.json 共 5 项（4 metrics+1 qualitative）。"
    )
    _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, packed))
    hits = _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4")
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "共 6 项" in hits[0].message and "5 metrics+1 qualitative" in hits[0].message
    assert "同一行的另一句里已有一致的写法" in hits[0].message

    # 写在同一句里的是变化过程，不报
    narrative = "- comparison.json 条目数：该步处置后共 6 项，终态共 5 项。"
    _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, narrative))
    assert _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4") == []


def test_critical_count_mismatch_parts_form_in_heading(tmp_path):
    """计数对不上（形态一，r009 CDX-R-03 的小节标题）：「N 项 metrics + M 项 qualitative」与实际条目数不符。"""
    verify = _swap(BASE_VERIFY, "### final.3 核心指标对照", "### final.3 核心指标对照（完整表见 comparison.json 4 项 metrics + 2 项 qualitative）")
    verify = _swap(verify, "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），", "")
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4", "block")
    assert len(hits) == 1
    assert "4 项 metrics + 2 项 qualitative" in hits[0].message
    assert "数值 3/4" in hits[0].message and "定性 1/1" in hits[0].message  # 报出重算口径是什么
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '2 项 qualitative')}"


def test_critical_count_mismatch_overall_ratio(tmp_path):
    """计数对不上（形态二，r009 CDX-R-03 的结论句）：overall_pass=true（N/N）与重算不符。"""
    verify = _swap(
        BASE_VERIFY,
        "overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。",
        "全部按语义 pass，overall_pass=true（6/6）。",
    )
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4", "block")
    assert len(hits) == 1
    assert "6/6" in hits[0].message
    assert hits[0].where == f"output/{RID}/verify_report.md:{_line_of(verify, '6/6')}"


def test_critical_core_elements_without_comparison_entry(tmp_path):
    """核心要素缺条目（r009 CDX-R-02）：矩阵里 SA5 / SA6 / SA7 是 core，comparison 里却没有它们。"""
    matrix = BASE_MATRIX + [("SA5", "core", "done"), ("SA6", "core", "done"), ("SA7", "core", "pending")]
    _make_case(tmp_path, matrix=matrix)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is True
    hits = _by(result, "P1", "block")
    assert len(hits) == 3  # 逐个报出
    for element_id, hit in zip(("SA5", "SA6", "SA7"), hits):
        assert f"核心要素 {element_id}" in hit.message
        assert hit.where.startswith(f"workspace/{RID}/spec/coverage_matrix.md:")
    assert result.stats["core_missing"] == ["SA5", "SA6", "SA7"]
    assert _by(result, "P4") == []

    # 补上条目：SA5 写了来源要素，SA6 只靠指标编号对上，SA7 没实测、显式标 N/A（r009 的写法）
    qualitative = _base_qualitative() + [
        {"key": "zhaoming_counterexample", "source_element": "SA5 反例", "expect": "R² 跃升", "observed": "R² 跃升", "pass": True},
        {"key": "sa6_high_prosperity_decay", "expect": "近年收益走弱", "observed": "近年收益走弱", "pass": True},
        {"key": "sa7_outlook_na", "expect": "N/A（研报 p41 优化方向展望，spec 标注未实测）", "observed": "展望项，原文未实测", "pass": True},
    ]
    verify = _swap(BASE_VERIFY, "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），", "")
    verify = _swap(verify, "，定性指标 1/1 通过，合计 4/5。", "。")
    _make_case(tmp_path, matrix=matrix, qualitative=qualitative, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert _by(result, "P1") == []
    assert result.stats["core_missing"] == []
    assert result.stats["explicit_na"] == 1


def test_critical_placeholder_value_counted_as_pass(tmp_path):
    """占位值计为通过（r009 CDX-R-01）：夏普 0/0 不可定义，对比条目按 0.0 占位、备注里承认，却照样记 pass。"""
    metrics = _base_metrics() + [
        _metric(
            "r7_sharpe|多空(动态)",
            "R7夏普比率-多空(动态)",
            "R7表",
            -0.70,
            0.0,
            True,
            note="全程空仓 120/120 月、年化波动 0，夏普 0/0 数学上不可定义，按 0.0 占位（非真实夏普值；metrics.json 如实保持 null）",
        )
    ]
    for entry in metrics:
        entry["pass"] = True
    _make_case(tmp_path, metrics=metrics, top={"overall_pass": True, "pass_count": 6, "total": 6}, mode="experimental", verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is True
    hits = _by(result, "P3", "block")
    assert len(hits) == 1
    assert "r7_sharpe|多空(动态)" in hits[0].message
    assert "占位" in hits[0].message and "计为通过" in hits[0].message
    assert hits[0].where.startswith(f"output/{RID}/results/comparison.json:")
    assert result.stats["empty_counted_as_pass"] == 1
    assert _by(result, "P1") == [] and _by(result, "P2") == [] and _by(result, "P4") == []


# ---------------------------------------------------------------------------
# P1 核心要素有对比条目
# ---------------------------------------------------------------------------


def test_r1_does_not_match_r10(tmp_path):
    # 矩阵要 R1，comparison 里只有 R10 的条目（来源要素、指标编号、名称都以 R10 开头）
    metrics = [_metric("r10_excess_return", "R10 超额年化", "R10（图表34）", 0.0462, 0.0451, True)]
    _make_case(tmp_path, matrix=[("R1", "core", "done")], metrics=metrics, qualitative=[], verify=None, final=None, metrics_json=None)
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P1", "block")
    assert len(hits) == 1 and "核心要素 R1" in hits[0].message
    assert result.stats["core_missing"] == ["R1"]

    # 反过来：矩阵要 R10，comparison 里只有 R1 的条目
    metrics = [_metric("r1_annual_return", "R1 策略年化收益", "R1表", 0.1049, 0.1041, True)]
    _make_case(tmp_path, matrix=[("R10", "core", "done")], metrics=metrics, qualitative=[], verify=None, final=None, metrics_json=None)
    result = pc.run_precheck(tmp_path, RID)
    assert result.stats["core_missing"] == ["R10"]

    # 两个都有：都不缺
    _make_case(tmp_path, matrix=[("R1", "core", "done"), ("R10", "core", "done")], verify=None, final=None)
    assert pc.run_precheck(tmp_path, RID).stats["core_missing"] == []


def test_source_element_matched_after_removing_whitespace(tmp_path):
    metrics = [
        _metric("annual", "策略年化", " R 1 表内格/p10 交叉验证", 0.1049, 0.1041, True),
        _metric("sharpe", "夏普", "R7/R15表", 0.76, 0.75, True),
        _metric("mdd", "回撤", "【R3.1】子变体", -0.2279, -0.2301, True),
    ]
    matrix = [("R1", "core", "done"), ("R7", "core", "done"), ("R15", "core", "done"), ("R3", "core", "done"), ("R3.1", "core", "done")]
    _make_case(tmp_path, matrix=matrix, metrics=metrics, qualitative=[], verify=None, final=None, metrics_json=None)
    result = pc.run_precheck(tmp_path, RID)
    assert _by(result, "P1") == []
    assert result.stats["core_elements"] == 5


def test_skipped_and_infeasible_core_elements_need_no_entry(tmp_path):
    _make_case(tmp_path, verify=None, final=None)  # 基础矩阵里 R3 skipped、SA2 infeasible，comparison 里都没有条目
    result = pc.run_precheck(tmp_path, RID)
    assert _by(result, "P1") == []
    assert "R3" not in result.stats["core_element_ids"] and "SA2" not in result.stats["core_element_ids"]

    # 状态改回 done 就要求有条目了
    matrix = [(eid, priority, "done" if eid in ("R3", "SA2") else status) for eid, priority, status in BASE_MATRIX]
    _make_case(tmp_path, matrix=matrix, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    assert result.stats["core_missing"] == ["R3", "SA2"]
    assert len(_by(result, "P1", "block")) == 2


def test_non_core_and_non_result_elements_ignored(tmp_path):
    # R4 是 extended，D1 / F1 / B1 不是 R、SA 类：都不要求对比条目
    _make_case(tmp_path, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    assert result.stats["core_element_ids"] == ["R1", "R2", "R10", "SA1"]


def test_explicit_na_by_verification_level(tmp_path):
    """r010 的写法：verification_level=unverifiable，研报值、复现值、pass 都是 null，来源要素写图表名。"""
    metrics = _base_metrics() + [
        _metric(
            "R5_coverage_ratio",
            "R5 覆盖度",
            "图表12",
            None,
            None,
            None,
            verification_level="unverifiable",
            attribution_status="assumption_linked",
            note="一致预期数据本地缺失，无法复现",
        )
    ]
    matrix = BASE_MATRIX + [("R5", "core", "infeasible_partial")]
    _make_case(tmp_path, matrix=matrix, metrics=metrics, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    assert result.findings == []  # 有显式 N/A 条目：P1 不缺；pass 为 null：P3 不报
    assert result.stats["explicit_na"] == 1
    assert result.stats["metrics_na"] == 1


def test_qualitative_entry_without_source_element_is_matched_by_key(tmp_path, monkeypatch):
    """定性条目按合同只有 key / expect / observed / pass：没写来源要素时，指标编号以要素编号开头即算。"""
    matrix = [("SA5", "core", "done"), ("SA50", "core", "done")]
    qualitative = [{"key": "sa5_zhaoming_counterexample", "expect": "R² 跃升", "observed": "R² 跃升", "pass": True}]
    _make_case(tmp_path, matrix=matrix, metrics=[], qualitative=qualitative, verify=None, final=None, metrics_json=None)
    monkeypatch.setattr(pc, "P1_KEY_FALLBACK", False)  # 不靠兜底开关
    result = pc.run_precheck(tmp_path, RID)
    assert result.stats["core_missing"] == ["SA50"]  # SA5 的条目不算 SA50 的
    assert [f.level for f in _by(result, "P1")] == ["block"]

    # 写了来源要素却对不上的，不算；只能走兜底开关
    qualitative[0]["source_element"] = "稳健性检验"
    _make_case(tmp_path, matrix=[("SA5", "core", "done")], metrics=[], qualitative=qualitative, verify=None, final=None, metrics_json=None)
    assert pc.run_precheck(tmp_path, RID).stats["core_missing"] == ["SA5"]
    monkeypatch.setattr(pc, "P1_KEY_FALLBACK", True)
    result = pc.run_precheck(tmp_path, RID)
    assert result.stats["core_missing"] == [] and [f.level for f in _by(result, "P1")] == ["warn"]


def test_key_fallback_can_be_turned_off(tmp_path, monkeypatch):
    metrics = [_metric("r10_strategy_annual_return", "策略年化", "EX34（图表34）", 0.1653, 0.1711, True)]
    _make_case(tmp_path, matrix=[("R10", "core", "done")], metrics=metrics, qualitative=[], verify=None, final=None, metrics_json=None)
    result = pc.run_precheck(tmp_path, RID)
    assert result.blocked is False
    assert len(_by(result, "P1", "warn")) == 1 and "R10" in _by(result, "P1", "warn")[0].message

    monkeypatch.setattr(pc, "P1_KEY_FALLBACK", False)
    result = pc.run_precheck(tmp_path, RID)
    assert result.blocked is True
    assert result.stats["core_missing"] == ["R10"]
    assert "EX34" in _by(result, "P1", "block")[0].message  # 说清对上的条目来源要素写的是什么


def test_missing_matrix_blocks_p1(tmp_path):
    _make_case(tmp_path, verify=None, final=None)
    (tmp_path / "workspace" / RID / "spec" / "coverage_matrix.md").unlink()
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P1", "block")
    assert len(hits) == 1 and "coverage_matrix.md" in hits[0].message


# ---------------------------------------------------------------------------
# P2 原始来源指针回查
# ---------------------------------------------------------------------------


def test_pointer_value_mismatch_blocks(tmp_path):
    metrics_json = {"strategies": {"core": {"annual_return": 0.1093, "max_drawdown": -0.23008}}}
    _make_case(tmp_path, metrics_json=metrics_json, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P2", "block")
    assert len(hits) == 1
    assert "r1_annual_return" in hits[0].message and "strategies.core.annual_return" in hits[0].message
    assert "0.1041" in hits[0].message and "0.1093" in hits[0].message
    assert hits[0].where.startswith(f"output/{RID}/results/comparison.json:")


def test_pointer_rounding_tolerance(tmp_path):
    # 复现值写到小数点后 4 位：原始值在末位半个单位以内算一致，超出就不算
    metrics = [_metric("r1_annual_return", "R1 策略年化收益", "R1表", 0.1049, 0.1041, True, source_pointer="a.b")]
    for raw, agrees in ((0.10414999, True), (0.10405001, True), (0.10416, False), (0.1040, False)):
        _make_case(tmp_path, matrix=[("R1", "core", "done")], metrics=metrics, qualitative=[], metrics_json={"a": {"b": raw}}, verify=None, final=None)
        result = pc.run_precheck(tmp_path, RID)
        assert (_by(result, "P2") == []) is agrees, raw


def test_pointer_forms_and_unresolvable_pointer(tmp_path):
    metrics = [
        _metric("r1_a", "年化", "R1表", 0.76, 0.52, False, source_pointer="table2[0].sharpe"),
        _metric("r1_b", "分年", "R1表", 0.10, 0.11, False, source_pointer="yearly[2015].ret"),
        _metric("r1_c", "带点的键", "R1表", 0.20, 0.21, False, source_pointer='metrics.json#perf["A.B"].sharpe'),
        _metric("r1_d", "带竖线的键", "R1表", 0.30, 0.31, False, source_pointer="m4|TOP5(动态).sharpe"),
        _metric("r1_e", "百分数存储", "R1表", 10.49, 10.41, True, unit="%", source_pointer="strategies.core.annual_return"),
        _metric("r1_f", "指不到", "R1表", 0.40, 0.41, False, source_pointer="strategies.missing.value"),
        _metric("r1_g", "下标越界", "R1表", 0.50, 0.51, False, source_pointer="table2[3].sharpe"),
        _metric("r1_h", "没带指针", "R1表", 0.60, 0.99, False),
    ]
    metrics_json = {
        "table2": [{"sharpe": 0.52}],
        "yearly": {"2015": {"ret": 0.11}},
        "perf": {"A.B": {"sharpe": 0.21}},
        "m4|TOP5(动态)": {"sharpe": 0.31},
        "strategies": {"core": {"annual_return": 0.10412345}},
    }
    _make_case(tmp_path, matrix=[("R1", "core", "done")], metrics=metrics, qualitative=[], metrics_json=metrics_json, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P2", "block")
    assert sorted(h.message.split(" ")[1] for h in hits) == ["r1_f", "r1_g"]
    assert all("取不到值" in h.message for h in hits)
    assert result.stats["pointers_checked"] == 7  # 没带指针的不查


def test_missing_metrics_json_blocks_only_when_pointers_exist(tmp_path):
    _make_case(tmp_path, metrics_json=None, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P2", "block")
    assert len(hits) == 1 and "metrics.json" in hits[0].message and "r1_annual_return" in hits[0].message

    metrics = _base_metrics()
    for entry in metrics:
        entry.pop("source_pointer", None)
    _make_case(tmp_path, metrics=metrics, metrics_json=None, verify=None, final=None)
    (tmp_path / "output" / RID / "results" / "metrics.json").unlink(missing_ok=True)
    assert pc.run_precheck(tmp_path, RID).findings == []


# ---------------------------------------------------------------------------
# P3 空值不得计为通过
# ---------------------------------------------------------------------------


def _p3_case(root: Path, entry: dict, *, mode: str = "strict", top: Optional[dict] = None, raw: str = "") -> pc.PrecheckResult:
    """造一个只有一条指标的案例；raw 给出时直接写 comparison.json 的原文（用来写 NaN 这类字面量）。"""
    _make_case(root, matrix=[("R1", "core", "done")], metrics=[entry], qualitative=[], top=top, mode=mode, verify=None, final=None, metrics_json={"x": None})
    if raw:
        (root / "output" / RID / "results" / "comparison.json").write_text(raw, encoding="utf-8")
    return pc.run_precheck(root, RID)


def test_null_value_with_self_declared_pass_blocks(tmp_path):
    result = _p3_case(tmp_path, _metric("r1_sharpe", "夏普", "R1表", 0.76, None, True))
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "r1_sharpe" in hits[0].message and "null" in hits[0].message


def test_nan_and_inf_values_counted_as_pass_block(tmp_path):
    for literal, shown in (("NaN", "NaN"), ("Infinity", "Inf"), ("-Infinity", "-Inf")):
        raw = (
            '{"metrics": [{"key": "r1_sharpe", "name": "夏普", "source_element": "R1表", "report_value": 0.76, '
            f'"reproduced_value": {literal}, "pass": true}}], "qualitative": []}}'
        )
        result = _p3_case(tmp_path, _metric("r1_sharpe", "夏普", "R1表", 0.76, 0.5, True), raw=raw)
        hits = _by(result, "P3", "block")
        assert len(hits) == 1 and shown in hits[0].message, literal


def test_experimental_mode_counts_nan_as_present_and_precheck_catches_it(tmp_path):
    # 实验模式的重算只核「产出在位」，NaN 会被算作在位；条目没写 pass 也照样报
    raw = '{"metrics": [{"key": "r1_sharpe", "source_element": "R1表", "report_value": 0.76, "reproduced_value": NaN}], "qualitative": []}'
    result = _p3_case(tmp_path, _metric("r1_sharpe", "夏普", "R1表", 0.76, 0.5, None), mode="experimental", raw=raw)
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "重算口径计为通过" in hits[0].message


def test_null_value_counted_through_top_level_pass_count(tmp_path):
    entry = _metric("r1_sharpe", "夏普", "R1表", 0.76, None, None)
    del entry["pass"]
    result = _p3_case(tmp_path, entry, top={"pass_count": 1, "total": 1})
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "pass_count=1" in hits[0].message

    # 顶层通过数没有把它算进去：不报
    result = _p3_case(tmp_path, entry, top={"pass_count": 0, "total": 1})
    assert _by(result, "P3") == []


def test_null_value_not_counted_as_pass_is_fine(tmp_path):
    result = _p3_case(tmp_path, _metric("r1_sharpe", "夏普", "R1表", 0.76, None, False))
    assert _by(result, "P3") == []


def test_qualitative_style_entry_is_exempt_from_p3(tmp_path):
    """研报值为 null、带文字 note 的对照项不在 P3 范围内（没有研报数值可比，通过与否看 note）。"""
    entry = _metric("r1_abs_dev_median", "R1 全表绝对偏差中位数", "R1表全量93格", None, None, True, note="原文无对应汇总值；逐格对照见 valuation_logic_l1.xlsx")
    result = _p3_case(tmp_path, entry)
    assert _by(result, "P3") == []

    # 没有 note 的不豁免
    entry = _metric("r1_abs_dev_median", "R1 全表绝对偏差中位数", "R1表全量93格", None, None, True)
    result = _p3_case(tmp_path, entry)
    assert len(_by(result, "P3", "block")) == 1


def test_placeholder_needs_sentinel_value_and_unnegated_admission(tmp_path):
    def run(value: float, note: str) -> list[pc.Finding]:
        entry = _metric("r1_sharpe", "夏普", "R1表", -0.70, value, True, note=note)
        return _by(_p3_case(tmp_path, entry, mode="experimental"), "P3")

    assert len(run(0.0, "全程空仓，按 0.0 占位，非真实夏普值")) == 1
    assert len(run(-999, "placeholder，数据未到")) == 1
    assert len(run(0.0, "夏普 0/0 不可定义")) == 1
    assert run(0.0, "本轮不再占位：多空组合全程有持仓，夏普实算为 0") == []  # 带否定的不算承认
    assert run(-0.3703, "此前按 0.0 占位，本轮已实算") == []  # 复现值不是 0 或哨兵值
    assert run(0.0, "当月收益恰为 0") == []  # 没有承认是占位


def test_placeholder_string_value_blocks(tmp_path):
    result = _p3_case(tmp_path, _metric("r1_sharpe", "夏普", "R1表", 0.76, "待补", True))
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "待补" in hits[0].message


def test_pointer_to_null_source_with_finite_value_blocks(tmp_path):
    entry = _metric("r1_sharpe", "夏普", "R1表", -0.70, 0.0, True, source_pointer="x")
    result = _p3_case(tmp_path, entry, mode="experimental")
    assert len(_by(result, "P2", "block")) == 1  # 复现值与原始值对不上
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "原始值是空的" in hits[0].message


def test_empty_observed_in_qualitative_counted_as_pass_blocks(tmp_path):
    qualitative = [{"key": "sa1_direction", "source_element": "SA1", "expect": "正收益", "observed": "", "pass": True}]
    _make_case(tmp_path, qualitative=qualitative, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID)
    hits = _by(result, "P3", "block")
    assert len(hits) == 1 and "sa1_direction" in hits[0].message


# ---------------------------------------------------------------------------
# P4 文书与机器结果一致
# ---------------------------------------------------------------------------


def test_copied_value_tolerates_format_differences(tmp_path):
    rows = {
        "| r1_annual_return | 10.49% | 10.41% | 0.76% |": [
            "| r1_annual_return | 10.49% | **10.41%** | 0.76% |",
            "| r1_annual_return | 10.49% | 0.1041 | 0.76% |",
            "| r1_annual_return | 10.49% | +10.4% | 0.76% |",
            "| r1_annual_return | 10.49% | 10.410% | 0.76% |",
            "| r1_annual_return | 10.49% | 10.41 %（向研报收敛） | 0.76% |",
            "| `r1_annual_return` | 10.49% | 10.41％ | 0.76% |",
        ],
        "| R1 最大回撤 | -22.79% | 23.01% | 0.97% |": [
            "| R1 最大回撤 | -22.79% | -23.01% | 0.97% |",
            "| R1 最大回撤 | -22.79% | −23.01% | 0.97% |",
            "| R1 最大回撤 | -22.79% | (23.01%) | 0.97% |",
            "| R1 最大回撤 | -22.79% | -0.2301 | 0.97% |",
            "| **R1 最大回撤** | -22.79% | -23% | 0.97% |",
        ],
    }
    for old, variants in rows.items():
        for new in variants:
            _make_case(tmp_path, verify=_swap(BASE_VERIFY, old, new))
            result = pc.run_precheck(tmp_path, RID, stage="result")
            assert result.findings == [], new


def test_copied_value_thousands_separator(tmp_path):
    metrics = _base_metrics() + [_metric("r1_trade_count", "R1 交易次数", "R1表", 1250, 1234, True)]
    row = "| R10 超额年化 | 4.62% | 4.5% | 2.38% |"
    verify = _swap(BASE_VERIFY, "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），", "")
    verify = _swap(verify, "数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。", "数值指标达标 4/5。")
    good = _swap(verify, row, row + "\n| r1_trade_count | 1,250 | 1,234 | 1.28% |")
    _make_case(tmp_path, metrics=metrics, verify=good)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    bad = _swap(verify, row, row + "\n| r1_trade_count | 1,250 | 1,243 | 1.28% |")
    _make_case(tmp_path, metrics=metrics, verify=bad)
    hits = _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4", "block")
    assert len(hits) == 1 and "r1_trade_count" in hits[0].message


def test_copied_value_only_checked_where_the_metric_can_be_identified(tmp_path):
    """认不出是哪条指标、哪个是复现值的地方不查：宁可漏报。"""
    extra = """
| 汇总项 | 图表 | 策略年化（复现 vs 研报） | 备注 |
| --- | --- | --- | --- |
| 全样本 | 图表6 | 99.99% vs 10.49%（偏差 1.43%） | 首格不是要素编号的行不查 |
| R1 | 图表6 | 99.99% vs 55.55% | 研报值对不上该要素任何条目的不查 |
| R2 | 图表7 | 99.99% vs 10.49% | 研报值是别的要素的条目的，不查 |
| R2 | 图表7 | 99.99% vs 0.8 | 研报值不足 3 位有效数字的不查 |
| R1 | 图表6 | 详见正文：99.99% vs 10.49% | 单元格不是以数对开头的不查 |

| 要素 | 图表 | 对照 | 备注 |
| --- | --- | --- | --- |
| R1 | 图表6 | 99.99% vs 10.49% | 列名没写明哪个是复现值的不查 |

| 指标 | 研报值 | 说明 |
| --- | --- | --- |
| r1_annual_return | 10.49% | 没有复现值列的表不查，这里写 99.99% 也不报 |
"""
    _make_case(tmp_path, verify=BASE_VERIFY + extra)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []


def test_page_date_and_subset_ratios_are_not_counts(tmp_path):
    """页码、日期、某个要素或某一簇的小计、带量词的比例，都不当成全案例的达标数。

    分母故意取 4（数值条目数）：这些写法一旦被当成达标数，「2/4」与重算的 3/4 对不上就会被报出来。
    """
    head = "- 运行时间 2026-11-20 10:21:07，exit=0。"
    guarded = [
        "- comparison.json 重算通过，日志第 2/4 页，数据截至 2026/10/31。",
        "- comparison.json 重算通过，复核日期 2/4 通过。",
        "- comparison.json 里 R2 分年通过 2/4 年。",
        "- 数值指标里 SA1 簇内达标 2/4。",
        "- 数值指标里 R1 表 2/4 格通过。",
        "- 数值指标抽查 2/4 条断言通过。",
        "- 数值指标门禁 G-VF 2/4 通过。",
        "- 数值指标相关的外审意见 2/4 已关闭、通过复核。",
        "- 数值指标里只有 2/4 个行业的拟合度通过检验。",
        "- 数值指标的版本号 2/4.1 通过校验，路径 a/2/4/b 通过。",
        "- 本轮共 4 项修改点，其中 2 项达标线附近的参数未动。",
        "- 第 2/4 批数据到位，通过率尚可。",
    ]
    _make_case(tmp_path, verify=_swap(BASE_VERIFY, head, "\n".join(guarded)))
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.findings == [], result.render()

    # 对照：去掉这些限定，同样的数字就是在讲达标数，要报出来
    for sentence in ("- comparison.json 重算后数值指标通过 2/4。", "- 数值指标达标 2/4。", "- 合计 2/4 通过。"):
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, head, sentence))
        result = pc.run_precheck(tmp_path, RID, stage="result")
        assert len(_by(result, "P4")) == 1, sentence
        assert "2/4" in _by(result, "P4")[0].message


def test_ratio_far_from_global_word_needs_matching_denominator(tmp_path):
    """没有紧挨着 overall_pass、合计这类字样的 a/b，分母得是条目总数才当成达标数（宁可漏认）。"""
    conclusion = "数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"
    # 句子里提到了 comparison，但 2/9 说的是别的东西
    verify = _swap(BASE_VERIFY, conclusion, "数值指标达标 3/4；comparison.json 重算通过，另核对 2/9 处引用通过。")
    _make_case(tmp_path, verify=verify)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    # 紧挨着全局字样：分母对不上也要报
    for sentence in ("合计通过 2/9。", "overall_pass=true（9/9）。", "总体 pass 8/9。"):
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, sentence))
        result = pc.run_precheck(tmp_path, RID, stage="result")
        assert len(_by(result, "P4", "block")) == 1, sentence


def test_copied_value_wrong_rounding_blocks(tmp_path):
    rows = {
        "| R1 最大回撤 | -22.79% | 23.01% | 0.97% |": ["| R1 最大回撤 | -22.79% | -24% | 0.97% |", "| R1 最大回撤 | -22.79% | 23.02% | 0.97% |"],
        "| r1_annual_return | 10.49% | 10.41% | 0.76% |": ["| r1_annual_return | 10.49% | 10.5% | 0.76% |", "| r1_annual_return | 10.49% | 0.105 | 0.76% |"],
        "| r2_sharpe | 0.76 | 0.52 | 31.58% |": ["| r2_sharpe | 0.76 | 0.520001 | 31.58% |", "| r2_sharpe | 0.76 | 0.76 | 31.58% |"],
    }
    for old, variants in rows.items():
        for new in variants:
            _make_case(tmp_path, verify=_swap(BASE_VERIFY, old, new))
            result = pc.run_precheck(tmp_path, RID, stage="result")
            assert len(_by(result, "P4", "block")) == 1, new


def test_count_forms_recognized(tmp_path):
    """各种明确在讲达标数的写法，数字不对都要报；对的不报。"""
    conclusion = "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"
    wrong = [
        "数值指标达标 2/4。",
        "数值指标共 4 项，其中 2 项达标。",
        "数值指标达标 2 项，共 4 项。",
        "4 项数值指标中 2 项通过。",
        "comparison.json 共 7 项验证条目。",
        "comparison.json 数值 4 + 定性 3。",
        "pass_count=2/4、overall_pass=false。",
        "数值指标未达标 2/4。",
    ]
    right = [
        "数值指标达标 3/4。",
        "数值指标共 4 项，其中 3 项达标。",
        "数值指标达标 3 项，共 4 项。",
        "4 项数值指标中 3 项通过。",
        "comparison.json 共 5 项验证条目。",
        "comparison.json 数值 4 + 定性 1。",
        "pass_count=3/4、overall_pass=false。",
        "数值指标未达标 1/4。",
    ]
    for sentence in wrong:
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, sentence))
        result = pc.run_precheck(tmp_path, RID, stage="result")
        assert len(_by(result, "P4", "block")) == 1, sentence
    for sentence in right:
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, sentence))
        result = pc.run_precheck(tmp_path, RID, stage="result")
        assert result.findings == [], sentence


def test_parts_naming_both_arrays_and_totals_near_the_entry_count(tmp_path):
    """没紧挨着 comparison 的「共 N 项」、点了两个数组名字的分项加和：数字贴近条目数才当作在讲总数。"""
    conclusion = "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"

    def check(sentence: str) -> list[pc.Finding]:
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, conclusion, sentence))
        return _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4")

    # r009 CDX-R-R1 的原句大致是这样：句子里没点名 comparison，两个数也都对不上当前的条目数
    hits = check("该步处置后共 6 项（5 metrics+1 qualitative）。")
    assert len(hits) == 1 and hits[0].level == "block"
    assert "共 6 项" in hits[0].message and "5 metrics+1 qualitative" in hits[0].message
    assert check("该步处置后共 5 项（4 metrics+1 qualitative）。") == []
    # 点了两个数组的名字：数值那一半贴近条目数就判，哪怕定性那一半对不上；用泛称写的同一句放过
    hits = check("该步处置后为 5 metrics+3 qualitative。")
    assert len(hits) == 1 and "5 metrics+3 qualitative" in hits[0].message
    assert check("该步处置后为数值 5 条 + 定性 3 条。") == []
    # 单说定性条目数也对（3 条定性贴近数值条目数 4，不认这个口径就会误报）
    three = _base_qualitative() + [
        {"key": "sa1_shape", "source_element": "SA1 稳健性", "expect": "单调", "observed": "单调", "pass": True},
        {"key": "r2_direction", "source_element": "R2 分年表", "expect": "同向", "observed": "同向", "pass": True},
    ]
    _make_case(tmp_path / "q3", qualitative=three, verify=_swap(BASE_VERIFY, conclusion, "修订后 qualitative 区共 3 项。"))
    assert _by(pc.run_precheck(tmp_path / "q3", RID, stage="result"), "P4") == []
    # 紧挨着 comparison.json 的，差多少都判
    assert len(check("comparison.json 共 30 项。")) == 1
    # 增减量、离条目数很远的分项、某一部分的小计、别的文件：都不是在讲对比表的条目总数
    assert check("本轮新增 2 项 metrics + 1 项 qualitative。") == []
    assert check("本步重写了 40 条 metrics + 3 条 qualitative 的备注。") == []
    assert check("comparison.json 的 metrics 区里涉及胜率的共 30 项，已逐条核对。") == []
    assert check("metrics 区其中胜率类共 6 项，已逐条核对。") == []
    assert check("metrics 区本步改动的共 6 项。") == []
    assert check("metrics.json 共 6 项，逐项与缓存一致。") == []
    # 泛称：两个数都跟条目数不沾边的，当作别的分项放过；数值那一半对得上条目数的才判
    assert check("其中方向可核验的有数值 9 条 + 定性 3 条。") == []
    assert len(check("对比条目为数值 4 条 + 定性 3 条。")) == 1


def test_count_in_change_sentence_or_history_is_not_reported(tmp_path):
    conclusion = "数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"
    # 同一行里写了变化过程，终值是对的
    verify = _swap(BASE_VERIFY, conclusion, "数值指标：上版 2/4 PASS → 本版 3/4 PASS。")
    _make_case(tmp_path, verify=verify)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    # 行内标了历史字样
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- 上一轮数值指标达标 2/4（历史记录）。")
    _make_case(tmp_path, verify=verify)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    # 所在章节的标题标了历史字样：计数、手抄表都不查
    history = """
## 四、历史轮次记录

数值指标达标 2/4。

| 指标 | 研报值 | 复现值 |
| --- | --- | --- |
| r2_sharpe | 0.76 | 0.41 |
"""
    _make_case(tmp_path, verify=BASE_VERIFY + history)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    # 同样的内容放在没标历史的章节里：文书最后的说法是错的，阻断
    _make_case(tmp_path, verify=BASE_VERIFY + history.replace("历史轮次记录", "补充记录"))
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert len(_by(result, "P4", "block")) == 2


def test_history_marked_column_is_skipped_but_other_columns_are_checked(tmp_path):
    """表头里标了历史字样的只是那一列不查；同一行的当前值照查。"""
    table = """
| 指标 | 上一轮复现 | 本轮复现 |
| --- | --- | --- |
| r2_sharpe | 0.41 | {current} |
"""
    previous = _previous_with("r2_sharpe", 0.410712)
    _make_case(tmp_path, verify=BASE_VERIFY + table.format(current="0.52"), previous=previous)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []

    _make_case(tmp_path, verify=BASE_VERIFY + table.format(current="0.58"), previous=previous)
    hits = _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4")
    assert len(hits) == 1 and hits[0].level == "block" and "0.58" in hits[0].message

    # 只有历史列的表：整行都不查
    only_old = "\n| 指标 | 复现值（修订前） |\n| --- | --- |\n| r2_sharpe | 0.41071 |\n"
    _make_case(tmp_path, verify=BASE_VERIFY + only_old, previous=previous)
    assert pc.run_precheck(tmp_path, RID, stage="result").findings == []


def test_count_equal_to_self_reported_but_not_recalculated(tmp_path, monkeypatch):
    """文书照抄 comparison.json 顶层自述的 pass_count / total，而自述与重算不一致：默认照样阻断。"""
    metrics = _base_metrics()
    metrics[2]["pass"] = True  # r2_sharpe 自述通过，实际偏差 31.6%
    conclusion = "comparison.json 共 5 项（4 项 metrics + 1 项 qualitative），overall_pass=false：数值指标达标 3/4，定性指标 1/1 通过，合计 4/5。"
    verify = _swap(BASE_VERIFY, conclusion, "数值对齐：pass_count=4/4、overall_pass=true。")
    _make_case(tmp_path, metrics=metrics, top={"overall_pass": True, "pass_count": 4, "total": 4}, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4", "block")
    assert len(hits) == 1 and "自述" in hits[0].message and "4/4" in hits[0].message

    monkeypatch.setattr(pc, "P4_SELF_REPORTED_LEVEL", "warn")
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is False and len(_by(result, "P4", "warn")) == 1


def test_superseded_level_can_be_made_strict(tmp_path, monkeypatch):
    stale_line = "- G-VF-3 处置：comparison.json 该步处置后共 6 项。"
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", stale_line)
    _make_case(tmp_path, verify=verify)
    assert pc.run_precheck(tmp_path, RID, stage="result").blocked is False
    monkeypatch.setattr(pc, "P4_SUPERSEDED_LEVEL", "block")
    assert pc.run_precheck(tmp_path, RID, stage="result").blocked is True


def test_copied_old_value_in_table_is_reported_as_stale(tmp_path):
    """对比表里的值等于上一版 comparison 的旧值：按旧数值残留提示，不阻断。"""
    verify = _swap(BASE_VERIFY, "| r2_sharpe | 0.76 | 0.52 | 31.58% |", "| r2_sharpe | 0.76 | 0.41 | 31.58% |")
    _make_case(tmp_path, verify=verify, previous=_previous_with("r2_sharpe", 0.410712))
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4")
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "r2_sharpe" in hits[0].message and "旧值" in hits[0].message

    # 没有上一版可对照时，同样的不一致就是阻断
    _make_case(tmp_path / "other", verify=verify)
    result = pc.run_precheck(tmp_path / "other", RID, stage="result")
    assert len(_by(result, "P4", "block")) == 1


def test_copied_value_from_an_older_snapshot_is_reported_as_stale(tmp_path):
    """对比表里的值不是上一版的、而是更早一轮快照里的旧值：同样按旧值提示，并说明出自第几轮。"""
    verify = _swap(BASE_VERIFY, "| r2_sharpe | 0.76 | 0.52 | 31.58% |", "| r2_sharpe | 0.76 | 0.33 | 31.58% |")
    _make_case(tmp_path, verify=verify, previous=_previous_with("r2_sharpe", 0.333331))
    _dump(tmp_path / "workspace" / RID / "iterations" / "iter_02" / "comparison.json", _previous_with("r2_sharpe", 0.410712))
    hits = _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4")
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "第 1 轮迭代快照里的旧值" in hits[0].message


def test_numbers_quoted_in_current_comparison_text_are_not_stale(tmp_path):
    """当前 comparison 的文字字段里写到的数，文书引用它不算旧数；位数更少的写法不能替位数更多的开脱。"""
    previous = _previous_with("r2_sharpe", 0.410712)  # 上一版 r2_sharpe 的偏差是 45.96%
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- R2 夏普比率的最大相对偏差 45.96%。")

    def scan(note: str) -> list[pc.Finding]:
        qualitative = _base_qualitative()
        qualitative[0]["note"] = note
        _make_case(tmp_path, verify=verify, qualitative=qualitative, previous=previous)
        return pc.scan_stale_numbers(tmp_path, RID)

    assert len(scan("与偏差无关的备注")) == 1
    assert scan("R2 夏普偏差在口径调整之前为 45.96%") == []
    assert len(scan("R2 夏普偏差在口径调整之前约 46.0%")) == 1


def test_stale_numbers_skip_history_marks_change_sentences_and_current_values(tmp_path):
    previous = _previous_with("r2_sharpe", 0.410712)
    head = "- 运行时间 2026-11-20 10:21:07，exit=0。"

    def scan(line: str) -> list[pc.Finding]:
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, head, line), previous=previous)
        return pc.scan_stale_numbers(tmp_path, RID)

    assert len(scan("- R2 夏普比率的最大相对偏差 45.96%。")) == 1
    assert len(scan("- 夏普实测 0.41071。")) == 1  # 五位有效数字，不要求同一行提到这条指标
    assert scan("- 最大相对偏差 45.96%。") == []  # 四位有效数字又没提到是哪条指标：可能只是撞数，不报
    assert scan("- R2 夏普比率的最大相对偏差 45.96%（上一轮）。") == []
    assert scan("- R2 夏普比率修订前偏差 45.96%。") == []
    assert scan("- R2 夏普比率偏差由 45.96% 降到 31.58%。") == []  # 同一行也写了新值：是在写变化过程
    assert scan("- R2 夏普比率 0.52，偏差 31.58%。") == []  # 当前值
    assert scan("- R10 超额 4.51%，R2 运行耗时 45.96s，版本 v0.41071.2。") == []  # 带单位、版本号里的数不算
    assert scan("```\nR2 夏普比率的最大相对偏差 45.96%\n```") == []  # 代码围栏里不查


def test_no_previous_snapshot_means_no_stale_scan(tmp_path):
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- R2 夏普比率的最大相对偏差 45.96%。")
    _make_case(tmp_path, verify=verify)
    assert pc.scan_stale_numbers(tmp_path, RID) == []
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.findings == [] and result.stats["previous"] is None

    # 迭代快照与当前一模一样（刚拍完快照）：也没有旧值可言
    _make_case(tmp_path, verify=verify, previous={"metrics": _base_metrics(), "qualitative": _base_qualitative()})
    assert pc.scan_stale_numbers(tmp_path, RID) == []


def test_latest_different_snapshot_is_used(tmp_path):
    verify = _swap(BASE_VERIFY, "- 运行时间 2026-11-20 10:21:07，exit=0。", "- R2 夏普比率曾为 0.41071，更早为 0.33333。")
    _make_case(tmp_path, verify=verify, previous=_previous_with("r2_sharpe", 0.333331))
    iterations = tmp_path / "workspace" / RID / "iterations"
    _dump(iterations / "iter_02" / "comparison.json", _previous_with("r2_sharpe", 0.410712))
    _dump(iterations / "iter_03" / "comparison.json", {"metrics": _base_metrics(), "qualitative": _base_qualitative()})
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.stats["previous"] == f"workspace/{RID}/iterations/iter_02/comparison.json"
    assert result.stats["older_snapshots"] == [1]
    hits = _by(result, "P4", "warn")
    assert len(hits) == 1
    assert "0.41071（指标 r2_sharpe 上一版的复现值" in hits[0].message
    # 更早一轮的旧数：写法有 5 位有效数字，也报，并说明出自第几轮
    assert "0.33333（指标 r2_sharpe 第 1 轮快照的复现值" in hits[0].message


def test_older_snapshot_values_need_five_significant_digits(tmp_path):
    """隔了几轮的旧数（r008 CDX-R-02 的「最大相对偏差 100.58%」）：只认有效数字够多的写法。"""
    head = "- 运行时间 2026-11-20 10:21:07，exit=0。"
    iterations = tmp_path / "workspace" / RID / "iterations"

    def scan(line: str) -> list[pc.Finding]:
        # 第 1 轮 r2_sharpe 复现 1.524444（偏差 100.58%），第 2 轮 0.410712（偏差 45.96%），当前 0.52（偏差 31.58%）
        _make_case(tmp_path, verify=_swap(BASE_VERIFY, head, line), previous=_previous_with("r2_sharpe", 1.524444))
        _dump(iterations / "iter_02" / "comparison.json", _previous_with("r2_sharpe", 0.410712))
        return _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4")

    hits = scan("- K2 不成立（4 项数值指标 1 项 FAIL，最大相对偏差 100.58%）。")
    assert len(hits) == 1 and hits[0].level == "warn"
    assert "100.58%（指标 r2_sharpe 第 1 轮快照的偏差" in hits[0].message
    assert scan("- R2 夏普比率曾到过 1.52。") == []  # 只有 3 位有效数字：更早轮次的不认
    assert len(scan("- R2 夏普比率此前偏差 45.96%。")) == 1  # 上一版的旧数照常按线索认


def test_generated_block_content_is_not_checked(tmp_path):
    wrong = "\n".join(
        [
            "comparison.json 共 9 项（7 项 metrics + 2 项 qualitative），overall_pass=true（9/9）。",
            "",
            "| 指标 | 研报值 | 复现值 |",
            "| --- | --- | --- |",
            "| r1_annual_return | 10.49% | 99.99% |",
            "| r2_sharpe | 0.76 | 0.41 |",
        ]
    )
    previous = _previous_with("r2_sharpe", 0.410712)
    inside = BASE_VERIFY + "\n" + BEGIN.format(name="comparison_table") + "\n" + wrong + "\n" + END.format(name="comparison_table") + "\n"
    _make_case(tmp_path, verify=inside, previous=previous)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.findings == [], result.render()
    assert pc.scan_stale_numbers(tmp_path, RID) == []

    # 同样的内容放在生成块外面，就都要报
    _make_case(tmp_path, verify=BASE_VERIFY + "\n" + wrong + "\n", previous=previous)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    assert result.blocked is True
    assert len(_by(result, "P4")) == 3  # 计数一行、手抄值两行


def test_generated_block_without_end_marker_is_flagged(tmp_path):
    verify = BASE_VERIFY + "\n" + BEGIN.format(name="artifacts") + "\n| a.png | 1 KB | 2026-11-20 10:00:00 |\n"
    _make_case(tmp_path, verify=verify)
    result = pc.run_precheck(tmp_path, RID, stage="result")
    hits = _by(result, "P4", "warn")
    assert len(hits) == 1 and "END" in hits[0].message and "artifacts" in hits[0].message


def test_missing_documents_are_skipped_and_noted(tmp_path):
    _make_case(tmp_path, verify=None, final=None)
    result = pc.run_precheck(tmp_path, RID, stage="report")
    assert result.findings == []
    assert result.stats["checked_docs"] == []
    assert result.stats["skipped_files"] == [f"output/{RID}/verify_report.md", f"workspace/{RID}/final_report.md"]
    assert "未核对" in result.render() and "\n" not in result.render()


# ---------------------------------------------------------------------------
# comparison.json 用不了
# ---------------------------------------------------------------------------


def test_missing_comparison_gives_single_block(tmp_path):
    _make_case(tmp_path)
    (tmp_path / "output" / RID / "results" / "comparison.json").unlink()
    result = pc.run_precheck(tmp_path, RID, stage="report")
    assert result.blocked is True
    assert len(result.findings) == 1
    assert result.findings[0].level == "block" and "comparison.json" in result.findings[0].message
    assert result.findings[0].where == f"output/{RID}/results/comparison.json"
    assert result.stats["metrics_total"] == 0 and result.stats["checked_files"] == []
    assert pc.comparison_counts(tmp_path, RID) == {"total": 0, "pass": 0, "fail": 0, "na": 0}
    assert "comparison.json" in pc.comparison_table(tmp_path, RID)
    assert pc.scan_stale_numbers(tmp_path, RID) == []


@pytest.mark.parametrize("raw", ["{ 不是 JSON", "[1, 2, 3]", ""])
def test_unparsable_comparison_gives_single_block(tmp_path, raw):
    _make_case(tmp_path)
    (tmp_path / "output" / RID / "results" / "comparison.json").write_text(raw, encoding="utf-8")
    result = pc.run_precheck(tmp_path, RID, stage="report")
    assert [f.level for f in result.findings] == ["block"]


def test_case_without_state_json_still_runs(tmp_path):
    _make_case(tmp_path)
    (tmp_path / "workspace" / RID / "state.json").unlink()
    result = pc.run_precheck(tmp_path, RID, stage="result")  # 类型未知：没有可用容差，按 strict 重算
    assert result.stats["report_type"] is None
    assert isinstance(result.render(), str)


# ---------------------------------------------------------------------------
# 机器生成的表与计数
# ---------------------------------------------------------------------------


def _table_rows(table: str) -> dict[str, list[str]]:
    rows = {}
    for line in table.split("\n")[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows[cells[0]] = cells
    return rows


def test_comparison_table_and_counts_use_recalculated_verdict(tmp_path):
    metrics = _base_metrics()
    metrics[2]["pass"] = True  # r2_sharpe：自述通过，实际偏差 31.6% 超出 5% 容差
    metrics[0]["pass"] = False  # r1_annual_return：自述未通过，实际偏差 0.76% 在容差内
    _make_case(tmp_path, metrics=metrics, top={"overall_pass": True, "pass_count": 5, "total": 5})

    table = pc.comparison_table(tmp_path, RID)
    lines = table.split("\n")
    assert lines[0] == "| 指标编号 | 名称 | 来源要素 | 研报值 | 复现值 | 偏差 | 结论 |"
    assert len(lines) == 2 + 4 + 1  # 表头、分隔行、4 条数值、1 条定性
    rows = _table_rows(table)
    assert rows["r2_sharpe"][1:6] == ["R2 夏普比率", "R2 分年表", "0.76", "0.52", "31.58%"]
    assert rows["r2_sharpe"][6].startswith("未达标") and "自述" in rows["r2_sharpe"][6]
    assert rows["r1_annual_return"][6] == "达标"
    assert rows["r10_excess_return"][6] == "达标"
    assert rows["sa1_direction"][3:7] == ["正收益", "正收益", "定性", "达标"]

    assert pc.comparison_counts(tmp_path, RID) == {"total": 5, "pass": 4, "fail": 1, "na": 0}
    breakdown = pc.comparison_breakdown(tmp_path, RID)
    assert (breakdown["metrics_total"], breakdown["metrics_pass"], breakdown["metrics_fail"]) == (4, 3, 1)
    assert (breakdown["qualitative_total"], breakdown["qualitative_pass"]) == (1, 1)

    # 嵌进文书的对比总表是机器生成块：自己写的表里的数不会再被 P4 核一遍
    verify = pc.upsert_block(BASE_VERIFY, "comparison_table", table)
    _make_case(tmp_path, metrics=metrics, verify=verify)
    assert _by(pc.run_precheck(tmp_path, RID, stage="result"), "P4") == []


def test_comparison_counts_na_and_experimental(tmp_path):
    metrics = _base_metrics() + [
        _metric("R5_x", "R5 覆盖度", "R5", None, None, None, verification_level="unverifiable", attribution_status="assumption_linked", note="数据缺失"),
        _metric("R6_y", "R6 方向", "R6", 0.10, 0.02, False, verification_level="directional", attribution_status="assumption_linked"),
    ]
    _make_case(tmp_path, metrics=metrics, verify=None, final=None)
    assert pc.comparison_counts(tmp_path, RID) == {"total": 7, "pass": 5, "fail": 1, "na": 1}
    rows = _table_rows(pc.comparison_table(tmp_path, RID))
    assert rows["R5_x"][6] == "N/A" and rows["R5_x"][3] == "—" and rows["R5_x"][4] == "—"
    assert rows["R6_y"][6] == "达标"  # 核验分级 directional：只核同号

    # 实验模式：只核产出是否在位
    _make_case(tmp_path, metrics=_base_metrics(), mode="experimental", verify=None, final=None)
    assert pc.comparison_counts(tmp_path, RID) == {"total": 5, "pass": 5, "fail": 0, "na": 0}
    assert _table_rows(pc.comparison_table(tmp_path, RID))["r2_sharpe"][6] == "产出在位"


def test_artifacts_table_lists_results_without_pycache(tmp_path):
    _make_case(tmp_path)
    results = tmp_path / "output" / RID / "results"
    (results / "net_value.png").write_bytes(b"\x89PNG" + b"0" * 2000)
    (results / "cache").mkdir()
    (results / "cache" / "m1.parquet").write_bytes(b"PAR1")
    (results / "__pycache__").mkdir()
    (results / "__pycache__" / "build.cpython-313.pyc").write_bytes(b"x")
    (results / ".DS_Store").write_bytes(b"x")

    table = pc.artifacts_table(tmp_path, RID)
    lines = table.split("\n")
    assert lines[0] == "| 文件名 | 大小 | 修改时间 |"
    names = [line.split("|")[1].strip() for line in lines[2:]]
    assert names[:-1] == ["cache/m1.parquet", "comparison.json", "metrics.json", "net_value.png"]
    assert names[-1] == "合计 4 个文件"
    assert "__pycache__" not in table and ".DS_Store" not in table
    row = next(line for line in lines if "net_value.png" in line)
    assert "2.0 KB" in row

    assert "结果目录不存在" in pc.artifacts_table(tmp_path, "nonexistent_case")


# ---------------------------------------------------------------------------
# 机器生成块
# ---------------------------------------------------------------------------


def test_upsert_block_replaces_existing_block():
    text = "# 标题\n\n前文\n\n" + BEGIN.format(name="counts") + "\n旧内容 1\n旧内容 2\n" + END.format(name="counts") + "\n\n后文\n"
    out = pc.upsert_block(text, "counts", "新内容")
    assert out == "# 标题\n\n前文\n\n" + BEGIN.format(name="counts") + "\n新内容\n" + END.format(name="counts") + "\n\n后文\n"
    assert "旧内容" not in out
    assert pc.extract_block(out, "counts") == "新内容"


def test_upsert_block_replaces_placeholder_line():
    text = "# 标题\n\n<!-- flow:block counts -->\n\n后文\n"
    out = pc.upsert_block(text, "counts", "达标 3 / 4\n")
    assert out == "# 标题\n\n" + BEGIN.format(name="counts") + "\n达标 3 / 4\n" + END.format(name="counts") + "\n\n后文\n"
    assert "flow:block" not in out
    # 别的名字的占位行不动
    assert pc.upsert_block(text, "artifacts", "x").count("<!-- flow:block counts -->") == 1


def test_upsert_block_appends_when_absent():
    text = "# 标题\n\n正文"
    out = pc.upsert_block(text, "artifacts", "| a | b |")
    assert out == "# 标题\n\n正文\n\n" + BEGIN.format(name="artifacts") + "\n| a | b |\n" + END.format(name="artifacts") + "\n"
    assert pc.upsert_block("", "artifacts", "x") == BEGIN.format(name="artifacts") + "\nx\n" + END.format(name="artifacts") + "\n"


def test_upsert_block_is_idempotent_and_blocks_are_independent():
    for text in ("# 标题\n\n正文\n", "# 标题\n\n<!-- flow:block counts -->\n\n后文\n", ""):
        once = pc.upsert_block(text, "counts", "达标 3 / 4")
        assert pc.upsert_block(once, "counts", "达标 3 / 4") == once
        both = pc.upsert_block(once, "artifacts", "| a |")
        assert pc.upsert_block(pc.upsert_block(both, "counts", "达标 3 / 4"), "artifacts", "| a |") == both
        assert pc.extract_block(both, "counts") == "达标 3 / 4"
        assert pc.extract_block(both, "artifacts") == "| a |"
        # 换内容只动自己的块
        changed = pc.upsert_block(both, "counts", "达标 4 / 4")
        assert pc.extract_block(changed, "counts") == "达标 4 / 4"
        assert pc.extract_block(changed, "artifacts") == "| a |"


def test_upsert_block_stays_idempotent_with_code_fences():
    """文书里的围栏没配平、块的正文里又带围栏时，标记照样认得出来，同一个块不会越追加越多。"""
    body = "```\n日志摘录\n```"
    for text in ("# 标题\n\n```python\nprint(1)\n", "# 标题\n\n~~~\n没收尾的围栏\n\n正文\n", "# 标题\n\n```\n配平的围栏\n```\n"):
        once = pc.upsert_block(text, "fragments", body)
        assert pc.upsert_block(once, "fragments", body) == once
        assert once.count("flow:generated fragments BEGIN") == 1
        assert pc.extract_block(once, "fragments") == body
        again = pc.upsert_block(once, "fragments", "换了内容")
        assert again.count("flow:generated fragments BEGIN") == 1 and pc.extract_block(again, "fragments") == "换了内容"


def test_blocks_can_nest_and_are_paired_by_name():
    inner = BEGIN.format(name="inner") + "\n里层\n" + END.format(name="inner")
    text = pc.upsert_block("# 标题\n", "outer", "外层开头\n" + inner + "\n外层结尾")
    assert pc.extract_block(text, "inner") == "里层"
    assert pc.extract_block(text, "outer") == "外层开头\n" + inner + "\n外层结尾"
    assert pc.upsert_block(text, "outer", "外层开头\n" + inner + "\n外层结尾") == text
    # 只换里层，外层的其余内容不动
    changed = pc.upsert_block(text, "inner", "里层新内容")
    assert pc.extract_block(changed, "inner") == "里层新内容"
    assert pc.extract_block(changed, "outer").startswith("外层开头\n") and pc.extract_block(changed, "outer").endswith("\n外层结尾")


def test_extract_block_and_names():
    assert pc.extract_block("没有块的文书", "counts") is None
    text = pc.upsert_block("正文\n", "a.b-c_1", "x\ny")
    assert pc.extract_block(text, "a.b-c_1") == "x\ny"
    assert pc.extract_block(text, "a.b") is None
    with pytest.raises(ValueError):
        pc.upsert_block("正文", "有 空格", "x")
    with pytest.raises(ValueError):
        pc.upsert_block("正文", "counts", "前\n" + END.format(name="counts") + "\n后")


def test_upsert_block_keeps_crlf_line_endings():
    text = "# 标题\r\n\r\n<!-- flow:block counts -->\r\n\r\n后文\r\n"
    out = pc.upsert_block(text, "counts", "一\n二")
    assert "\n" not in out.replace("\r\n", "")
    assert pc.extract_block(out, "counts") == "一\n二"
    assert pc.upsert_block(out, "counts", "一\n二") == out


# ---------------------------------------------------------------------------
# 只读：造的案例与三个真实案例
# ---------------------------------------------------------------------------

_KERNEL_OWNED = {"state.json", ".state.lock", "events.jsonl", "board.html"}  # 内核和看板随时会刷新的文件，不算预检写的


def _mtimes(*dirs: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            parts = path.relative_to(base).parts
            if "__pycache__" in parts or parts[0] == "flow" or path.name in _KERNEL_OWNED:
                continue
            try:
                if path.is_file():
                    out[str(path)] = path.stat().st_mtime_ns
            except OSError:
                continue
    return out


def test_precheck_does_not_write_into_fixture(tmp_path):
    verify = _swap(BASE_VERIFY, "| r1_annual_return | 10.49% | 10.41% |", "| r1_annual_return | 10.49% | 10.93% |")
    _make_case(tmp_path, verify=verify, previous=_previous_with("r2_sharpe", 0.410712))
    before = _mtimes(tmp_path)
    names_before = sorted(str(p) for p in tmp_path.rglob("*"))
    pc.run_precheck(tmp_path, RID, stage="report")
    pc.scan_stale_numbers(tmp_path, RID)
    pc.comparison_table(tmp_path, RID)
    pc.comparison_counts(tmp_path, RID)
    pc.artifacts_table(tmp_path, RID)
    assert sorted(str(p) for p in tmp_path.rglob("*")) == names_before
    assert _mtimes(tmp_path) == before


REAL_CASES = ["r008_inflection_trend_size_rotation", "r009_industry_rotation", "r010_breakout_ratio_timing"]


@pytest.mark.parametrize("report_id", REAL_CASES)
def test_real_case_runs_without_error_and_writes_nothing(report_id):
    if not (REPO_ROOT / "output" / report_id / "results" / "comparison.json").is_file():
        pytest.skip(f"真实案例 {report_id} 不在本机")
    dirs = (REPO_ROOT / "output" / report_id, REPO_ROOT / "workspace" / report_id)
    before = _mtimes(*dirs)

    result = pc.run_precheck(REPO_ROOT, report_id, stage="report")
    assert isinstance(result.render(), str) and result.render()
    json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.stats["metrics_total"] > 0
    assert {f.check for f in result.findings} <= {"P1", "P2", "P3", "P4"}
    assert {f.level for f in result.findings} <= {"block", "warn"}
    assert pc.comparison_counts(REPO_ROOT, report_id)["total"] == result.stats["total"]
    assert pc.comparison_table(REPO_ROOT, report_id).count("\n") == result.stats["total"] + 1
    assert pc.artifacts_table(REPO_ROOT, report_id)
    pc.scan_stale_numbers(REPO_ROOT, report_id)

    assert _mtimes(*dirs) == before
