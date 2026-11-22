"""tools/flowlib/packs.py：按角色与步骤切上下文包、口径卡、lint、影子包统计。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import state as st  # noqa: E402
from tools.flowlib import packs  # noqa: E402

SPEC = """# 测试研报 复现规格书

## 二、数据要求（D 类）

### [D1] 日行情
- 页码: p3
- 原文: > "日度收盘价 D1 原文"

### [D2] 财务数据
- 页码: p4
- 原文: > "归母净利润 D2 原文"

### [D3] 用不到的数据
- 页码: p4
- 原文: > "D3 原文"

## 三、因子定义（F 类）

### [F1] 动量因子
- 页码: p5
- 原文: > "F1 原文"
- 公式（转写）: mom = close / close.shift(20) - 1
- 依赖数据: D1 / 关联基准: R1

### [F2] 盈利因子
- 页码: p6
- 原文: > "F2 原文"
- 公式（转写）: 用 F1 的窗口，分母取 D2
- 依赖数据: D2 / 关联基准: R2

## 四、回测设置（B 类）

### [B1] 月度调仓
- 页码: p7
- 原文: > "B1 原文"
- 参数值: 月频

## 五、研报核心数值结果基准（R 类）

### [R1] 动量多空收益
- 页码: p8
- 原文: > "R1 原文"
- 关联要素: F1, B1

### [R2] 盈利多空收益
- 页码: p9
- 原文: > "R2 原文"
- 关联要素: F2

## 七、敏感性分析（SA 类）

### [SA1] 窗口敏感性
- 页码: p10
- 原文: > "SA1 原文"
- 关联要素: F1

## 八、提取自检声明

自检文字，不属于任何要素。
"""

MATRIX = """# 覆盖矩阵

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | D | 日行情 | p3 | core | m1 | done | | src/demo/data.py:load_price | ok | verify |
| D2 | D | 财务 | p4 | core | m2 | done | | src/demo/data.py:load_fin | ok | verify |
| D3 | D | 用不到 | p4 | optional | | skipped | 无关 | | | plan |
| F1 | F | 动量 | p5 | core | m1 | done | | src/demo/strategy.py:momentum | ok | verify |
| F2 | F | 盈利 | p6 | core | m2 | done | | strategy.py:earnings | ok | verify |
| B1 | B | 调仓 | p7 | core | m1 | done | | src/demo/main.py:run | ok | verify |
| R1 | R | 动量收益 | p8 | core | m1 | done | | src/demo/main.py:run | ok | verify |
| R2 | R | 盈利收益 | p9 | core | m2 | done | | src/demo/main.py:run | ok | verify |
| SA1 | SA | 窗口 | p10 | support | m2 | done | | src/demo/main.py:run | ok | verify |

## 变更日志

| 时间 | 事件 | 来源 | 说明 |
|---|---|---|---|
| t | e | s | 不是要素行 |
"""

ASSUMPTIONS = """# 假设登记簿

### [AS1] 动量窗口取 20 日
- 来源: A1（auto 裁决）
- 假设内容: 窗口 20 个交易日 AS1内容
- 行业惯例依据: 很长的依据 AS1依据
- 影响面: method
- 影响 milestone: m1
- 影响指标: R1
- 预期影响: AS1预期
- 验证后回看: 很长的回看文字 AS1回看
- 状态: assumed
- 高亮等级: major-auto
- 参数绑定: momentum_window

### [AS2] 盈利口径
- 来源: A2
- 假设内容: 旧口径 AS2内容
- 影响面: data
- 影响 milestone: m2（下游 m1 不受影响）
- 影响指标: R2
- 预期影响: AS2预期
- 修订记录: 第一次修订 AS2修订一
- 验证后回看（iter_01 修订）: AS2回看一
- 修订记录(2): 第二次修订，新口径在这里 AS2修订二
- 状态: revised
- 高亮等级: -

### [AS3] 只写了影响指标
- 来源: A3
- 假设内容: AS3内容
- 影响面: trading
- 影响 milestone: -
- 影响指标: SA1 的结论
- 状态: assumed

