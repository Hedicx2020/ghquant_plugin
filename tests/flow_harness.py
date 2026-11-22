"""内核端到端测试的公共夹具：一个玩具案例、一组桩 agent、一个假的外审引擎。全程不花 token。

桩 agent 按工单办事：读工单里的步骤编号与清单，写出这一步该交回的文件和回执，内容刚好能过真实门禁。
剧本（Scenario）里的开关用来制造各种路径：指标超差后迭代、外审提 critical、子 agent 漏交产物、数据缺口等。
外审不调真的 CLI：把 tools/external_review.run_review 换成按剧本写回结果的假函数。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import external_review as er  # noqa: E402
from tools import pdf_extract  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import decisions  # noqa: E402
from tools.flowlib.core import read_json  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402

SPEC = """---
report_name: 玩具研报
title: 玩具动量策略
institution: 测试机构
report_date: 2023-08-22
authors: 张三
market: A股
pdf_pages: 3
exhibit_declared: {fig_max: 2, tbl_max: 1}
element_counts: {D: 1, F: 2, B: 1, R: 2, SA: 0, FIG_registered: 2, TBL_registered: 1}
type_hint: factor
tags_hint: []
---

# 玩具动量策略 复现规格书

## 二、数据要求（D 类）

### [D1] 日行情
- 页码: p1
- 原文: > "使用全部 A 股日度收盘价"

## 三、因子定义（F 类）

### [F1] 动量因子
- 页码: p2
- 原文: > "过去 20 日收益率"
- 公式（转写）: mom = close / close.shift(20) - 1
- 依赖数据: D1 / 关联基准: R1

### [F2] 反转因子
- 页码: p2
- 原文: > "过去 5 日收益率取负"
- 公式（转写）: rev = -(close / close.shift(5) - 1)
- 依赖数据: D1 / 关联基准: R2

## 四、回测设置（B 类）

### [B1] 月度调仓
- 页码: p2
- 原文: > "每月末调仓，分五组"
- 参数值: 月频，5 组

## 五、研报核心数值结果基准（R 类）

### [R1] 动量 RankIC 均值
- 页码: p3
- 原文: > "RankIC 均值 5.00%"
- 关联要素: F1, B1

### [R2] 反转 RankIC 均值
- 页码: p3
- 原文: > "RankIC 均值 4.00%"
- 关联要素: F2, B1

## 六、图表登记清单

| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| FIG1 | IC 序列 | p3 | 月度 IC | reproduce | R1 |
| FIG2 | 分组净值 | p3 | 五组净值 | reproduce | R1 |
| TBL1 | 绩效表 | p3 | IC 与收益 | reproduce | R1, R2 |
"""

MATRIX_HEAD = (
    "# 覆盖矩阵\n\n"
    "| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)
ELEMENTS = [("D1", "D", "日行情", "p1"), ("F1", "F", "动量", "p2"), ("F2", "F", "反转", "p2"), ("B1", "B", "调仓", "p2"), ("R1", "R", "动量IC", "p3"), ("R2", "R", "反转IC", "p3")]
OWNER = {
    1: {eid: "m1" for eid, *_ in ELEMENTS},
    2: {"D1": "m1", "F1": "m1", "B1": "m1", "R1": "m1", "F2": "m2", "R2": "m2"},
    3: {"D1": "m1", "F1": "m2", "B1": "m1", "R1": "m2", "F2": "m3", "R2": "m3"},
}
AMBIGUITIES_EMPTY = "# 歧义清单\n\n（无）\n"
AMBIGUITY_MAJOR = """# 歧义清单

### [A1] 动量窗口的口径
- 等级: major
- 页码: p2
- 描述: 研报没有写明 20 日是交易日还是自然日
- 裁决方式: auto
- 裁决结果: 取交易日
- 依据: 行业惯例
- 状态: resolved
"""
ASSUMPTIONS = """# 假设登记簿

### [AS1] 动量窗口取 20 个交易日
- 来源: A1（auto 裁决）
- 假设内容: 窗口按交易日计
- 行业惯例依据: 量价因子普遍按交易日
- 参数绑定: momentum_window
- 影响面: param
- 影响 milestone: m1
- 影响指标: R1
- 预期影响: 影响很小
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto
"""
MOCK_SPEC = """version: 1
seed: 7
period: [2020-01-01, 2020-12-31]
freq: D
n_codes: 20
tables:
  - name: toy_price.parquet
    note: 玩具行情，本地没有
    columns:
      - {name: stock_code, kind: code}
      - {name: date, kind: date}
      - {name: close, kind: price, start: [5, 80], vol: 0.02}
