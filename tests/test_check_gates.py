"""tools/check_gates.py 的测试：门禁判定逻辑与 standards.json 容差重算。

fixture 策略：在 tmp_path 下伪造最小 workspace（spec.md / coverage_matrix.md /
comparison.json / templates/standards.json 等），不依赖任何真实案例数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import check_gates as cg  # noqa: E402
from tools import state as st  # noqa: E402


def _init_workspace(tmp_path: Path, report_id: str = "demo", *, type_: str = "factor", difficulty: str = "medium", tags: list | None = None) -> None:
    st.init_state(tmp_path, report_id, "reports/demo.pdf")
    if type_ is not None:
        st.set_field(tmp_path, report_id, "type", type_)
    if difficulty is not None:
        st.set_field(tmp_path, report_id, "difficulty", difficulty)
    if tags:
        st.set_field(tmp_path, report_id, "tags", json.dumps(tags))


SPEC_FRONTMATTER = """---
report_name: 测试研报
title: 测试研报标题
institution: 测试机构
report_date: 2023-08-22
authors: 张三
market: A股
pdf_pages: 22
exhibit_declared: {fig_max: 2, tbl_max: 1}
element_counts: {D: 1, F: 1, B: 1, R: 1, SA: 0, FIG_registered: 2, TBL_registered: 1}
type_hint: factor
tags_hint: []
---
"""

SPEC_BODY_CONSISTENT = """
## 二、数据要求（D 类）
### [D1] 测试数据要求
- 页码: p1
- 原文: > "测试原文 D1"

## 三、因子/策略定义（F 类）
### [F1] 测试因子
- 页码: p2
- 原文: > "测试原文 F1"

## 四、回测设置（B 类）
### [B1] 测试回测设置
- 页码: p3
- 原文: > "测试原文 B1"

## 五、研报核心数值结果基准（R 类）
### [R1] 测试结果表
- 页码: p4
- 原文: > "测试原文 R1"