### [AS4] 归属不明
- 来源: A4
- 假设内容: AS4内容
- 影响面: method
- 影响 milestone: 待定
- 影响指标: 无
- 状态: assumed

### [AS5] 已跳过的要素
- 来源: A5
- 假设内容: AS5内容
- 影响面: data
- 影响 milestone: 不影响m1-m2；对应D3已skipped
- 影响指标: 无
- 状态: assumed

### [AS6] 没按模板写
- 裁决状态: 已裁决
- 裁决依据: AS6依据
- 影响 milestone: m1
- 自定义说明: AS6自定义
"""

PLAN = """---
report_name: 测试研报
type: factor
difficulty: medium
milestones:
  - id: m1
    name: 数据与动量
    deps: []
    elements: [D1, F1, B1, R1]
  - id: m2
    name: 盈利与敏感性
    deps: [m1]
    elements: [D2, F2, R2]
---
# 复现开发计划

## 一、核心策略

```python
# m1 不是标题
## 二、回测参数 也不是标题
```

## 二、回测参数（复现对齐用）

| 参数 | 值 |
|---|---|
| 调仓 | 月频 PLAN参数 |

## 四、复现计划（按 milestone 拆分）

### m1: 数据与动量

m1 的计划正文 PLAN-m1

### m2：盈利与敏感性（deps: [m1]）

m2 的计划正文 PLAN-m2

## 五、难度判定

