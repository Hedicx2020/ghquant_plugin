"""tools/flowlib/usage.py：两个宿主会话记录的用量解析。夹具是按真实记录的键结构人造的。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.flowlib import usage as us  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------


def _assistant(mid: str, ts: str, usage: dict, blocks: list[dict]) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "cwd": "/work/proj",
        "message": {"id": mid, "model": "claude-opus-5-5", "role": "assistant", "usage": usage, "content": blocks},
    }


def _claude_records() -> list[dict]:
    u1 = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 50}
    u2 = {"input_tokens": 5, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 1000, "output_tokens": 80}
    return [
        {"type": "user", "timestamp": "2026-08-01T01:00:00.000Z", "cwd": "/work/proj", "message": {"role": "user", "content": "复现 r009_demo 的 m2"}},
        # 同一次调用按内容块写成两行，usage 重复
        _assistant("msg_1", "2026-08-01T01:00:05.000Z", u1, [{"type": "text", "text": "先读文件"}]),
        _assistant("msg_1", "2026-08-01T01:00:06.000Z", u1, [{"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}}]),
        {"type": "user", "timestamp": "2026-08-01T01:00:07.000Z", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1"}]}},
        _assistant("msg_2", "2026-08-01T01:00:20.000Z", u2, [{"type": "tool_use", "id": "tu_2", "name": "Bash", "input": {}}, {"type": "tool_use", "id": "tu_3", "name": "Read", "input": {}}]),
        {"type": "attachment", "timestamp": "2026-08-01T01:00:21.000Z"},
        "这一行不是字典",  # type: ignore[list-item]
    ]


def test_parse_claude_subagent_transcript(tmp_path: Path) -> None:
    path = tmp_path / "sess-1" / "subagents" / "agent-abc.jsonl"
    _write_jsonl(path, _claude_records())
    path.with_suffix(".meta.json").write_text(json.dumps({"agentType": "quant-coder", "description": "implement.m2.code#1"}), encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write("{坏行\n")

    s = us.parse_claude_transcript(path, needle="r009_demo")
    assert (s.host, s.role, s.label, s.parent_id) == ("claude_code", "quant-coder", "implement.m2.code#1", "sess-1")
    assert s.mentions and s.error is None and s.model == "claude-opus-5-5" and s.cwd == "/work/proj"
    u = s.usage
    assert (u.uncached_input, u.cache_write, u.cache_read, u.output) == (15, 1200, 1000, 130)  # msg_1 只算一次
    assert u.calls == 2 and u.tool_calls == 3 and s.tools == {"Read": 2, "Bash": 1}
    assert u.peak_context == 5 + 200 + 1000 and u.total_input == 2215
    assert s.started_at == "2026-08-01T01:00:00.000Z" and s.ended_at == "2026-08-01T01:00:21.000Z"
    assert s.seconds == 21.0
    assert not us.parse_claude_transcript(path, needle="r010_other").mentions


def test_parse_claude_main_transcript_and_missing_meta(tmp_path: Path) -> None:
    path = tmp_path / "sess-1.jsonl"
    _write_jsonl(path, _claude_records())
    s = us.parse_claude_transcript(path)
    assert s.role == "main" and s.parent_id is None and s.label is None and s.usage.calls == 2
    sub = tmp_path / "sess-1" / "subagents" / "agent-nometa.jsonl"
    _write_jsonl(sub, _claude_records())
    assert us.parse_claude_transcript(sub).role is None  # 没有元数据文件也能读


def test_parse_claude_takes_max_of_progressive_usage(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write_jsonl(
        path,
        [
            _assistant("m", "2026-08-01T01:00:00Z", {"input_tokens": 3, "output_tokens": 1}, []),
            _assistant("m", "2026-08-01T01:00:01Z", {"input_tokens": 3, "output_tokens": 40}, []),
            _assistant(None, "2026-08-01T01:00:02Z", {"input_tokens": 7, "output_tokens": 2}, []),  # type: ignore[arg-type]
        ],
    )
    u = us.parse_claude_transcript(path).usage
    assert (u.uncached_input, u.output, u.calls) == (10, 42, 2)


def test_claude_project_dir_and_find(tmp_path: Path) -> None:
    root = Path("/Users/someone/report_reproduce")
    project = us.claude_project_dir(root, home=tmp_path)
    assert project == tmp_path / ".claude" / "projects" / "-Users-someone-report-reproduce"
    assert us.find_claude_transcripts(root, home=tmp_path) == []
    _write_jsonl(project / "s1.jsonl", [])
    _write_jsonl(project / "s1" / "subagents" / "agent-a.jsonl", [])
    (project / "s1" / "subagents" / "agent-a.meta.json").write_text("{}", encoding="utf-8")
    found = us.find_claude_transcripts(root, home=tmp_path)
    assert [p.name for p in found] == ["s1.jsonl", "agent-a.jsonl"]


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------


def _tc(ts: str, total: tuple[int, int, int, int], last: tuple[int, int, int, int] | None) -> dict:
    def pack(v: tuple[int, int, int, int]) -> dict:
        return {"input_tokens": v[0], "cached_input_tokens": v[1], "cache_write_input_tokens": 0, "output_tokens": v[2], "reasoning_output_tokens": v[3], "total_tokens": v[0] + v[2]}

    info = {"total_token_usage": pack(total), "last_token_usage": pack(last) if last else None}
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": info}}


def _meta(ts: str, sid: str, cwd: str, source, originator: str = "codex_exec") -> dict:
    return {"timestamp": ts, "type": "session_meta", "payload": {"id": sid, "cwd": cwd, "originator": originator, "source": source}}


def _tool(ts: str, kind: str, name: str) -> dict:
    return {"timestamp": ts, "type": "response_item", "payload": {"type": kind, "name": name}}


def _codex_main(cwd: str = "/work/proj") -> list[dict]:
    return [
        _meta("2026-09-25T04:07:00.000Z", "main-1", cwd, "exec"),
        {"timestamp": "2026-09-25T04:07:01.000Z", "type": "event_msg", "payload": {"type": "task_started"}},
        {"timestamp": "2026-09-25T04:07:01.000Z", "type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "high"}},
        {"timestamp": "2026-09-25T04:07:02.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "审查 workspace/r010_demo/spec"}},
        {"timestamp": "2026-09-25T04:07:03.000Z", "type": "event_msg", "payload": {"type": "token_count", "info": None}},
        _tc("2026-09-25T04:07:10.000Z", (1000, 0, 50, 20), (1000, 0, 50, 20)),
        _tool("2026-09-25T04:07:11.000Z", "custom_tool_call", "exec"),
        _tc("2026-09-25T04:07:20.000Z", (3000, 900, 120, 60), (2000, 900, 70, 40)),
        _tc("2026-09-25T04:07:20.500Z", (3000, 900, 120, 60), (2000, 900, 70, 40)),  # 重复上报
        _tool("2026-09-25T04:07:21.000Z", "function_call", "spawn_agent"),
        _tool("2026-09-25T04:07:22.000Z", "local_shell_call", ""),
        _tc("2026-09-25T04:08:00.000Z", (7000, 4500, 200, 90), (4000, 3600, 80, 30)),
    ]


def test_parse_codex_fresh_session(tmp_path: Path) -> None:
    path = tmp_path / "rollout-2026-09-25T12-07-00-main-1.jsonl"
    _write_jsonl(path, _codex_main())
    s = us.parse_codex_session(path, needle="r010_demo")
    assert (s.host, s.session_id, s.role, s.parent_id, s.originator) == ("codex", "main-1", "main", None, "codex_exec")
    assert (s.model, s.effort, s.cwd, s.mentions) == ("gpt-5.6-sol", "high", "/work/proj", True)
    u = s.usage
    assert u.total_input == 7000 and u.cache_read == 4500 and u.uncached_input == 2500
    assert (u.output, u.reasoning_output, u.calls, u.peak_context) == (200, 90, 3, 4000)
    assert s.tools == {"exec": 1, "spawn_agent": 1, "local_shell_call": 1} and u.tool_calls == 3
    assert s.inherited_input == 0 and s.seconds == 60.0


def test_parse_codex_forked_subagent_subtracts_inherited_counter(tmp_path: Path) -> None:
    source = {"subagent": {"thread_spawn": {"parent_thread_id": "main-1", "depth": 1, "agent_nickname": "implement.m2.code#1", "agent_role": "quant-coder"}}}
    records = [
        _meta("2026-07-26T02:28:47.000Z", "sub-1", "/work/proj", source),
        # 分叉时重放的父会话记录
        _meta("2026-07-26T02:27:08.000Z", "main-1", "/work/proj", "vscode", originator="codex_vscode"),
        {"timestamp": "2026-07-26T02:28:47.000Z", "type": "turn_context", "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"}},
        # 创建时写入的父会话计数器快照：累计远大于单次
        _tc("2026-07-26T02:28:47.000Z", (4_503_191, 4_000_000, 30_000, 9_000), (155_688, 150_000, 800, 300)),
        _tc("2026-07-26T02:29:30.000Z", (4_703_191, 4_150_000, 31_000, 9_200), (200_000, 150_000, 1_000, 200)),
        _tc("2026-07-26T02:30:30.000Z", (4_953_191, 4_390_000, 32_500, 9_900), (250_000, 240_000, 1_500, 700)),
    ]
    path = tmp_path / "rollout-2026-07-26T10-28-47-sub-1.jsonl"
    _write_jsonl(path, records)
    s = us.parse_codex_session(path)
    assert (s.session_id, s.role, s.parent_id, s.label, s.originator) == ("sub-1", "quant-coder", "main-1", "implement.m2.code#1", "codex_exec")
    assert s.inherited_input == 4_503_191
    u = s.usage
    assert u.total_input == 450_000  # 只算自己的两次调用
    assert u.cache_read == 390_000 and u.uncached_input == 60_000
    assert (u.output, u.reasoning_output, u.calls, u.peak_context) == (2_500, 900, 2, 250_000)


def test_parse_codex_snapshot_with_zero_last(tmp_path: Path) -> None:
    source = {"subagent": {"thread_spawn": {"parent_thread_id": "main-1"}}}
    path = tmp_path / "rollout-2026-07-26T21-13-18-sub-2.jsonl"
    _write_jsonl(
        path,
        [
            _meta("2026-07-26T13:13:18.000Z", "sub-2", "/work/proj", source),
            _tc("2026-07-26T13:13:18.000Z", (8_762_518, 8_000_000, 40_000, 10_000), (0, 0, 0, 0)),
            _tc("2026-07-26T13:14:00.000Z", (8_862_518, 8_090_000, 40_500, 10_100), (100_000, 90_000, 500, 100)),
        ],
    )
    s = us.parse_codex_session(path)
    assert s.role == "subagent" and s.inherited_input == 8_762_518
    assert (s.usage.total_input, s.usage.calls, s.usage.output) == (100_000, 1, 500)


def test_parse_codex_empty_and_garbage(tmp_path: Path) -> None:
    path = tmp_path / "rollout-2026-01-01T00-00-00-x.jsonl"
    path.write_text('{坏行\n"token_count" 但不是 json\n', encoding="utf-8")
    s = us.parse_codex_session(path)
    assert s.usage.total_input == 0 and s.usage.calls == 0 and s.error is None
    assert us.parse_codex_session(tmp_path / "nope.jsonl").error is not None


def test_parse_codex_zst(tmp_path: Path) -> None:
    exe = shutil.which("zstd")
    if not exe:
        pytest.skip("没有 zstd 命令")
    plain = tmp_path / "rollout-2026-09-25T12-07-00-main-1.jsonl"
    _write_jsonl(plain, _codex_main())
    subprocess.run([exe, "-q", "--rm", str(plain)], check=True)
    packed = plain.with_name(plain.name + ".zst")
    s = us.parse_codex_session(packed, needle="r010_demo")
    assert s.session_id == "main-1" and s.usage.total_input == 7000 and s.mentions and s.error is None


def test_find_codex_sessions_filters_by_filename_time(tmp_path: Path) -> None:
    base = tmp_path / ".codex"
    names = [
        "sessions/2026/09/20/rollout-2026-09-20T08-00-00-a.jsonl",
        "sessions/2026/09/25/rollout-2026-09-25T12-07-00-b.jsonl",
        "archived_sessions/rollout-2026-09-26T09-00-00-c.jsonl.zst",
        "sessions/2026/10/01/rollout-2026-10-01T00-00-00-d.jsonl",
        "sessions/odd-name.jsonl",
    ]
    for name in names:
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text("", encoding="utf-8")
    assert len(us.find_codex_sessions(home=tmp_path)) == 5
    since = datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc)
    until = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    found = [p.name for p in us.find_codex_sessions(since, until, home=tmp_path)]
    # 文件名时间按 ±36 小时粗筛；取不到时间的文件不排除
    assert found == ["odd-name.jsonl", "rollout-2026-09-25T12-07-00-b.jsonl", "rollout-2026-09-26T09-00-00-c.jsonl.zst"]
    assert us.codex_session_time(Path("rollout-2026-09-25T12-07-00-b.jsonl")) == datetime(2026, 9, 25, 12, 7, 0)
    assert us.codex_session_time(Path("odd.jsonl")) is None


# ---------------------------------------------------------------------------
# 按案例汇总
# ---------------------------------------------------------------------------


def test_collect_case_usage_follows_parent_links_and_window(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "home"
    sessions = home / ".codex" / "sessions" / "2026" / "09" / "25"
    _write_jsonl(sessions / "rollout-2026-09-25T12-07-00-main-1.jsonl", _codex_main(str(root)))
    child_source = {"subagent": {"thread_spawn": {"parent_thread_id": "main-1", "agent_role": "explorer"}}}
    _write_jsonl(  # 子代理自己没提案例编号，跟着父会话算进来
        sessions / "rollout-2026-09-25T12-09-00-sub-1.jsonl",
        [_meta("2026-09-25T04:09:00.000Z", "sub-1", str(root), child_source), _tc("2026-09-25T04:09:30.000Z", (500, 0, 10, 0), (500, 0, 10, 0))],
    )
    other = [r for r in _codex_main(str(root))]
    other[0] = _meta("2026-09-25T04:07:00.000Z", "main-2", str(root), "exec")
    other[3] = {"timestamp": "2026-09-25T04:07:02.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "别的案例"}}
    _write_jsonl(sessions / "rollout-2026-09-25T12-08-00-main-2.jsonl", other)  # 同工作区但没提这个案例
    elsewhere = [r for r in _codex_main("/somewhere/else")]
    elsewhere[0] = _meta("2026-09-25T04:07:00.000Z", "main-3", "/somewhere/else", "exec")
    _write_jsonl(sessions / "rollout-2026-09-25T12-10-00-main-3.jsonl", elsewhere)  # 别的工作目录
    late = [dict(r, timestamp=r["timestamp"].replace("2026-09-25", "2026-09-26")) for r in _codex_main(str(root))]
    late[0] = _meta("2026-09-26T04:07:00.000Z", "main-4", str(root), "exec")
    _write_jsonl(home / ".codex" / "sessions" / "2026" / "09" / "26" / "rollout-2026-09-26T12-07-00-main-4.jsonl", late)  # 时间窗之外

    state = {"created_at": "2026-09-25T10:53:41+08:00", "updated_at": "2026-09-25T17:37:25+08:00"}
    found = us.collect_case_usage(root, "r010_demo", state, hosts=("codex",), home=home)
    assert sorted(s.session_id for s in found) == ["main-1", "sub-1"]
    summary = us.summarize(found)
    assert summary["sessions"] == 2 and summary["total"]["total_input"] == 7500
    assert set(summary["groups"]) == {"codex/main", "codex/explorer"}
    assert summary["groups"]["codex/main"]["calls"] == 3

    since, until = us.case_window(state)  # 前后各留一小时
    assert since == datetime(2026, 9, 25, 1, 53, 41, tzinfo=timezone.utc) and until.tzinfo is not None
    assert us.case_window({}) == (None, None)


def test_collect_case_usage_claude_host(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "home"
    project = us.claude_project_dir(root, home)
    _write_jsonl(project / "s1.jsonl", _claude_records())
    _write_jsonl(project / "s1" / "subagents" / "agent-a.jsonl", [r for r in _claude_records() if isinstance(r, dict) and r.get("type") == "assistant"])
    found = us.collect_case_usage(root, "r009_demo", {}, hosts=("claude_code",), home=home)
    assert sorted(s.session_id for s in found) == ["agent-a", "s1"]  # 子代理没提编号，跟着主会话
    assert us.collect_case_usage(root, "r999_none", {}, hosts=("claude_code",), home=home) == []


def test_sessions_that_cannot_belong_to_the_case_are_not_read_to_the_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """看板逐案例归集用量时，明显无关的会话不整份解析：结果不变，只是不白读。"""
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "home"
    state = {"created_at": "2026-08-01T09:00:00+08:00", "updated_at": "2026-08-01T09:30:00+08:00"}

    # Claude Code：案例收尾之后才开始的会话，开头几行就能排除
    project = us.claude_project_dir(root, home)
    _write_jsonl(project / "s1.jsonl", _claude_records())
    later = [dict(r, timestamp=r["timestamp"].replace("2026-08-01", "2026-11-21")) if isinstance(r, dict) else r for r in _claude_records()]
    _write_jsonl(project / "s2.jsonl", later)
    assert us.claude_transcript_start(project / "s1.jsonl") == datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    assert us.claude_transcript_start(project / "s2.jsonl") == datetime(2026, 11, 21, 1, 0, tzinfo=timezone.utc)
    _write_jsonl(project / "s3.jsonl", [{"type": "summary"}, "不是字典"])  # type: ignore[list-item]
    assert us.claude_transcript_start(project / "s3.jsonl") is None  # 读不到时间的不排除，照旧整份解析

    parsed: list[str] = []
    real_claude = us.parse_claude_transcript
    monkeypatch.setattr(us, "parse_claude_transcript", lambda path, **kw: (parsed.append(path.name), real_claude(path, **kw))[1])
    found = us.collect_case_usage(root, "r009_demo", state, hosts=("claude_code",), home=home)
    assert [s.session_id for s in found] == ["s1"] and sorted(parsed) == ["s1.jsonl", "s3.jsonl"]
    assert [s.session_id for s in us.collect_case_usage(root, "r009_demo", {}, hosts=("claude_code",), home=home)] == ["s1", "s2"]  # 没有时间窗时不预筛

    # Codex：别的工作目录的会话读到元信息就停
    sessions = home / ".codex" / "sessions" / "2026" / "08" / "01"
    mine = sessions / "rollout-2026-08-01T09-05-00-main-1.jsonl"
    theirs = sessions / "rollout-2026-08-01T09-06-00-main-9.jsonl"
    day = lambda records: [dict(r, timestamp=r["timestamp"].replace("2026-09-25T04", "2026-08-01T01")) for r in records]  # noqa: E731
    _write_jsonl(mine, day(_codex_main(str(root))))
    elsewhere = day(_codex_main("/somewhere/else"))
    elsewhere[0] = dict(_meta("2026-08-01T01:07:00.000Z", "main-9", "/somewhere/else", "exec"))
    _write_jsonl(theirs, elsewhere)
    root_text = str(root)
    stopped = us.parse_codex_session(theirs, needle="r010_demo", only_cwd=root_text)
    full = us.parse_codex_session(theirs, needle="r010_demo")
    assert stopped.cwd == "/somewhere/else" and stopped.usage.calls == 0 and full.usage.calls > 0
    assert us.parse_codex_session(mine, needle="r010_demo", only_cwd=root_text).to_dict() == us.parse_codex_session(mine, needle="r010_demo").to_dict()
    found = us.collect_case_usage(root, "r010_demo", state, hosts=("codex",), home=home)
    assert [s.session_id for s in found] == ["main-1"] and found[0].usage.calls == full.usage.calls


# ---------------------------------------------------------------------------
# 只算给定时段内的用量
# ---------------------------------------------------------------------------


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_parse_codex_slices_by_interval(tmp_path: Path) -> None:
    path = tmp_path / "rollout-2026-09-25T12-07-00-main-1.jsonl"
    _write_jsonl(path, _codex_main())
    whole = us.parse_codex_session(path, needle="r010_demo")
    assert not whole.sliced and whole.active_seconds is None and whole.seconds == 60.0

    # 只含第二次调用：累计计数器相邻两次的差
    s = us.parse_codex_session(path, needle="r010_demo", intervals=[(_utc("2026-09-25T04:07:15"), _utc("2026-09-25T04:07:30"))])
    u = s.usage
    assert s.sliced and (u.total_input, u.cache_read, u.uncached_input) == (2000, 900, 1100)
    assert (u.output, u.reasoning_output, u.calls, u.peak_context) == (70, 40, 1, 2000)
    assert s.tools == {"spawn_agent": 1, "local_shell_call": 1} and u.tool_calls == 2
    assert not s.mentions and s.mention_counts == {}  # 提到案例的那一行在时段之外
    assert s.seconds == 2.0  # 时段内首末记录相隔 2 秒
    assert (s.started_at, s.ended_at) == ("2026-09-25T04:07:00.000Z", "2026-09-25T04:08:00.000Z")  # 起止仍是整份会话的

    # 两段：第一次与第三次调用
    two = us.parse_codex_session(
        path,
        needle="r010_demo",
        intervals=[
            (_utc("2026-09-25T04:07:50"), _utc("2026-09-25T04:08:10")),
            (_utc("2026-09-25T04:07:01"), _utc("2026-09-25T04:07:12")),
        ],
    )
    assert (two.usage.total_input, two.usage.cache_read, two.usage.output, two.usage.calls) == (5000, 3600, 130, 2)
    assert two.tools == {"exec": 1} and two.mentions and two.seconds == 10.0
    # 各段相加等于整份
    parts = [
        us.parse_codex_session(path, intervals=[(_utc(a), _utc(b))]).usage
        for a, b in [("2026-09-25T04:07:00", "2026-09-25T04:07:15"), ("2026-09-25T04:07:15.001", "2026-09-25T04:07:30"), ("2026-09-25T04:07:30.001", "2026-09-25T04:09:00")]
    ]
    assert sum(x.total_input for x in parts) == whole.usage.total_input
    assert sum(x.output for x in parts) == whole.usage.output and sum(x.calls for x in parts) == whole.usage.calls
    # 时段与会话完全不交叠
    none = us.parse_codex_session(path, needle="r010_demo", intervals=[(_utc("2026-09-26T00:00:00"), _utc("2026-09-26T01:00:00"))])
    assert none.usage.calls == 0 and none.usage.total_input == 0 and none.seconds == 0 and not none.mentions


def test_parse_codex_sliced_forked_subagent_keeps_baseline(tmp_path: Path) -> None:
    source = {"subagent": {"thread_spawn": {"parent_thread_id": "main-1"}}}
    path = tmp_path / "rollout-2026-07-26T10-28-47-sub-1.jsonl"
    _write_jsonl(
        path,
        [
            _meta("2026-07-26T02:28:47.000Z", "sub-1", "/work/proj", source),
            _tc("2026-07-26T02:28:47.000Z", (4_503_191, 4_000_000, 30_000, 9_000), (155_688, 150_000, 800, 300)),
            _tc("2026-07-26T02:29:30.000Z", (4_703_191, 4_150_000, 31_000, 9_200), (200_000, 150_000, 1_000, 200)),
            _tc("2026-07-26T02:30:30.000Z", (4_953_191, 4_390_000, 32_500, 9_900), (250_000, 240_000, 1_500, 700)),
        ],
    )
    # 时段只含最后一次调用：差值相对上一次的累计值算，继承的基数不会混进来
    s = us.parse_codex_session(path, intervals=[(_utc("2026-07-26T02:30:00"), _utc("2026-07-26T02:31:00"))])
    assert (s.usage.total_input, s.usage.cache_read, s.usage.output, s.usage.calls) == (250_000, 240_000, 1_500, 1)
    assert s.inherited_input == 4_503_191


def test_parse_claude_slices_by_interval(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write_jsonl(path, _claude_records())
    late = us.parse_claude_transcript(path, needle="r009_demo", intervals=[(_utc("2026-08-01T01:00:10"), _utc("2026-08-01T01:00:30"))])
    assert late.sliced and (late.usage.uncached_input, late.usage.cache_write, late.usage.cache_read, late.usage.output) == (5, 200, 1000, 80)
    assert late.usage.calls == 1 and late.tools == {"Bash": 1, "Read": 1} and not late.mentions
    assert late.seconds == 1.0  # 01:00:20 到 01:00:21
    # 一条消息的几行按第一行的时间归属；工具调用按它自己那一行的时间
    early = us.parse_claude_transcript(path, needle="r009_demo", intervals=[(_utc("2026-08-01T01:00:00"), _utc("2026-08-01T01:00:05.500"))])
    assert (early.usage.uncached_input, early.usage.cache_write, early.usage.output, early.usage.calls) == (10, 1000, 50, 1)
    assert early.usage.tool_calls == 0 and early.mentions and early.mention_counts == {"r009_demo": 1}


def test_mention_counts_and_dominance(tmp_path: Path) -> None:
    def said(ts: str, text: str) -> dict:
        return {"timestamp": ts, "type": "event_msg", "payload": {"type": "user_message", "message": text}}

    records = [
        _meta("2026-09-25T04:07:00.000Z", "m", "/work/proj", "exec"),
        said("2026-09-25T04:07:01.000Z", "看 workspace/r010_demo/spec 和 workspace/r010_demo/plan.md"),  # 一行里出现两次只算一行
        said("2026-09-25T04:07:02.000Z", "r010_demo 的门禁"),
        said("2026-09-25T04:07:03.000Z", "顺便列一下 r011_other"),
        _tc("2026-09-25T04:07:10.000Z", (1000, 0, 50, 20), (1000, 0, 50, 20)),
    ]
    path = tmp_path / "rollout-2026-09-25T12-07-00-m.jsonl"
    _write_jsonl(path, records)
    s = us.parse_codex_session(path, needle="r010_demo", needles=["r010_demo", "r011_other", "r012_absent"])
    assert s.mention_counts == {"r010_demo": 2, "r011_other": 1} and s.mentions
    assert us._dominant(s, "r010_demo") and not us._dominant(s, "r011_other") and not us._dominant(s, "r012_absent")
    s.mention_counts = {"r010_demo": 2, "r011_other": 2}
    assert not us._dominant(s, "r010_demo")  # 打平不算


def _case_session(sid: str, root: str, day: str, lines: list[tuple[str, str]], total: tuple[int, int, int, int]) -> list[dict]:
    """一个极简的 Codex 主会话：若干条用户消息（时刻, 文本）加一次模型调用。"""
    records = [_meta(f"{day}T04:07:00.000Z", sid, root, "exec")]
    records += [{"timestamp": f"{day}T{t}.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": text}} for t, text in lines]
    records.append(_tc(f"{day}T04:30:00.000Z", total, total))
    return records


def test_collect_case_usage_picks_sessions_dominated_by_the_case(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "home"
    day = home / ".codex" / "sessions" / "2026" / "09" / "25"
    own = _case_session("own", str(root), "2026-09-25", [("04:08:00", "跑 r010_demo"), ("04:09:00", "r010_demo 的 plan"), ("04:10:00", "列出 r011_other")], (1000, 0, 10, 0))
    passing = _case_session("passing", str(root), "2026-09-25", [("04:08:00", "跑 r011_other"), ("04:09:00", "r011_other 的 spec"), ("04:10:00", "顺带看 r010_demo")], (2000, 0, 20, 0))
    tie = _case_session("tie", str(root), "2026-09-25", [("04:08:00", "r010_demo"), ("04:09:00", "r011_other")], (4000, 0, 40, 0))
    _write_jsonl(day / "rollout-2026-09-25T12-07-00-own.jsonl", own)
    _write_jsonl(day / "rollout-2026-09-25T12-07-01-passing.jsonl", passing)
    _write_jsonl(day / "rollout-2026-09-25T12-07-02-tie.jsonl", tie)
    state = {"created_at": "2026-09-25T10:53:41+08:00", "updated_at": "2026-09-25T17:37:25+08:00"}
    ids = ["r010_demo", "r011_other"]

    found = us.collect_case_usage(root, "r010_demo", state, hosts=("codex",), home=home, other_ids=ids)
    assert [s.session_id for s in found] == ["own"] and found[0].usage.total_input == 1000
    assert [s.session_id for s in us.collect_case_usage(root, "r011_other", state, hosts=("codex",), home=home, other_ids=ids)] == ["passing"]
    # 不给其他案例编号时，只要提到就算（三个会话都提到了 r010_demo）
    assert len(us.collect_case_usage(root, "r010_demo", state, hosts=("codex",), home=home)) == 3


def test_collect_case_usage_slices_a_session_that_ran_two_cases(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "home"
    records = [
        _meta("2026-09-25T04:00:00.000Z", "long", str(root), "exec"),
        {"timestamp": "2026-09-25T04:01:00.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "先跑 r010_demo"}},
        _tc("2026-09-25T04:30:00.000Z", (1000, 0, 10, 0), (1000, 0, 10, 0)),
        # 第二天改跑另一个案例，提到它的次数更多
        {"timestamp": "2026-09-26T04:01:00.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "再跑 r011_other"}},
        {"timestamp": "2026-09-26T04:02:00.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "r011_other 的 plan"}},
        {"timestamp": "2026-09-26T04:03:00.000Z", "type": "event_msg", "payload": {"type": "user_message", "message": "r011_other 的门禁"}},
        _tc("2026-09-26T04:30:00.000Z", (9000, 0, 90, 0), (8000, 0, 80, 0)),
    ]
    _write_jsonl(home / ".codex" / "sessions" / "2026" / "09" / "25" / "rollout-2026-09-25T12-00-00-long.jsonl", records)
    ids = ["r010_demo", "r011_other"]
    first = us.span_interval("2026-09-25T12:00:00+08:00", "2026-09-25T13:00:00+08:00")
    second = us.span_interval("2026-09-26T12:00:00+08:00", "2026-09-26T13:00:00+08:00")
    a = us.collect_case_usage(root, "r010_demo", hosts=("codex",), home=home, intervals=[first], other_ids=ids)
    b = us.collect_case_usage(root, "r011_other", hosts=("codex",), home=home, intervals=[second], other_ids=ids)
    assert [(s.session_id, s.usage.total_input, s.usage.calls) for s in a] == [("long", 1000, 1)]
    assert [(s.session_id, s.usage.total_input, s.usage.calls) for s in b] == [("long", 8000, 1)]
    # 时段里没有调用的会话不算
    idle = us.span_interval("2026-09-25T20:00:00+08:00", "2026-09-25T21:00:00+08:00")
    assert us.collect_case_usage(root, "r010_demo", hosts=("codex",), home=home, intervals=[idle], other_ids=ids) == []


def test_span_interval() -> None:
    low, high = us.span_interval("2026-09-25T10:00:00+08:00", "2026-09-25T12:00:00+08:00")
    assert low == datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc) and high == datetime(2026, 9, 25, 5, 0, tzinfo=timezone.utc)
    assert us.span_interval("2026-09-25T12:00:00+08:00", "2026-09-25T10:00:00+08:00") == (low, high)  # 起止写反也行
    assert us.span_interval("2026-09-25T10:00:00+08:00", "2026-09-25T10:00:00+08:00", margin_hours=0)[0] == datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc)
    assert us.span_interval(None, "2026-09-25T10:00:00+08:00") is None and us.span_interval("坏", "坏") is None


def test_usage_arithmetic() -> None:
    a = us.Usage(uncached_input=100, cache_write=40, cache_read=1000, output=10, calls=2, tool_calls=3, peak_context=900)
    b = us.Usage(uncached_input=1, cache_read=5, output=2, reasoning_output=1, calls=1, peak_context=1200)
    c = a.add(b)
    assert (c.uncached_input, c.cache_write, c.cache_read, c.output, c.calls, c.tool_calls, c.peak_context) == (101, 40, 1005, 12, 3, 3, 1200)
    assert a.total_input == 1140
    assert a.weighted == pytest.approx(100 * 1.0 + 40 * 1.25 + 1000 * 0.1 + 10 * 5.0)
    assert a.to_dict()["total_input"] == 1140 and "weighted" in a.to_dict()