"""
GAP_REQUIREMENT = {
    "name": "A股日行情",
    "source": "toy_price.parquet",
    "status": "available",
    "files": ["toy_price.parquet"],
    "fields": ["stock_code", "date", "close"],
    "period": "2020-01-01~2020-12-31",
    "freq": "D",
    "core": True,
    "elements": ["D1"],
}
REPORT_SECTIONS = ["结论", "指标对比", "假设登记簿", "迭代历史", "审计回应", "残余偏差", "未复现清单", "复跑指引"]
CHARTS = ["ic_series.png", "ic_distribution.png", "group_cumulative_returns.png", "group_returns_bar.png", "net_value_comparison.png"]


def matrix_text(n_milestones: Optional[int]) -> str:
    owner = OWNER.get(n_milestones or 0, {})
    rows = [f"| {eid} | {cat} | {desc} | {page} | core | {owner.get(eid, '')} | pending |  |  |  | {'plan' if owner else 'extract'} |" for eid, cat, desc, page in ELEMENTS]
    return MATRIX_HEAD + "\n".join(rows) + "\n"


def plan_text(difficulty: str, n: int, data_requirements: Optional[list[dict[str, Any]]] = None, feasibility: str = "feasible", tags: Optional[list[str]] = None) -> str:
    import yaml

    owner = OWNER[n]
    milestones = [
        {"id": f"m{i}", "name": f"第 {i} 步", "desc": "玩具", "deps": [f"m{i - 1}"] if i > 1 else [], "elements": [e for e, m in owner.items() if m == f"m{i}"]}
        for i in range(1, n + 1)
    ]
    front = {
        "report_name": "toy",
        "title": "玩具动量策略",
        "type": "factor",
        "tags": tags or [],
        "difficulty": difficulty,
        "feasibility": feasibility,
        "data_requirements": data_requirements if data_requirements is not None else [{"name": "A股日行情", "source": "外部", "status": "available"}],
        "milestones": milestones,
    }
    body = ["# 玩具动量策略 复现开发计划", ""]
    for m in milestones:
        body += [f"## {m['id']} {m['name']}", "", f"交付要素 {', '.join(m['elements'])}。", ""]
    body += ["## 回测参数", "", "- 调仓频率: 月频", "- 分组数: 5", ""]
    return "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n" + "\n".join(body)


def big_bytes(n: int = 16 * 1024) -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * (n // 256 + 1))[: n + 64]


# ---------------------------------------------------------------------------
# 剧本
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    difficulty: str = "easy"
    milestones: int = 1
    tags: list[str] = field(default_factory=list)
    feasibility: list[str] = field(default_factory=lambda: ["feasible"])  # 第 n 次 plan.main 给出的可行性（用完后沿用最后一个）
    data_requirements: Optional[list[list[dict[str, Any]]]] = None  # 第 n 次 plan.main 写的数据需求
    ambiguities: str = AMBIGUITIES_EMPTY
    assumptions: str = ASSUMPTIONS
    mock_spec: str = MOCK_SPEC
    manifest_source: str = "real"  # 真实结果的数据清单里把数据文件记成 real 还是 mock（做过试跑的案例才写清单）
    # 第 n 次整批验证给出的复现值（R1, R2）；研报值是 0.05 与 0.04
    verify_values: list[tuple[float, float]] = field(default_factory=lambda: [(0.0501, 0.0401)])
    diagnose: list[str] = field(default_factory=lambda: ["continue"])  # 各轮诊断结论
    oos: str = "full"  # full / skip
    # 外审剧本：{kind: [第 1 轮的意见列表, 第 2 轮的意见列表, …]}，意见形如 {"severity": "major", "category": "x", "description": "…"}
    reviews: dict[str, list[list[dict[str, Any]]]] = field(default_factory=dict)
    review_fail: dict[str, list[str]] = field(default_factory=dict)  # {kind: [第 n 次调用的失败状态]}，如 ["timeout", "timeout"]
    rulings: dict[str, dict[str, Any]] = field(default_factory=dict)  # 意见编号 → 答卷里的那一项（默认全部 accepted）
    omit: dict[str, int] = field(default_factory=dict)  # 步骤编号 → 前 n 次派发故意不交产物
    blocked: dict[str, int] = field(default_factory=dict)  # 步骤编号 → 前 n 次派发回执写 blocked
    milestone_verify_fail: dict[str, int] = field(default_factory=dict)  # milestone → 前 n 次验证判 fail
    audit_critical: dict[str, int] = field(default_factory=dict)  # 步骤编号 → 前 n 次内审报 critical
    hooks: dict[str, Callable[["Stub", dict[str, Any]], None]] = field(default_factory=dict)  # 步骤编号 → 做完后额外执行


class Stub:
    """桩 agent：run(order) 按工单写产物与回执。"""

    def __init__(self, root: Path, report_id: str, scenario: Scenario) -> None:
        self.root, self.report_id, self.sc = root, report_id, scenario
        self.ws = root / "workspace" / report_id
        self.src = root / "src" / report_id
        self.out = root / "output" / report_id
        self.calls: list[str] = []
        self.counts: dict[str, int] = {}
        self.verify_runs = 0
        self.review_calls: dict[str, int] = {}

    # ---- 小工具 ----
    def state(self) -> dict[str, Any]:
        return st.load_state(self.root, self.report_id)

    def results(self) -> Path:
        trial = ((self.state().get("ext") or {}).get("trial") or {}).get("active")
        return self.out / ("results_mock" if trial else "results")

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def receipt(self, order: dict[str, Any], **fields: Any) -> None:
        if not order.get("receipt"):
            return
        data = {"format": "flow-receipt v1", "step": order["description"], "status": "done", "summary": f"桩 agent 完成 {order['description']}", **fields}
        self.write(self.root / order["receipt"], json.dumps(data, ensure_ascii=False, indent=2))

    def n_milestones(self) -> int:
        return self.sc.milestones

    def elements_of(self, mid: Optional[str]) -> list[str]:
        owner = OWNER[self.n_milestones()]
        return [e for e, m in owner.items() if mid in (None, "all") or m == mid]

    def nth(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    # ---- 入口 ----
    def run(self, order: dict[str, Any]) -> str:
        """做一张工单，返回子 agent 对主会话说的那一行（DONE 或 BLOCKED: …）。"""
        step = order["description"]
        self.calls.append(order["step_id"])
        attempt = self.nth(step)
        if attempt <= self.sc.omit.get(step, 0):
            return "DONE"  # 嘴上说做完了，其实什么都没交
        if attempt <= self.sc.blocked.get(step, 0):
            self.receipt(order, status="blocked", summary="桩 agent：缺少外部输入")
            return "BLOCKED: 缺少外部输入"
        handler = self._handler(step)
        handler(order, attempt)
        hook = self.sc.hooks.get(step)
        if hook:
            hook(self, order)
        return "DONE"

    def _handler(self, step: str) -> Callable[[dict[str, Any], int], None]:
        table: list[tuple[str, Callable[[dict[str, Any], int], None]]] = [
            (r"extract\.main$", self.extract),
            (r"plan\.main$", self.plan),
            (r"plan\.mock_spec$", self.mock_spec),
            (r"spec_audit\.internal$", self.spec_internal),
            (r"implement\.revise_plan$", self.revise_plan),
            (r"implement\.revise_config$", self.code),
            (r"implement\.(m\d+|all)\.code$", self.code),
            (r"implement\.m\d+\.verify$", self.milestone_verify),
            (r".*\.m\d+\.audit$", self.impl_audit),
            (r"code_audit\.internal$", self.impl_audit),
            (r"(verify\.main|iterate\.r\d+\.verify|.*\.reverify\.r\d+)$", self.verify),
            (r"iterate\.r\d+\.diagnose$", self.diagnose),
            (r"iterate\.r\d+\.fix$", self.iterate_fix),
            (r"iterate\.final\.attribution$", self.attribution),
            (r"result_audit\.internal$", self.result_internal),
            (r"oos\.main$", self.oos),
            (r"report\.main$", self.report),
            (r".*\.ext\.r\d+\.fallback$", self.fallback),
        ]
        for pattern, handler in table:
            if re.fullmatch(pattern, step):
                return handler
        return self.generic

    # ---- 各角色 ----
    def generic(self, order: dict[str, Any], attempt: int) -> None:
        """修复类工单（fix / gatefix / docfix / modify / adhoc）：按步骤名做最小的事。"""
        step = order["description"]
        fields: dict[str, Any] = {}
        if order["role"] == "quant-coder":
            self.touch_src(f"# {step} 第 {attempt} 次修复\n")
        if order["role"] == "quant-verifier" and step.endswith(("docfix", "gatefix")):
            fields = self._verify_fill()
        self.receipt(order, **fields)

    def extract(self, order: dict[str, Any], attempt: int) -> None:
        self.write(self.ws / "spec" / "spec.md", SPEC)
        self.write(self.ws / "spec" / "coverage_matrix.md", matrix_text(None))
        self.write(self.ws / "spec" / "ambiguities.md", self.sc.ambiguities)
        self.receipt(order)

    def plan(self, order: dict[str, Any], attempt: int) -> None:
        feas = self.sc.feasibility[min(attempt, len(self.sc.feasibility)) - 1]
        reqs = None
        if self.sc.data_requirements:
            reqs = self.sc.data_requirements[min(attempt, len(self.sc.data_requirements)) - 1]
        self.write(self.ws / "plan.md", plan_text(self.sc.difficulty, self.n_milestones(), reqs, feas, self.sc.tags))
        if not (self.ws / "assumptions.md").is_file():
            self.write(self.ws / "assumptions.md", self.sc.assumptions)
        current = (self.ws / "spec" / "coverage_matrix.md").read_text(encoding="utf-8")
        if "| pending |  |  |  | extract |" in current:
            self.write(self.ws / "spec" / "coverage_matrix.md", matrix_text(self.n_milestones()))
        self.receipt(order)

    def mock_spec(self, order: dict[str, Any], attempt: int) -> None:
        self.write(self.ws / "data_mock" / "spec.yaml", self.sc.mock_spec)
        self.receipt(order)

    def data_manifest(self, results: Path, source: str) -> None:
        """策略代码经 data_path() 取数时运行期会写的数据清单；桩替它写。"""
        entry = {"name": "toy_price.parquet", "path": str(self.root / "data" / "toy_price.parquet"), "source": source, "size": 1, "mtime": None, "fingerprint": "1-1"}
        self.write(results / "data_manifest.json", json.dumps({"report_id": self.report_id, "trial": source == "mock" and results.name == "results_mock", "files": [entry]}, ensure_ascii=False))

    def spec_internal(self, order: dict[str, Any], attempt: int) -> None:
        self.write(self.ws / "audit" / "extract_audit.md", "# 规格内审\n\n## C1 要素完整性\n\n未发现问题。\n\n结论: pass\n")
        self.receipt(order, audit={"verdict": "pass", "critical": 0, "major": 0})

    def revise_plan(self, order: dict[str, Any], attempt: int) -> None:
        path = self.ws / "assumptions.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("- 假设内容: 窗口按交易日计", "- 假设内容: 窗口按自然日计（revise）").replace("- 状态: assumed", "- 状态: revised", 1)
        text = re.sub(r"- 验证后回看: .*", "- 修订记录: revise 第 1 轮改为自然日\n- 验证后回看: [verify 后填]", text, count=1)
        self.write(path, text)
        self.receipt(order)

    def touch_src(self, extra: str = "") -> None:
        self.src.mkdir(parents=True, exist_ok=True)
        config = self.src / "config.py"
        if not config.is_file():
            config.write_text("momentum_window = 20\nreversal_window = 5\nn_groups = 5\n", encoding="utf-8")
        strategy = self.src / "strategy.py"
        base = strategy.read_text(encoding="utf-8") if strategy.is_file() else "def momentum(close, window=20):\n    return close / close.shift(window) - 1\n\n\ndef reversal(close, window=5):\n    return -(close / close.shift(window) - 1)\n"
        strategy.write_text(base + extra, encoding="utf-8")
        main = self.src / "main.py"
        if not main.is_file():
            main.write_text("def run():\n    return 0\n\n\nif __name__ == '__main__':\n    run()\n", encoding="utf-8")

    def code(self, order: dict[str, Any], attempt: int) -> None:
        self.touch_src(f"# {order['description']} 第 {attempt} 次\n" if attempt > 1 else "")
        mid = order.get("milestone")
        where = {"D1": "main.py:run", "F1": "strategy.py:momentum", "F2": "strategy.py:reversal", "B1": "main.py:run", "R1": "main.py:run", "R2": "main.py:run"}
        rows = []
        for eid in self.elements_of(mid):
            row = cg_row(self.ws, eid)
            if row.get("状态") in ("pending", "in_progress"):
                rows.append({"id": eid, "实现位置": f"src/{self.report_id}/{where[eid]}", "状态": "done"})
        fields: dict[str, Any] = {"matrix": rows} if rows else {}
        if attempt == 1 and mid in ("m1", "all") and order["description"].endswith(".code"):
            fields["assumptions"] = {"binding": [{"id": "AS1", "参数绑定": "momentum_window"}]}
        self.receipt(order, **fields)

    def milestone_verify(self, order: dict[str, Any], attempt: int) -> None:
        mid = order["milestone"]
        self.write(self.out / "verify_fragments" / f"{mid}.md", f"{mid} 的验证记录（第 {attempt} 次）：冒烟运行通过。\n")
        if attempt <= self.sc.milestone_verify_fail.get(mid, 0):
            self.receipt(order, verify={"verdict": "fail", "failures": [f"{mid} 的输出列缺失"]})
            return
        self.receipt(order, verify={"verdict": "pass", "failures": []}, matrix=[{"id": e, "验证结果": f"{mid} 级验证通过"} for e in self.elements_of(mid)])

    def impl_audit(self, order: dict[str, Any], attempt: int) -> None:
        step = order["description"]
        critical = 1 if attempt <= self.sc.audit_critical.get(step, 0) else 0
        targets = [p for p in order["outputs"] if "impl_audit_" in p]
        for rel in targets:
            self.write(self.root / rel, f"# 实现内审 {Path(rel).stem}\n\n逐条核对通过。critical {critical} 条。\n")
        self.receipt(order, audit={"verdict": "fail" if critical else "pass", "critical": critical, "major": 0, "not_found": []})

    def comparison(self, values: tuple[float, float]) -> dict[str, Any]:
        metrics = []
        for key, element, report, got in (("rank_ic_mean_mom", "R1", 0.05, values[0]), ("rank_ic_mean_rev", "R2", 0.04, values[1])):
            metrics.append(
                {
                    "key": key,
                    "name": f"{element} RankIC 均值",
                    "report_value": report,
                    "reproduced_value": got,
                    "rel_dev": abs(got - report) / report,
                    "tolerance_key": "rank_ic_mean",
                    "source_page": "p3",
                    "source_element": element,
                    "pass": abs(got - report) / report <= 0.2,
                }
            )
        return {"meta": {"report_id": self.report_id}, "metrics": metrics, "qualitative": []}

    def _verify_fill(self) -> dict[str, Any]:
        rows = [{"id": eid, "验证结果": "与研报对上"} for eid, *_ in ELEMENTS if cg_row(self.ws, eid).get("状态") not in ("skipped", "infeasible")]
        from tools import check_gates as cg

        blocks = cg.parse_id_blocks((self.ws / "assumptions.md").read_text(encoding="utf-8"))
        ids = [b.id for b in blocks if "[verify 后填]" in str(b.fields.get("验证后回看") or "")]
        fields: dict[str, Any] = {"matrix": rows}
        if ids:
            fields["assumptions"] = {"lookback": [{"id": i, "text": "复现 5.01% vs 研报 5.00%，假设获数据支持"} for i in ids]}
        return fields

    def verify(self, order: dict[str, Any], attempt: int) -> None:
        self.verify_runs += 1
        values = self.sc.verify_values[min(self.verify_runs, len(self.sc.verify_values)) - 1]
        results = self.results()
        results.mkdir(parents=True, exist_ok=True)
        trial = results.name == "results_mock"
        self.write(results / "run_log.md", f"# 运行记录\n\n- 第 {self.verify_runs} 次整批运行 exit=0\n")
        self.write(results / "metrics.json", json.dumps({"rank_ic_mean_mom": values[0], "rank_ic_mean_rev": values[1]}, indent=2))
        for name in CHARTS:
            (results / name).write_bytes(big_bytes())
        (results / "backtest_summary.xlsx").write_bytes(b"PK\x03\x04" + b"x" * 2048)
        if trial:
            self.data_manifest(results, "mock")
            self.receipt(order, verify={"verdict": "pass", "failures": []})
            self._freshen(results)
            return
        if (self.ws / "data_mock" / "manifest.json").is_file():
            self.data_manifest(results, self.sc.manifest_source)
        self.write(results / "comparison.json", json.dumps(self.comparison(values), ensure_ascii=False, indent=2))
        self.write(
            self.out / "verify_report.md",
            "# 验证报告\n\n## 指标对比\n\n<!-- flow:block comparison_table -->\n\n## 产物清单\n\n<!-- flow:block artifacts -->\n\n## 说明\n\n指标 rank_ic_mean_mom 与 rank_ic_mean_rev 的明细见上表。\n",
        )
        hard = self.sc.difficulty == "hard"
        self.write(self.ws / "audit" / "evidence_manifest.md", "# 证据清单\n\n- run_log.md：exit=0\n" + ("\n## 扰动测试\n\n窗口 20→21，指标随之变化，排除硬编码。\n" if hard else ""))
        self.receipt(order, verify={"verdict": "pass", "failures": []}, **self._verify_fill())
        self._freshen(results)

    def _freshen(self, results: Path) -> None:
        """产物时间必须晚于 src 的最新修改时间（G-VF-6）；桩在同一毫秒里写完，手工把产物时间往后拨。"""
        stamp = time.time() + 5 + self.verify_runs
        for path in results.rglob("*"):
            if path.is_file():
                os.utime(path, (stamp, stamp))

    def diagnose(self, order: dict[str, Any], attempt: int) -> None:
        n = int(re.search(r"iterate\.r(\d+)\.", order["description"]).group(1))
        conclusion = self.sc.diagnose[min(n, len(self.sc.diagnose)) - 1]
        directory = self.ws / "iterations" / f"iter_{n:02d}"
        text = f"# 第 {n} 轮诊断\n\n## 归因\n\n动量窗口口径偏了。\n\n"
        if n >= 2:
            text += "## 已排除假设\n\n- 调仓日对齐：已核对无误。\n\n"
        text += f"结论: {conclusion}\n"
        self.write(directory / "diagnosis.md", text)
        if conclusion == "stop_partial":
            self._attribute()
        self.receipt(order, diagnosis={"conclusion": conclusion})

    def _attribute(self) -> None:
        path = self.results() / "comparison.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for metric in data["metrics"]:
            if not metric.get("pass"):
                metric["attribution_status"] = "accepted"
        stamp = path.stat().st_mtime
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.utime(path, (stamp, stamp))

    def iterate_fix(self, order: dict[str, Any], attempt: int) -> None:
        n = int(re.search(r"iterate\.r(\d+)\.", order["description"]).group(1))
        self.touch_src(f"# 迭代第 {n} 轮修改\n")
        self.write(self.ws / "iterations" / f"iter_{n:02d}" / "changes.md", f"# 第 {n} 轮改动\n\n- strategy.py：窗口口径修正\n")
        self.receipt(order)

    def attribution(self, order: dict[str, Any], attempt: int) -> None:
        self._attribute()
        self.receipt(order, diagnosis={"conclusion": "stop_partial"})

    def result_internal(self, order: dict[str, Any], attempt: int) -> None:
        path = self.ws / "audit" / "evidence_manifest.md"
        text = path.read_text(encoding="utf-8") if path.is_file() else "# 证据清单\n"
        self.write(path, text.rstrip("\n") + "\n\n## 反虚报复核\n\n三方数值一致。\n")
        self.receipt(order, audit={"verdict": "pass", "critical": 0, "major": 0})

    def oos(self, order: dict[str, Any], attempt: int) -> None:
        if self.sc.oos == "skip":
            self.receipt(order, skip={"reason": "本地没有研报回测区间之后的数据"})
            return
        results = self.out / "results"
        self.write(
            results / "oos_metrics.json",
            json.dumps({"in_sample_end": "2023-06-30", "oos_start": "2023-07-03", "oos_end": "2025-06-30", "oos_days": 480, "baseline": "pass", "metrics": [{"key": "rank_ic_mean_mom", "in_sample_value": 0.05, "oos_value": 0.03, "change": -0.02}], "conclusion": "衰减"}, ensure_ascii=False),
        )
        (results / "oos_nav.png").write_bytes(big_bytes())
        (results / "oos_summary.xlsx").write_bytes(b"PK\x03\x04" + b"x" * 512)
        self.write(self.ws / "oos_report.md", "# 样本外表现\n\n样本外 480 个交易日，效应衰减。\n")
        self.receipt(order)

    def report(self, order: dict[str, Any], attempt: int) -> None:
        state = self.state()
        sections = list(REPORT_SECTIONS)
        if state["stages"]["oos"]["status"] == "done":
            sections.append("样本外表现")
        if state.get("reproduction_mode") == "experimental":
            sections.append("市场迁移声明")
        rejected = []
        responses = self.ws / "audit" / "audit_responses.md"
        if responses.is_file():
            rejected = re.findall(r"^\|\s*(CDX-[A-Z]-\d+)\s*\|[^\n]*\|\s*rejected\s*\|", responses.read_text(encoding="utf-8"), re.MULTILINE)
        lines = ["# 玩具动量策略 复现报告", ""]
        for name in sections:
            lines += [f"## {name}", ""]
            if name == "指标对比":
                lines += ["<!-- flow:block comparison_table -->", ""]
            elif name == "假设登记簿":
                lines += ["<!-- flow:block assumptions_register -->", ""]
            elif name == "未复现清单" and rejected:
                lines += [f"遗留的 rejected 意见：{'、'.join(rejected)}", ""]
            else:
                lines += [f"{name}见各节素材。", ""]
        self.write(self.ws / "final_report.md", "\n".join(lines))
        self.receipt(order)

    def fallback(self, order: dict[str, Any], attempt: int) -> None:
        target = self.root / order["outputs"][0]
        self.write(target, json.dumps({"verdict": "approve", "findings": []}, ensure_ascii=False))

    # ---- 判断工单 ----
    def judge(self, order: dict[str, Any]) -> None:
        self.calls.append(order["step_id"])
        task = (self.root / order["prompt_file"]).read_text(encoding="utf-8")
        stage, rnd = re.fullmatch(r"(\w+)\.rule\.r(\d+)", order["description"]).groups()
        data = read_json(self.ws / "flow" / "answers" / f"{stage}.findings.r{rnd}.json") or {}
        owners = {"spec_audit": "quant-planner", "code_audit": "quant-coder", "result_audit": "quant-verifier"}
        findings = {}
        for fid in data.get("unruled") or []:
            assert fid in task, f"判断工单里没有列出 {fid}"
            findings[fid] = {"处置": "accepted", "回应": "接受并修复", "owner": owners[stage], **self.sc.rulings.get(fid, {})}
        diffs = {did: {"裁决": "dismissed", "依据": "核对原文后 spec 无误", "owner": "none", **self.sc.rulings.get(did, {})} for did in data.get("unruled_diffs") or []}
        self.write(self.root / order["answer_file"], json.dumps({"findings": findings, "diffs": diffs}, ensure_ascii=False, indent=2))


def cg_row(ws: Path, element_id: str) -> dict[str, str]:
    from tools import check_gates as cg

    for row in cg.load_matrix_rows(ws / "spec" / "coverage_matrix.md"):
        if cg._row_get(row, "要素ID") == element_id:
            return {"状态": cg._row_get(row, "状态"), "实现位置": cg._row_get(row, "实现位置"), "验证结果": cg._row_get(row, "验证结果")}
    return {}


# ---------------------------------------------------------------------------
# 工作区、建案、驱动
# ---------------------------------------------------------------------------


def make_root(tmp_path: Path, config: Optional[dict[str, Any]] = None) -> Path:
    root = tmp_path / "wsroot"
    root.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "templates", root / "templates")
    (root / "reports").mkdir()
    (root / "data").mkdir()
    cfg = {"data_root": str(root / "data"), "audit_level": "standard", "default_mode": "auto", **(config or {})}
    (root / ".reproduce.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return root


def fake_extract(pdf_path: Path, out_dir: Path) -> pdf_extract.ExtractResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(f"===== PAGE {n} =====\n第 {n} 页的正文。RankIC 均值 5.00%。\n\n" for n in (1, 2, 3))
    (out_dir / "report_text.md").write_text(text, encoding="utf-8")
    (out_dir / "tables_extracted.md").write_text("# 表格\n\n（无）\n", encoding="utf-8")
    return pdf_extract.ExtractResult(n_pages=3, engine="fake", table_count=0, report_text_path=out_dir / "report_text.md", tables_path=out_dir / "tables_extracted.md")


def new_case(root: Path, monkeypatch: Any, slug: str = "toy", **kwargs: Any) -> str:
    monkeypatch.setattr(pdf_extract, "run_extract", fake_extract)
    monkeypatch.setenv("REPRODUCE_NO_USAGE", "1")
    monkeypatch.setenv("REPRODUCE_NO_TTY", "1")
    pdf = root / "reports" / f"{slug}.pdf"
    pdf.write_bytes(b"%PDF-1.4 toy " + slug.encode())
    summary = decisions.init_case(root, str(pdf), slug=slug, host="claude_code", **kwargs)
    assert summary["gate"] == "PASS", summary
    return summary["report_id"]


def drive(root: Path, report_id: str, stub: Stub, max_rounds: int = 300, until: Optional[Callable[[dict[str, Any]], bool]] = None) -> dict[str, Any]:
    """像主会话那样推进：取工单 → 交给桩 agent → 点收，直到停下。返回最后一次 next 的结果。"""
    engine = Engine(root, report_id, host="claude_code")
    out: dict[str, Any] = {}
    for _ in range(max_rounds):
        engine.notes = []
        out = engine.advance()
        if until and until(out):
            return out
        if out.get("halt"):
            return out
        orders = out.get("orders") or []
        assert orders or out.get("wait"), f"既没有工单也没有停机说明：{out}"
        for order in orders:
            step = order["step_id"]
            if order["kind"] == "legacy_card":
                return out
            if order["kind"] == "exec":
                engine.exec_step(step, detach=False)
            elif order["kind"] == "judge":
                stub.judge(order)
                results = engine.done([step], collect_usage=False)
                assert results[0]["ok"], results
            else:
                reply = stub.run(order)
                if reply.startswith("BLOCKED") and not order.get("receipt"):
                    engine.fail(step, "blocked", reply)  # 没有回执的步骤，受阻由主会话转告内核
                else:
                    engine.done([step], collect_usage=False)
    raise AssertionError(f"推进了 {max_rounds} 轮还没有停下：{out}")


def write_price(root: Path, columns: tuple[str, ...] = ("stock_code", "date", "close"), name: str = "toy_price.parquet") -> Path:
    """往数据根里放一份「真实」行情：20 只股票、2020 年全年工作日。"""
    import numpy as np
    import pandas as pd

    dates = pd.bdate_range("2020-01-01", "2020-12-31")
    codes = [f"{i:06d}" for i in range(1, 21)]
    frame = pd.DataFrame({"stock_code": np.repeat(codes, len(dates)), "date": np.tile(dates, len(codes))})
    rng = np.random.default_rng(3)
    for column in columns:
        if column not in frame:
            frame[column] = rng.uniform(5, 80, len(frame)).round(2)
    path = root / "data" / name
    frame[list(columns)].to_parquet(path, index=False)
    return path


def decide(root: Path, report_id: str, key: str, choice: str, quote: str = "同意，继续", **kwargs: Any) -> dict[str, Any]:
    return decisions.decide(Engine(root, report_id, host="claude_code"), key, choice, quote, **kwargs)


def pending(root: Path, report_id: str) -> list[dict[str, Any]]:
    return st.pending_checkpoints(st.load_state(root, report_id))


def events(root: Path, report_id: str) -> list[str]:
    return [r["event"] for r in st.read_event_records(root, report_id)]


# ---------------------------------------------------------------------------
# 假的外审引擎
# ---------------------------------------------------------------------------


def install_fake_review(monkeypatch: Any, stub: Stub) -> None:
    """把外审 CLI 换成按剧本写结果的假函数。调用次数、推理强度等记在 stub.review_log 里。"""
    stub.review_log = []  # type: ignore[attr-defined]

    def fake_run_review(engine: str, prompt_path: Path, output_path: Path, cwd: Path, timeout: int, **kwargs: Any) -> er.ReviewResult:
        jdir = Path(output_path).parent
        job = read_json(jdir / "job.json") or {}
        kind, rnd = job.get("kind"), int(job.get("round") or 1)
        call = Path(prompt_path).name.replace(".request_", "").replace(".md", "")
        n = stub.review_calls[kind] = stub.review_calls.get(kind, 0) + 1
        stub.review_log.append({"kind": kind, "round": rnd, "call": call, "effort": kwargs.get("effort"), "engine": engine, "mode": job.get("mode")})  # type: ignore[attr-defined]
        failures = stub.sc.review_fail.get(kind) or []
        if n <= len(failures):
            return er.ReviewResult(engine, failures[n - 1], f"剧本：第 {n} 次调用{failures[n - 1]}", None, None, 0.1, None)
        text = review_output(stub, kind, rnd, call)
        Path(output_path).write_text(text, encoding="utf-8")
        return er.ReviewResult(engine, "success", "", 0, str(output_path), 0.1, None)

    monkeypatch.setattr(er, "run_review", fake_run_review)


def review_output(stub: Stub, kind: str, rnd: int, call: str) -> str:
    rounds = stub.sc.reviews.get(kind) or [[]]
    findings = rounds[min(rnd, len(rounds)) - 1]
    letter = {"spec": "S", "code": "C", "result": "R"}.get(kind, "X")
    items = []
    for index, finding in enumerate(findings, 1):
        items.append(
            {
                "id": finding.get("id") or f"CDX-{letter}-{index:02d}",
                "severity": finding.get("severity", "minor"),
                "category": finding.get("category", "一致性"),
                "location": finding.get("location", "spec.md:1"),
                "description": finding.get("description", f"第 {index} 条意见"),
                "suggestion": finding.get("suggestion", "修正"),
            }
        )
    verdict = "request_changes" if any(i["severity"] == "critical" for i in items) else "approve"
    body = json.dumps({"verdict": verdict, "findings": items}, ensure_ascii=False, indent=2)
    if kind == "second_opinion":
        return "# 第二意见\n\n独立看法：窗口口径值得再查。\n"
    if kind == "spec" and "blind" in call:
        return "## 盲提取\n\n### [F1] 动量因子\n- 页码: p2\n- 原文: > \"过去 20 日收益率\"\n\n### [R1] RankIC\n- 页码: p3\n- 原文: > \"RankIC 均值 5.00%\"\n"
    return body + "\n"
