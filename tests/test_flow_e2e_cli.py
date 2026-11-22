"""从命令行入口把玩具案例完整走一遍：flow init → next / done / exec → decide → accept。

内核函数层的行为在 test_flow_engine.py、test_flow_decisions.py 里测；这里只确认命令行这一层
（参数解析、输出格式、返回码、看板与钩子索引的刷新）接得上。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_harness as fh  # noqa: E402
from tools import flow  # noqa: E402
from tools import pdf_extract  # noqa: E402
from tools import state as st  # noqa: E402


class Cli:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        self.root, self.capsys = root, capsys
        monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
        monkeypatch.setenv("REPRODUCE_NO_TTY", "1")
        monkeypatch.setattr(pdf_extract, "run_extract", fh.fake_extract)

    def run(self, *argv: str, code: int = 0) -> str:
        self.capsys.readouterr()
        got = flow.main([str(a) for a in argv])
        captured = self.capsys.readouterr()
        assert got == code, f"flow {' '.join(map(str, argv))} 返回 {got}：{captured.out[-800:]}{captured.err[-800:]}"
        return captured.out if got == 0 else captured.out + captured.err

    def json(self, *argv: str, code: int = 0) -> dict[str, Any]:
        out = self.run(*argv, code=code)
        return json.loads(out)  # 整段输出必须是一个 JSON 对象


def _drive(cli: Cli, rid: str, stub: fh.Stub, out: dict[str, Any]) -> dict[str, Any]:
    """照 SKILL 里的主循环推进，直到停下。每条命令的输出就是下一步的依据。"""
    for _ in range(200):
        if out.get("halt"):
            return out
        orders = out["orders"]
        assert orders, out
        done: list[str] = []
        for order in orders:
            if order["kind"] == "exec":
                out = cli.json("exec", rid, order["step_id"], "--host", "claude_code")  # 测试里前台跑；外审引擎是假的
                assert out["exec"]["state"] in ("success", "failed")
                break
            if order["kind"] == "judge":
                stub.judge(order)
            else:
                assert "只回一行" in order["prompt_inline"] and (cli.root / order["prompt_file"]).is_file()
                stub.run(order)
            done.append(order["step_id"])
        else:
            out = cli.json("done", rid, *done, "--no-usage", "--host", "claude_code")
            assert all(item["ok"] for item in out["collected"]), out["collected"]
    raise AssertionError("没有停下")


def test_toy_case_through_the_command_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = fh.make_root(tmp_path)
    cli = Cli(root, monkeypatch, capsys)
    pdf = root / "reports" / "toy.pdf"
    pdf.write_bytes(b"%PDF-1.4 toy")

    summary = cli.json("init", str(pdf), "--slug", "toy", "--mode", "interactive", "--until", "plan", "--host", "claude_code", "--json")
    rid = summary["report_id"]
    assert rid == "r001_toy" and summary["gate"] == "PASS" and summary["pages"] == 3
    assert (root / "workspace" / rid / "board.html").is_file() and (root / "workspace" / "board.html").is_file()
    # 同一份 PDF 再建一次：撞库，停在检查点等人决定
    again = cli.json("init", str(pdf), "--slug", "toy_again", "--host", "claude_code", "--json")
    assert again["duplicates"] == [rid]
    dup = cli.json("next", again["report_id"], "--host", "claude_code")
    assert dup["halt"]["checkpoints"][0]["name"] == "pdf_duplicate"
    out = cli.json("decide", again["report_id"], "cp_01", "--choice", "abort", "--quote", "重复了，不做", "--host", "claude_code")
    assert out["decision"]["status"] == "aborted" and out["halt"]["reason"] == "terminal"

    stub = fh.Stub(root, rid, fh.Scenario(reviews={"result": [[{"severity": "major", "description": "归因缺量级分解"}], []]}))
    fh.install_fake_review(monkeypatch, stub)
    out = _drive(cli, rid, stub, cli.json("next", rid, "--host", "claude_code"))
    seen = []
    while out["halt"]["checkpoints"][0]["name"] != "final_review":
        cp = out["halt"]["checkpoints"][0]
        seen.append(cp["name"])
        # 钩子用的索引里登记了待决的检查点
        index = json.loads((root / "workspace" / "_registry" / "guard_index.json").read_text(encoding="utf-8"))
        assert [p["id"] for p in index["cases"][rid]["pending"]] == [cp["id"]]
        text = cli.run("status", rid)
        assert cp["id"] in text and "等" in text
        out = cli.json("decide", rid, cp["id"], "--choice", "approve", "--quote", "看过了，继续", "--host", "claude_code")
        assert out["decision"]["credential"] == "self_report"
        out = _drive(cli, rid, stub, out)
    assert seen == ["spec_final", "until", "plan_final", "verify_done"]
    assert "result_audit.rule.r1#1" in stub.calls and "result_audit.fix.verifier.r1#1" in stub.calls

    # 只读命令
    status = cli.json("status", rid, "--json")
    assert status["status"] == "awaiting_review" and status["verdict"]["result"] == "pass"
    assert "final_review" in json.dumps(status, ensure_ascii=False)
    listing = cli.run("status")
    assert rid in listing and "r002_toy_again" in listing
    assert "没有过期的步骤" in cli.run("stale", rid)
    assert cli.run("get", rid, "element", "F1", "--step", "implement.m1.code").startswith("### [F1]")
    assert "门禁通过" in cli.run("gate", rid, "verify", "--no-record")
    assert cli.run("precheck", rid, "--stage", "result")
    cost = cli.run("cost", rid, "--steps")
    assert "共派发" in cost and "quant-extractor" in cost and "extract.main#1" in cost and "主会话调用内核" in cost
    ledger = cli.json("cost", rid, "--json")
    assert ledger["source"] == "ledger" and ledger["totals"]["dispatches"] == len(ledger["rows"]) >= len(stub.calls)
    assert all(r["task_bytes"] > 0 for r in ledger["rows"] if r["kind"] == "dispatch")
    calls = ledger["kernel_calls"]
    assert calls["by_command"]["done"] >= 5 and calls["by_command"]["decide"] == 4 and calls["out_bytes"] > 0
    # 主会话每派发一次，平均不到两次内核调用（验收目标是不超过 4 次）
    assert calls["total"] / ledger["totals"]["dispatches"] < 2.5
    external = [r for r in ledger["rows"] if r["kind"] == "exec"]
    assert external and all(r["outcome"] == "done" and r.get("input_bytes") for r in external)  # 外审同样入账
    cli.run("board", rid)
    board = (root / "workspace" / rid / "board.html").read_text(encoding="utf-8")
    assert "最终评审" in board and "verify_done" not in board  # 看板说人话，不露内部名

    # 不带原话不能收尾；带上才行
    assert "原话" in cli.run("accept", rid, code=1)
    done = cli.json("accept", rid, "--quote", "结果可以，收尾")
    assert done["accepted"]["status"] == "done"
    assert st.load_state(root, rid)["status"] == "done"
    assert cli.json("next", rid, "--host", "claude_code")["halt"]["reason"] == "terminal"
    index = json.loads((root / "workspace" / "_registry" / "guard_index.json").read_text(encoding="utf-8"))
    assert not index["cases"].get(rid, {}).get("pending") and not index["cases"].get(rid, {}).get("inflight")


def test_command_line_reports_errors_plainly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = fh.make_root(tmp_path)
    cli = Cli(root, monkeypatch, capsys)
    pdf = root / "reports" / "toy.pdf"
    pdf.write_bytes(b"%PDF-1.4 toy")
    rid = cli.json("init", str(pdf), "--slug", "toy", "--host", "claude_code", "--json")["report_id"]
    out = cli.json("next", rid, "--host", "claude_code")
    step = out["orders"][0]["step_id"]
    # 什么都没交就说做完了：点收不过，返回码非零，输出里有缺什么，并且直接给出重派的工单
    out = cli.json("done", rid, step, "--no-usage", "--host", "claude_code", code=1)
    assert out["collected"][0]["class"] == "incomplete" and any("spec.md" in m for m in out["collected"][0]["missing"])
    assert out["orders"][0]["step_id"] == "extract.main#2"
    assert "没有步骤" in cli.run("done", rid, "plan.main", "--no-usage", code=1)
    assert "没有检查点" in cli.run("decide", rid, "cp_09", "--choice", "approve", "--quote", "x", code=1)
    assert "不在最终评审" in cli.run("accept", rid, "--quote", "收尾", code=1)
    out = cli.json("fail", rid, "extract.main", "--class", "blocked", "--note", "PDF 是扫描件，读不出文字", "--host", "claude_code")
    assert out["failed"]["class"] == "blocked" and out["halt"]["checkpoints"][0]["name"] == "step_blocked"
    assert "读不出文字" in out["halt"]["checkpoints"][0]["reason"]
    text = cli.run("next", rid, "--text", "--host", "claude_code")
    assert text.startswith("停：") and "{" not in text.splitlines()[0]
