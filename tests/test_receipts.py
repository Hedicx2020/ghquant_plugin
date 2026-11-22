"""回执的接受与拒收（tools/flowlib/receipts.py），经引擎走完整的点收路径。

这里的两类写法都来自真实子 agent 的回执：一条假设跨几个影响面、绑几个 config 字段。真实的
coder 按内核任务文件实现 r010 的 m1 时，这两种写法各出现过，当时的内核把它们一律拒收，
为格式问题白白重派了一次编码。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_harness as fh  # noqa: E402
from tools import assumptions_xlsx as ax  # noqa: E402
from tools.flowlib import decisions  # noqa: E402
from tools.flowlib import receipts as rc  # noqa: E402

CODE_STEP = "implement.m1.code"


def _rewrite_receipt(make: Callable[[dict[str, Any], int, list[str]], dict[str, Any]]) -> Callable[[fh.Stub, dict[str, Any]], None]:
    """桩 agent 写完回执之后，按 make(回执, 第几次派发, 预留编号) 改写它。预留编号从任务文件里读，和真实 agent 一样。"""

    def hook(stub: fh.Stub, order: dict[str, Any]) -> None:
        path = stub.root / order["receipt"]
        task = (stub.root / order["prompt_file"]).read_text(encoding="utf-8")
        found = re.search(r"预留给你的新假设编号：AS(\d+)–AS(\d+)", task)
        reserved = [f"AS{n}" for n in range(int(found.group(1)), int(found.group(2)) + 1)] if found else []
        data = make(json.loads(path.read_text(encoding="utf-8")), stub.counts[order["description"]], reserved)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return hook


def _case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hook: Callable[[fh.Stub, dict[str, Any]], None]) -> tuple[Path, str, fh.Stub]:
    root = fh.make_root(tmp_path, None)
    rid = fh.new_case(root, monkeypatch)
    stub = fh.Stub(root, rid, fh.Scenario(hooks={CODE_STEP: hook}))
    fh.install_fake_review(monkeypatch, stub)
    return root, rid, stub


def _card(text: str, as_id: str) -> str:
    """登记簿里一条假设的全文。"""
    found = re.search(rf"^### \[{as_id}\].*?(?=^### \[|\Z)", text, re.M | re.S)
    assert found, f"登记簿里没有 {as_id}"
    return found.group(0)


def test_receipt_takes_the_forms_real_agents_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, list[str]] = {}

    def make(data: dict[str, Any], attempt: int, reserved: list[str]) -> dict[str, Any]:
        seen["reserved"] = reserved
        data["assumptions"] = {
            "binding": [{"id": "AS1", "参数绑定": "momentum_window，momentum_skip"}],  # 一条假设落到两个字段上，分隔符还是全角的
            "new": [
                {
                    "id": reserved[0],
                    "title": "财报记录的选取与时点对齐",
                    "fields": {
                        "来源": "coder 主动简化",
                        "假设内容": "只用合并报表的累计口径记录",
                        "影响面": "method、data",
                        "影响 milestone": "m1（指标构造）、m2（复合条件）",
                        "影响指标": "R1",
                        "预期影响": "影响很小",
                        "参数绑定": "fin_avail_lag_days, roll_min_periods",
                    },
                },
                {"id": reserved[1], "title": "流动性门槛", "fields": {"假设内容": "取截面前两成", "影响面": "param / method", "参数绑定": None}},
            ],
        }
        return data

    root, rid, stub = _case(tmp_path, monkeypatch, _rewrite_receipt(make))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert stub.counts[CODE_STEP] == 1, "这些写法都该一次收下，不该重派"

    text = (root / "workspace" / rid / "assumptions.md").read_text(encoding="utf-8")
    first, second = seen["reserved"][:2]
    assert "- 参数绑定: momentum_window, momentum_skip\n" in _card(text, "AS1")  # 落盘时统一成英文逗号
    card = _card(text, first)
    assert card.startswith(f"### [{first}] 财报记录的选取与时点对齐\n")
    assert "- 影响面: method、data\n" in card and "- 参数绑定: fin_avail_lag_days, roll_min_periods\n" in card
    assert "- 来源: coder 主动简化\n" in card and "- 状态: assumed\n" in card
    card = _card(text, second)
    assert "- 影响面: param、method\n" in card and "参数绑定" not in card  # 各面统一用顿号并列；没绑字段就不写这一行


def test_malformed_receipt_is_sent_back_without_redoing_the_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def make(data: dict[str, Any], attempt: int, reserved: list[str]) -> dict[str, Any]:
        if attempt == 1:
            data["assumptions"] = {
                "binding": [{"id": "AS1", "参数绑定": "momentum_window = 20（回看窗口）"}],
                "new": [
                    {"id": reserved[0], "title": "流程类假设", "fields": {"假设内容": "略", "影响面": "process"}},
                    {"id": reserved[1], "title": "绑定里带了说明", "fields": {"假设内容": "略", "影响面": "data", "参数绑定": "hk_window（港股窗口）"}},
                    {"id": "AS99", "title": "编号不在预留区间", "fields": {"假设内容": "略", "影响面": "data"}},
                ],
            }
        return data

    root, rid, stub = _case(tmp_path, monkeypatch, _rewrite_receipt(make))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert stub.counts[CODE_STEP] == 2

    task = (root / "workspace" / rid / "flow" / "tasks" / f"{CODE_STEP}.2.md").read_text(encoding="utf-8")
    assert "回执被拒收" in task
    assert "AS1：参数绑定只写 config.py 里的字段名" in task and "'momentum_window = 20（回看窗口）'" in task
    assert "影响面取 data / method / output / param / trading，一条假设跨几个面时用顿号并列（收到 'process'）" in task
    assert "'hk_window（港股窗口）'" in task and "AS99" in task
    # 活已经干完，只是回执有毛病：要告诉接手的人别重干，上一次的回执在哪
    assert "交回的文件和代码不用重做" in task and f"workspace/{rid}/flow/receipts/{CODE_STEP}.1.json" in task
    assert "只处理上面指出的问题；与它无关的内容不要动。" not in task
    first = (root / "workspace" / rid / "flow" / "tasks" / f"{CODE_STEP}.1.md").read_text(encoding="utf-8")
    assert "影响面取 param / data / method / trading / output" in first and "多个用英文逗号隔开" in first  # 写法在首派时就讲清楚

    text = (root / "workspace" / rid / "assumptions.md").read_text(encoding="utf-8")
    assert "流程类假设" not in text and "绑定里带了说明" not in text and "AS99" not in text  # 一份回执要么全收要么全不收
    assert "- 参数绑定: momentum_window\n" in _card(text, "AS1")  # 第二次的回执是桩的默认写法


def test_redispatch_keeps_the_reserved_ids_so_the_old_receipt_can_be_fixed_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """重派沿用上一次预留的假设编号。

    上一次写下的代码注释、回执用的就是这些编号。真实案例里出现过：回执因格式被拒收，重派时换了一段
    新编号，照着旧回执改好再交又因为编号不在新区间里被拒收，两次重派额度就这样用完了。
    """
    ranges: list[list[str]] = []

    def make(data: dict[str, Any], attempt: int, reserved: list[str]) -> dict[str, Any]:
        ranges.append(reserved)
        new = {"id": ranges[0][0], "title": "停牌日的收益口径", "fields": {"假设内容": "停牌日记 0", "影响面": "trading" if attempt > 1 else "交易"}}
        data["assumptions"] = {"new": [new]}  # 第二次照着第一次的回执改：编号不动，只把影响面改对
        return data

    root, rid, stub = _case(tmp_path, monkeypatch, _rewrite_receipt(make))
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review" and stub.counts[CODE_STEP] == 2
    assert len(ranges) == 2 and ranges[0] == ranges[1] and len(ranges[0]) >= 3
    text = (root / "workspace" / rid / "assumptions.md").read_text(encoding="utf-8")
    assert "- 影响面: trading\n" in _card(text, ranges[0][0])

    # 编号进了登记簿之后就不能再沿用：下一次预留从它后面接着排，水位也没有被往回拨
    from tools import state as st
    from tools.flowlib import steps as sp
    from tools.flowlib import tasks as tk
    from tools.flowlib.engine import Engine

    state = st.load_state(root, rid)
    ctx = Engine(root, rid, "claude_code").ctx()
    step = sp.code_step(ctx, state["milestones"][0])
    fresh = tk.reserve_assumption_ids(ctx, step, prior=ranges[0])
    assert not set(fresh) & set(ranges[0]) and int(fresh[0][2:]) > int(ranges[0][-1][2:])
    assert int(state["flow"]["as_reserved"]) >= int(ranges[0][-1][2:])


def test_impact_and_binding_grammar() -> None:
    assert rc.normalize_impact("method") == "method"
    assert rc.normalize_impact(" method、data ") == "method、data"
    assert rc.normalize_impact("param / method") == rc.normalize_impact("param,method") == rc.normalize_impact("param+method") == "param、method"
    assert rc.normalize_impact("data、data") == "data"
    for bad in ("", None, "process", "method（主要）", "data、process"):
        assert rc.normalize_impact(bad) is None

    assert rc.normalize_binding("cost_bps") == "cost_bps"
    assert rc.normalize_binding("a，b、 c ; a") == "a, b, c"
    assert rc.normalize_binding("config.window") == "config.window"
    for bad in ("", None, "window = 8", "g_exp_source（源切换开关）", "8", "a,, b-c"):
        assert rc.normalize_binding(bad) is None

    # 改口径后的重跑档位：跨几个面的取最重的一面，认不出的写法取最重一档；内核与 Excel 工具口径一致
    for value, scope in [("output", "output"), ("param、method", "method"), ("method、data", "data"), ("trading / output", "trading"), ("process", "data"), ("", "data"), ("method（主要）", "data")]:
        assert decisions.impact_scope(value) == scope and ax.impact_scope(value) == scope
    assert ax.impact_rank("param、trading") == ax.impact_rank("param") < ax.impact_rank("谁也认不出") == ax.impact_rank("data")
    assert ax.merged_scope([{"impact": "output"}, {"impact": "param、trading"}]) == "param"
    assert ax.merged_scope([{"impact": "trading"}, {"impact": "process"}]) == "data"

    assert ax.bind_fields("a, b") == ["a", "b"] and ax.bind_fields("cost_bps") == ["cost_bps"] and ax.bind_fields("") == []
    assert ax.bind_fields("g_exp_source（源切换开关）, w = 8") == ["g_exp_source（源切换开关）, w = 8"]  # 带说明的旧写法原样当成一个
