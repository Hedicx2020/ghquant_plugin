"""tools/flowlib/reviewpacks.py：检查点审阅包。

每种审阅包渲染一遍，核对关键小节、放行命令、字节上限、截断提示，以及文书缺失时不抛异常。
最后在仓库里的真实案例上各渲染一遍（只读）。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import state as st  # noqa: E402
from tools.flowlib import reviewpacks as rp  # noqa: E402

CASE = "r001_demo"
WS = f"workspace/{CASE}"
OUT = f"output/{CASE}"
ALL_NAMES = [
    "spec_final",
    "plan_final",
    "milestone_done",
    "verify_done",
    "iterate_round",
    "pre_report",
    "final_review",
    "data_gap",
    "trial_done",
    "circuit_breaker",
    "stall",  # 没有专用模板的名称走通用模板
]
GAP_REPORT = "| 数据需求 | 结论 | 实测 |\n| --- | --- | --- |\n| 一致预期 | 缺失 | 本地没有这张表 |"
PAYLOADS = {
    "milestone_done": {"milestone": "m1"},
    "iterate_round": {"round": 3},
    "data_gap": {"gaps": ["一致预期"], "gap_report": GAP_REPORT},
    "circuit_breaker": {"keys": ["verify:G-VF-4"], "streak": {"verify:G-VF-4": 3}},
    "stall": {"idle_hours": 30.5, "steps": ["implement.m2.code"], "threshold": 24},
}

SPEC = """---
title: 测试研报
institution: 测试证券
pdf_pages: 20
element_counts: {D: 2, F: 2, B: 1, R: 2, SA: 1}
---
# 测试研报 复现规格书

## 二、数据要求（D 类）

### [D1] 日行情
- 页码: p3
- 原文: > "日度收盘价"
- 数据状态: available
- 说明: 本地有全量日行情

### [D2] 一致预期
- 页码: p4
- 原文: > "分析师一致预期净利润"
- 数据状态: missing
- 说明: 本地没有分析师预期数据

## 三、因子定义（F 类）

### [F1] 动量因子
- 页码: p5
- 原文: > "F1 原文"
- 公式（转写）: mom = close / close.shift(20) - 1
- 依赖数据: D1

### [F2] 预期修正因子
- 页码: p6
- 原文: > "F2 原文"
- 说明（转写）: 预期净利润环比上调即为 1
- 依赖数据: D2

## 四、回测设置（B 类）

### [B1] 月度调仓
- 页码: p7
- 原文: > "B1 原文"
- 参数值: 月频 | 月末最后一个交易日
- 关联要素: F1

## 五、研报核心数值结果基准（R 类）

### [R1] 动量多空收益表
- 页码: p8
- 原文: > "R1 原文"
- 关联要素: F1, B1

### [R2] 预期修正多空收益表
- 页码: p9
- 原文: > "R2 原文"
- 关联要素: F2

## 七、敏感性分析（SA 类）

### [SA1] 窗口敏感性
- 页码: p10
- 原文: > "SA1 原文"
- 关联要素: F1
"""

AMBIGUITIES = """# 歧义清单

### [A1] 调仓日未说明
- 页码: p7
- 关联要素: B1
- 等级: blocking
- 候选解释: 解释1 月末；解释2 月初
- 裁决方式: 人工
- 状态: open

### [A2] 费率未披露
- 页码: p8
- 关联要素: R1
- 等级: major
- 候选解释: 解释1 零费率；解释2 双边千三
- 裁决方式: auto
- 裁决结果: 采解释1，零费率；登记 AS1
- 状态: resolved

### [A3] 图例颜色
- 页码: p9
- 等级: minor
- 候选解释: 无关紧要
- 状态: resolved
"""

ASSUMPTIONS = """# 假设登记簿

### [AS1] 零费率回测
- 来源: A2（auto 裁决）
- 假设内容: 回测不计交易费用
- 影响面: trading
- 影响 milestone: m1
- 影响指标: R1
- 预期影响: 年化被高估
- 验证后回看: 实测方向与预期相反，零费口径下复现年化仍低于研报
- 状态: assumed
- 高亮等级: major-auto
- 参数绑定: cost_bps

### [AS2] 窗口映射
- 来源: coder 主动简化
- 假设内容: 一个月按 20 个交易日
- 影响面: method
- 影响 milestone: m1
- 影响指标: R1
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS3] 预期数据代理
- 来源: 数据限制
- 假设内容: 用财报实际值代理一致预期
- 影响面: data
- 影响 milestone: m2
- 影响指标: R2
- 验证后回看: 与研报方向一致，支持该口径
- 状态: confirmed
- 高亮等级: major-auto
"""

MATRIX = f"""# 覆盖矩阵

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
|---|---|---|---|---|---|---|---|---|---|---|
| D1 | D | 日行情 | p3 | core | m1 | done | | src/{CASE}/data.py:load_price | ok | verify |
| D2 | D | 一致预期 | p4 | core | m2 | infeasible | data_missing：本地没有 | | | plan |
| F1 | F | 动量 | p5 | core | m1 | done | | src/{CASE}/strategy.py:momentum；src/{CASE}/strategy.py:signal | ok | verify |
| F2 | F | 预期修正 | p6 | core | m2 | skipped | 依赖 D2 | | | plan |
| B1 | B | 调仓 | p7 | core | m1 | done | | common/timing_backtest.py:run | ok | verify |
| R1 | R | 动量收益表 | p8 | core | m1 | done | | src/{CASE}/main.py:run | 年化对上 | verify |
| R2 | R | 预期修正收益表 | p9 | support | m2 | pending | | | | plan |
| SA1 | SA | 窗口 | p10 | optional | m2 | in_progress | | | | plan |

## 变更日志

| 时间 | 事件 | 来源 | 说明 |
|---|---|---|---|
| t | e | s | 不是要素行 |
"""

PLAN = """---
report_name: 测试研报
type: timing
difficulty: medium
feasibility: degraded
data_requirements:
  - {name: 日行情, source: ashare_price, status: available}
  - {name: 一致预期, source: 无, status: missing}
milestones:
  - id: m1
    name: 数据与动量
    deps: []
    elements: [D1, F1, B1, R1]
  - id: m2
    name: 预期修正
    deps: [m1]
    elements: [D2, F2, R2, SA1]
---
# 复现开发计划

## 分诊结论

- 基准档：medium，规则型信号
- 数据可得性：D2 缺失，可行性降为 degraded

## 二、milestone

### m1: 数据与动量

做数据与动量。
"""

RESPONSES = """# 审计回应

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应 | 复核 |
|---|---|---|---|---|---|
| CDX-S-01 | major | F1 窗口口径没写清 | accepted | 已补 | pass |
| CDX-S-02 | critical | D2 缺失未标 | accepted | 已标 | |
| CDX-C-01 | major | 静态池用了未来数据 | rejected | 不成立 | pass |
| EXT-01 | minor | 不带外审编号的行 | accepted | | |
"""

IMPL_AUDIT = f"""# m1 内审

### IM1-01 [major] 动量窗口含当日

- **CA-C01** / severity: minor / 证据定位: src/{CASE}/strategy.py:12 / 依据: 窗口长度写成了魔法数字

verdict: pass_with_issues
"""

EVIDENCE = """# 证据链

| 证据ID | 内容 | 结果 |
|---|---|---|
| EVD-01 | 重跑 main.py | pass |
| EVD-02 | 逐项对数 | pass（含 1 点分歧） |

## 扰动测试记录

- 结论：已执行，回测截止日提前一年，
  12 项指标全部变化，没有硬编码
"""

FINAL_REPORT = """# 最终复现报告

## 一、结论

**可信度评级：B（core 覆盖不全、存在 major-auto 假设）**

正文。
"""

DIAGNOSIS = {
    1: "# iter_01 诊断\n\n## 已排除假设\n\n1. **AS2 窗口映射**（实验证伪）：换 21 日没有改善\n2. **费率口径**：千三之后偏差更大\n\n结论: continue\n",
    2: "# iter_02 诊断\n\n## 零、已确认读过的已排除假设清单\n\n1. **只是回顾不该重复列出**：见上一轮\n\n## 五、已排除假设\n\n### 本轮新排除\n\n1. **AS2 窗口映射**（iter_01 已证伪）：不再试\n2. **调仓日口径**：月初月末差别不到 0.1pct\n\n结论: continue\n",
    3: "# iter_03 诊断\n\n没有新的排除项。\n\n结论: **continue**\n",
}
CHANGES = f"""# iter_03 改动清单

## 一、改动文件清单

