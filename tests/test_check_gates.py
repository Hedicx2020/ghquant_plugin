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
# M2：_parse_codex_output 降级路径只统计首格匹配 ^CDX- 的表格行（与
# _parse_audit_responses 按 CDX- ID 识别行的语义对称），不把文中其它表格
# （如「已检查维度」汇总表）的行也计入 issues 数。
# ---------------------------------------------------------------------------


def test_parse_codex_output_fallback_only_counts_cdx_prefixed_rows(tmp_path: Path) -> None:
    codex_path = tmp_path / "spec_audit_codex.md"
    codex_path.write_text(
        """# spec audit（降级为 markdown，非 JSON）

## 已检查维度
| 维度 | 结果 |
| --- | --- |
| 盲提取diff | no_findings |
| 遗漏检查 | no_findings |

## 意见
| ID | severity | category | location | description | suggestion |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | 遗漏 | p9 | 缺少敏感性分析 | 补充 SA 要素 |

VERDICT: pass_with_issues
""",
        encoding="utf-8",
    )
    issues_count, verdict = cg._parse_codex_output(codex_path)
    # 旧实现会把「已检查维度」表的 2 行也计入，得到 3；新实现只认首格 ^CDX- 的行，应为 1。
    assert issues_count == 1
    assert verdict == "pass_with_issues"


def test_parse_codex_output_fallback_returns_zero_when_no_cdx_rows(tmp_path: Path) -> None:
    codex_path = tmp_path / "code_audit_codex.md"
    codex_path.write_text(
        "# code audit\n\n## 已检查维度\n| 维度 | 结果 |\n| --- | --- |\n| 公式一致 | no_findings |\n\nVERDICT: pass\n",
        encoding="utf-8",
    )
    issues_count, verdict = cg._parse_codex_output(codex_path)
    assert issues_count == 0
    assert verdict == "pass"


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
# I2：G-VF-7 豁免不一致——skipped/infeasible 的 core/support 行不要求「验证结果」
# 列非空，与 G-IM-5 对「实现位置」列的豁免口径统一。
# ---------------------------------------------------------------------------


def test_check_verify_g_vf_7_skipped_core_row_exempt_from_verify_result(tmp_path: Path) -> None:
    """skipped 的 core 行天然不会有验证结果（要素本就没做），不应因此永久卡在 G-VF-7。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    metrics = [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": True}]
    _write_verify_artifacts(tmp_path, "demo", metrics)

    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    matrix_skipped = """| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 测试数据 | p1 | core | M1 | skipped | data_missing: 数据源不可得 |  |  | plan |
"""
    (spec_dir / "coverage_matrix.md").write_text(matrix_skipped, encoding="utf-8")

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-7"].passed is True, by_id["G-VF-7"].detail


def test_check_verify_g_vf_7_non_skipped_core_row_still_requires_verify_result(tmp_path: Path) -> None:
    """非 skipped/infeasible 的 core 行仍必须有验证结果——确认豁免没有被放宽到全部行。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    metrics = [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": True}]
    _write_verify_artifacts(tmp_path, "demo", metrics)

    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    matrix_pending = """| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 测试数据 | p1 | core | M1 | done |  | src/demo/strategy.py:load |  | implement |
"""
    (spec_dir / "coverage_matrix.md").write_text(matrix_pending, encoding="utf-8")

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-7"].passed is False
    assert "D1" in by_id["G-VF-7"].detail


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
# I3：G-RA-3 不再信任 comparison.json 自述的 pass 字段，改用与 G-VF-3 相同的
# recalc_metric（按 standards.json 重算，按 type 取容差）圈定"超差"指标集合。
# ---------------------------------------------------------------------------


def _write_comparison(tmp_path: Path, report_id: str, metrics: list[dict]) -> None:
    results_dir = tmp_path / "output" / report_id / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "comparison.json").write_text(
        json.dumps({"metrics": metrics, "qualitative": []}, ensure_ascii=False), encoding="utf-8"
    )


def test_check_result_audit_g_ra_3_does_not_trust_self_reported_pass(tmp_path: Path) -> None:
    """comparison.json 谎称 pass=true，但按 standards.json 重算其实同号违规超差，且无
    attribution_status——G-RA-3 必须依重算结果判 FAIL，不能被自述的 pass=true 蒙混过关。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    _write_comparison(tmp_path, "demo", [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": -0.06, "pass": True}])
    _write_result_audit(tmp_path, "demo", "| CDX-R-1 | critical | accepted | pass |\n| CDX-R-2 | major | accepted | pass |\n")

    results = cg.check_result_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-RA-3"].passed is False
    assert "rank_ic_mean" in by_id["G-RA-3"].detail


def test_check_result_audit_g_ra_3_passes_when_attribution_status_present(tmp_path: Path) -> None:
    """重算确实超差，但已写 attribution_status（收尾模式/stop_partial 已归因）——应 PASS。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    _write_comparison(
        tmp_path,
        "demo",
        [
            {
                "key": "rank_ic_mean",
                "report_value": 0.05,
                "reproduced_value": -0.06,
                "pass": False,
                "attribution_status": "assumption_linked",
            }
        ],
    )
    _write_result_audit(tmp_path, "demo", "| CDX-R-1 | critical | accepted | pass |\n| CDX-R-2 | major | accepted | pass |\n")

    results = cg.check_result_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-RA-3"].passed is True, by_id["G-RA-3"].detail