## 六、图表登记清单
| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| FIG1 | 测试图1 | p1 | 测试摘要1 | reproduce |  |
| FIG2 | 测试图2 | p2 | 测试摘要2 | reproduce |  |
| TBL1 | 测试表1 | p3 | 测试摘要3 | reproduce |  |
"""

MATRIX_CONSISTENT = """| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 测试数据 | p1 | core | M1 | pending |  |  |  | extract |
| F1 | F | 测试因子 | p2 | core | M1 | pending |  |  |  | extract |
| B1 | B | 测试回测 | p3 | core | M1 | pending |  |  |  | extract |
| R1 | R | 测试结果 | p4 | core | M1 | pending |  |  |  | extract |
"""


def _write_spec_files(tmp_path: Path, report_id: str, body: str, matrix: str) -> None:
    spec_dir = tmp_path / "workspace" / report_id / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(SPEC_FRONTMATTER + body, encoding="utf-8")
    (spec_dir / "coverage_matrix.md").write_text(matrix, encoding="utf-8")
    (spec_dir / "ambiguities.md").write_text("# 歧义清单\n\n（无）\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------


def test_parse_frontmatter_basic() -> None:
    fm, body = cg.parse_frontmatter(SPEC_FRONTMATTER + SPEC_BODY_CONSISTENT)
    assert fm is not None
    assert fm["report_name"] == "测试研报"
    assert fm["element_counts"]["D"] == 1
    assert "## 二、数据要求" in body


def test_parse_frontmatter_missing_returns_none() -> None:
    fm, body = cg.parse_frontmatter("没有 frontmatter 的普通文本")
    assert fm is None


def test_parse_id_blocks_extracts_fields() -> None:
    blocks = cg.parse_id_blocks(SPEC_BODY_CONSISTENT)
    d1 = next(b for b in blocks if b.id == "D1")
    assert d1.fields["页码"] == "p1"
    assert "测试原文 D1" in d1.fields["原文"]


def test_parse_markdown_table_rows() -> None:
    rows = cg.parse_markdown_table_rows(MATRIX_CONSISTENT)
    assert len(rows) == 4
    assert rows[0]["要素ID"] == "D1"
    assert rows[0]["状态"] == "pending"


# ---------------------------------------------------------------------------
# G-EX：计数一致 / 不一致
# ---------------------------------------------------------------------------


def test_check_extract_pass_when_counts_consistent(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    _write_spec_files(tmp_path, "demo", SPEC_BODY_CONSISTENT, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}

    assert by_id["G-EX-4"].passed is True, by_id["G-EX-4"].detail
    assert all(r.passed for r in results), [cg.format_check(r) for r in results if not r.passed]


def test_check_extract_fails_when_matrix_row_missing(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    # 矩阵少一行（只剩 3 行），制造"三方不一致"
    matrix_mismatch = "\n".join(MATRIX_CONSISTENT.splitlines()[:-1]) + "\n"
    _write_spec_files(tmp_path, "demo", SPEC_BODY_CONSISTENT, matrix_mismatch)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}

    assert by_id["G-EX-4"].passed is False
    assert "正则=4" in by_id["G-EX-4"].detail
    assert "矩阵=3" in by_id["G-EX-4"].detail


def test_check_extract_fails_when_frontmatter_count_mismatch(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    bad_frontmatter = SPEC_FRONTMATTER.replace("element_counts: {D: 1, F: 1, B: 1, R: 1, SA: 0", "element_counts: {D: 2, F: 1, B: 1, R: 1, SA: 0")
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(bad_frontmatter + SPEC_BODY_CONSISTENT, encoding="utf-8")
    (spec_dir / "coverage_matrix.md").write_text(MATRIX_CONSISTENT, encoding="utf-8")
    (spec_dir / "ambiguities.md").write_text("（无）", encoding="utf-8")

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-4"].passed is False
    assert "frontmatter=5" in by_id["G-EX-4"].detail


def test_check_extract_detects_missing_evidence_lines(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    body_missing_evidence = SPEC_BODY_CONSISTENT.replace('- 原文: > "测试原文 R1"\n', "")
    _write_spec_files(tmp_path, "demo", body_missing_evidence, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-5"].passed is False
    assert "R1" in by_id["G-EX-5"].detail


def test_check_extract_fails_when_spec_missing(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    results = cg.check_extract(tmp_path, "demo")
    assert results[0].id == "G-EX-1"
    assert results[0].passed is False


# ---------------------------------------------------------------------------
# G-EX-8：图表登记清单改按「图表登记」H2 节内的 markdown 表格解析（非 ### [ID] 块）
# ---------------------------------------------------------------------------


def test_check_extract_g_ex_8_passes_when_exhibit_registry_consistent(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    _write_spec_files(tmp_path, "demo", SPEC_BODY_CONSISTENT, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-8"].passed is True, by_id["G-EX-8"].detail


def test_check_extract_g_ex_8_fails_when_row_count_missing(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    # 少一行 FIG2，登记清单表格只剩 2 行（FIG 桶从 2 掉到 1），制造行数缺失
    body = SPEC_BODY_CONSISTENT.replace("| FIG2 | 测试图2 | p2 | 测试摘要2 | reproduce |  |\n", "")
    _write_spec_files(tmp_path, "demo", body, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-8"].passed is False
    assert "FIG+EX行数=1" in by_id["G-EX-8"].detail
    assert "FIG_registered=2" in by_id["G-EX-8"].detail


def test_check_extract_g_ex_8_fails_when_number_exceeds_declared_max(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    # 行数仍是 2（FIG1 + FIG5），计数断言仍过，但编号 5 超出 exhibit_declared.fig_max=2
    body = SPEC_BODY_CONSISTENT.replace(
        "| FIG2 | 测试图2 | p2 | 测试摘要2 | reproduce |  |", "| FIG5 | 测试图5 | p2 | 测试摘要2 | reproduce |  |"
    )
    _write_spec_files(tmp_path, "demo", body, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-8"].passed is False
    assert "FIG/EX最大编号=5>exhibit_declared.fig_max=2" in by_id["G-EX-8"].detail


def test_check_extract_g_ex_8_ex_prefix_counts_into_fig_bucket(tmp_path: Path) -> None:
    """研报用「图表N」统一编号时，EX 前缀替代 TBL/FIG，计入 FIG 桶（FIG_registered/fig_max）。"""
    _init_workspace(tmp_path)
    body = SPEC_BODY_CONSISTENT.replace(
        "| FIG2 | 测试图2 | p2 | 测试摘要2 | reproduce |  |", "| EX2 | 统一编号图表2 | p2 | 测试摘要2 | reproduce |  |"
    )
    _write_spec_files(tmp_path, "demo", body, MATRIX_CONSISTENT)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-8"].passed is True, by_id["G-EX-8"].detail


# ---------------------------------------------------------------------------
# recalc_metric：容差语义（同号违规 / 超容差 / abs_eps 近零 / default 兜底 / 数量级）
# ---------------------------------------------------------------------------


def test_recalc_metric_sign_violation_fails_regardless_of_magnitude() -> None:
    spec = {"max_rel_dev": 0.50, "require_same_sign": True}
    metric = {"key": "ls_annual_return", "report_value": 0.08, "reproduced_value": -0.01}
    r = cg.recalc_metric(metric, spec)
    assert r.passed is False
    assert "同号" in r.reason


def test_recalc_metric_exceeds_tolerance_fails() -> None:
    spec = {"max_rel_dev": 0.15}
    metric = {"key": "sharpe", "report_value": 1.0, "reproduced_value": 1.20}
    r = cg.recalc_metric(metric, spec)
    assert r.rel_dev == pytest.approx(0.20)
    assert r.passed is False


def test_recalc_metric_within_tolerance_passes() -> None:
    spec = {"max_rel_dev": 0.15}
    metric = {"key": "sharpe", "report_value": 1.0, "reproduced_value": 1.10}
    r = cg.recalc_metric(metric, spec)
    assert r.passed is True


def test_recalc_metric_abs_eps_near_zero_pass_and_fail() -> None:
    spec = {"max_rel_dev": 0.20, "abs_eps": 0.005}
    passing = cg.recalc_metric({"key": "rank_ic_mean", "report_value": 0.003, "reproduced_value": 0.004}, spec)
    assert passing.passed is True
    assert "近零" in passing.reason

    failing = cg.recalc_metric({"key": "rank_ic_mean", "report_value": 0.003, "reproduced_value": 0.02}, spec)
    assert failing.passed is False


def test_recalc_metric_near_zero_takes_priority_over_same_sign_veto() -> None:
    """require_same_sign 与 abs_eps 同时出现时，近零判定优先：符号在近零区间是噪声，
    不应因反号被同号否决一票判负；改用绝对偏差判定。"""
    spec = {"max_rel_dev": 0.20, "require_same_sign": True, "abs_eps": 0.005}

    near_zero_opposite_sign = cg.recalc_metric({"key": "rank_ic_mean", "report_value": 0.003, "reproduced_value": -0.002}, spec)
    assert near_zero_opposite_sign.passed is True
    assert "同号要求违反" not in near_zero_opposite_sign.reason  # 不应因符号被一票否决
    assert "近零" in near_zero_opposite_sign.reason


def test_recalc_metric_same_sign_veto_still_applies_when_not_near_zero() -> None:
    """|report_value| >= abs_eps（非近零）时，同号否决逻辑照常生效。"""
    spec = {"max_rel_dev": 0.20, "require_same_sign": True, "abs_eps": 0.005}

    not_near_zero_opposite_sign = cg.recalc_metric({"key": "ls_annual_return", "report_value": 0.08, "reproduced_value": -0.07}, spec)
    assert not_near_zero_opposite_sign.passed is False
    assert "同号" in not_near_zero_opposite_sign.reason


def test_recalc_metric_default_fallback() -> None:
    standards = {"factor": {"metrics": {"default": {"max_rel_dev": 0.15}}}}
    spec = cg._tolerance_spec_for_metric(standards, "factor", {"key": "unlisted_metric"})
    assert spec == {"max_rel_dev": 0.15}

    ok = cg.recalc_metric({"key": "unlisted_metric", "report_value": 1.0, "reproduced_value": 1.10}, spec)
    assert ok.passed is True
    bad = cg.recalc_metric({"key": "unlisted_metric", "report_value": 1.0, "reproduced_value": 1.30}, spec)
    assert bad.passed is False


def test_recalc_metric_order_of_magnitude_only() -> None:
    spec = {"order_of_magnitude_only": True}
    same_order = cg.recalc_metric({"key": "turnover", "report_value": 5.0, "reproduced_value": 8.0}, spec)
    assert same_order.passed is True
    diff_order = cg.recalc_metric({"key": "turnover", "report_value": 5.0, "reproduced_value": 60.0}, spec)
    assert diff_order.passed is False


def test_recalc_metric_ml_layer_direction_only() -> None:
    standards = {"ml": {"layers": {"model": {"direction_only": True}, "data_feature": {"max_rel_dev": 0.05}}}}
    spec = cg._tolerance_spec_for_metric(standards, "ml", {"key": "ic_same_sign", "layer": "model"})
    r = cg.recalc_metric({"key": "ic_same_sign", "report_value": 1, "reproduced_value": 1}, spec)
    assert r.passed is True
    r_bad = cg.recalc_metric({"key": "ic_same_sign", "report_value": 1, "reproduced_value": -1}, spec)
    assert r_bad.passed is False


# ---------------------------------------------------------------------------
# G-VF：整体重算（不信任 comparison.json 里自称的 pass）
# ---------------------------------------------------------------------------


STANDARDS_FIXTURE = {
    "factor": {
        "metrics": {
            "rank_ic_mean": {"max_rel_dev": 0.20, "require_same_sign": True, "abs_eps": 0.005},
            "turnover": {"order_of_magnitude_only": True},
            "default": {"max_rel_dev": 0.15},
        },
        "required_charts": [],
        "required_excels": [],
    }
}


def _write_standards(tmp_path: Path, data: dict) -> None:
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "standards.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_verify_artifacts(tmp_path: Path, report_id: str, metrics: list[dict], *, exit_ok: bool = True) -> None:
    results_dir = tmp_path / "output" / report_id / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "run_log.md").write_text(f"命令: python -m src.{report_id}.main\nexit={'0' if exit_ok else '1'}\n", encoding="utf-8")
    comparison = {"metrics": metrics, "qualitative": [], "overall_pass": True, "pass_count": len(metrics), "total": len(metrics)}
    (results_dir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    src_dir = tmp_path / "src" / report_id
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.py").write_text("print('demo')\n", encoding="utf-8")
    # 保证 results/ 的 mtime 晚于 src/（E2 新鲜度）
    import os
    import time

    time.sleep(0.01)
    now = time.time() + 5
    os.utime(results_dir / "comparison.json", (now, now))
    os.utime(results_dir / "run_log.md", (now, now))


def test_check_verify_passes_when_all_metrics_within_tolerance(tmp_path: Path) -> None:
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    metrics = [
        {"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": True},
        {"key": "turnover", "report_value": 5.0, "reproduced_value": 6.0, "pass": True},
    ]
    _write_verify_artifacts(tmp_path, "demo", metrics)

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-1"].passed is True
    assert by_id["G-VF-3"].passed is True, by_id["G-VF-3"].detail


def test_check_verify_does_not_trust_file_pass_field(tmp_path: Path) -> None:
    """comparison.json 里的 metric 谎称 pass=true，但实际相对偏差超容差；重算必须判 FAIL。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    metrics = [
        {"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": -0.06, "pass": True},  # 文件谎称通过，实际同号违规
    ]
    _write_verify_artifacts(tmp_path, "demo", metrics)

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-3"].passed is False
    assert "rank_ic_mean" in by_id["G-VF-3"].detail