medium
"""

COMMON_UTILS = '''"""utils"""


def winsorize(x, lower=0.01, upper=0.99):
    """去极值。

    更多说明。
    """
    return x


def _private(x):
    return x


class Engine:
    """回测引擎。"""

    def run(
        self,
        data,
    ):
        """
        跑回测。
        """
        return data

    def _hidden(self):
        return None
'''

SRC_DATA = '''from common.utils import winsorize
from common import extra_tool


def load_price(path):
    """读行情。"""
    return path


def load_fin(path): return path
'''


@pytest.fixture()
def case(tmp_path: Path) -> packs.CaseDocs:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(tmp_path, "demo", "type", "factor")
    ws = tmp_path / "workspace" / "demo"
    (ws / "spec" / "spec.md").write_text(SPEC, encoding="utf-8")
    (ws / "spec" / "coverage_matrix.md").write_text(MATRIX, encoding="utf-8")
    (ws / "assumptions.md").write_text(ASSUMPTIONS, encoding="utf-8")
    (ws / "plan.md").write_text(PLAN, encoding="utf-8")
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "factor.md").write_text("# factor 模板\n\n用 common/factor_extra.py 的接口。TEMPLATE正文\n", encoding="utf-8")
    (templates / "standards.json").write_text(json.dumps({"factor": {"metrics": {}}}), encoding="utf-8")
    common = tmp_path / "common"
    common.mkdir()
    (common / "__init__.py").write_text("", encoding="utf-8")
    (common / "utils.py").write_text(COMMON_UTILS, encoding="utf-8")
    (common / "factor_extra.py").write_text("def extra_factor():\n    return 1\n", encoding="utf-8")
    (common / "extra_tool.py").write_text("def tool():\n    return 1\n", encoding="utf-8")
    (common / "ml_pipeline.py").write_text("def train_everything():\n    return 1\n", encoding="utf-8")
    src = tmp_path / "src" / "demo"
    (src / "data.py").write_text(SRC_DATA, encoding="utf-8")
    (src / "strategy.py").write_text("def momentum(x):\n    return x\n\n\ndef earnings(x):\n    return x\n", encoding="utf-8")
    (src / "main.py").write_text("def run():\n    return 0\n", encoding="utf-8")
    results = tmp_path / "output" / "demo" / "results"
    (results / "nav.png").write_bytes(b"png")
    return packs.CaseDocs.load(tmp_path, "demo")


def _keys(pack: packs.Pack, kind: str) -> list[str]:
    out: list[str] = []
    for seg in pack.segments():
        if seg.kind == kind and seg.key not in out:
            out.append(seg.key)
    return out


# ---------------------------------------------------------------------------
# 案例文书的基本查询
# ---------------------------------------------------------------------------


def test_step_elements_is_union_of_matrix_and_plan(case: packs.CaseDocs) -> None:
    assert case.milestone_ids() == ["m1", "m2"]
    assert case.step_elements("m1") == ["D1", "F1", "B1", "R1"]
    # SA1 只在矩阵里归到 m2（plan 的 elements 没写），取并集后仍在
    assert case.step_elements("m2") == ["D2", "F2", "R2", "SA1"]
    assert case.milestone_deps("m2") == ["m1"] and case.milestone_deps("m1") == []
    assert case.report_type == "factor"


def test_assumption_attribution(case: packs.CaseDocs) -> None:
    owners = {b.id: case.assumption_owners(b) for b in case.assumption_blocks}
    assert owners["AS1"] == ["m1"]
    assert owners["AS2"] == ["m2"]  # 括号里的 m1 不算主归属
    assert owners["AS3"] == ["m2"]  # 靠「影响指标」命中 SA1
    assert owners["AS4"] == []
    assert owners["AS5"] == [] and case.assumption_explicit_none(case.assumption("AS5"))
    assert not case.assumption_explicit_none(case.assumption("AS4"))
    assert owners["AS6"] == ["m1"]


# ---------------------------------------------------------------------------
# 各角色的包
# ---------------------------------------------------------------------------


def test_every_segment_is_byte_substring_of_its_source(case: packs.CaseDocs) -> None:
    targets = [(role, m) for m in ("m1", "m2") for role in packs.MILESTONE_ROLES]
    targets += [(role, packs.FINAL_STEP) for role in packs.FINAL_ROLES]
    for role, step in targets:
        pack = packs.build_pack(case, role, step)
        assert packs.verify_pack(case, pack) == [], (role, step)
        assert pack.segments(), (role, step)
        rendered = pack.render()
        for seg in pack.segments():
            assert seg.text in rendered
            assert seg.text.encode("utf-8") in (case.root / seg.source).read_bytes()
        assert pack.nbytes == len(rendered.encode("utf-8"))
        assert "冲突，以原文为准" in rendered


def test_coder_pack_contents(case: packs.CaseDocs) -> None:
    pack = packs.build_pack(case, "coder", "m2")
    text = pack.render()
    # 本步要素全文；F2 的公式行引用了 F1（非 R），按一跳规则带入全文，排在本步要素之后
    assert _keys(pack, "element") == ["D2", "F2", "R2", "SA1", "F1"]
    assert _keys(pack, "element_index") == ["D1", "D3", "B1", "R1"]
    assert "F2 原文" in text and "F1 原文" in text and "B1 原文" not in text and "### [B1] 月度调仓" in text
    assert pack.summary["closure_elements"] == 1
    # 口径卡：主归属 m2 的 AS2、AS3，加上归属不明的 AS4；写明不影响的 AS5 只列标题
    assert _keys(pack, "assumption_card") == ["AS2", "AS3", "AS4"]
    assert _keys(pack, "assumption_index") == ["AS1", "AS5", "AS6"]
    assert "AS2修订二" in text and "AS2修订一" not in text  # 只带最新一条修订记录
    assert "AS2回看一" not in text and "AS2预期" not in text
    assert "AS1内容" not in text and "### [AS1] 动量窗口取 20 日" in text
    # 矩阵只带本步的行，表头带一次
    assert _keys(pack, "matrix") == ["header", "D2", "F2", "R2", "SA1"]
    assert "不是要素行" not in text
    # 计划：本步小节 + 回测参数；围栏里的假标题不干扰
    assert "PLAN-m2" in text and "PLAN-m1" not in text and "PLAN参数" in text
    assert "TEMPLATE正文" in text
    assert pack.summary["assumption_cards"] == 3
    assert any("只在矩阵里有归属" in w and "SA1" in w for w in pack.warnings)
    assert pack.full_bytes == sum(
        len((case.root / rel).read_bytes())
        for rel in (
            "workspace/demo/spec/spec.md",
            "workspace/demo/assumptions.md",
            "workspace/demo/spec/coverage_matrix.md",
            "workspace/demo/plan.md",
            "templates/factor.md",
        )
    )


def test_coder_pack_one_hop_closure(case: packs.CaseDocs) -> None:
    pack = packs.build_pack(case, "coder", "m1")
    # m1 的 F1 依赖 D1（已在本步）；「关联基准: R1」这类 R 引用不触发带入；F2 引用 F1 是反方向
    assert _keys(pack, "element") == ["D1", "F1", "B1", "R1"]
    assert pack.summary["closure_elements"] == 0
    # m2：F2 的公式行引用 F1 → 带入；只走一跳，F1 依赖的 D1 不再跟进
    assert packs._closure(case, case.step_elements("m2")) == ["F1"]
    assert "D1" not in _keys(packs.build_pack(case, "coder", "m2"), "element")


def test_coder_signatures_scoped_by_type_and_upstream(case: packs.CaseDocs) -> None:
    pack = packs.build_pack(case, "coder", "m2")
    sig_sources = sorted({s.source for s in pack.segments() if s.kind == "signature"})
    # 通用模块 + 类型前缀 + 模板点名 + 上游代码导入的；无关的机器学习模块不带
    assert "common/utils.py" in sig_sources
    assert "common/factor_extra.py" in sig_sources
    assert "common/extra_tool.py" in sig_sources
    assert "common/ml_pipeline.py" not in sig_sources
    # 直接上游 m1 的实现文件（来自矩阵「实现位置」列，含只写文件名的写法）
    assert "src/demo/data.py" in sig_sources and "src/demo/strategy.py" in sig_sources
    names = _keys(pack, "signature")
    assert {"winsorize", "Engine", "Engine.run", "load_price", "load_fin"} <= set(names)
    assert "_private" not in names and "Engine._hidden" not in names
    text = pack.render()
    assert 'def winsorize(x, lower=0.01, upper=0.99):\n    """去极值。\n' in text
    assert "更多说明" not in text and "return x" not in text.replace("def load_fin(path): return path", "")
    assert '"""\n        跑回测。\n' in text  # 文档串首行只有引号时带上摘要行
    # m1 没有上游，不带 src 的签名
    m1 = packs.build_pack(case, "coder", "m1")
    assert not [s for s in m1.segments() if s.kind == "signature" and s.source.startswith("src/")]