| 文件 | 位置 | 改动内容 |
| --- | --- | --- |
| `src/{CASE}/config.py` | L10 | 窗口 20 → 21 |
"""


def _comparison(annual: float, sharpe: float) -> dict:
    """三条数值指标（年化、夏普、回撤）加两条定性；文件里自报全过，实际要靠重算。"""
    return {
        "metrics": [
            {"key": "r1_annual_return", "report_value": 0.10, "reproduced_value": annual, "tolerance_key": "annual_return", "source_element": "R1", "pass": True, "attribution_status": "assumption_linked"},
            {"key": "r1_sharpe", "report_value": 1.0, "reproduced_value": sharpe, "tolerance_key": "sharpe", "source_element": "R1", "pass": True},
            {"key": "r1_max_drawdown", "report_value": -0.20, "reproduced_value": -0.201, "tolerance_key": "max_drawdown", "source_element": "R1", "pass": True},
        ],
        "qualitative": [
            {"key": "q_direction", "expect": "up", "observed": "up", "pass": True},
            {"key": "q_rank", "expect": "top", "observed": "bottom", "pass": True},
        ],
        "pass_count": 5,
        "total": 5,
    }


def _put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _checkpoint(name: str, payload: object = None, **extra: object) -> dict:
    cp = {
        "id": "cp_03",
        "name": name,
        "kind": "human",
        "stage": "plan",
        "status": "pending",
        "opened_at": "2026-11-22T02:07:00+08:00",
        "reason": "测试用的原因",
        "options": [],
        "pack": None,
        "payload": PAYLOADS.get(name) if payload is None else payload,
        "code": "K7QM",
        "prev_status": "running",
        "decision": None,
    }
    cp.update(extra)
    return cp


def _render(root: Path, state: dict, name: str, payload: object = None, **extra: object) -> str:
    return rp.render(root, CASE, name, state=state, checkpoint=_checkpoint(name, payload, **extra))


def _section(text: str, title: str) -> str:
    """取出某个二级小节的正文。"""
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
    assert m, f"没有小节「{title}」"
    return m.group(1)


def _snapshot(base: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(base)): (p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(base.rglob("*"))}


_OPEN_FOR_WRITE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_CHANGE_EVENTS = ("os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.truncate", "os.utime", "os.chmod", "os.link", "os.symlink", "shutil.rmtree", "tempfile.mkstemp", "tempfile.mkdtemp")
_WATCHED: list[tuple[tuple[str, ...], list[str]]] = []
_AUDIT = {"installed": False}


def _audit(event: str, args: tuple) -> None:
    """记下本进程对被盯目录的每一次改动（打开来写、建目录、改名、删除等）。没有人在盯时什么都不做。"""
    if not _WATCHED:
        return
    if event == "open":
        mode, flags = (tuple(args) + (None, None, None))[1:3]
        writing = (isinstance(mode, str) and bool(set(mode) & set("wax+"))) or (isinstance(flags, int) and bool(flags & _OPEN_FOR_WRITE))
        targets = tuple(args)[:1] if writing else ()
    elif event in _CHANGE_EVENTS:
        targets = tuple(args)[:2]
    else:
        return
    for target in targets:
        try:
            path = os.path.abspath(os.fsdecode(target))
        except (TypeError, ValueError):  # 文件描述符、权限位这类不是路径的参数
            continue
        for bases, hits in _WATCHED:
            if any(path == base or path.startswith(base + os.sep) for base in bases):
                hits.append(f"{event} {path}")


@contextmanager
def _changes_under(*dirs: Path) -> Iterator[list[str]]:
    """盯住本进程对这些目录的改动，退出后列表里就是全部命中。

    只管本进程：别的进程（比如正在跑案例的内核）动了什么不算，所以比对目录快照查不准的时候用它。
    审计钩子装上就卸不掉，故只装一次，没有人在盯时它直接返回。
    """
    if not _AUDIT["installed"]:
        sys.addaudithook(_audit)
        _AUDIT["installed"] = True
    bases = tuple(sorted({form(str(d)) for d in dirs for form in (os.path.abspath, os.path.realpath)}))
    entry: tuple[tuple[str, ...], list[str]] = (bases, [])
    _WATCHED.append(entry)
    try:
        yield entry[1]
    finally:
        _WATCHED[:] = [item for item in _WATCHED if item is not entry]


@contextmanager
def _deadline(seconds: float) -> Iterator[None]:
    """超过时限就让测试失败，而不是一直挂着（靠 SIGALRM；没有这个信号的平台不设时限）。"""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _expired(_signum: int, _frame: object) -> None:
        raise AssertionError(f"超过 {seconds:g} 秒还没渲染完")

    previous = signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture(autouse=True)
def builtin_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认不看内核的检查点表，用模块自带的那份，免得内核改措辞时这里跟着变；内核表另有专门的测试。"""
    monkeypatch.setattr(rp, "_kernel", lambda: None)


@pytest.fixture()
def empty(tmp_path: Path) -> tuple[Path, dict]:
    """只有 state.json、没有任何文书的案例。"""
    st.init_state(tmp_path, CASE, f"reports/{CASE}.pdf", schema_version=2)
    return tmp_path, st.load_state(tmp_path, CASE)


@pytest.fixture()
def case(tmp_path: Path) -> tuple[Path, dict]:
    """文书、审计、迭代、结果都齐的最小案例。"""
    root = tmp_path
    st.init_state(root, CASE, f"reports/{CASE}.pdf", schema_version=2)
    (root / "templates").mkdir()
    shutil.copy(REPO_ROOT / "templates" / "standards.json", root / "templates" / "standards.json")
    for rel, text in {
        f"{WS}/spec/spec.md": SPEC,
        f"{WS}/spec/ambiguities.md": AMBIGUITIES,
        f"{WS}/spec/coverage_matrix.md": MATRIX,
        f"{WS}/assumptions.md": ASSUMPTIONS,
        f"{WS}/plan.md": PLAN,
        f"{WS}/audit/audit_responses.md": RESPONSES,
        f"{WS}/audit/impl_audit_m1.md": IMPL_AUDIT,
        f"{WS}/audit/evidence_manifest.md": EVIDENCE,
        f"{WS}/final_report.md": FINAL_REPORT,
        f"{WS}/iterations/iter_03/changes.md": CHANGES,
        f"src/{CASE}/strategy.py": "WINDOW = 20\n",
        f"{OUT}/results/run_log.md": "python main.py\nexit=0\n",
        f"{OUT}/results/net_value.png": "png",
        f"{OUT}/verify_report.md": "# verify\n",
    }.items():
        _put(root, rel, text)
    rounds = {1: _comparison(0.080, 0.5), 2: _comparison(0.081, 0.8), 3: _comparison(0.082, 0.9)}
    for n, comparison in rounds.items():
        _put(root, f"{WS}/iterations/iter_{n:02d}/comparison.json", json.dumps(comparison, ensure_ascii=False))
        _put(root, f"{WS}/iterations/iter_{n:02d}/diagnosis.md", DIAGNOSIS[n])
    _put(root, f"{OUT}/results/comparison.json", json.dumps(rounds[3], ensure_ascii=False))
    state = st.load_state(root, CASE)
    state.update(
        {
            "type": "timing",
            "difficulty": "medium",
            "current_stage": "verify",
            "verdict": {"result": "partial", "comparison_file": None, "metrics_pass": 5, "metrics_total": 5, "decided_at": None},
            "iteration": {"current": 3, "max": 5, "history": []},
            "external_reviews": [
                {"checkpoint": "spec", "engine": "claude_fallback", "verdict": "fail", "critical": 1, "major": 0, "minor": 0, "note": "第一轮"},
                {"checkpoint": "spec", "engine": "codex", "verdict": "pass_with_issues", "critical": 0, "major": 1, "minor": 0, "note": "复审"},
                {"checkpoint": "code", "engine": "same_host_fallback", "verdict": "pass", "critical": 0, "major": 0, "minor": 1, "note": "外审超时"},
            ],
            "gate_latest": {
                "verify": {"verdict": "FAIL", "timestamp": "2026-11-22T01:00:00+08:00", "failed": [{"id": "G-VF-4", "desc": "必需图表存在", "detail": "缺 drawdown.png"}]}
            },
        }
    )
    return root, state


# ---------------------------------------------------------------------------
# 接口与固定结构
# ---------------------------------------------------------------------------


def test_limits_and_pack_path() -> None:
    kb = 1024
    assert rp.PACK_LIMITS == {"spec_final": 8 * kb, "plan_final": 10 * kb, "milestone_done": 5 * kb, "verify_done": 8 * kb, "iterate_round": 5 * kb, "pre_report": 6 * kb}
    assert rp.limit_for("stall") == rp.limit_for("data_gap") == 6 * kb  # 表里没有的走默认
    assert rp.pack_path(CASE, "cp_03", "data_gap") == f"{WS}/reviews/cp_03_data_gap.md"
    assert rp.pack_path(CASE, "cp_12", "../x y") == f"{WS}/reviews/cp_12_x_y.md"  # 名称里的怪字符不会变成路径


