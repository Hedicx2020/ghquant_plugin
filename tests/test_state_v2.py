"""tools/state.py 的 v3 地基测试：案例锁、schema v2、事件流哈希链、v1 → v2 迁移。"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import state as st  # noqa: E402


def _make_case(root: Path, report_id: str = "demo", schema_version: int = 1) -> dict:
    return st.init_state(root, report_id, f"reports/{report_id}.pdf", schema_version=schema_version)


def _checks(*results: tuple[str, str]) -> list[dict]:
    return [{"id": cid, "desc": f"{cid} 描述", "result": result} for cid, result in results]


# ---------------------------------------------------------------------------
# 案例锁
# ---------------------------------------------------------------------------


def _worker_record_events(root: str, report_id: str, tag: str, count: int) -> None:
    from tools import state as worker_st

    for i in range(count):
        worker_st.record_event(Path(root), report_id, f"w:{tag}:{i}", {"i": i})


@pytest.mark.parametrize("schema_version", [1, 2])
def test_concurrent_writers_do_not_lose_updates(tmp_path: Path, schema_version: int) -> None:
    _make_case(tmp_path, schema_version=schema_version)
    ctx = mp.get_context("spawn")
    workers, per_worker = 4, 12
    procs = [
        ctx.Process(target=_worker_record_events, args=(str(tmp_path), "demo", f"p{n}", per_worker))
        for n in range(workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0

    state = st.load_state(tmp_path, "demo")
    if schema_version == 1:
        names = [e["event"] for e in state["events"]]
    else:
        names = [r["event"] for r in st.read_event_records(tmp_path, "demo")]
        assert st.verify_event_chain(tmp_path, "demo", state)["ok"]
    written = [n for n in names if n.startswith("w:")]
    assert len(written) == workers * per_worker
    assert len(set(written)) == workers * per_worker
    assert not st.lock_path(tmp_path, "demo").exists()


def test_case_lock_is_reentrant_in_same_thread(tmp_path: Path) -> None:
    _make_case(tmp_path)
    with st.case_lock(tmp_path, "demo"):
        assert st.lock_path(tmp_path, "demo").is_file()
        with st.case_lock(tmp_path, "demo"):
            st.record_event(tmp_path, "demo", "nested")  # 写操作内部再次加锁不死锁
        assert st.lock_path(tmp_path, "demo").is_file()  # 内层退出不释放外层的锁
    assert not st.lock_path(tmp_path, "demo").exists()


def test_case_lock_blocks_other_thread_until_released(tmp_path: Path) -> None:
    _make_case(tmp_path)
    order: list[str] = []
    entered = threading.Event()

    def other() -> None:
        entered.set()
        with st.case_lock(tmp_path, "demo", timeout=10):
            order.append("other")

    with st.case_lock(tmp_path, "demo"):
        t = threading.Thread(target=other)
        t.start()
        entered.wait(5)
        time.sleep(0.15)
        order.append("main")
    t.join(10)
    assert order == ["main", "other"]


def test_case_lock_times_out_when_held_by_live_process(tmp_path: Path) -> None:
    _make_case(tmp_path)
    lock = st.lock_path(tmp_path, "demo")
    # 伪造一把由「另一台主机」持有的新锁：无法探活，锁龄又没到上限，只能等到超时
    lock.write_text(json.dumps({"pid": 1, "host": "another-host", "ts": st.now_iso()}), encoding="utf-8")
    with pytest.raises(st.StateLockTimeout):
        with st.case_lock(tmp_path, "demo", timeout=0.3):
            pass
    assert lock.is_file()  # 超时不得擅自删除别人的锁


def test_case_lock_takes_over_lock_of_dead_process(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows 上不探活，只按锁龄判断")
    _make_case(tmp_path)
    ctx = mp.get_context("spawn")
    proc = ctx.Process(target=time.sleep, args=(0,))
    proc.start()
    proc.join(30)
    dead_pid = proc.pid
    lock = st.lock_path(tmp_path, "demo")
    import socket

    lock.write_text(json.dumps({"pid": dead_pid, "host": socket.gethostname(), "ts": st.now_iso()}), encoding="utf-8")
    with st.case_lock(tmp_path, "demo", timeout=5):
        info = json.loads(lock.read_text(encoding="utf-8"))
        assert info["pid"] == os.getpid()
    assert not lock.exists()


def test_case_lock_takes_over_aged_lock_from_unknown_host(tmp_path: Path) -> None:
    _make_case(tmp_path)
    lock = st.lock_path(tmp_path, "demo")
    lock.write_text(json.dumps({"pid": 1, "host": "another-host", "ts": "x"}), encoding="utf-8")
    old = time.time() - st.LOCK_STALE_SECONDS - 5
    os.utime(lock, (old, old))
    with st.case_lock(tmp_path, "demo", timeout=5):
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_case_lock_on_missing_case_does_not_create_directory(tmp_path: Path) -> None:
    with st.case_lock(tmp_path, "ghost"):
        pass
    assert not (tmp_path / "workspace" / "ghost").exists()
    with pytest.raises(FileNotFoundError):
        st.record_event(tmp_path, "ghost", "x")


def test_cli_reports_lock_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _make_case(tmp_path)
    lock = st.lock_path(tmp_path, "demo")
    lock.write_text(json.dumps({"pid": 1, "host": "another-host", "ts": st.now_iso()}), encoding="utf-8")

    def short_lock(root, report_id, timeout=0.2):
        return original(root, report_id, timeout=0.2)

    original = st.case_lock
    monkeypatch.setattr(st, "case_lock", short_lock)
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    rc = st.main(["record-event", "demo", "x"])
    assert rc == 1
    assert "等待案例锁超时" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# schema 版本分流
# ---------------------------------------------------------------------------


def test_v1_is_still_the_default_and_rejects_v2_keys(tmp_path: Path) -> None:
    state = _make_case(tmp_path)
    assert state["schema_version"] == 1
    assert st.validate_state(state) == []
    assert not st.events_path(tmp_path, "demo").exists()
    state["flow"] = {}
    assert any("未声明的顶层字段" in e for e in st.validate_state(state))


def test_v2_init_is_valid_and_requires_v2_keys(tmp_path: Path) -> None:
    state = _make_case(tmp_path, schema_version=2)
    assert state["schema_version"] == 2
    assert st.validate_state(state) == []
    assert st.V2_TOP_FIELDS <= state.keys()
    for key in sorted(st.V2_TOP_FIELDS):
        broken = dict(state)
        del broken[key]
        assert any("缺少顶层字段" in e for e in st.validate_state(broken)), key


def test_unknown_schema_version_is_rejected(tmp_path: Path) -> None:
    state = _make_case(tmp_path)
    state["schema_version"] = 3
    assert any("不支持的 schema_version" in e for e in st.validate_state(state))
    with pytest.raises(ValueError):
        st.init_state(tmp_path, "other", "reports/other.pdf", schema_version=3)


@pytest.mark.parametrize(
    "mutate, needle",
    [
        (lambda s: s["flow"].pop("inflight"), "flow 字段不完整"),
        (lambda s: s["flow"].__setitem__("generation", "0"), "flow.generation"),
        (lambda s: s.__setitem__("checkpoints", {}), "checkpoints 必须是数组"),
        (lambda s: s.__setitem__("counters", []), "counters 必须是对象"),
        (lambda s: s["events_head"].pop("hash"), "events_head 字段不完整"),
        (lambda s: s["events_head"].__setitem__("seq", -1), "events_head.seq"),
    ],
)
def test_v2_field_shapes_are_validated(tmp_path: Path, mutate, needle: str) -> None:
    state = _make_case(tmp_path, schema_version=2)
    mutate(state)
    assert any(needle in e for e in st.validate_state(state))


# ---------------------------------------------------------------------------
# 事件流与哈希链（v2）
# ---------------------------------------------------------------------------


def test_v2_init_writes_event_log_with_head(tmp_path: Path) -> None:
    state = _make_case(tmp_path, schema_version=2)
    records = st.read_event_records(tmp_path, "demo")
    assert [r["event"] for r in records] == ["state:init"]
    assert records[0]["seq"] == 1 and records[0]["prev"] is None
    assert state["events_head"] == {"seq": 1, "hash": records[0]["hash"]}
    assert st.verify_event_chain(tmp_path, "demo", state) == {
        "ok": True,
        "count": 1,
        "errors": [],
        "uncommitted_tail": 0,
    }


def test_v2_mutators_append_to_log_and_keep_chain(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    st.set_stage(tmp_path, "demo", "init", "running")
    st.set_field(tmp_path, "demo", "difficulty", "hard")
    st.record_event(tmp_path, "demo", "custom", {"k": "值"})
    st.record_gate(tmp_path, "demo", "init", "PASS", _checks(("G-IN-1", "PASS")))
    state = st.load_state(tmp_path, "demo")
    records = st.read_event_records(tmp_path, "demo")
    assert [r["event"] for r in records] == [
        "state:init",
        "stage:init:running",
        "set:difficulty",
        "custom",
        "gate:init",
    ]
    assert [r["seq"] for r in records] == [1, 2, 3, 4, 5]
    assert records[3]["payload"] == {"k": "值"}
    assert records[4]["payload"]["verdict"] == "PASS"
    assert state["events_head"] == {"seq": 5, "hash": records[-1]["hash"]}
    assert st.verify_event_chain(tmp_path, "demo", state)["ok"]
    # state.events 的条目格式与 v1 相同
    assert state["events"][-1] == {
        "event": "gate:init",
        "timestamp": records[-1]["ts"],
        "payload": records[-1]["payload"],
    }


def test_v2_state_keeps_only_recent_events(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    total = st.STATE_EVENTS_KEEP + 15
    for i in range(total):
        st.record_event(tmp_path, "demo", f"e{i}")
    state = st.load_state(tmp_path, "demo")
    assert len(state["events"]) == st.STATE_EVENTS_KEEP
    assert state["events"][-1]["event"] == f"e{total - 1}"
    records = st.read_event_records(tmp_path, "demo")
    assert len(records) == total + 1  # 完整历史都在 events.jsonl
    assert st.verify_event_chain(tmp_path, "demo", state)["ok"]


def test_v1_state_events_are_not_truncated(tmp_path: Path) -> None:
    _make_case(tmp_path)
    for i in range(st.STATE_EVENTS_KEEP + 15):
        st.record_event(tmp_path, "demo", f"e{i}")
    state = st.load_state(tmp_path, "demo")
    assert len(state["events"]) == st.STATE_EVENTS_KEEP + 15 + 1
    assert not st.events_path(tmp_path, "demo").exists()


def test_event_chain_detects_tampering(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    for i in range(4):
        st.record_event(tmp_path, "demo", f"e{i}", {"i": i})
    path = st.events_path(tmp_path, "demo")
    original = path.read_text(encoding="utf-8")
    state = st.load_state(tmp_path, "demo")

    # 改内容
    lines = original.splitlines()
    rec = json.loads(lines[2])
    rec["payload"] = {"i": 999}
    lines[2] = json.dumps(rec, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = st.verify_event_chain(tmp_path, "demo", state)
    assert not result["ok"] and "第 3 条" in result["errors"][0]

    # 删中间一条
    lines = original.splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not st.verify_event_chain(tmp_path, "demo", state)["ok"]

    # 截断尾部
    path.write_text("\n".join(original.splitlines()[:3]) + "\n", encoding="utf-8")
    result = st.verify_event_chain(tmp_path, "demo", state)
    assert not result["ok"] and "截断" in result["errors"][0]

    # 链头被改
    path.write_text(original, encoding="utf-8")
    forged = dict(state, events_head={"seq": state["events_head"]["seq"], "hash": "0" * 64})
    assert not st.verify_event_chain(tmp_path, "demo", forged)["ok"]
    assert st.verify_event_chain(tmp_path, "demo", state)["ok"]


def test_uncommitted_tail_is_reported_not_an_error(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    st.record_event(tmp_path, "demo", "committed")
    state_before = st.load_state(tmp_path, "demo")
    # 模拟「事件已写、state 没落盘」：直接往事件流追加一条
    with st.case_lock(tmp_path, "demo"):
        st.append_event_record(tmp_path, "demo", "orphan", None, st.now_iso())
    result = st.verify_event_chain(tmp_path, "demo", state_before)
    assert result["ok"] and result["uncommitted_tail"] == 1
    # 之后的写入接着孤儿事件续链，链仍然完整
    st.record_event(tmp_path, "demo", "next")
    state = st.load_state(tmp_path, "demo")
    assert state["events_head"]["seq"] == 4
    assert st.verify_event_chain(tmp_path, "demo", state) == {"ok": True, "count": 4, "errors": [], "uncommitted_tail": 0}


def test_invalid_state_does_not_leave_orphan_event(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    before = st.events_path(tmp_path, "demo").read_text(encoding="utf-8")
    with pytest.raises(st.StateValidationError):
        st.set_field(tmp_path, "demo", "stages", "not-a-dict")
    assert st.events_path(tmp_path, "demo").read_text(encoding="utf-8") == before


def test_last_event_record_handles_long_lines(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    st.record_event(tmp_path, "demo", "big", {"blob": "数" * 20000})  # 单行远超一个读块
    st.record_event(tmp_path, "demo", "after")
    state = st.load_state(tmp_path, "demo")
    assert state["events_head"]["seq"] == 3
    assert st.verify_event_chain(tmp_path, "demo", state)["ok"]


# ---------------------------------------------------------------------------
# 门禁记录（v2）：只留各阶段最新一条 + 连败计数
# ---------------------------------------------------------------------------


def test_v2_record_gate_keeps_latest_per_stage_and_counts_streak(tmp_path: Path) -> None:
    _make_case(tmp_path, schema_version=2)
    st.record_gate(tmp_path, "demo", "plan", "PASS", _checks(("G-PL-1", "PASS")))
    st.record_gate(tmp_path, "demo", "verify", "FAIL", _checks(("G-VF-1", "PASS"), ("G-VF-4", "FAIL")))
    st.record_gate(tmp_path, "demo", "verify", "FAIL", _checks(("G-VF-1", "FAIL"), ("G-VF-4", "FAIL")))
    state = st.record_gate(tmp_path, "demo", "verify", "FAIL", _checks(("G-VF-1", "PASS"), ("G-VF-4", "FAIL")))

    assert [g["stage"] for g in state["gates"]] == ["plan", "verify"]
    assert state["gates"][-1]["stage"] == "verify"  # 最后一条仍是全局最新
    assert state["gate_latest"]["verify"]["verdict"] == "FAIL"
    assert [c["id"] for c in state["gate_latest"]["verify"]["failed"]] == ["G-VF-4"]
    assert state["gate_latest"]["plan"]["failed"] == []
    streak = state["counters"]["gate_fail_streak"]
    assert streak == {"verify:G-VF-4": 3}  # G-VF-1 中途通过过，清零

    state = st.record_gate(tmp_path, "demo", "plan", "PASS", _checks(("G-PL-1", "PASS")))
    assert [g["stage"] for g in state["gates"]] == ["verify", "plan"]
    state = st.record_gate(tmp_path, "demo", "verify", "PASS", _checks(("G-VF-1", "PASS"), ("G-VF-4", "PASS")))
    assert state["counters"]["gate_fail_streak"] == {}

    gate_events = [r for r in st.read_event_records(tmp_path, "demo") if r["event"].startswith("gate:")]
    assert len(gate_events) == 6  # 完整门禁历史在事件流里


def test_v1_record_gate_keeps_full_history(tmp_path: Path) -> None:
    _make_case(tmp_path)
    for _ in range(3):
        state = st.record_gate(tmp_path, "demo", "verify", "FAIL", _checks(("G-VF-4", "FAIL")))
    assert len(state["gates"]) == 3
    assert "counters" not in state


# ---------------------------------------------------------------------------
# v1 → v2 迁移
# ---------------------------------------------------------------------------


def _build_v1_history(root: Path) -> dict:
    _make_case(root)
    st.set_stage(root, "demo", "init", "running")
    st.record_gate(root, "demo", "init", "PASS", _checks(("G-IN-1", "PASS")))
    st.set_stage(root, "demo", "init", "done")
    st.set_stage(root, "demo", "verify", "running")
    st.record_gate(root, "demo", "verify", "FAIL", _checks(("G-VF-3", "FAIL"), ("G-VF-4", "FAIL")))
    st.record_gate(root, "demo", "verify", "FAIL", _checks(("G-VF-3", "PASS"), ("G-VF-4", "FAIL")))
    st.record_event(root, "demo", "custom", {"x": 1})
    return st.load_state(root, "demo")


def test_migrate_to_v2_moves_history_and_is_idempotent(tmp_path: Path) -> None:
    v1 = _build_v1_history(tmp_path)
    raw_v1 = st.state_path(tmp_path, "demo").read_bytes()

    preview = st.migrate_to_v2(tmp_path, "demo", dry_run=True)
    assert preview["migrated"] is False and preview["reason"] == "dry_run"
    assert st.state_path(tmp_path, "demo").read_bytes() == raw_v1
    assert not st.events_path(tmp_path, "demo").exists()

    summary = st.migrate_to_v2(tmp_path, "demo")
    assert summary["migrated"] is True
    assert summary["events"] == len(v1["events"]) and summary["gates"] == 3
    state = st.load_state(tmp_path, "demo")
    assert state["schema_version"] == 2 and st.validate_state(state) == []

    # 备份与原文件逐字节一致
    backup = st.state_path(tmp_path, "demo").with_name("state.v1.json")
    assert backup.read_bytes() == raw_v1

    # 事件流 = v1 事件 + v1 门禁 + 一条迁移事件，哈希链完整
    records = st.read_event_records(tmp_path, "demo")
    assert len(records) == len(v1["events"]) + len(v1["gates"]) + 1
    assert records[-1]["event"] == "migrate:v2"
    assert st.verify_event_chain(tmp_path, "demo", state) == {
        "ok": True,
        "count": len(records),
        "errors": [],
        "uncommitted_tail": 0,
    }
    # v1 事件的相对顺序与内容原样保留
    non_gate = [(r["event"], r["ts"], r["payload"]) for r in records[:-1] if not r["event"].startswith("gate:")]
    assert non_gate == [(e["event"], e["timestamp"], e["payload"]) for e in v1["events"]]
    gate_records = [r for r in records if r["event"].startswith("gate:")]
    assert [(r["event"], r["payload"]["verdict"], r["payload"]["checks"]) for r in gate_records] == [
        (f"gate:{g['stage']}", g["verdict"], g["checks"]) for g in v1["gates"]
    ]

    # state 只留各阶段最新门禁；最后一条不变；连败计数按历史回放
    assert [g["stage"] for g in state["gates"]] == ["init", "verify"]
    assert state["gates"][-1] == v1["gates"][-1]
    assert state["counters"]["gate_fail_streak"] == {"verify:G-VF-4": 2}
    assert [c["id"] for c in state["gate_latest"]["verify"]["failed"]] == ["G-VF-4"]

    # 其余字段原样
    for key in st.CANONICAL_TOP_FIELDS - {"schema_version", "events", "gates", "updated_at"}:
        assert state[key] == v1[key], key

    # 幂等：再迁一次不动任何文件
    snapshot = {p.name: p.read_bytes() for p in (tmp_path / "workspace" / "demo").iterdir() if p.is_file()}
    again = st.migrate_to_v2(tmp_path, "demo")
    assert again == {"report_id": "demo", "migrated": False, "reason": "already_v2"}
    assert {p.name: p.read_bytes() for p in (tmp_path / "workspace" / "demo").iterdir() if p.is_file()} == snapshot


def test_migrated_case_keeps_working_with_mutators(tmp_path: Path) -> None:
    _build_v1_history(tmp_path)
    st.migrate_to_v2(tmp_path, "demo")
    st.set_stage(tmp_path, "demo", "verify", "done")
    state = st.record_gate(tmp_path, "demo", "verify", "FAIL", _checks(("G-VF-3", "PASS"), ("G-VF-4", "FAIL")))
    assert state["counters"]["gate_fail_streak"] == {"verify:G-VF-4": 3}
    assert st.verify_event_chain(tmp_path, "demo", state)["ok"]
    assert "stage 状态" in st.show_summary(tmp_path, "demo")


def test_migrate_rejects_invalid_v1_state(tmp_path: Path) -> None:
    _make_case(tmp_path)
    path = st.state_path(tmp_path, "demo")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "not-a-status"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(st.StateValidationError):
        st.migrate_to_v2(tmp_path, "demo")
    assert not st.events_path(tmp_path, "demo").exists()
    assert not path.with_name("state.v1.json").exists()


def test_merge_history_orders_gates_by_time() -> None:
    events = [
        {"event": "a", "timestamp": "2026-01-01T10:00:00+08:00", "payload": None},
        {"event": "b", "timestamp": "2026-01-01T10:00:05+08:00", "payload": None},
        {"event": "c", "timestamp": "2026-01-01T10:00:09+08:00", "payload": None},
    ]
    gates = [
        {"stage": "s1", "verdict": "PASS", "checks": [], "timestamp": "2026-01-01T10:00:05+08:00"},  # 与 b 同秒：排在 b 前
        {"stage": "s2", "verdict": "FAIL", "checks": [], "timestamp": "2026-01-01T02:00:07Z"},  # 另一时区写法，实为 10:00:07
        {"stage": "s3", "verdict": "PASS", "checks": [], "timestamp": "2026-01-01T10:00:30+08:00"},  # 晚于所有事件
    ]
    timeline = st._merge_history(events, gates)
    assert [name for _ts, name, _payload in timeline] == ["a", "gate:s1", "b", "gate:s2", "c", "gate:s3"]


def _real_case_ids() -> list[str]:
    ws = REPO_ROOT / "workspace"
    if not ws.is_dir():
        return []
    return [p.name for p in sorted(ws.iterdir()) if (p / "state.json").is_file()]


@pytest.mark.parametrize("report_id", _real_case_ids())
def test_real_cases_migrate_on_a_copy(tmp_path: Path, report_id: str) -> None:
    """仓库里现有的每个案例都能迁移（在副本上做，不动真实 workspace）。"""
    src = REPO_ROOT / "workspace" / report_id / "state.json"
    dst_dir = tmp_path / "workspace" / report_id
    dst_dir.mkdir(parents=True)
    shutil.copy2(src, dst_dir / "state.json")
    v1 = json.loads(src.read_text(encoding="utf-8"))
    if v1.get("schema_version") != 1:
        pytest.skip("已是 v2")

    summary = st.migrate_to_v2(tmp_path, report_id)
    assert summary["migrated"] is True
    state = st.load_state(tmp_path, report_id)
    assert st.validate_state(state) == []
    records = st.read_event_records(tmp_path, report_id)
    assert len(records) == len(v1["events"]) + len(v1["gates"]) + 1
    assert st.verify_event_chain(tmp_path, report_id, state)["ok"]
    for key in st.CANONICAL_TOP_FIELDS - {"schema_version", "events", "gates", "updated_at"}:
        assert state[key] == v1[key], key
    if v1["gates"]:
        assert state["gates"][-1] == v1["gates"][-1]
    assert len(state["events"]) <= st.STATE_EVENTS_KEEP
    assert st.migrate_to_v2(tmp_path, report_id)["migrated"] is False
    # 真实 workspace 没被碰过
    assert json.loads(src.read_text(encoding="utf-8")) == v1
    assert not (src.parent / "events.jsonl").exists() or v1.get("schema_version") == 2