def test_auditor_code_pack_holds_all_fb_and_all_assumptions(case: packs.CaseDocs) -> None:
    pack = packs.build_pack(case, "auditor_code", "m2")
    assert _keys(pack, "element") == ["D2", "F1", "F2", "B1", "R2", "SA1"]  # 全部 F、B + 本步 D/R/SA
    assert _keys(pack, "assumption_card") == ["AS1", "AS2", "AS3", "AS4", "AS5", "AS6"]  # 审计持全部假设
    assert _keys(pack, "assumption_index") == []
    assert not [s for s in pack.segments() if s.kind in ("plan", "template", "signature")]
    text = pack.render()
    assert "AS6自定义" in text and "AS6依据" in text  # 没有「假设内容」的条目整块带入


def test_verifier_pack_contents(case: packs.CaseDocs) -> None:
    pack = packs.build_pack(case, "verifier", "m2")
    assert _keys(pack, "element")[:2] == ["R2", "SA1"]  # 本步 R/SA
    assert set(_keys(pack, "element")) == {"R2", "SA1", "F2", "F1"}  # 加「关联要素」一跳；F2 依赖的 D2 是第二跳，不带
    text = pack.render()
    assert "AS2预期" in text  # 验证的口径卡带「预期影响」
    assert _keys(pack, "standards") == ["standards.json"] and "TEMPLATE正文" in text
    assert "PLAN-m2" not in text


def test_final_packs(case: packs.CaseDocs) -> None:
    verifier = packs.build_pack(case, "verifier", packs.FINAL_STEP)
    assert _keys(verifier, "element") == ["B1", "R1", "R2", "SA1"]
    assert _keys(verifier, "element_index") == ["D1", "D2", "D3", "F1", "F2"]
    assert len(_keys(verifier, "assumption_card")) == 6
    assert "output/demo/results/nav.png" in verifier.render()
    assert len(_keys(verifier, "matrix")) == 1 + 9
    auditor = packs.build_pack(case, "auditor_result", packs.FINAL_STEP)
    assert not [s for s in auditor.segments() if s.kind in ("standards", "template")]