@pytest.mark.parametrize("name", ALL_NAMES)
def test_every_pack_has_the_fixed_structure(case: tuple[Path, dict], name: str) -> None:
    root, state = case
    text = _render(root, state, name)
    assert len(text.encode("utf-8")) <= rp.limit_for(name)
    assert "专用模板渲染失败" not in text
    first = text.splitlines()[0]
    assert first.startswith(f"# {rp.checkpoint_title(name, _checkpoint(name))} · {CASE}") and first.endswith("（cp_03）")
    order = [text.index(piece) for piece in ("## 为什么停在这里", "测试用的原因", "## 你可以怎么决定", rp.FOOTER)]
    assert order == sorted(order) and text.rstrip().endswith(rp.FOOTER)
    # 逐个选项一行，各带可以直接复制的命令；短码写明
    tail = _section(text, "你可以怎么决定")
    for option in rp.checkpoint_options(name):
        assert f"- `{option['key']}` {option['label']}" in tail
        assert f"`{rp.option_command(CASE, name, 'cp_03', option['key'])}`" in tail
    assert "放行短码 `K7QM`" in tail and "自述" in tail
    if name == "final_review":  # 三种决定各有自己的命令，都带原话；终止走 flow decide
        assert f'`flow accept {CASE} --quote "<你的原话>"`' in tail
        assert f'`flow revise {CASE} --assumption <假设编号> --new-text "<新口径>" --quote "<你的原话>"`' in tail
        assert f'`flow reopen {CASE} --from <阶段或 milestone> --reason "<原因>" --quote "<你的原话>"`' in tail
        assert f'`flow decide {CASE} cp_03 --choice abort --quote "<你的原话>"`' in tail and tail.count("flow decide") == 1
    else:
        assert f'flow decide {CASE} cp_03 --choice {rp.checkpoint_options(name)[0]["key"]} --quote "<你的原话>"' in tail
    if any(o["key"] == "rollback" for o in rp.checkpoint_options(name)):  # 回退要指明从哪里重做，内核才收
        assert f'`flow decide {CASE} cp_03 --choice rollback --to <阶段或 milestone> --quote "<你的原话>"`' in tail


@pytest.mark.parametrize("name", ALL_NAMES)
def test_missing_documents_never_raise(empty: tuple[Path, dict], name: str) -> None:
    root, state = empty
    before = _snapshot(root)
    text = _render(root, state, name, {} if name == "data_gap" else None, reason="")  # 缺口清单也不给
    assert len(text.encode("utf-8")) <= rp.limit_for(name) and "专用模板渲染失败" not in text
    assert "## 为什么停在这里" in text and "## 你可以怎么决定" in text and "flow " in text
    if name != "stall":
        assert rp.EMPTY in text  # 没有文书的小节写「（尚无）」
    assert _snapshot(root) == before  # 渲染不写任何东西
    # 状态是空字典、检查点也不给，照样出得来
    bare = rp.render(root, CASE, name, state={})
    assert f"--choice {rp.checkpoint_options(name)[0]['key']}" in bare or "flow accept" in bare
    assert rp.CP_PLACEHOLDER in bare or name == "final_review"


def test_unreadable_documents_fall_back_quietly(case: tuple[Path, dict]) -> None:
    root, state = case
    (root / WS / "spec" / "spec.md").write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    (root / OUT / "results" / "comparison.json").write_text("{不是 json", encoding="utf-8")
    for name in ("spec_final", "verify_done", "pre_report", "final_review"):
        text = _render(root, state, name)
        assert "## 你可以怎么决定" in text and len(text.encode("utf-8")) <= rp.limit_for(name)
        assert "专用模板渲染失败" not in text
    # 读不出来不是「没有」：文末写明读取失败，免得人把一排「（尚无）」当成真的没有文书
    spec = _render(root, state, "spec_final")
    assert "案例文书读取失败（UnicodeDecodeError" in _section(spec, "读取说明") and rp.EMPTY in _section(spec, "要素计数")
    assert spec.index("## 读取说明") < spec.index("## 你可以怎么决定")
    tally = _section(_render(root, state, "verify_done"), "重算达标数")
    assert f"`{OUT}/results/comparison.json` 在，但读不出来或重算不了" in tally and "数值 " not in tally
    assert "读取说明" not in _render(root, state, "circuit_breaker")  # 没读文书的包不提


def test_pathological_lines_do_not_stall_the_render(case: tuple[Path, dict]) -> None:
    """文书里有上万个连续空白或符号的行，渲染照样一下子出来：渲染在内核事务里做，不能被一行怪文书拖住。"""
    root, state = case
    n = 20000
    blank = " " * n
    odd = "\n".join([blank, "- " + blank + "x", "*" * n, "- " + "*" * n + blank, blank + "结论", "- **结论**" + blank + "x"]) + "\n"
    assert "## 扰动测试记录\n\n- 结论" in EVIDENCE  # 怪行插在结论行前面，逐行找结论时才会先扫到它们
    _put(root, f"{WS}/audit/evidence_manifest.md", EVIDENCE.replace("## 扰动测试记录\n\n", "## 扰动测试记录\n\n" + odd))
    _put(root, f"{WS}/audit/impl_audit_m1.md", IMPL_AUDIT + "\n".join(["- **CA-C09** / severity: minor / " + blank + "空白后面的描述", "- **CA-C10** minor" + " /" * n, "| CA-A11 | major | " + " | " * n, "verdict" + blank, "-" * n, ">" * n + "verdict", "判定:" + blank + "not"]) + "\n")
    _put(root, f"{WS}/iterations/iter_03/diagnosis.md", "结论:" + blank + "x\n结论:" + "*" * n + "x\n" + DIAGNOSIS[3])
    _put(root, f"{WS}/spec/coverage_matrix.md", MATRIX.replace(f"src/{CASE}/data.py:load_price", "src/" * 5000 + f" src/{CASE}/data.py:load_price"))
    with _deadline(30):  # 正常是几十毫秒；正则里相邻量词一重叠就是立方级，两万个空格要跑上几个小时
        texts = {name: _render(root, state, name) for name in ALL_NAMES}
    assert all("专用模板渲染失败" not in text and len(text.encode("utf-8")) <= rp.limit_for(name) for name, text in texts.items())
    audit = _section(texts["milestone_done"], "内审结论")
    assert "- 问题 5 条：major 2 · minor 3" in audit and "- CA-C09（minor）空白后面的描述" in audit
    assert f"- `src/{CASE}/data.py`（文件不存在）：D1" in _section(texts["milestone_done"], "实现文件")
    assert "- 扰动测试记录：结论：已执行，回测截止日提前一年，12 项指标全部变化，没有硬编码" in _section(texts["verify_done"], "扰动结果")
    assert "- 第 3 轮诊断结论：continue" in _section(texts["iterate_round"], "本轮修改点")


# ---------------------------------------------------------------------------
# 各检查点的主体
# ---------------------------------------------------------------------------


def test_spec_final(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "spec_final")
    counts = _section(text, "要素计数")
    assert "测试研报，测试证券，20 页" in counts and "D 2 · F 2 · B 1 · R 2 · SA 1，共 8 条" in counts and "element_counts 一致" in counts
    formulas = _section(text, "F 类公式（首行）")
    assert "- F1 动量因子（p5）：mom = close / close.shift(20) - 1" in formulas
    assert "- F2 预期修正因子（p6）：预期净利润环比上调即为 1" in formulas  # 没有「公式」字段时取转写说明
    assert "| B1 | 月度调仓 | 月频 \\| 月末最后一个交易日 | p7 |" in _section(text, "B 类参数表")  # 单元格里的竖线要转义
    results = _section(text, "R 表清单")
    assert "- R1 动量多空收益表（p8）" in results and "- R2 预期修正多空收益表（p9）" in results
    blocking = _section(text, "blocking 歧义")
    assert "歧义共 3 条：blocking 1 · major 1 · minor 1；尚未裁决（状态不是 resolved）1 条" in blocking
    assert "- A1 调仓日未说明（p7；关联 B1；状态 open）：候选：解释1 月末；解释2 月初" in blocking
    major = _section(text, "major 歧义")
    assert "- A2 费率未披露（p8；关联 R1；状态 resolved）：裁决：采解释1，零费率；登记 AS1" in major and "A3" not in major
    missing = _section(text, "缺失数据")
    assert "数据要求 2 条：available 1 · missing 1" in missing
    assert "- D2 一致预期（p4）：本地没有分析师预期数据" in missing and "D1" not in missing

    # 自报的要素数与实数对不上时要说出来
    _put(root, f"{WS}/spec/spec.md", SPEC.replace("element_counts: {D: 2, F: 2,", "element_counts: {D: 2, F: 5,"))
    assert "不一致：F 自报 5、实数 2" in _section(_render(root, state, "spec_final"), "要素计数")