def test_check_result_audit_g_ra_3_passes_when_metric_genuinely_within_tolerance(tmp_path: Path) -> None:
    """重算确实在容差内，无需归因，attribution_status 缺失也不应 FAIL。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    _write_comparison(tmp_path, "demo", [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": True}])
    _write_result_audit(tmp_path, "demo", "| CDX-R-1 | critical | accepted | pass |\n| CDX-R-2 | major | accepted | pass |\n")

    results = cg.check_result_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-RA-3"].passed is True, by_id["G-RA-3"].detail


# ---------------------------------------------------------------------------
# I1 / G-CA-3：impl_audit 空壳判定改行锚定结构化匹配 `判定: not_found`，不再对
# 全文做 `not[_ ]found` 子串 grep（否定句式如「无 not_found 判定」不应误触发）。
# ---------------------------------------------------------------------------


def _write_impl_audit(tmp_path: Path, report_id: str, filename: str, content: str) -> None:
    audit_dir = tmp_path / "workspace" / report_id / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / filename).write_text(content, encoding="utf-8")


def test_check_code_audit_g_ca_3_detects_structured_not_found_verdict(tmp_path: Path) -> None:
    _init_workspace(tmp_path)
    _write_impl_audit(
        tmp_path,
        "demo",
        "impl_audit_m1.md",
        "## F1 核对\n实现位置指向的函数体只有 pass，未见真实计算逻辑。\n判定: not_found\n",
    )

    results = cg.check_code_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-CA-3"].passed is False
    assert "impl_audit_m1.md" in by_id["G-CA-3"].detail


def test_check_code_audit_g_ca_3_negated_mention_does_not_trigger(tmp_path: Path) -> None:
    """否定句式「无 not_found 判定」只是全文子串命中，不满足行锚定「判定: not_found」
    结构，不应被误判为空壳（旧的全文 grep 会误报）。"""
    _init_workspace(tmp_path)
    _write_impl_audit(
        tmp_path,
        "demo",
        "impl_audit_m1.md",
        "## F1 核对\n实现完整，逐条核对通过，无 not_found 判定。\n判定: pass\n",
    )

    results = cg.check_code_audit(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-CA-3"].passed is True, by_id["G-CA-3"].detail


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
# C1：coverage_matrix.md 的「变更日志」等非要素表格不得污染五处门禁
# （G-EX-4 / G-PL-6 / G-IM-5 / G-VF-7 / G-FN-3）对要素行的计数与遍历。
# fixture 对模板忠实：附加 templates/audit/coverage_matrix.md 文末原样的
# 「变更日志」表格（2 条示例数据行，表头「时间/事件/来源/说明」与主表不同）。
# ---------------------------------------------------------------------------

CHANGELOG_SECTION = """
## 变更日志（只追加，禁止修改/删除历史行）

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| 2024-01-01 extract | 初始化 4 行 | quant-extractor | 首次提取建矩阵 |
| 2024-01-02 spec_audit | 追加 1 行 F13 | 依据 CDX-S-02 追加 | codex 盲提取发现遗漏因子 |
"""

# 4 条要素行终态齐全（milestone / 实现位置 / 验证结果均已填、状态 done），
# 用于验证 G-PL-6 / G-IM-5 / G-VF-7 / G-FN-3 在"本该 PASS"的前提下不被变更日志污染。
MATRIX_DONE = """| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 测试数据 | p1 | core | M1 | done |  | src/demo/strategy.py:load_d1 | verify_report.md#d1 偏差0% pass | verify |
| F1 | F | 测试因子 | p2 | core | M1 | done |  | src/demo/strategy.py:calc_f1 | verify_report.md#f1 偏差0% pass | verify |
| B1 | B | 测试回测 | p3 | core | M1 | done |  | src/demo/strategy.py:backtest | verify_report.md#b1 偏差0% pass | verify |
| R1 | R | 测试结果 | p4 | core | M1 | done |  | src/demo/strategy.py:report_r1 | verify_report.md#r1 偏差0% pass | verify |
"""


def test_load_matrix_rows_filters_changelog_table_rows(tmp_path: Path) -> None:
    """正：4 要素 + 2 变更日志行 -> load_matrix_rows 只返回 4 条真正的要素行。"""
    matrix_path = tmp_path / "coverage_matrix.md"
    matrix_path.write_text(MATRIX_CONSISTENT + CHANGELOG_SECTION, encoding="utf-8")

    rows = cg.load_matrix_rows(matrix_path)
    assert len(rows) == 4
    assert [r["要素ID"] for r in rows] == ["D1", "F1", "B1", "R1"]


def test_load_matrix_rows_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    assert cg.load_matrix_rows(tmp_path / "不存在.md") == []


def test_check_extract_g_ex_4_ignores_changelog_rows(tmp_path: Path) -> None:
    """正：4 要素 + 2 变更日志行 -> 矩阵计数仍是 4，三方一致 PASS。"""
    _init_workspace(tmp_path)
    _write_spec_files(tmp_path, "demo", SPEC_BODY_CONSISTENT, MATRIX_CONSISTENT + CHANGELOG_SECTION)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-4"].passed is True, by_id["G-EX-4"].detail
    assert "矩阵=4" in by_id["G-EX-4"].detail


def test_check_extract_g_ex_4_still_detects_real_mismatch_with_changelog_present(tmp_path: Path) -> None:
    """反：变更日志表格存在的同时矩阵真的少一行（3 要素）——不能被日志行掩盖或误加，
    仍须如实报告矩阵=3（既不是被误算成 5，也不是被日志行"顶"成看似一致的 4）。"""
    _init_workspace(tmp_path)
    matrix_missing_one = "\n".join(MATRIX_CONSISTENT.splitlines()[:-1]) + "\n"
    _write_spec_files(tmp_path, "demo", SPEC_BODY_CONSISTENT, matrix_missing_one + CHANGELOG_SECTION)

    results = cg.check_extract(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-EX-4"].passed is False
    assert "矩阵=3" in by_id["G-EX-4"].detail


def test_check_plan_g_pl_6_ignores_changelog_rows(tmp_path: Path) -> None:
    """旧实现：变更日志行缺「状态」「milestone」列，_row_get 落空字符串，被误判为
    "状态非 skipped/infeasible 且 milestone 为空" 混入 missing_milestone_rows，
    尽管矩阵真正的 4 条要素行 milestone 全部已填。"""
    _init_workspace(tmp_path)
    plan_text = """---