def test_unknown_fields_are_kept_in_card(case: packs.CaseDocs, tmp_path: Path) -> None:
    path = case.root / "workspace" / "demo" / "assumptions.md"
    path.write_text(ASSUMPTIONS.replace("- 参数绑定: momentum_window", "- 参数绑定: momentum_window\n- 公司行动近似一: 逐项近似 AS1近似"), encoding="utf-8")
    docs = packs.CaseDocs.load(case.root, "demo")
    text = packs.build_pack(docs, "coder", "m1").render()
    assert "AS1近似" in text and "AS1依据" not in text and "AS1回看" not in text
    assert any(f.code == "assumption_extra_field" and "AS1" in f.message for f in packs.lint(docs))


def test_build_pack_errors(case: packs.CaseDocs, tmp_path: Path) -> None:
    with pytest.raises(packs.PackError, match="没有 milestone m9"):
        packs.build_pack(case, "coder", "m9")
    with pytest.raises(packs.PackError, match="final"):
        packs.build_pack(case, "coder", packs.FINAL_STEP)
    with pytest.raises(packs.PackError):
        packs.build_pack(case, "auditor_result", "m1")
    (case.root / "workspace" / "demo" / "assumptions.md").unlink()
    with pytest.raises(packs.PackError, match="assumptions.md"):
        packs.build_pack(packs.CaseDocs.load(case.root, "demo"), "verifier", packs.FINAL_STEP)


def test_review_edit_does_not_change_coder_segment_hashes(case: packs.CaseDocs) -> None:
    """verifier 回填「验证后回看」不应让 coder 包里的片失效（按片记哈希，不按整份文件）。"""
    before = packs.build_pack(case, "coder", "m1")
    path = case.root / "workspace" / "demo" / "assumptions.md"
    path.write_text(ASSUMPTIONS.replace("很长的回看文字 AS1回看", "verify 之后改写的回看，长度也变了"), encoding="utf-8")
    after = packs.build_pack(packs.CaseDocs.load(case.root, "demo"), "coder", "m1")
    sha = lambda p: [(s.kind, s.key, s.sha) for s in p.segments()]  # noqa: E731
    assert sha(before) == sha(after)
    assert before.sources["workspace/demo/assumptions.md"] != after.sources["workspace/demo/assumptions.md"]
    # 改口径本身则会变
    path.write_text(ASSUMPTIONS.replace("窗口 20 个交易日 AS1内容", "窗口 60 个交易日"), encoding="utf-8")
    changed = packs.build_pack(packs.CaseDocs.load(case.root, "demo"), "coder", "m1")
    assert sha(before) != sha(changed)


def test_manifest_shape(case: packs.CaseDocs) -> None:
    manifest = packs.build_pack(case, "coder", "m1").manifest()
    assert manifest["format"] == packs.PACK_FORMAT and manifest["role"] == "coder" and manifest["step"] == "m1"
    assert manifest["bytes"] > 0 and manifest["full_contract_bytes"] > manifest["bytes"] / 10
    assert all({"source", "kind", "key", "start", "end", "sha"} <= set(s) for s in manifest["segments"])
    assert sum(manifest["bytes_by_kind"].values()) == manifest["bytes"]
    json.dumps(manifest, ensure_ascii=False)


def test_get_block(case: packs.CaseDocs) -> None:
    assert packs.get_block(case, "element", "F1").text.startswith("### [F1] 动量因子")
    assert "AS1回看" in packs.get_block(case, "assumption", "AS1").text  # 逃生门给整块
    assert packs.get_block(case, "matrix-row", "D2").text.startswith("| D2 |")
    for kind, key in (("element", "F99"), ("assumption", "AS99"), ("matrix-row", "X1"), ("page", "p3")):
        with pytest.raises(packs.PackError):
            packs.get_block(case, kind, key)