def test_plan_final(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "plan_final")
    triage = _section(text, "分诊依据")
    assert "类型 timing · 难度 medium · 可行性 degraded" in triage and "数据需求 2 条：available 1 · missing 1" in triage
    assert "- 基准档：medium，规则型信号" in triage and "- 数据可得性：D2 缺失，可行性降为 degraded" in triage
    table = _section(text, "milestone 表")
    assert "| m1 | 数据与动量 | - | 4 个：D1 F1 B1 R1 |" in table and "| m2 | 预期修正 | m1 | 4 个：D2 F2 R2 SA1 |" in table
    highlighted = _section(text, "major-auto 假设（逐条）")
    assert "假设共 3 条，其中 major-auto 2 条" in highlighted
    assert "- AS1 零费率回测（来源 A2（auto 裁决）；影响 m1；参数 cost_bps）：回测不计交易费用" in highlighted
    assert "- AS3 预期数据代理（来源 数据限制；影响 m2）：用财报实际值代理一致预期" in highlighted and "AS2" not in highlighted
    skipped = _section(text, "core 级被跳过的要素")
    assert "core 要素 6 个，其中被跳过或判不可行 2 个" in skipped
    assert "- D2 一致预期（p4；infeasible）：data_missing：本地没有" in skipped and "- F2 预期修正（p6；skipped）：依赖 D2" in skipped
    review = _section(text, "spec 外审结论")
    assert "引擎 codex（未降级） · 结论 pass_with_issues · critical 0 / major 1 / minor 0 · 复审" in review  # 取最新一条
    assert "CDX-S 意见 2 条：处置 accepted 2；复核 pass 1 条；critical 未闭环 1 条（CDX-S-02）" in review
    excel = _section(text, "Excel 批量回改入口")
    assert f"tools/assumptions_xlsx.py export {CASE}" in excel and f"{WS}/assumptions.xlsx" in excel and "config.py` 还没有生成" in excel


def test_milestone_done(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "milestone_done")
    assert text.splitlines()[0].startswith(f"# {rp.checkpoint_title('milestone_done')}（m1） · {CASE}")
    delivered = _section(text, "交付要素")
    assert "m1 共 4 个要素：done 4" in delivered and "- F1 动量 · core · done" in delivered and "D2" not in delivered
    files = _section(text, "实现文件")
    assert f"- `src/{CASE}/strategy.py`：F1" in files  # 同一个文件在一格里出现两次只记一次
    assert f"- `src/{CASE}/data.py`（文件不存在）：D1" in files and "- `common/timing_backtest.py`（文件不存在）：B1" in files
    audit = _section(text, "内审结论")
    assert "判定（impl_audit_m1.md）：verdict: pass_with_issues" in audit and "问题 2 条：major 1 · minor 1" in audit
    assert "- IM1-01（major）动量窗口含当日" in audit and "- CA-C01（minor）依据: 窗口长度写成了魔法数字" in audit
    assert "空壳判定（判定: not_found）：未命中" in audit
    matched = _section(text, "已对上的指标")
    assert "归到 m1 的数值指标 3 项：对上 1 项、没对上 2 项" in matched and "没对上：r1_annual_return、r1_sharpe" in matched
    assert "- `r1_max_drawdown` 研报 -0.2 / 复现 -0.201，偏差 0.5%" in matched and "验证记录" not in matched
    _put(root, f"{OUT}/verify_fragments/m1.md", "m1 的验证记录\n")  # 内核流程里 milestone 级验证各写一份分片
    assert f"- 这一步的验证记录：[{OUT}/verify_fragments/m1.md](../../../{OUT}/verify_fragments/m1.md)" in _section(_render(root, state, "milestone_done"), "已对上的指标")
    added = _section(text, "这一步新增的假设")
    assert "推断，共 1 条" in added and "- AS2 窗口映射（来源 coder 主动简化；-）" in added and "AS1" not in added  # AS1 来自歧义裁决

    # 内核明说了新增哪几条就用它的；空壳判定要报
    m2 = _render(root, state, "milestone_done", {"milestone": "m2", "new_assumptions": ["AS3"]})
    assert "内核登记这一步新增 1 条" in _section(m2, "这一步新增的假设") and "- AS3 预期数据代理" in m2
    # 审计文件还不在：检查点是验证通过时开的，内审可能还在途，也可能留到代码审计阶段。只陈述事实，不说「没做」
    wanted = f"`{WS}/audit/impl_audit_m2.md`"
    assert f"- 审计文件 {wanted} 还不在，步骤表里也没有这个 milestone 单独的内审步骤" in _section(m2, "内审结论")
    assert "state.json 记的进度" not in m2  # 状态里没有这个 milestone 时不写
    state["milestones"] = [{"id": "m1", "implement": "done", "code_review": "done", "verify": "done"}, {"id": "m2", "implement": "done", "code_review": "pending", "verify": "done"}]
    state["flow"]["steps"] = {"implement.m2.audit": {"status": "inflight", "attempt": 1, "kind": "dispatch", "role": "quant-auditor", "stage": "implement", "milestone": "m2"}}
    m2 = _render(root, state, "milestone_done", {"milestone": "m2"})
    assert f"- 内审步骤 `implement.m2.audit` 眼下是「在途」，审计文件 {wanted} 还没有交出来" in _section(m2, "内审结论")
    assert "- state.json 记的进度：编码 已完成 · 内审 未开始 · 验证 已完成" in _section(m2, "交付要素")
    _put(root, f"{WS}/audit/impl_audit_m2.md", "- F2 判定: not_found\n\nverdict: fail\n")
    assert "空壳判定（判定: not_found）：命中" in _section(_render(root, state, "milestone_done", {"milestone": "m2"}), "内审结论")
    assert "检查点没有指明是哪个 milestone" in _render(root, state, "milestone_done", {"other": 1})


def test_verify_done(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "verify_done")
    tally = _section(text, "重算达标数")
    assert "按 standards.json 重算达标：数值 1/3、定性 1/2（文件自报 5/5，不采信）" in tally  # 不信文件里的 pass
    assert "没过的定性项 1 个：q_rank" in tally and "验证门禁最近一次：未过（G-VF-4）" in tally
    worst = _section(text, "超差前 10（按相对偏差）")
    assert "没过的数值指标共 2 项" in worst
    assert worst.index("`r1_annual_return` 研报 0.1 / 复现 0.082，偏差 18.0%（归因 assumption_linked）") < worst.index("`r1_sharpe` 研报 1 / 复现 0.9，偏差 10.0%")
    charts = _section(text, "核心图")
    assert f"- [net_value.png](../../../{OUT}/results/net_value.png)" in charts and "- drawdown.png（缺）" in charts
    evidence = _section(text, "证据链")
    assert "[evidence_manifest.md](../audit/evidence_manifest.md)：证据 2 条，结果 pass 2" in evidence
    assert "run_log.md)：含 exit=0" in evidence and f"[verify_report.md](../../../{OUT}/verify_report.md)" in evidence
    assert "- 扰动测试记录：结论：已执行，回测截止日提前一年，12 项指标全部变化，没有硬编码" in _section(text, "扰动结果")  # 折行接上
    denied = _section(text, "被数据否定的假设")
    assert "3 条假设写了「验证后回看」，其中 1 条出现" in denied
    assert "- AS1 零费率回测：实测方向与预期相反" in denied and "AS3" not in denied  # 「支持该口径」不算否定


def test_verify_done_orders_by_deviation_and_respects_verification_level(case: tuple[Path, dict]) -> None:
    root, state = case
    metrics = [{"key": f"r1_m{i:02d}", "report_value": 1.0, "reproduced_value": 1.0 + 0.1 * (i + 1), "tolerance_key": "sharpe"} for i in range(14)]
    metrics.append({"key": "r1_directional", "report_value": 10.0, "reproduced_value": -40.0, "verification_level": "directional", "attribution_status": "assumption_linked"})
    metrics.append({"key": "r1_unverifiable", "report_value": 1.0, "reproduced_value": 9.0, "verification_level": "unverifiable", "attribution_status": "assumption_linked"})
    _put(root, f"{OUT}/results/comparison.json", json.dumps({"metrics": metrics, "qualitative": []}))
    text = _render(root, state, "verify_done")
    assert "数值 0/15；另有 1 项 unverifiable 不计入分母" in _section(text, "重算达标数")
    worst = _section(text, "超差前 10（按相对偏差）")
    lines = [line for line in worst.splitlines() if line.startswith("- `")]
    assert len(lines) == 10 and "没过的数值指标共 15 项，列偏差最大的 10 项" in worst
    assert lines[0].startswith("- `r1_directional` 研报 10 / 复现 -40，偏差 500.0%（只核方向；归因 assumption_linked）")  # 只核方向的也按偏差排
    assert lines[1].startswith("- `r1_m13`") and lines[-1].startswith("- `r1_m05`")
    assert f"- 其余 5 条见 `{OUT}/results/comparison.json`" in worst

    # 实验模式只核产出在不在位
    state["reproduction_mode"] = "experimental"
    assert "实验模式，数值对齐按模式豁免，只核产出是否在位：数值 16/16 在位" in _section(_render(root, state, "verify_done"), "重算达标数")


