"""钩子与事后核对：禁读护栏（tools/guard.py）、「人在场」记录（tools/presence.py）、
它们读的索引（flowlib/guardindex.py），以及没有钩子的宿主上的事后核对（usage.forbidden_reads）。

两个钩子脚本按线上的方式跑：独立进程、python3 -I -S、标准输入给一段 JSON。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_harness as fh  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import checkpoints as cps  # noqa: E402
from tools.flowlib import guardindex  # noqa: E402
from tools.flowlib import usage as us  # noqa: E402
from tools.flowlib.engine import Engine  # noqa: E402

CODER = "quant-report-reproduce:quant-coder"


def _hook(script: str, payload: Any, root: Path | None = None, raw: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", **({"CLAUDE_PROJECT_DIR": str(root)} if root else {})}
    return subprocess.run(
        [sys.executable, "-I", "-S", str(REPO_ROOT / "tools" / script)],
        input=raw if raw is not None else json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _guard(root: Path, tool: str, tool_input: dict[str, Any], agent: str | None = None, agent_type: str | None = None) -> subprocess.CompletedProcess[str]:
    payload: dict[str, Any] = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(root), "session_id": "s1"}
    if agent:
        payload.update(agent_id=agent, agent_type=agent_type)
    return _hook("guard.py", payload, root)


@pytest.fixture()
def running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, dict[str, dict[str, Any]]]:
    """一个 hard 案例，停在「m1 的验证、内审与 m2 的编码同时在途」的时刻。返回（根, 编号, 在途步骤）。"""
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch)
    stub = fh.Stub(root, rid, fh.Scenario(difficulty="hard", milestones=3))
    fh.install_fake_review(monkeypatch, stub)
    fh.drive(root, rid, stub, until=lambda o: len([x for x in o["orders"] if x["kind"] == "dispatch"]) >= 3)
    guardindex.sync(root, rid)
    index = json.loads((root / guardindex.INDEX_REL).read_text(encoding="utf-8"))
    return root, rid, index["cases"][rid]["inflight"]


# ---------------------------------------------------------------------------
# 护栏
# ---------------------------------------------------------------------------


def test_guard_is_silent_outside_a_reproduce_workspace(tmp_path: Path) -> None:
    plain = tmp_path / "elsewhere"
    plain.mkdir()
    assert _guard(plain, "Write", {"file_path": str(plain / "workspace" / "x" / "state.json")}).returncode == 0
    assert _hook("guard.py", None, plain, raw="这不是 JSON").returncode == 0
    assert _hook("guard.py", ["不是对象"], plain).returncode == 0


def test_nobody_may_write_state_files_directly(running: tuple[Path, str, dict]) -> None:
    root, rid, _steps = running
    for tool, key, name in (("Write", "file_path", "state.json"), ("Edit", "file_path", "events.jsonl"), ("MultiEdit", "file_path", "state.v1.json")):
        result = _guard(root, tool, {key: str(root / "workspace" / rid / name)})
        assert result.returncode == 2 and "flow decide" in result.stderr, (tool, result.stderr)
    for rel in ("workspace/_registry/presence.jsonl", "workspace/_registry/guard_index.json", "workspace/_registry/guard_agents.json"):
        assert _guard(root, "Write", {"file_path": rel}).returncode == 2
    assert _guard(root, "Bash", {"command": "echo '{}' >> workspace/_registry/presence.jsonl"}).returncode == 2
    # 相对路径、带 .. 的写法照样认得出
    assert _guard(root, "Edit", {"file_path": f"workspace/{rid}/spec/../state.json"}).returncode == 2
    # 别的文件、主会话的读取都不拦
    assert _guard(root, "Write", {"file_path": str(root / "workspace" / rid / "plan.md")}).returncode == 0
    assert _guard(root, "Read", {"file_path": str(root / "workspace" / rid / "state.json")}).returncode == 0
    assert _guard(root, "Read", {"file_path": str(root / "workspace" / rid / "spec" / "report_text.md")}).returncode == 0
    log = [json.loads(line) for line in (root / "workspace" / rid / "flow" / "guard.log").read_text(encoding="utf-8").splitlines()]
    assert len(log) == 4 and {entry["tool"] for entry in log} == {"Write", "Edit", "MultiEdit"}


def test_subagent_reads_are_checked_against_its_step(running: tuple[Path, str, dict]) -> None:
    root, rid, steps = running
    coder = steps["implement.m2.code"]
    ws = f"workspace/{rid}"

    def read(rel: str, agent: str = "agent-coder", agent_type: str = CODER) -> int:
        return _guard(root, "Read", {"file_path": str(root / rel)}, agent, agent_type).returncode

    # 第一次读到自己的任务文件：放行，并记下这个 agent 在做哪一步
    assert read(coder["task"]) == 0
    mapping = json.loads((root / "workspace" / "_registry" / "guard_agents.json").read_text(encoding="utf-8"))
    assert mapping["agent-coder"]["step"] == "implement.m2.code" and mapping["agent-coder"]["case"] == rid
    assert read(coder["task"]) == 0 and read(coder["receipt"]) == 0  # 自己的任务文件与回执随时可读
    # 禁读：研报原文转写、状态与事件流、审阅包、别的步骤的任务文件与回执
    for rel in (f"{ws}/spec/report_text.md", f"{ws}/spec/tables_extracted.md", f"{ws}/state.json", f"{ws}/events.jsonl", f"{ws}/board.html", f"{ws}/reviews/cp_01_x.md", steps["implement.m1.verify"]["task"], steps["implement.m1.audit"]["receipt"]):
        assert read(rel) == 2, rel
    denied = _guard(root, "Read", {"file_path": str(root / ws / "spec" / "report_text.md")}, "agent-coder", CODER)
    assert "上下文包" in denied.stderr and "flow get" in denied.stderr
    # 该读的照常读
    for rel in (f"{ws}/spec/spec.md", f"{ws}/plan.md", f"src/{rid}/strategy.py", "templates/factor.md"):
        assert read(rel) == 0, rel
    # 数据文件不用读文件工具打开；写脚本取数没问题
    assert read("data/toy_price.parquet") == 2
    assert _guard(root, "Bash", {"command": f"python src/{rid}/main.py > output/{rid}/results/run.log 2>&1; tail -5 output/{rid}/results/run.log"}, "agent-coder", CODER).returncode == 0
    # 命令里碰禁读路径同样拦；产物目录（扰动结果、运行缓存）脚本要往里写，不拦命令，只拦直接打开
    assert _guard(root, "Bash", {"command": f"cat {ws}/spec/report_text.md | head"}, "agent-coder", CODER).returncode == 2
    assert _guard(root, "Bash", {"command": f"grep -n RankIC {root}/{ws}/state.json"}, "agent-coder", CODER).returncode == 2
    assert _guard(root, "Bash", {"command": f"python src/{rid}/main.py --out output/{rid}/results/perturb_check/"}, "agent-coder", CODER).returncode == 0
    assert read(f"output/{rid}/results/perturb_check/metrics.json") == 2
    assert _guard(root, "Grep", {"pattern": "RankIC", "path": str(root / ws / "reviews")}, "agent-coder", CODER).returncode == 2
    assert _guard(root, "Glob", {"pattern": "*.md", "path": str(root / ws / "flow" / "tasks")}, "agent-coder", CODER).returncode == 2
    # 拦下的每一次都留痕，内核下次点收时并入事件流
    log = [json.loads(line) for line in (root / ws / "flow" / "guard.log").read_text(encoding="utf-8").splitlines()]
    assert all(entry["steps"] == ["implement.m2.code"] for entry in log) and len(log) >= 10
    engine = Engine(root, rid, host="claude_code")
    engine._ingest_guard_log()
    denied_events = [r for r in st.read_event_records(root, rid) if r["event"] == "guard:denied"]
    assert len(denied_events) == len(log) and denied_events[0]["payload"]["agent_type"] == CODER
    engine._ingest_guard_log()  # 再并一次不会重复入账
    assert len([r for r in st.read_event_records(root, rid) if r["event"] == "guard:denied"]) == len(log)


def test_unmapped_and_unknown_agents(running: tuple[Path, str, dict]) -> None:
    root, rid, _steps = running
    source = {"file_path": str(root / "workspace" / rid / "spec" / "report_text.md")}
    # 还没读过任务文件的量化角色：按同角色在途步骤的禁读清单处理
    assert _guard(root, "Read", source, "agent-new", CODER).returncode == 2
    assert _guard(root, "Read", source, "agent-v", "quant-verifier").returncode == 2  # 不带插件前缀的角色名也认
    # 这个角色当前没有在途步骤：无从判断，放行
    assert _guard(root, "Read", source, "agent-r", "quant-reporter").returncode == 0
    # 认不出来的 agent 一律放行（主会话自己起的搜索 agent 等）
    assert _guard(root, "Read", source, "agent-x", "Explore").returncode == 0
    # 未对上具体步骤时，不拦数据文件（可能是别的角色的合理读取）
    assert _guard(root, "Read", {"file_path": str(root / "data" / "x.parquet")}, "agent-new", CODER).returncode == 0


def test_extractor_may_read_the_source_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch)
    order = Engine(root, rid, host="claude_code").advance()["orders"][0]
    guardindex.sync(root, rid)
    agent = ("agent-e", "quant-report-reproduce:quant-extractor")
    assert _guard(root, "Read", {"file_path": str(root / order["prompt_file"])}, *agent).returncode == 0
    assert _guard(root, "Read", {"file_path": str(root / "workspace" / rid / "spec" / "report_text.md")}, *agent).returncode == 0
    assert _guard(root, "Read", {"file_path": str(root / "workspace" / rid / "state.json")}, *agent).returncode == 2


def test_guard_fails_open_when_its_inputs_are_broken(running: tuple[Path, str, dict]) -> None:
    root, rid, _steps = running
    source = {"file_path": str(root / "workspace" / rid / "spec" / "report_text.md")}
    (root / guardindex.INDEX_REL).write_text("{坏的", encoding="utf-8")
    assert _guard(root, "Read", source, "agent-new", CODER).returncode == 0
    (root / guardindex.INDEX_REL).unlink()
    assert _guard(root, "Read", source, "agent-new", CODER).returncode == 0
    # 写保护不依赖索引
    assert _guard(root, "Write", {"file_path": str(root / "workspace" / rid / "state.json")}).returncode == 2


def test_index_follows_the_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch, mode="interactive")
    stub = fh.Stub(root, rid, fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    out = fh.drive(root, rid, stub)
    guardindex.sync(root, rid)
    entry = json.loads((root / guardindex.INDEX_REL).read_text(encoding="utf-8"))["cases"][rid]
    cp = out["halt"]["checkpoints"][0]
    assert entry["inflight"] == {} and [p["name"] for p in entry["pending"]] == ["spec_final"] and entry["pending"][0]["code"]
    fh.decide(root, rid, cp["id"], "approve", "继续")
    guardindex.sync(root, rid)
    assert rid not in json.loads((root / guardindex.INDEX_REL).read_text(encoding="utf-8"))["cases"]  # 没有在途也没有待决：不留条目
    guardindex.sync(root, "r999_no_such_case")  # 不存在的案例不抛


# ---------------------------------------------------------------------------
# 「人在场」记录
# ---------------------------------------------------------------------------


def _presence(root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = _hook("presence.py", {"cwd": str(root), "session_id": "s1", **payload}, root)
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""  # 永远静默
    log = root / "workspace" / "_registry" / "presence.jsonl"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def test_presence_records_only_while_a_checkpoint_is_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch, mode="interactive")
    guardindex.sync(root, rid)
    prompt = {"hook_event_name": "UserPromptSubmit", "prompt": "先随便聊聊，别记我"}
    assert _presence(root, prompt) == []  # 没有检查点在等人：不留用户输入

    stub = fh.Stub(root, rid, fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    cp = fh.drive(root, rid, stub)["halt"]["checkpoints"][0]
    guardindex.sync(root, rid)
    code = next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"])["code"]
    entries = _presence(root, {"hook_event_name": "UserPromptSubmit", "prompt": f"spec 看过了，放行 {code}\n" + "啊" * 5000})
    assert len(entries) == 1 and entries[0]["source"] == "prompt" and len(entries[0]["text"]) == 2000 and code in entries[0]["text"]
    # 子 agent 里发生的事不是人说的话；别的工具、空输入都不记
    assert len(_presence(root, {"hook_event_name": "UserPromptSubmit", "prompt": "我是子 agent", "agent_id": "a1"})) == 1
    assert len(_presence(root, {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})) == 1
    assert len(_presence(root, {"hook_event_name": "UserPromptSubmit", "prompt": "   "})) == 1
    # 提问工具的回答连同题面一起记
    ask = {
        "hook_event_name": "PostToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": [{"question": f"[{cp['id']} · {code}] spec 定稿，是否继续？", "options": [{"label": "通过"}, {"label": "修改"}]}]},
        "tool_response": {"answers": {"q1": "通过"}},
    }
    entries = _presence(root, ask)
    assert entries[-1]["source"] == "ask" and "通过" in entries[-1]["text"] and code in entries[-1]["question"]
    # 内核据此给出钩子级凭据
    checkpoint = next(c for c in st.load_state(root, rid)["checkpoints"] if c["id"] == cp["id"])
    assert cps.credential_for(root, checkpoint, "spec 看过了，放行") == "hook"
    result = fh.decide(root, rid, cp["id"], "approve", "spec 看过了，放行")
    assert result["credential"] == "hook"


def test_presence_prunes_old_entries_and_survives_garbage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch, mode="interactive")
    stub = fh.Stub(root, rid, fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    fh.drive(root, rid, stub)
    guardindex.sync(root, rid)
    log = root / "workspace" / "_registry" / "presence.jsonl"
    old = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=20)).isoformat(timespec="seconds")
    recent = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=2)).isoformat(timespec="seconds")
    log.write_text(json.dumps({"ts": old, "source": "prompt", "text": "三周前"}) + "\n不是 JSON\n" + json.dumps({"ts": recent, "source": "prompt", "text": "前天"}) + "\n", encoding="utf-8")
    entries = _presence(root, {"hook_event_name": "UserPromptSubmit", "prompt": "今天"})
    assert [e["text"] for e in entries] == ["前天", "今天"]  # 只保留最近 14 天
    assert _hook("presence.py", None, root, raw="{{{").returncode == 0
    assert _hook("presence.py", {"hook_event_name": "UserPromptSubmit", "prompt": "x", "cwd": str(tmp_path / "nowhere")}).returncode == 0


# ---------------------------------------------------------------------------
# 没有钩子的宿主：事后核对
# ---------------------------------------------------------------------------


def test_forbidden_reads_scans_tool_calls_only(tmp_path: Path) -> None:
    forbid = ["workspace/r1/spec/report_text.md", "workspace/r1/state.json", "output/r1/results/cache/"]
    own = "workspace/r1/flow/tasks/implement.m1.code.1.md"

    def line(*blocks: dict[str, Any]) -> str:
        return json.dumps({"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}, ensure_ascii=False)

    transcript = tmp_path / "agent.jsonl"
    transcript.write_text(
        "\n".join(
            [
                # 任务文件的正文里列着禁读清单：读任务文件、在正文里提到路径都不算
                line({"type": "tool_use", "name": "Read", "input": {"file_path": f"/root/{own}"}}),
                json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "不要读：workspace/r1/spec/report_text.md"}]}}, ensure_ascii=False),
                line({"type": "text", "text": "我不会去读 workspace/r1/state.json"}),
                # 真的去读了
                line({"type": "tool_use", "name": "Bash", "input": {"command": "head -50 workspace/r1/spec/report_text.md"}}),
                # 往缓存目录里写是正常的；用读文件工具打开才算
                line({"type": "tool_use", "name": "Bash", "input": {"command": "python main.py --cache output/r1/results/cache/"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert us.forbidden_reads(transcript, "claude_code", forbid, allowed=[own]) == ["workspace/r1/spec/report_text.md"]
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(line({"type": "tool_use", "name": "Read", "input": {"file_path": "/root/output/r1/results/cache/big.pkl"}}) + "\n")
    assert us.forbidden_reads(transcript, "claude_code", forbid, allowed=[own]) == ["output/r1/results/cache/", "workspace/r1/spec/report_text.md"]

    codex = tmp_path / "rollout.jsonl"
    codex.write_text(
        "\n".join(
            [
                json.dumps({"type": "response_item", "payload": {"type": "message", "content": [{"type": "text", "text": "不要读 workspace/r1/state.json"}]}}, ensure_ascii=False),
                json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": "sed -n 1,40p workspace/r1/state.json"})}}),
                json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": "ls output/r1/results/cache/"})}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert us.forbidden_reads(codex, "codex", forbid) == ["workspace/r1/state.json"]
    assert us.forbidden_reads(tmp_path / "missing.jsonl", "codex", forbid) == []
    assert us.forbidden_reads(codex, "codex", []) == []


def test_hooks_config_points_at_scripts_that_exist() -> None:
    config = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    commands = [h["command"] for entries in config.values() for entry in entries for h in entry["hooks"]]
    assert len(commands) == 3 and all(h.startswith("python3 -I -S ") and "${CLAUDE_PLUGIN_ROOT}/tools/" in h for h in commands)
    for command in commands:
        script = command.split("${CLAUDE_PLUGIN_ROOT}/")[1].rstrip('"')
        source = (REPO_ROOT / script).read_text(encoding="utf-8")
        # 钩子脚本以 -I -S 运行：只能用标准库，不能导入内核
        assert "from tools" not in source and "import tools" not in source and "import yaml" not in source
    assert set(config) == {"PreToolUse", "UserPromptSubmit", "PostToolUse"}
    assert "Read" in config["PreToolUse"][0]["matcher"] and config["PostToolUse"][0]["matcher"] == "AskUserQuestion"