# ---------------------------------------------------------------------------
# lint 与影子包统计
# ---------------------------------------------------------------------------


def test_lint_findings(case: packs.CaseDocs) -> None:
    codes = {(f.level, f.code) for f in packs.lint(case)}
    assert ("warn", "assumption_unattributed") in codes  # AS4
    assert ("info", "assumption_explicit_none") in codes  # AS5
    assert ("warn", "assumption_no_content_field") in codes  # AS6
    assert ("info", "owner_matrix_only") in codes  # SA1
    assert ("warn", "element_no_owner") not in codes  # D3 是 optional + skipped，不告警
    messages = "\n".join(f.message for f in packs.lint(case))
    assert "AS4" in messages and "AS1 " not in messages


def test_lint_reports_ownerless_elements_once(case: packs.CaseDocs) -> None:
    path = case.root / "workspace" / "demo" / "spec" / "coverage_matrix.md"
    path.write_text(
        MATRIX.replace("| D3 | D | 用不到 | p4 | optional | | skipped |", "| D3 | D | 用不到 | p4 | core | | pending |")
        .replace("| SA1 | SA | 窗口 | p10 | support | m2 |", "| SA1 | SA | 窗口 | p10 | support | m7 |"),
        encoding="utf-8",
    )
    findings = packs.lint(packs.CaseDocs.load(case.root, "demo"))
    ownerless = [f for f in findings if f.code == "element_no_owner"]
    assert len(ownerless) == 1 and "D3" in ownerless[0].message
    assert any(f.code == "unknown_milestone" and "m7" in f.message for f in findings)


def test_lint_before_plan_has_no_owner_noise(tmp_path: Path) -> None:
    st.init_state(tmp_path, "early", "reports/early.pdf")
    ws = tmp_path / "workspace" / "early"
    (ws / "spec" / "spec.md").write_text(SPEC, encoding="utf-8")
    (ws / "spec" / "coverage_matrix.md").write_text(MATRIX.replace("| m1 |", "| |").replace("| m2 |", "| |"), encoding="utf-8")
    findings = packs.lint(packs.CaseDocs.load(tmp_path, "early"))
    assert [f.code for f in findings] == ["no_milestones"]
    assert packs.lint(packs.CaseDocs.load(tmp_path, "ghost"))[0].code == "no_spec"


def test_shadow_stats_writes_nothing(case: packs.CaseDocs) -> None:
    before = sorted(p.as_posix() for p in case.root.rglob("*") if "__pycache__" not in p.parts)
    stats = packs.shadow_stats(case.root, "demo")
    assert sorted(p.as_posix() for p in case.root.rglob("*") if "__pycache__" not in p.parts) == before
    assert stats["milestones"] == ["m1", "m2"] and not stats["errors"]
    assert len(stats["packs"]) == 2 * 3 + 2
    assert all(row["substring_ok"] and row["bytes"] > 0 for row in stats["packs"])
    summary = packs.summarize_ratios([stats])
    assert set(summary) == {"coder", "auditor_code", "verifier", "verifier(final)", "auditor_result(final)"}
    assert summary["coder"]["n"] == 2


def _real_cases() -> list[str]:
    ws = REPO_ROOT / "workspace"
    if not ws.is_dir():
        return []
    return [p.name for p in sorted(ws.iterdir()) if (p / "plan.md").is_file() and (p / "assumptions.md").is_file() and (p / "spec" / "spec.md").is_file()]


@pytest.mark.parametrize("report_id", _real_cases())
def test_real_cases_build_all_packs(report_id: str) -> None:
    """仓库里已有的案例：每个角色、每一步都拼得出包，片都是原文子串，编码包明显小于现行合同全量。"""
    stats = packs.shadow_stats(REPO_ROOT, report_id)
    assert not stats["errors"], stats["errors"]
    assert stats["packs"] and all(row["substring_ok"] for row in stats["packs"])
    for row in stats["packs"]:
        assert row["bytes"] < row["full_bytes"], (row["role"], row["step"])