def test_iterate_round(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "iterate_round")
    assert "（第 3 轮）" in text.splitlines()[0]
    changes = _section(text, "本轮修改点")
    assert "第 3 轮诊断结论：continue" in changes and f"- src/{CASE}/config.py：窗口 20 → 21" in changes
    trend = _section(text, "指标 × 轮次趋势")
    assert "| 指标 | iter_01 | iter_02 | iter_03 |" in trend
    assert "| 重算达标 | 数值 1/3、定性 1/2 | 数值 1/3、定性 1/2 | 数值 1/3、定性 1/2 |" in trend
    assert "| `r1_annual_return` | 20.0% | 19.0% | 18.0% |" in trend and "| `r1_sharpe` | 50.0% | 20.0% | 10.0% |" in trend
    assert "r1_max_drawdown" not in trend  # 只列最新一轮没过的
    excluded = _section(text, "已排除假设")
    assert excluded.count("AS2 窗口映射") == 1 and "- iter_02：AS2 窗口映射（iter_01 已证伪）：不再试" in excluded  # 各轮去重，取最新的说法
    assert "- iter_02：调仓日口径：月初月末差别不到 0.1pct" in excluded and "- iter_01：费率口径：千三之后偏差更大" in excluded
    assert "只是回顾不该重复列出" not in excluded
    warn = _section(text, "无改善预警")
    assert "有 1 项连续两轮偏差改善都不到 10%" in warn
    assert "- `r1_annual_return`：iter_01 20.0% → iter_02 19.0% → iter_03 18.0%" in warn and "r1_sharpe" not in warn

    # 这一轮没有 changes.md；快照不足三份时不判断无改善
    second = _render(root, state, "iterate_round", {"round": 2})
    assert "这一轮没有 changes.md" in _section(second, "本轮修改点")
    shutil.rmtree(root / WS / "iterations" / "iter_01")
    assert "快照只有 2 份，不足三份，暂不判断" in _section(_render(root, state, "iterate_round"), "无改善预警")


def test_pre_report(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "pre_report")
    head = _section(text, "verdict 与覆盖率")
    assert "verdict：partial；按 standards.json 重算达标：数值 1/3、定性 1/2" in head
    assert "覆盖率 4/8（50.0%，按矩阵现算）：跳过 1 · 不可行 1 · 未完成 2；core 4/6" in head
    reviews = _section(text, "三审查点的引擎与降级")
    assert "| spec | codex | 否 | pass_with_issues | 0 / 1 / 0 |" in reviews and "| code | same_host_fallback | 是 | pass | 0 / 0 / 1 |" in reviews
    assert "| result | 尚无记录 | - | - | - |" in reviews
    rejected = _section(text, "rejected 意见")
    assert "回应表共 3 条带编号的外审意见，其中 rejected 1 条" in rejected and "- CDX-C-01（major）：静态池用了未来数据" in rejected
    undone = _section(text, "未复现清单")
    assert "矩阵 8 行里 skipped / infeasible 共 2 行" in undone and "- D2 一致预期（core，infeasible）：data_missing：本地没有" in undone
    precheck = _section(text, "G-FN 输入侧预检")
    assert "（G-FN-3）：否，还有 R2 SA1" in precheck and "（G-FN-4）：否，1 处（AS2）" in precheck and "（G-FN-5）：CDX-C-01" in precheck

    state["coverage_stats"] = {"total": 8, "done": 6, "skipped": 1, "infeasible": 1, "pending": 0}
    state["external_reviews"].append({"checkpoint": "code_revise", "engine": "codex", "verdict": "pass", "critical": 0, "major": 0, "minor": 0})
    again = _render(root, state, "pre_report")
    assert "覆盖率 6/8（75.0%，取自 state.coverage_stats）" in again and "另有增量审查记录：code_revise" in again


def test_final_review(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "final_review")
    conclusion = _section(text, "结论与评级")
    assert "- verdict：partial" in conclusion and "- 可信度评级：B（core 覆盖不全、存在 major-auto 假设）" in conclusion
    assert "数值 1/3、定性 1/2" in conclusion and "覆盖率 4/8" in conclusion
    paths = _section(text, "报告与结果页")
    assert f"- 最终报告：[{WS}/final_report.md](../final_report.md)" in paths
    assert f"- 验证报告：[{OUT}/verify_report.md](../../../{OUT}/verify_report.md)" in paths
    batch = f'`flow revise {CASE} --from-excel --quote "<你的原话>"`'
    assert "假设登记簿 Excel：还没有导出" in paths and f"`tools/assumptions_xlsx.py export {CASE}`" in paths and batch in paths and "结果页" not in paths
    _put(root, f"{WS}/assumptions.xlsx", "xlsx")
    _put(root, f"{OUT}/final_report.html", "<html>")
    again = _section(_render(root, state, "final_review"), "报告与结果页")
    assert f"- 假设登记簿 Excel：[{WS}/assumptions.xlsx](../assumptions.xlsx)（黄底三列可改；改完用 {batch} 成批修订）" in again
    assert f"- 结果页：[{OUT}/final_report.html]" in again and "还没有导出" not in again

    _put(root, f"{WS}/final_report.md", "# 报告\n\n可信度评级:A(覆盖率 100%)——见附录。\n")
    assert "- 可信度评级:A(覆盖率 100%)——见附录。" in _render(root, state, "final_review")
    _put(root, f"{WS}/final_report.md", "# 报告\n\n没有评级句。\n")
    assert "没有找到「可信度评级：X（…）」这句话" in _render(root, state, "final_review")


def test_data_gap(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "data_gap")
    assert GAP_REPORT in _section(text, "缺口清单")  # 内核渲染好的清单原样放入
    table = _section(text, "处置选项")
    rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith(("| 处置", "| ---"))]
    assert [row.split(" | ")[0].lstrip("| ") for row in rows] == ["补数据", "等价替代", "缩小范围", "先用 mock 试跑", "砍掉相关要素", "终止"]
    assert "| 补数据 | `supply` | 你去补 | 暂停；补完执行 `flow data recheck` |" in table
    assert "| 先用 mock 试跑 | `mock` | 用模拟数据先把代码和流水线跑通；这一轮只算试跑，不出结论 |" in table
    assert "| 砍掉相关要素 | `drop` | 标为 infeasible（data_missing），其余照做 | 继续 |" in table

    # 检查点自带的选项里没有某种处置时，对应的选项键留空
    few = _render(root, state, "data_gap", options=[{"key": "supply", "label": "补"}, {"key": "abort", "label": "停"}])
    assert "| 等价替代 | - |" in few and "--choice supply" in few and "--choice mock" not in few

    # 清单再长也压在上限内：清单逐行截，处置表与选项全留
    long_gap = "\n".join(f"| 表 {i:03d} | 缺失 | 这一行是凑长度用的说明文字 |" for i in range(400))
    big = _render(root, state, "data_gap", {"gap_report": long_gap})
    assert len(big.encode("utf-8")) <= rp.limit_for("data_gap")
    hidden = re.search(rf"其余 (\d+) 条见 `{WS}/data_check.json`", big)
    assert hidden and int(hidden.group(1)) + big.count("| 表 ") == 400
    assert "| 终止 | `abort` |" in big and "--choice drop" in big


def _kernel_style_gap_report(n: int) -> str:
    """内核那种自带标题的缺口清单：一级标题加概述，每个缺口一个二级小节，末尾另有附注小节。"""
    lines = ["# 数据缺口清单 · r001_demo", "", "> 体检于 2026-11-22T01:00:00+08:00，数据根目录 `~/local_data`。", f"> 共 {n} 条数据需求：缺失 {n}。缺口 {n} 个，其中 {n} 个还没有处置决定。", ""]
    for i in range(1, n + 1):
        lines += [f"## {i}. 数据需求 {i}", "", "- 结论：缺失 · 核心数据 · 待处置", f"- 文件：`table_{i}.parquet`", "- 缺什么：", "  - 文件不存在（file_missing）：本地没有这张表", "```", "# 围栏里的井号行不是标题", "```", f"- 影响要素（2 个）：D{i}、F{i}", ""]
    return "\n".join(lines + ["## 已替代（1 条，不算缺口）", "", "- 日行情：替代数据查过", ""])