type: factor
difficulty: medium
feasibility: feasible
milestones:
  - id: M1
    name: 因子实现
    deps: []
---
正文
"""
    (tmp_path / "workspace" / "demo" / "plan.md").write_text(plan_text, encoding="utf-8")
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "coverage_matrix.md").write_text(MATRIX_CONSISTENT + CHANGELOG_SECTION, encoding="utf-8")
    (spec_dir / "ambiguities.md").write_text("# 歧义清单\n\n（无）\n", encoding="utf-8")

    results = cg.check_plan(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-PL-6"].passed is True, by_id["G-PL-6"].detail


def test_check_implement_g_im_5_ignores_changelog_rows(tmp_path: Path) -> None:
    """旧实现同 G-PL-6 的机理：变更日志行缺「实现位置」列，被误判为缺失混入
    missing_impl_loc，尽管矩阵真正的 4 条要素行「实现位置」全部已填。"""
    _init_workspace(tmp_path)
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "coverage_matrix.md").write_text(MATRIX_DONE + CHANGELOG_SECTION, encoding="utf-8")
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True, exist_ok=True)
    (src / "strategy.py").write_text("def load_d1():\n    pass\n", encoding="utf-8")
    (src / "main.py").write_text("print('ok')\n", encoding="utf-8")

    results = cg.check_implement(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IM-5"].passed is True, by_id["G-IM-5"].detail


def test_check_verify_g_vf_7_ignores_changelog_rows(tmp_path: Path) -> None:
    """G-VF-7 与其余四处门禁统一改走 load_matrix_rows：变更日志表格不影响判定
    （4 条要素行「验证结果」均已填，PASS）。"""
    _init_workspace(tmp_path, type_="factor")
    _write_standards(tmp_path, STANDARDS_FIXTURE)
    metrics = [{"key": "rank_ic_mean", "report_value": 0.05, "reproduced_value": 0.055, "pass": True}]
    _write_verify_artifacts(tmp_path, "demo", metrics)
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "coverage_matrix.md").write_text(MATRIX_DONE + CHANGELOG_SECTION, encoding="utf-8")

    results = cg.check_verify(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-VF-7"].passed is True, by_id["G-VF-7"].detail


def test_check_report_g_fn_3_ignores_changelog_rows(tmp_path: Path) -> None:
    """G-FN-3 与其余四处门禁统一改走 load_matrix_rows：变更日志表格不影响判定
    （4 条要素行状态均为 done，无 pending/in_progress，PASS）。"""
    _init_workspace(tmp_path)
    (tmp_path / "workspace" / "demo" / "final_report.md").write_text("## 结论\n通过\n", encoding="utf-8")
    spec_dir = tmp_path / "workspace" / "demo" / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "coverage_matrix.md").write_text(MATRIX_DONE + CHANGELOG_SECTION, encoding="utf-8")

    results = cg.check_report(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-FN-3"].passed is True, by_id["G-FN-3"].detail


# ---------------------------------------------------------------------------
# C2：stop_partial / blocked 轮豁免 changes.md（G-IT-1），否则会死锁——这两种
# 结论下 diagnoser 不再给 coder 修改指令，changes.md 天然不存在。
# ---------------------------------------------------------------------------


def test_check_iterate_stop_partial_round_exempt_from_changes_md(tmp_path: Path) -> None:
    """stop_partial 轮只有 diagnosis.md + comparison.json（无 changes.md）——G-IT-1 仍应 PASS。"""
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "iteration.current", "1")
    iter_dir = tmp_path / "workspace" / "demo" / "iterations" / "iter_01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "diagnosis.md").write_text("## 归因\n数据源口径差异，同指标已连续 3 轮 fail。\n\n结论: stop_partial\n", encoding="utf-8")
    (iter_dir / "comparison.json").write_text("{}", encoding="utf-8")

    results = cg.check_iterate(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IT-1"].passed is True, by_id["G-IT-1"].detail


def test_check_iterate_blocked_round_exempt_from_changes_md(tmp_path: Path) -> None:
    """blocked 轮同样豁免 changes.md（全角冒号「结论：」也须识别）。"""
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "iteration.current", "1")
    iter_dir = tmp_path / "workspace" / "demo" / "iterations" / "iter_01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "diagnosis.md").write_text("## 归因\n缺关键外部数据，无法继续修正。\n\n结论：blocked\n", encoding="utf-8")
    (iter_dir / "comparison.json").write_text("{}", encoding="utf-8")

    results = cg.check_iterate(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IT-1"].passed is True, by_id["G-IT-1"].detail


def test_check_iterate_continue_round_still_requires_changes_md(tmp_path: Path) -> None:
    """反：continue 轮缺 changes.md 仍应 FAIL——豁免不能扩大到非 stop_partial/blocked 轮。"""
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "iteration.current", "1")
    iter_dir = tmp_path / "workspace" / "demo" / "iterations" / "iter_01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "diagnosis.md").write_text("## 归因\n换手率口径偏差，锁定修改点。\n\n结论: continue\n", encoding="utf-8")
    (iter_dir / "comparison.json").write_text("{}", encoding="utf-8")
    # 故意不写 changes.md

    results = cg.check_iterate(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IT-1"].passed is False
    assert "changes.md" in by_id["G-IT-1"].detail


def test_check_iterate_continue_mentioning_stop_partial_not_exempt(tmp_path: Path) -> None:
    """反：continue 结论行内附注提及 stop_partial（如「已排除」）不得被误判豁免。"""
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "iteration.current", "1")
    iter_dir = tmp_path / "workspace" / "demo" / "iterations" / "iter_01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "diagnosis.md").write_text(
        "## 归因\n锁定修改点。\n\n结论: continue（此前怀疑应为 stop_partial 但已排除）\n",
        encoding="utf-8",
    )
    (iter_dir / "comparison.json").write_text("{}", encoding="utf-8")
    # 故意不写 changes.md

    results = cg.check_iterate(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IT-1"].passed is False
    assert "changes.md" in by_id["G-IT-1"].detail


def test_check_iterate_stop_partial_with_trailing_note_still_exempt(tmp_path: Path) -> None:
    """正：结论值后带附注（「结论: stop_partial（同指标3轮红线）」）仍应豁免 changes.md。"""
    _init_workspace(tmp_path)
    st.set_field(tmp_path, "demo", "iteration.current", "1")
    iter_dir = tmp_path / "workspace" / "demo" / "iterations" / "iter_01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / "diagnosis.md").write_text(
        "## 归因\n数据源口径差异。\n\n结论: stop_partial（同指标 3 轮红线，疑数据源口径差异）\n",
        encoding="utf-8",
    )
    (iter_dir / "comparison.json").write_text("{}", encoding="utf-8")

    results = cg.check_iterate(tmp_path, "demo")
    by_id = {r.id: r for r in results}
    assert by_id["G-IT-1"].passed is True, by_id["G-IT-1"].detail


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
