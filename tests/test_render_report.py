"""tools/render_report.py 单测：硬输入校验 / 指标表渲染 / PNG 内嵌 / 可选节容错 / markdown 转换。"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import render_report as rr  # noqa: E402


def _fixture(root: Path, *, with_oos: bool = False, with_png: bool = False,
             with_md: bool = True) -> None:
    ws = root / "workspace" / "demo"
    res = root / "output" / "demo" / "results"
    ws.mkdir(parents=True, exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)
    (ws / "state.json").write_text(json.dumps({
        "verdict": {"result": "partial", "metrics_pass": 3, "metrics_total": 4},
        "coverage_stats": {"total": 10, "done": 9, "skipped": 0, "infeasible": 1},
        "iteration": {"current": 2, "max": 5},
        "external_reviews": [{"checkpoint": "result", "engine": "codex", "verdict": "fail",
                              "critical": 1, "major": 0, "minor": 0}],
        "type": "timing", "difficulty": "hard", "updated_at": "2026-07-10T00:00:00+08:00",
    }, ensure_ascii=False), encoding="utf-8")
    (res / "comparison.json").write_text(json.dumps({
        "pass_count": 3, "total": 4, "overall_pass": False,
        "metrics": [
            {"key": "annual_return", "report_value": 0.10, "reproduced_value": 0.101,
             "rel_dev": 0.01, "pass": True},
            {"key": "sharpe", "report_value": 1.5, "reproduced_value": 1.2,
             "rel_dev": 0.2, "pass": False,
             "attribution_status": "accepted", "attribution_note": "引擎口径差异"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    if with_md:
        (ws / "final_report.md").write_text(
            "# 报告\n\n## 一、结论\n\n可信度评级：**B**\n\n| 列A | 列B |\n|---|---|\n| 1 | 2 |\n",
            encoding="utf-8")
        (ws / "assumptions.md").write_text("## 假设\n\n- AS1 **测试假设**\n", encoding="utf-8")
    if with_oos:
        (res / "oos_metrics.json").write_text(json.dumps({
            "in_sample_end": "2023-12-29", "oos_start": "2024-01-02", "oos_end": "2025-06-30",
            "oos_days": 350, "baseline": "partial", "conclusion": "延续",
            "metrics": [{"key": "sharpe", "in_sample_value": 1.2, "oos_value": 1.0, "change": -0.17}],
        }, ensure_ascii=False), encoding="utf-8")
    if with_png:
        (res / "nav.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 100)


def test_render_produces_selfcontained_html(tmp_path):
    _fixture(tmp_path, with_oos=True, with_png=True)
    out = rr.render(tmp_path, "demo")
    assert out == tmp_path / "output" / "demo" / "final_report.html"
    t = out.read_text(encoding="utf-8")
    # 指标表：pass/fail 行与归因
    assert "annual_return" in t and "sharpe" in t
    assert "引擎口径差异" in t
    # 评级从 final_report.md 提取
    assert "可信度评级 B" in t
    # PNG base64 内嵌（自包含）
    assert "data:image/png;base64," in t
    expected_b64 = base64.b64encode(b"\x89PNG\r\n" + b"\x00" * 100).decode("ascii")
    assert expected_b64 in t
    # 样本外节
    assert "样本外表现" in t and "延续" in t
    # 外审台账
    assert "外部审查台账" in t
    # 无外链（CSP 自包含检查：不引用 http 资源）
    assert "src='http" not in t and 'src="http' not in t


def test_render_tolerates_missing_optional_inputs(tmp_path):
    """无 oos / 无 PNG / 无 md：对应节省略或占位，不崩溃。"""
    _fixture(tmp_path, with_oos=False, with_png=False, with_md=False)
    t = rr.render(tmp_path, "demo").read_text(encoding="utf-8")
    assert "样本外表现" not in t
    assert "未找到 PNG 图表" in t
    assert "未找到 assumptions.md / final_report.md" in t


def test_render_requires_hard_inputs(tmp_path):
    (tmp_path / "workspace" / "demo").mkdir(parents=True)
    with pytest.raises(SystemExit):
        rr.render(tmp_path, "demo")


def test_md_table_and_inline_conversion():
    out = rr.md_to_html("| A | B |\n|---|---|\n| **x** | `y` |\n")
    assert "<table>" in out and "<strong>x</strong>" in out and "<code>y</code>" in out


def test_html_escapes_content(tmp_path):
    """产物中的注入字符必须被转义。"""
    _fixture(tmp_path)
    res = tmp_path / "output" / "demo" / "results"
    data = json.loads((res / "comparison.json").read_text(encoding="utf-8"))
    data["metrics"][0]["key"] = "<script>alert(1)</script>"
    (res / "comparison.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    t = rr.render(tmp_path, "demo").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in t
    assert "&lt;script&gt;" in t


def test_render_shows_verification_level_layers(tmp_path):
    """降级核验项在指标表与分层说明中透明展示。"""
    _fixture(tmp_path)
    res = tmp_path / "output" / "demo" / "results"
    data = json.loads((res / "comparison.json").read_text(encoding="utf-8"))
    data["metrics"][1]["verification_level"] = "directional"
    (res / "comparison.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    t = rr.render(tmp_path, "demo").read_text(encoding="utf-8")
    assert "核验分层" in t and "1 项因研报参数不明降级核验" in t
    assert "方向" in t