def test_data_gap_embeds_a_report_that_has_its_own_headings(case: tuple[Path, dict]) -> None:
    root, state = case
    fixed = ["为什么停在这里", "缺口清单", "处置选项", "你可以怎么决定"]
    text = _render(root, state, "data_gap", {"gap_report": _kernel_style_gap_report(2)})
    # 清单自带的标题降两级嵌进「缺口清单」，文字不动；审阅包自己的一、二级标题还是那几个
    assert [line for line in text.splitlines() if line.startswith("# ") and "围栏里" not in line] == [text.splitlines()[0]]
    assert [line[3:] for line in text.splitlines() if line.startswith("## ")] == fixed
    gap = _section(text, "缺口清单")
    assert gap.startswith("\n### 数据缺口清单 · r001_demo\n\n> 体检于 2026-11-22T01:00:00+08:00，数据根目录 `~/local_data`。\n> 共 2 条数据需求")
    assert "\n\n#### 1. 数据需求 1\n\n- 结论：缺失 · 核心数据 · 待处置\n- 文件：`table_1.parquet`\n" in gap and "\n\n#### 2. 数据需求 2\n\n" in gap
    assert "\n\n#### 已替代（1 条，不算缺口）\n\n- 日行情：替代数据查过\n" in gap and "其余" not in gap
    assert gap.count("\n# 围栏里的井号行不是标题\n") == 2  # 代码围栏里的不动

    # 缺口多到放不下：概述留着，按整个缺口截，处置表与选项全留
    big = _render(root, state, "data_gap", {"gap_report": _kernel_style_gap_report(40)})
    assert rp.limit_for("data_gap") - 600 < len(big.encode("utf-8")) <= rp.limit_for("data_gap") and "正文超出上限" not in big
    assert [line[3:] for line in big.splitlines() if line.startswith("## ")] == fixed
    gap = _section(big, "缺口清单")
    assert "> 共 40 条数据需求：缺失 40。缺口 40 个" in gap
    shown = re.findall(r"^#### (\d+)\. 数据需求 \d+$", gap, flags=re.M)
    hidden = re.search(rf"\n\n其余 (\d+) 条见 `{WS}/data_check.json`\n", gap)
    assert shown == [str(i) for i in range(1, len(shown) + 1)] and 0 < len(shown) < 40
    assert hidden and len(shown) + int(hidden.group(1)) == 41  # 40 个缺口加末尾的附注小节
    assert gap.count("- 影响要素（2 个）") == len(shown)  # 留下的每个缺口都是完整的一段
    assert "| 终止 | `abort` |" in big and "--choice drop" in big

    # 只有标题没有分节的清单按行截；等人补数据的检查点走通用模板，清单同样嵌入
    flat = _section(_render(root, state, "data_gap", {"gap_report": "# 数据缺口清单\n\n没有数据缺口。"}), "缺口清单")
    assert flat == "\n### 数据缺口清单\n\n没有数据缺口。\n\n"
    wait = _render(root, state, "data_wait", {"gaps": ["数据需求 1"], "gap_report": _kernel_style_gap_report(1)})
    assert "#### 1. 数据需求 1" in _section(wait, "缺口清单") and "gap_report" not in wait


def test_trial_done(case: tuple[Path, dict]) -> None:
    root, state = case
    mock = f"{OUT}/results_mock"
    absent = _render(root, state, "trial_done")
    assert f"试跑结果目录 `{mock}/` 不存在，三件事都无从检查" in absent and rp.EMPTY in _section(absent, "哪些数据是 mock")

    _put(root, f"{mock}/run_log.md", "exit=0\n")
    _put(root, f"{mock}/net_value.png", "png")
    _put(root, f"{mock}/metrics.json", json.dumps({"annual_return": 0.1, "by_year": [{"y": 2020, "ret": None}], "sharpe": float("nan")}))
    files = [{"name": "ashare_price.parquet", "source": "real"}, {"name": "consensus.parquet", "source": "mock"}]
    _put(root, f"{mock}/data_manifest.json", json.dumps({"report_id": CASE, "trial": True, "files": files}))
    text = _render(root, state, "trial_done")
    checks = _section(text, "试跑只查三件事")
    assert "- 跑得通：是（run_log.md 含 exit=0）" in checks
    assert "- 产物齐：否（缺 5 个：drawdown.png、position_signal.png、yearly_returns.png、rolling_sharpe.png、backtest_summary.xlsx）" in checks
    assert "- 指标都算得出：否（2 处算不出：by_year[0].ret、sharpe）" in checks and "按结果目录里的文件现算" in checks
    assert f"- `{mock}/`，4 个文件" in _section(text, "试跑结果目录")
    mocked = _section(text, "哪些数据是 mock")
    assert "记了 2 个文件，其中 mock 1 个、真实 1 个" in mocked and "- `consensus.parquet`" in mocked and "ashare_price" not in mocked

    # 内核试跑检查给了结果就用它的
    kernel = {"ran": True, "missing": [], "empty_metrics": [], "mock_files": ["consensus.parquet"], "ok": True, "results_dir": mock}
    checks = _section(_render(root, state, "trial_done", kernel), "试跑只查三件事")
    assert "- 产物齐：是" in checks and "- 指标都算得出：是" in checks and "取自内核试跑检查的记录" in checks


def test_circuit_breaker_and_generic(case: tuple[Path, dict]) -> None:
    root, state = case
    text = _render(root, state, "circuit_breaker", stage="verify")
    assert "- 验证 G-VF-4：连续 3 次未过" in _section(text, "连败的检查项")
    detail = _section(text, "最近一次未过的明细")
    assert "验证门禁，2026-11-22 01:00，结论 FAIL，未过 1 项" in detail and "- G-VF-4 必需图表存在：缺 drawdown.png" in detail

    stall = _render(root, state, "stall", {"idle_hours": 30.5, "steps": ["implement.m2.code"], "note": "很长" * 300})
    points = _section(stall, "要点")
    assert "- idle_hours：30.5" in points and '- steps：["implement.m2.code"]' in points
    note = next(line for line in points.splitlines() if line.startswith("- note："))
    assert note.endswith("…") and len(note) < 220  # 过长截断

    # 带缺口清单的检查点（等人补数据）把清单单列一节，不挤成一行
    wait = _render(root, state, "data_wait", {"gaps": ["一致预期"], "gap_report": GAP_REPORT})
    assert GAP_REPORT in _section(wait, "缺口清单") and "gap_report" not in _section(wait, "要点")


def test_auto_resolved_and_unopened_checkpoints(case: tuple[Path, dict]) -> None:
    root, state = case
    auto = _render(root, state, "external_degraded", kind="auto")
    assert "按策略自动放行，只留痕，不需要你决定" in auto and "flow decide" not in auto
    done = _render(root, state, "spec_final", status="resolved", decision={"choice": "approve", "quote": "继续", "credential": "self_report", "by": "human", "at": "2026-11-22T03:00:00+08:00"})
    assert "已经处理：选择 `approve`，放行方：人，凭据：自述（没有人在场凭据），2026-11-22 03:00" in done and "flow decide" not in done
    assert rp.credential_cn("terminal") == "人在终端输入了短码" and rp.credential_cn("policy") == "按策略，不需要凭据"
    assert rp.credential_cn("别的") == "别的" and rp.credential_cn(None) == "未记录"
    # 个别选项要多带参数：回退给 --to，提高预算给新上限
    assert rp.decide_command(CASE, "cp_09", "raise") == f'flow decide {CASE} cp_09 --choice raise --budget-tokens <新上限> --quote "<你的原话>"'
    assert rp.decide_command(CASE, None, "approve", "继续") == f'flow decide {CASE} {rp.CP_PLACEHOLDER} --choice approve --quote "继续"'

    # 不给检查点：state 里有同名待决的就用它，没有就留占位符
    state["checkpoints"] = [_checkpoint("spec_final", id="cp_07", code="ABCD"), _checkpoint("plan_final", id="cp_08", status="resolved")]
    opened = rp.render(root, CASE, "spec_final", state=state)
    assert "（cp_07）" in opened.splitlines()[0] and f"flow decide {CASE} cp_07 --choice approve" in opened and "`ABCD`" in opened
    unopened = rp.render(root, CASE, "plan_final", state=state)
    assert f"flow decide {CASE} {rp.CP_PLACEHOLDER} --choice approve" in unopened and "由 `flow status` 给出" in unopened

    # 检查点自带选项时用它的
    custom = _render(root, state, "spec_final", options=[{"key": "ok", "label": "好"}, {"label": "没有键的不算"}])
    tail = _section(custom, "你可以怎么决定")
    assert "- `ok` 好" in tail and f'`flow decide {CASE} cp_03 --choice ok --quote "<你的原话>"`' in tail and "approve" not in tail


def test_names_and_options_follow_the_kernel_table(case: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch) -> None:
    root, state = case
    fake = types.SimpleNamespace(HUMAN={"spec_final": ("规格定稿（内核叫法）", "awaiting_review", [("ok", "好"), ("no", "不好")])}, AUTO={"auto_x": "自动的"})
    monkeypatch.setattr(rp, "_kernel", lambda: fake)
    assert rp.checkpoint_title("spec_final") == "规格定稿（内核叫法）" and rp.checkpoint_title("auto_x") == "自动的"
    assert rp.checkpoint_options("spec_final") == [{"key": "ok", "label": "好"}, {"key": "no", "label": "不好"}]
    assert rp.is_auto(None, "auto_x") and not rp.is_auto({"kind": "human", "name": "auto_x"})
    assert rp.checkpoint_title("plan_final") == rp.CHECKPOINT_CN["plan_final"]  # 内核表里没有的退回自带的
    assert rp.credential_cn("hook") == rp.CREDENTIAL_CN["hook"]  # 内核没给凭据表时也一样
    fake.CREDENTIAL_CN = {"hook": "钩子（内核叫法）"}
    assert rp.credential_cn("hook") == "钩子（内核叫法）" and rp.credential_cn("policy") == rp.CREDENTIAL_CN["policy"]
    text = _render(root, state, "spec_final")
    assert text.startswith("# 规格定稿（内核叫法） · ") and f"flow decide {CASE} cp_03 --choice ok" in text and "--choice approve" not in text