def test_check_verify_fails_without_run_log_exit0(tmp_path: Path) -> None:
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    _write_verify_artifacts(tmp_path, "demo", [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.05, "pass": True}], exit_ok=False)

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-1"].passed is False


# ---------------------------------------------------------------------------
# G-RA：result_audit 回应行数一致性（与 G-SA-4/G-CA-4 相同的三审查点回应协议）
# ---------------------------------------------------------------------------

RESULT_AUDIT_CODEX_TWO_ISSUES = """# result audit（codex）

| ID | 描述 | severity |
| --- | --- | --- |
| CDX-R-1 | 数字与原始产物不符 | critical |
| CDX-R-2 | 归因造假疑点 | major |
"""


def _write_result_audit(tmp_path: Path, report_id: str, response_rows: str) -> None:
    audit_dir = tmp_path / "workspace" / report_id / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "result_audit_codex.md").write_text(RESULT_AUDIT_CODEX_TWO_ISSUES, encoding="utf-8")
    (audit_dir / "audit_responses.md").write_text(
        "| 编号 | severity | 处置 | 复核 |\n| --- | --- | --- | --- |\n" + response_rows, encoding="utf-8"
    )


def test_check_result_audit_response_count_matches_issues_passes(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    _write_result_audit(
        tmp_path,
        "demo",
        "| CDX-R-1 | critical | accepted | pass |\n| CDX-R-2 | major | accepted | pass |\n",
    )

    results = cg.check_result_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-RA-5"].passed is True, by_id["G-RA-5"].detail
    assert "回应=2" in by_id["G-RA-5"].detail
    assert "issues=2" in by_id["G-RA-5"].detail


def test_check_result_audit_response_count_mismatch_fails(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    # codex 提了 2 条意见（CDX-R-1/CDX-R-2），回应表漏了 CDX-R-2
    _write_result_audit(tmp_path, "demo", "| CDX-R-1 | critical | accepted | pass |\n")

    results = cg.check_result_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-RA-5"].passed is False
    assert "回应=1" in by_id["G-RA-5"].detail
    assert "issues=2" in by_id["G-RA-5"].detail


# ---------------------------------------------------------------------------
# 必跑 stage 被标 skipped -> --assert-done 判 FAIL；iterate 允许 skipped
# ---------------------------------------------------------------------------


def test_assert_done_required_stage_marked_skipped_fails(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    st.set_stage(tmp_path, "demo", "extract", "skipped")
    check = cg.check_assert_done(tmp_path, "demo", "extract")
    assert check.passed is False
    assert "必跑" in check.detail


def test_assert_done_iterate_skipped_is_allowed(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    st.set_stage(tmp_path, "demo", "iterate", "skipped")
    check = cg.check_assert_done(tmp_path, "demo", "iterate")
    assert check.passed is True


def test_assert_done_done_stage_passes(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    st.set_stage(tmp_path, "demo", "extract", "running")
    st.set_stage(tmp_path, "demo", "extract", "done")
    check = cg.check_assert_done(tmp_path, "demo", "extract")
    assert check.passed is True


def test_assert_done_pending_stage_fails(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    check = cg.check_assert_done(tmp_path, "demo", "plan")
    assert check.passed is False


# ---------------------------------------------------------------------------
# 其它 stage 的基础覆盖（G-IN / G-PL / G-IM / G-FN）
# ---------------------------------------------------------------------------


def test_check_init_fails_without_report_text(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    results = cg.check_init(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IN-1"].passed is True
    assert by_id["G-IN-2"].passed is True  # init_state 已建目录骨架
    assert by_id["G-IN-3"].passed is False  # report_text.md 未生成


def test_check_init_passes_with_matching_page_marks(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "pdf_pages", "2")
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    (spec_dir / "report_text.md").write_text("===== PAGE 1 =====\n内容1\n\n===== PAGE 2 =====\n内容2\n", encoding="utf-8")
    (spec_dir / "tables_extracted.md").write_text("# 无表格\n", encoding="utf-8")

    results = cg.check_init(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IN-4"].passed is True
    assert by_id["G-IN-5"].passed is True
    assert by_id["G-IN-6"].passed is True


def test_check_plan_rejects_invalid_enum_and_cycle(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    plan_text = """---
type: not_a_real_type
difficulty: medium
feasibility: feasible
milestones:
  - id: M1
    name: 因子实现
    deps: [M2]
  - id: M2
    name: 回测
    deps: [M1]
---
正文
"""
    (tmp_path / "workspace" / "demo" / "plan.md").write_text(plan_text, encoding="utf-8")
    results = cg.check_plan(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-PL-3"].passed is False  # type 非法
    assert by_id["G-PL-5"].passed is False  # M1<->M2 互相依赖成环


def test_check_implement_compileall_detects_syntax_error(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True, exist_ok=True)
    (src / "strategy.py").write_text("def f(:\n    pass\n", encoding="utf-8")  # 语法错误
    (src / "main.py").write_text("print('ok')\n", encoding="utf-8")

    results = cg.check_implement(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IM-1"].passed is True
    assert by_id["G-IM-2"].passed is True
    assert by_id["G-IM-3"].passed is False


def test_check_report_detects_missing_sections(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    (tmp_path / "workspace" / "demo" / "final_report.md").write_text("## 结论\n通过\n", encoding="utf-8")
    results = cg.check_report(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-FN-2"].passed is False
    assert "指标对比" in by_id["G-FN-2"].detail


def test_check_report_requires_coverage_stats_total_positive(tmp_path: Path) -> None:
    """coverage_stats 是可信度评级依赖的字段：state.json 里必须写入且 total > 0。"""
    _init_workspace(tmp_path)
    (tmp_path / "workspace" / "demo" / "final_report.md").write_text("## 结论\n通过\n", encoding="utf-8")

    # init_state 的默认 coverage_stats.total 是 0（尚未写入真实统计），应判 FAIL
    results = cg.check_report(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-FN-6"].passed is False

    st.set_field(tmp_path, "demo", "coverage_stats.total", "12")
    results = cg.check_report(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-FN-6"].passed is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_exit_code_matches_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    st.init_state(tmp_path, "demo", "reports/demo.pdf")

    rc = cg.main(["demo", "--stage", "extract"])
    assert rc == 1  # spec.md 不存在，必然 FAIL
    captured = capsys.readouterr()
    assert "VERDICT: FAIL" in captured.out
    assert "[FAIL] G-EX-1" in captured.out


def test_cli_record_writes_gate_to_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    st.init_state(tmp_path, "demo", "reports/demo.pdf")

    cg.main(["demo", "--stage", "extract", "--record"])
    state = st.load_state(tmp_path, "demo")
    assert state["gates"][-1]["stage"] == "extract"
    assert state["gates"][-1]["verdict"] == "FAIL"


def test_cli_assert_done_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "init", "done")

    rc = cg.main(["demo", "--stage", "init", "--assert-done"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "VERDICT: PASS" in captured.out