def test_real_kernel_table_names_all_render(case: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # 这里要用真的内核表
    kernel = rp._kernel()
    if kernel is None:
        pytest.skip("内核的检查点模块眼下不可用")
    root, state = case
    for name in list(kernel.HUMAN) + list(kernel.AUTO):
        cp = _checkpoint(name, kind="auto" if name in kernel.AUTO else "human")
        text = rp.render(root, CASE, name, state=state, checkpoint=cp)
        assert text.startswith(f"# {rp.checkpoint_title(name, cp)} · {CASE}") and len(text.encode("utf-8")) <= rp.limit_for(name)
        assert "专用模板渲染失败" not in text
        if name in kernel.AUTO:
            continue
        keys = [key for key, _label in kernel.HUMAN[name][2]]
        assert [o["key"] for o in rp.checkpoint_options(name)] == keys
        for key in keys:
            assert f"- `{key}` " in text


def test_commands_are_accepted_by_the_kernel_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """审阅包和看板给的命令，把占位符换成真值后内核的命令行都认；参数名对不上会在这里露出来。"""
    monkeypatch.undo()  # 这里要用真的内核表
    kernel = rp._kernel()
    try:
        from tools import flow
    except Exception:  # noqa: BLE001 - 内核在改动中导不进来时不算这里的失败
        flow = None
    if kernel is None or not hasattr(flow, "build_parser"):
        pytest.skip("内核的命令行眼下不可用")
    parser = flow.build_parser()
    fill = {"<阶段或 milestone>": "plan", "<假设编号>": "AS1", "<新上限>": "100", rp.CP_PLACEHOLDER: "cp_03"}
    commands = {rp.option_command(CASE, name, "cp_03", o["key"]) for name in kernel.HUMAN for o in rp.checkpoint_options(name)}
    commands |= {rp.REVISE_FROM_EXCEL.format(flow=rp.FLOW, id=CASE, quote=rp.QUOTE_PLACEHOLDER), rp.decide_command(CASE, None, "approve")}
    assert len(commands) > 20
    for command in sorted(commands):
        for placeholder, value in fill.items():
            command = command.replace(placeholder, value)
        argv = shlex.split(command)
        assert argv[0] == rp.FLOW
        try:
            args = parser.parse_args(argv[1:])
        except SystemExit:
            pytest.fail(f"内核的命令行不认这条命令：{command}")
        assert args.report_id == CASE and args.quote == rp.QUOTE_PLACEHOLDER  # 放行都带人的原话
        if argv[1] == "decide":
            assert args.checkpoint == "cp_03" and args.choice
            assert (args.to == "plan") == (args.choice == "rollback") and (args.budget_tokens == 100) == (args.choice == "raise")


# ---------------------------------------------------------------------------
# 上限与截断
# ---------------------------------------------------------------------------


def _big_case(root: Path) -> None:
    """要素、假设、矩阵行都很多的案例，哪种审阅包都装不下全部明细。"""
    blocks = ["# 大研报 复现规格书\n"]
    for i in range(1, 61):
        blocks.append(f"### [D{i}] 数据 {i}\n- 页码: p{i}\n- 原文: > \"x\"\n- 数据状态: missing\n- 说明: 第 {i} 张表本地没有，这里再补一句凑长度的说明\n")
        blocks.append(f"### [F{i}] 因子 {i}\n- 页码: p{i}\n- 原文: > \"x\"\n- 公式（转写）: f{i} = rank(close / close.shift({i})) - 这里是一条比较长的公式首行\n")
        blocks.append(f"### [B{i}] 设置 {i}\n- 页码: p{i}\n- 原文: > \"x\"\n- 参数值: 参数 {i} 取值说明比较长比较长比较长\n")
        blocks.append(f"### [R{i}] 结果表 {i}\n- 页码: p{i}\n- 原文: > \"x\"\n")
    _put(root, f"{WS}/spec/spec.md", "\n".join(blocks))
    _put(root, f"{WS}/spec/ambiguities.md", "# 歧义\n\n" + "\n".join(
        f"### [A{i}] 歧义 {i}\n- 页码: p{i}\n- 关联要素: F{i}\n- 等级: {'blocking' if i <= 3 else 'major'}\n- 候选解释: 解释1 这样；解释2 那样；再补一句凑长度\n- 状态: open\n" for i in range(1, 41)
    ))
    rows = ["| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i in range(1, 61):
        rows.append(f"| D{i} | D | 数据 {i} | p{i} | core | m1 | infeasible | data_missing：第 {i} 张表本地没有 | | | plan |")
        rows.append(f"| F{i} | F | 因子 {i} | p{i} | core | m1 | done | | src/{CASE}/f{i}.py:calc | ok | verify |")
        rows.append(f"| R{i} | R | 结果表 {i} | p{i} | core | m1 | skipped | 依赖 D{i}，这里再补一句理由 | | 第 {i} 张表对上了 | plan |")
    _put(root, f"{WS}/spec/coverage_matrix.md", "# 覆盖矩阵\n\n" + "\n".join(rows) + "\n")
    _put(root, f"{WS}/assumptions.md", "# 假设登记簿\n\n" + "\n".join(
        f"### [AS{i}] 假设 {i}\n- 来源: coder 主动简化\n- 假设内容: 第 {i} 条假设的内容写得比较长比较长比较长比较长\n- 影响 milestone: m1\n"
        f"- 验证后回看: 这一条的回看写得比较长比较长比较长比较长比较长比较长，实测结果与预期相反，第 {i} 条被否定，后面还跟着一段比较长比较长比较长的说明\n- 高亮等级: major-auto\n- 参数绑定: p{i}\n"
        for i in range(1, 81)
    ))
    plan = "---\ntype: timing\ndifficulty: hard\nfeasibility: degraded\nmilestones:\n  - id: m1\n    name: 全部\n    deps: []\n    elements: [F1]\n---\n# 计划\n\n## 分诊结论\n\n"
    _put(root, f"{WS}/plan.md", plan + "\n".join(f"- 第 {i} 条分诊依据，写得比较长比较长比较长比较长比较长比较长" for i in range(1, 61)) + "\n")
    metrics = [{"key": f"r{i}_annual_return", "report_value": 1.0, "reproduced_value": 1.0 + 0.1 * i, "tolerance_key": "annual_return", "source_element": f"R{i}"} for i in range(1, 61)]
    for n in (1, 2, 3):
        _put(root, f"{WS}/iterations/iter_{n:02d}/comparison.json", json.dumps({"metrics": metrics, "qualitative": []}))
        _put(root, f"{WS}/iterations/iter_{n:02d}/diagnosis.md", "## 已排除假设\n\n" + "\n".join(f"{i}. **第 {n} 轮排除项 {i}**：理由写得比较长比较长比较长" for i in range(1, 31)) + "\n\n结论: continue\n")
    _put(root, f"{OUT}/results/comparison.json", json.dumps({"metrics": metrics, "qualitative": []}))
    _put(root, f"{WS}/audit/audit_responses.md", "| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |\n|---|---|---|---|---|---|\n" + "\n".join(
        f"| CDX-R-{i:02d} | major | 第 {i} 条被驳回的意见，摘要写得比较长比较长比较长 | rejected | 不成立 | pass |" for i in range(1, 61)
    ) + "\n")


@pytest.mark.parametrize("name", ["spec_final", "plan_final", "milestone_done", "verify_done", "iterate_round", "pre_report"])
def test_oversized_packs_keep_conclusions_and_say_what_was_cut(empty: tuple[Path, dict], name: str) -> None:
    root, state = empty
    (root / "templates").mkdir()
    shutil.copy(REPO_ROOT / "templates" / "standards.json", root / "templates" / "standards.json")
    _big_case(root)
    state.update({"type": "timing", "iteration": {"current": 3, "max": 6}})
    text = _render(root, state, name)
    assert rp.limit_for(name) - 400 < len(text.encode("utf-8")) <= rp.limit_for(name)  # 压在上限内，也没有白白浪费空间
    assert "专用模板渲染失败" not in text and "正文超出上限" not in text
    notes = re.findall(r"其余 (\d+) 条见 `([^`]+)`", text)
    assert notes and all((root / path).exists() for _n, path in notes)  # 截掉的明细指向原文件
    # 结论与选项都在
    tail = _section(text, "你可以怎么决定")
    assert all(f"--choice {o['key']} " in tail for o in rp.checkpoint_options(name)) and text.rstrip().endswith(rp.FOOTER)
    conclusion = {
        "spec_final": "按标题块实数：D 60 · F 60 · B 60 · R 60 · SA 0，共 240 条",
        "plan_final": "假设共 80 条，其中 major-auto 80 条",
        "milestone_done": "m1 共 180 个要素",
        "verify_done": "按 standards.json 重算达标：数值 0/60",
        "iterate_round": "有 60 项连续两轮偏差改善都不到 10%",
        "pre_report": "回应表共 60 条带编号的外审意见，其中 rejected 60 条",
    }[name]
    assert conclusion in text
    if name == "spec_final":  # 明细条数对得上：列出来的加上「其余」等于总数；blocking 歧义一条不截
        formulas = _section(text, "F 类公式（首行）")
        shown = sum(line.startswith("- F") for line in formulas.splitlines())
        assert 0 < shown < 60 and shown + int(re.search(r"其余 (\d+) 条", formulas).group(1)) == 60
        assert sum(line.startswith("- A") for line in _section(text, "blocking 歧义").splitlines()) == 3
    if name == "verify_done":  # 前 10 之外的指标、放不下的假设都计入「其余」
        assert f"- 其余 50 条见 `{OUT}/results/comparison.json`" in _section(text, "超差前 10（按相对偏差）")
        denied = _section(text, "被数据否定的假设")
        shown = sum(line.startswith("- AS") for line in denied.splitlines())
        assert 0 < shown < 80 and shown + int(re.search(r"其余 (\d+) 条", denied).group(1)) == 80


def test_compose_hard_clips_when_conclusions_alone_are_too_long() -> None:
    head, tail = "# 标题\n\n", "## 你可以怎么决定\n\n- `approve` 继续\n"
    secs = [rp.Sec("很长的结论", lines=["- " + "结论" * 400 for _ in range(6)], items=["- 明细"] * 5, source="x.md")]
    text = rp._compose(head, secs, tail, 2048)
    assert len(text.encode("utf-8")) <= 2048 and text.startswith(head) and text.endswith(tail) and "正文超出上限，已截断" in text
    assert rp._compose(head, [rp.Sec("空的")], tail, 2048) == head + f"## 空的\n\n{rp.EMPTY}\n\n" + tail
    assert len(rp._compose("头" * 2000, secs, tail, 1024).encode("utf-8")) <= 1024  # 头尾本身超限也不越线

    # 小节的截断提示：列表接成最后一条，表格另起一段；没有原文件时也说明截了多少
    listed = rp.Sec("列表", items=[f"- 第 {i} 条" for i in range(5)], source="a/b.md").render(2)
    assert listed == "## 列表\n\n- 第 0 条\n- 第 1 条\n- 其余 3 条见 `a/b.md`\n\n"
    table = rp.Sec("表格", lead=["| a |", "| --- |"], items=["| 1 |", "| 2 |"]).render(1)
    assert table == "## 表格\n\n| a |\n| --- |\n| 1 |\n\n其余 1 条未列出\n\n"
    assert rp.Sec("全截", lines=["- 结论"], items=["- x"], source="c.md").render(0) == "## 全截\n\n- 结论\n\n其余 1 条见 `c.md`\n\n"


# ---------------------------------------------------------------------------
# 写盘
# ---------------------------------------------------------------------------


def test_write_creates_the_pack_and_nothing_else(case: tuple[Path, dict]) -> None:
    root, state = case
    assert not (root / WS / "reviews").exists()
    before = _snapshot(root)
    cp = _checkpoint("data_gap", id="cp_04")
    rel = rp.write(root, CASE, cp, state=state)
    assert rel == f"{WS}/reviews/cp_04_data_gap.md" == rp.pack_path(CASE, "cp_04", "data_gap")
    assert (root / rel).read_text(encoding="utf-8") == rp.render(root, CASE, "data_gap", state=state, checkpoint=cp)
    after = _snapshot(root)
    added = sorted(set(after) - set(before))
    assert added == [f"{WS}/reviews", rel] and all(after[k] == before[k] for k in before if k != WS)  # 只多了审阅包
    rp.write(root, CASE, {**cp, "reason": "换了原因"}, state=state)  # 同一个检查点再写一次是覆盖
    assert "换了原因" in (root / rel).read_text(encoding="utf-8") and not list((root / WS / "reviews").glob("*.tmp"))


def test_render_is_pure_and_deterministic(case: tuple[Path, dict]) -> None:
    root, state = case
    before = _snapshot(root)
    frozen = json.dumps(state, ensure_ascii=False, sort_keys=True)
    with _changes_under(root) as changes:
        first = {name: _render(root, state, name) for name in ALL_NAMES}
        assert {name: _render(root, state, name) for name in ALL_NAMES} == first  # 同样的输入给出同样的输出
    assert changes == [] and _snapshot(root) == before and json.dumps(state, ensure_ascii=False, sort_keys=True) == frozen


def test_the_change_watch_sees_writes_and_ignores_reads(tmp_path: Path) -> None:
    """上面「渲染不写任何东西」靠的这只眼睛得真看得见：写、建、改名、删都记，读和别处的写不记。"""
    watched, elsewhere = tmp_path / "watched", tmp_path / "elsewhere"
    watched.mkdir()
    elsewhere.mkdir()
    (watched / "old.md").write_text("旧", encoding="utf-8")
    with _changes_under(watched) as changes:
        assert (watched / "old.md").read_text(encoding="utf-8") == "旧" and sorted(p.name for p in watched.rglob("*")) == ["old.md"]
        (elsewhere / "x.md").write_text("别处", encoding="utf-8")
        assert changes == []
        (watched / "sub").mkdir()
        (watched / "sub" / "new.md").write_text("新", encoding="utf-8")
        with (watched / "old.md").open("a", encoding="utf-8") as handle:
            handle.write("追加")
        os.replace(watched / "sub" / "new.md", watched / "moved.md")
        (watched / "moved.md").unlink()
    kinds = [hit.split(" ", 1)[0] for hit in changes]
    assert kinds.count("open") == 2 and {"os.mkdir", "os.rename", "os.remove"} <= set(kinds)
    count = len(changes)
    (watched / "after.md").write_text("出了作用域就不再记", encoding="utf-8")
    assert len(changes) == count
    # 写盘函数确实会被它看见：只动 reviews 目录和审阅包本身
    root = tmp_path / "root"
    (root / WS).mkdir(parents=True)
    with _changes_under(root) as changes:
        rel = rp.write(root, CASE, _checkpoint("stall", id="cp_09"), state={})
    assert changes and all(f"{WS}/reviews" in hit for hit in changes) and (root / rel).is_file()


# ---------------------------------------------------------------------------
# 仓库里的真实案例：能渲染、不超限、不写任何文件
# ---------------------------------------------------------------------------

REAL_CASES = ["r008_inflection_trend_size_rotation", "r009_industry_rotation", "r010_breakout_ratio_timing"]
REAL_PACKS = {
    "spec_final": ["要素计数", "F 类公式（首行）", "B 类参数表", "R 表清单", "blocking 歧义", "major 歧义", "缺失数据"],
    "plan_final": ["分诊依据", "milestone 表", "major-auto 假设（逐条）", "core 级被跳过的要素", "spec 外审结论", "Excel 批量回改入口"],
    "verify_done": ["重算达标数", "超差前 10（按相对偏差）", "核心图", "证据链", "扰动结果", "被数据否定的假设"],
    "pre_report": ["verdict 与覆盖率", "三审查点的引擎与降级", "rejected 意见", "未复现清单", "G-FN 输入侧预检"],
    "final_review": ["结论与评级", "报告与结果页"],
}


@pytest.mark.parametrize("report_id", REAL_CASES)
def test_real_cases_render_within_limits_without_writing(report_id: str) -> None:
    ws = REPO_ROOT / "workspace" / report_id
    if not (ws / "state.json").is_file():
        pytest.skip(f"仓库里没有案例 {report_id}")
    state = json.loads((ws / "state.json").read_text(encoding="utf-8"))
    out = REPO_ROOT / "output" / report_id

    def footprint() -> tuple[dict[str, tuple[int, int]], list[str]]:
        """案例目录的快照。内核自己随时会刷新的几样（状态、事件流、看板、flow/ 下的账本）不算，别的进程可能正好在动。"""
        kernel_owned = ("state.json", ".state.lock", "events.jsonl", "board.html")
        files = {k: v for k, v in _snapshot(ws).items() if k not in kernel_owned and k != "flow" and not k.startswith("flow/")}
        return files, sorted(p.name for p in out.iterdir()) if out.is_dir() else []

    before = footprint()
    had_reviews = (ws / "reviews").exists()
    sizes: dict[str, int] = {}
    with _changes_under(ws, out) as changes:
        for name, sections in REAL_PACKS.items():
            cp = {"id": "cp_01", "name": name, "kind": "human", "stage": "review", "status": "pending", "opened_at": "2026-11-22T02:07:00+08:00", "reason": "", "options": [], "pack": None, "payload": None, "code": "K7QM", "decision": None}
            text = rp.render(REPO_ROOT, report_id, name, state=state, checkpoint=cp)
            sizes[name] = len(text.encode("utf-8"))
            assert sizes[name] <= rp.limit_for(name), f"{name} {sizes[name]} 字节，超过上限"
            assert "专用模板渲染失败" not in text and "正文超出上限" not in text
            for title in sections:
                assert _section(text, title).strip() != rp.EMPTY, f"{name} 的「{title}」是空的"  # 真实案例的文书是齐的
            assert "## 你可以怎么决定" in text and text.rstrip().endswith(rp.FOOTER)
        assert "按 standards.json 重算达标" in rp.render(REPO_ROOT, report_id, "verify_done", state=state) or state.get("reproduction_mode") == "experimental"
    assert changes == []  # 本进程没有对案例目录做过任何改动（内核自己的文件也在内）
    assert footprint() == before  # 真实案例只读
    assert (ws / "reviews").exists() == had_reviews  # 渲染不落盘，审阅包目录不会凭空出现
    print(f"\n{report_id} 各审阅包字节数：" + "，".join(f"{k} {v}" for k, v in sizes.items()))
