"""tools/flow.py 与它背后的时间线（flowlib/events.py）、步骤调度（flowlib/steps.py）。

批次 A 的命令都是只读或纯新增的：status / next / board / cost / pack / data probe / migrate。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_packs as tp  # noqa: E402 - 复用切片测试里的文书夹具
from tools import flow  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import events as ev  # noqa: E402
from tools.flowlib import steps  # noqa: E402

CASE = "r001_demo"


def _checks(*results: tuple[str, str]) -> list[dict]:
    return [{"id": cid, "desc": f"{cid} 描述", "result": result, "detail": f"{cid} 的明细"} for cid, result in results]


def _milestones() -> str:
    return json.dumps(
        [
            {"id": "m1", "name": "数据底座", "deps": [], "implement": "done", "code_review": "done", "verify": "pending"},
            {"id": "m2", "name": "因子与回测", "deps": ["m1"], "implement": "running", "code_review": "pending", "verify": "pending"},
        ],
        ensure_ascii=False,
    )


def _make_case(root: Path, report_id: str = CASE, schema_version: int = 1) -> None:
    """一个走到 implement 的案例：extract 门禁先败后过。"""
    st.init_state(root, report_id, f"reports/{report_id}.pdf", schema_version=schema_version)
    st.set_stage(root, report_id, "init", "running")
    st.record_gate(root, report_id, "init", "PASS", _checks(("G-IN-1", "PASS")))
    st.set_stage(root, report_id, "init", "done")
    st.set_stage(root, report_id, "extract", "running")
    st.record_gate(root, report_id, "extract", "FAIL", _checks(("G-EX-1", "PASS"), ("G-EX-4", "FAIL")))
    st.record_gate(root, report_id, "extract", "PASS", _checks(("G-EX-1", "PASS"), ("G-EX-4", "PASS")))
    st.set_stage(root, report_id, "extract", "done")
    st.set_field(root, report_id, "type", "factor")
    st.set_field(root, report_id, "difficulty", "medium")
    st.set_stage(root, report_id, "plan", "running")
    st.set_field(root, report_id, "milestones", _milestones())
    st.set_stage(root, report_id, "plan", "done")
    st.set_stage(root, report_id, "spec_audit", "skipped")
    st.set_stage(root, report_id, "implement", "running")
    st.record_event(root, report_id, "custom_note", {"why": "测试"})


def _age(root: Path, report_id: str, hours: float) -> None:
    """把案例的全部时间戳往前挪，模拟「很久没动」。直接改文件，只用于 v1 夹具。"""
    path = st.state_path(root, report_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    delta = timedelta(hours=hours)

    def shift(value: str) -> str:
        return (datetime.fromisoformat(value) - delta).isoformat(timespec="seconds")

    state["created_at"], state["updated_at"] = shift(state["created_at"]), shift(state["updated_at"])
    for item in state["events"] + state["gates"]:
        item["timestamp"] = shift(item["timestamp"])
    for entry in state["stages"].values():
        if entry.get("updated_at"):
            entry["updated_at"] = shift(entry["updated_at"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class _Clock:
    """每取一次时间走一秒的假时钟：真实案例里相邻事件不会挤在同一秒，夹具也不该。"""

    def __init__(self) -> None:
        self.now = datetime.now(st.TZ_CN) - timedelta(minutes=5)

    def __call__(self) -> str:
        self.now += timedelta(seconds=1)
        return self.now.isoformat(timespec="seconds")


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # 宿主会话记录指到一个空目录
    monkeypatch.setattr(st, "now_iso", _Clock())
    return tmp_path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = flow.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


# ---------------------------------------------------------------------------
# 时间线与人话描述
# ---------------------------------------------------------------------------


def test_timeline_is_the_same_for_v1_and_migrated_v2(root: Path) -> None:
    _make_case(root)
    state = st.load_state(root, CASE)
    before = ev.timeline(root, CASE, state)
    names = [item["event"] for item in before]
    assert names[0] == "state:init" and names.count("gate:extract") == 2 and names[-1] == "custom_note"
    assert [item["seq"] for item in before] == list(range(1, len(before) + 1))
    # 门禁按时间归并进事件：两次 extract 门禁都排在 extract 收口之前
    assert max(i for i, n in enumerate(names) if n == "gate:extract") < names.index("stage:extract:done")
    assert before[names.index("gate:extract")]["payload"]["verdict"] == "FAIL"

    st.migrate_to_v2(root, CASE)
    after = ev.timeline(root, CASE)
    assert [(i["ts"], i["event"], i["payload"]) for i in after[:-1]] == [(i["ts"], i["event"], i["payload"]) for i in before]
    assert after[-1]["event"] == "migrate:v2"


def test_describe_covers_known_events() -> None:
    assert ev.describe("state:init") == "建立案例"
    assert ev.describe("stage:code_audit:running") == "代码审计：进行中"
    assert ev.describe("milestone:m2:code_review:done") == "m2 内审：已完成"
    assert ev.describe("gate:verify", {"verdict": "FAIL", "checks": _checks(("G-VF-1", "PASS"), ("G-VF-3", "FAIL"))}) == "门禁 验证：未过（G-VF-3）"
    assert ev.describe("gate:plan", {"verdict": "PASS", "checks": []}) == "门禁 计划：通过"
    assert ev.describe("set:status", {"value": "awaiting_review"}) == "状态改为「等待评审」"
    assert ev.describe("set:pdf_pages", {"value": 62}) == "设置 pdf_pages = 62"
    assert ev.describe("migrate:v2", {"events": 3}).startswith("状态文件升级到 v2")
    # 认不出的事件原样给出，载荷截短但不吞
    text = ev.describe("human_override", {"why": "x" * 200})
    assert text.startswith("human_override：") and text.endswith("…") and len(text) < 120
    assert ev.describe("bare_event") == "bare_event"


def test_fmt_duration_and_parse_ts() -> None:
    assert [ev.fmt_duration(h) for h in (None, 0.001, 0.5, 3.04, 72)] == ["未知", "不到 1 分钟", "30 分钟", "3.0 小时", "3.0 天"]
    assert ev.parse_ts("2026-08-01T08:00:00+08:00") == datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    assert ev.parse_ts("2026-08-01T00:00:00Z") == datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    assert ev.parse_ts("2026-08-01T08:00:00").utcoffset() == timedelta(hours=8)  # 没写时区按东八区
    assert ev.parse_ts("乱写") is None and ev.parse_ts(None) is None


def test_stall_info_running_case(root: Path) -> None:
    _make_case(root)
    fresh = ev.stall_info(st.load_state(root, CASE))
    assert fresh["status"] == "running" and not fresh["stalled"] and fresh["waiting_hours"] is None and fresh["idle_hours"] < 0.1
    _age(root, CASE, hours=10)
    state = st.load_state(root, CASE)
    stale = ev.stall_info(state, timeline=ev.timeline(root, CASE, state))
    assert stale["stalled"] and 9.9 < stale["idle_hours"] < 10.1 and stale["waiting_for"] == "流程自己"
    assert not ev.stall_info(state, threshold_hours=24)["stalled"]


def test_waiting_time_counts_from_status_change_and_survives_migration(root: Path) -> None:
    _make_case(root)
    st.set_field(root, CASE, "status", "awaiting_review")
    st.record_event(root, CASE, "note_after_pause", None)  # 进入等待之后还有别的写入
    _age(root, CASE, hours=50)
    state = st.load_state(root, CASE)
    info = ev.stall_info(state, timeline=ev.timeline(root, CASE, state))
    assert info["waiting_for"] == "你来评审" and not info["stalled"] and 49.9 < info["waiting_hours"] < 50.1

    st.migrate_to_v2(root, CASE)  # 迁移会刷新 updated_at，但不该把等待时间归零
    state = st.load_state(root, CASE)
    assert ev.hours_since(state["updated_at"]) < 0.1
    for timeline in (ev.timeline(root, CASE, state), None):  # 给不给完整时间线都一样
        info = ev.stall_info(state, timeline=timeline)
        assert 49.9 < info["waiting_hours"] < 50.1 and 49.9 < info["idle_hours"] < 50.1
    first, last = ev.activity_span(state, ev.timeline(root, CASE, state))
    assert 49.9 < ev.hours_since(first) < 50.1 and 49.9 < ev.hours_since(last) < 50.1


# ---------------------------------------------------------------------------
# 步骤调度：本批所有阶段都返回「按执行卡推进」
# ---------------------------------------------------------------------------


def test_plan_next_returns_legacy_card_for_first_open_stage(root: Path) -> None:
    _make_case(root)
    before = _snapshot(root)
    state = st.load_state(root, CASE)
    result = steps.plan_next(state)
    assert result["status"] == "running" and result["halt"] is None and result["wait"] == []
    (order,) = result["orders"]
    assert (order["step_id"], order["kind"], order["stage"], order["driver"]) == ("implement#card", "legacy_card", "implement", "card")
    assert (order["stage_status"], order["attempts"], order["role"]) == ("running", 1, "orchestrator")
    assert Path(order["card"]).is_file() and Path(order["card"]).name == "implement.md" and order["card"] in order["prompt_inline"]
    assert steps.plan_next(state) == result and _snapshot(root) == before  # 只读、可重复


def test_plan_next_moves_past_closed_stages(root: Path) -> None:
    _make_case(root)
    st.set_stage(root, CASE, "implement", "done")
    assert steps.plan_next(st.load_state(root, CASE))["orders"][0]["step_id"] == "code_audit#card"
    assert steps.current_stage(st.load_state(root, CASE)) == "code_audit"
    for stage in st.STAGE_ORDER[st.STAGE_ORDER.index("code_audit"):]:
        st.set_stage(root, CASE, stage, "done")
    done = steps.plan_next(st.load_state(root, CASE))
    assert done["orders"] == [] and done["halt"]["reason"] == "all_stages_done"


@pytest.mark.parametrize("stage", st.STAGE_ORDER)
def test_every_stage_has_a_card(stage: str) -> None:
    assert steps.card_path(stage) is not None, f"skills/reproduce/stages/{stage}.md 不存在"


def test_plan_next_halts_while_waiting_or_finished(root: Path) -> None:
    _make_case(root)
    blocker = [{"stage": "implement", "code": "DATA_MISSING", "message": "缺一致预期数据", "evidence": "plan.md"}]
    st.set_field(root, CASE, "blockers", json.dumps(blocker, ensure_ascii=False))
    st.set_field(root, CASE, "pending_question", json.dumps("补数据、降级还是放弃？", ensure_ascii=False))
    st.set_field(root, CASE, "status", "paused_blocked")
    paused = steps.plan_next(st.load_state(root, CASE))
    assert paused["orders"] == [] and paused["halt"]["reason"] == "paused_blocked" and paused["halt"]["stage"] == "implement"
    assert paused["halt"]["blockers"] == blocker and paused["halt"]["pending_question"] == "补数据、降级还是放弃？"

    st.set_field(root, CASE, "status", "awaiting_review")
    review = steps.plan_next(st.load_state(root, CASE))
    assert review["orders"] == [] and review["halt"]["reason"] == "awaiting_review"

    for status in ("done", "done_partial", "aborted"):
        st.set_field(root, CASE, "status", status)
        ended = steps.plan_next(st.load_state(root, CASE))
        assert ended["orders"] == [] and ended["halt"]["reason"] == "terminal"


def test_stage_driver_honours_pin(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    assert steps.stage_driver(st.load_state(root, CASE), "plan") == "card"  # v1 案例一律由执行卡驱动
    _make_case(root, "r002_v2", schema_version=2)
    assert steps.stage_driver(st.load_state(root, "r002_v2"), "plan") == "kernel"  # v2 默认由内核驱动
    # flow.pinned 归内核管理：不能用 state.py set 直接改，要经 flow pin，并且必须写原因
    with pytest.raises(st.StateGuardError):
        st.set_field(root, "r002_v2", "flow.pinned", json.dumps({"plan": {"mode": "card"}}))
    code, _, err = _run(capsys, "pin", "r002_v2", "verify", "--mode", "card", "--reason", " ")
    assert code == 1 and "原因" in err
    code, out, _ = _run(capsys, "pin", "r002_v2", "verify", "--mode", "card", "--reason", "步骤表判断不了，退回执行卡")
    assert code == 0 and "验证阶段现在由执行卡驱动" in out
    state = st.load_state(root, "r002_v2")
    assert steps.stage_driver(state, "verify") == "card" and steps.stage_driver(state, "plan") == "kernel"
    assert state["flow"]["pinned"]["verify"]["reason"] == "步骤表判断不了，退回执行卡"
    assert any(e["event"] == "pin:verify:card" for e in st.read_event_records(root, "r002_v2"))


# ---------------------------------------------------------------------------
# flow status / next
# ---------------------------------------------------------------------------


def test_status_single_case_text_and_json(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    before = _snapshot(root)
    code, out, _ = _run(capsys, "status", "r001")  # 编号前缀即可
    assert code == 0
    assert f"{CASE}  运行中" in out and "选股因子 · 难度 medium · auto 模式 · 状态文件 v1" in out
    assert "通过（共 2 次，未过 1 次）" in out  # extract 先败后过
    assert "编码 ←" in out and "下一步：编码阶段，按执行卡推进" in out
    assert "m2" in out and "因子与回测" in out
    assert "未过的检查项" not in out  # 各阶段最近一次门禁都过了

    code, out, _ = _run(capsys, "status", CASE, "--json")
    data = json.loads(out)
    assert code == 0 and data["report_id"] == CASE and data["schema_version"] == 1 and "event_chain" not in data
    assert data["stages"]["extract"]["gate"] == {"count": 2, "fails": 1, "verdict": "PASS", "ts": data["stages"]["extract"]["gate"]["ts"], "failed": []}
    assert data["stages"]["plan"]["gate"] is None and data["next"]["orders"][0]["step_id"] == "implement#card"
    assert data["events"] == len(ev.timeline(root, CASE))
    assert _snapshot(root) == before


def test_status_shows_failed_checks_blockers_and_stale_question(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    st.record_gate(root, CASE, "implement", "FAIL", _checks(("G-IM-1", "PASS"), ("G-IM-4", "FAIL")))
    st.set_field(root, CASE, "blockers", json.dumps([{"stage": "implement", "code": "X1", "message": "缺数据"}], ensure_ascii=False))
    st.set_field(root, CASE, "pending_question", json.dumps("怎么办？", ensure_ascii=False))
    st.set_field(root, CASE, "status", "paused_blocked")
    code, out, _ = _run(capsys, "status", CASE)
    assert code == 0 and "已暂停，等人处理（等你来处理阻断，已等" in out
    assert "未过的检查项：" in out and "编码 G-IM-4 G-IM-4 描述" in out
    assert "阻断：X1 缺数据" in out and "等你回答：怎么办？" in out and "下一步：停。已暂停" in out

    st.set_field(root, CASE, "status", "awaiting_review")  # 状态往前走了，但提问没清
    _, out, _ = _run(capsys, "status", CASE)
    assert "状态里留着一条没有清掉的提问（案例已不在暂停状态）：怎么办？" in out and "等你回答" not in out


def test_status_v2_keeps_failed_detail_and_checks_chain(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root, schema_version=2)
    st.record_gate(root, CASE, "implement", "FAIL", _checks(("G-IM-4", "FAIL")))
    code, out, _ = _run(capsys, "status", CASE)
    assert code == 0 and "状态文件 v2" in out and "编码 G-IM-4 G-IM-4 描述（G-IM-4 的明细）" in out
    assert "事件流校验未通过" not in out
    _, out, _ = _run(capsys, "status", CASE, "--json")
    assert json.loads(out)["event_chain"]["ok"] is True

    log = st.events_path(root, CASE)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert '"stage:init:running"' in lines[1]
    lines[1] = lines[1].replace("stage:init:running", "stage:init:done", 1)  # 改掉一条历史记录
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    code, out, _ = _run(capsys, "status", CASE)
    assert code == 0 and "事件流校验未通过" in out


def test_status_overview_lists_all_cases(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, "status")
    assert code == 0 and "还没有任何案例" in out
    _make_case(root)
    _make_case(root, "r002_other")
    st.set_field(root, "r002_other", "status", "awaiting_review")
    _age(root, CASE, hours=30)
    (root / "workspace" / "_registry").mkdir()  # 不是案例的目录不该被当成案例
    code, out, _ = _run(capsys, "status")
    lines = out.splitlines()
    assert code == 0 and len(lines) == 3 and lines[0].split()[:3] == ["案例", "状态", "停在"]
    assert "运行中（疑似停滞）" in lines[1] and "距上次事件 30." in lines[1]
    assert "等待评审" in lines[2] and "已等 " in lines[2]
    _, out, _ = _run(capsys, "status", "--json")
    rows = json.loads(out)
    assert [(r["report_id"], r["status"], r["stalled"]) for r in rows] == [(CASE, "running", True), ("r002_other", "awaiting_review", False)]


def test_next_command(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    before = _snapshot(root)
    code, out, _ = _run(capsys, "next", CASE)
    data = json.loads(out)
    assert code == 0 and set(data) == {"report_id", "status", "orders", "wait", "halt", "notes"} and data["orders"][0]["stage"] == "implement"
    assert data["orders"][0]["kind"] == "legacy_card" and "flow migrate" in data["notes"][0]  # v1 案例照旧按执行卡走，只多一句提示
    code, out, _ = _run(capsys, "next", CASE, "--text")
    assert code == 0 and out.startswith("implement#card  编码阶段仍由执行卡驱动")
    assert _snapshot(root) == before
    st.set_field(root, CASE, "status", "awaiting_review")
    code, out, _ = _run(capsys, "next", CASE, "--text")
    assert code == 0 and out.startswith("停：等待评审")


def test_unknown_case_is_an_error(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    for argv in (("status", "r999"), ("next", "r999"), ("cost", "r999"), ("migrate", "r999"), ("pack", "lint", "r999")):
        code, out, err = _run(capsys, *argv)
        assert code == 1 and "错误" in err and out == "", argv


# ---------------------------------------------------------------------------
# flow migrate
# ---------------------------------------------------------------------------


def test_migrate_dry_run_changes_nothing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    before = _snapshot(root)
    code, out, _ = _run(capsys, "migrate", "--all", "--dry-run")
    assert code == 0 and out.startswith(f"{CASE}: 将会把 ") and "条门禁记录移入 events.jsonl" in out and "备份" not in out
    assert _snapshot(root) == before
    code, _, err = _run(capsys, "migrate")
    assert code == 1 and "--all" in err


def test_migrate_then_status_and_idempotence(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    v1 = st.load_state(root, CASE)
    code, out, _ = _run(capsys, "migrate", CASE)
    assert code == 0 and f"{CASE}: 已把 " in out and "state.v1.json" in out and "如需退回" in out
    ws = root / "workspace" / CASE
    assert json.loads((ws / "state.v1.json").read_text(encoding="utf-8")) == v1
    state = st.load_state(root, CASE)
    assert state["schema_version"] == 2 and st.verify_event_chain(root, CASE, state)["ok"]
    assert state["current_stage"] == v1["current_stage"] and state["stages"] == v1["stages"] and state["milestones"] == v1["milestones"]
    # 迁移时正在进行的阶段钉在执行卡上跑完，下一阶段起才交给内核
    assert set(state["flow"]["pinned"]) == {"implement"} and state["flow"]["pinned"]["implement"]["mode"] == "card"
    assert steps.stage_driver(state, "implement") == "card" and steps.stage_driver(state, "code_audit") == "kernel"

    frozen = _snapshot(root)
    code, out, _ = _run(capsys, "migrate", "--all")
    assert code == 0 and "已是 v2，未改动" in out and _snapshot(root) == frozen
    code, out, _ = _run(capsys, "status", CASE)
    assert code == 0 and "状态文件 v2" in out and "下一步：编码阶段" in out


def test_migrate_reports_broken_state(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    _make_case(root, "r002_broken")
    path = st.state_path(root, "r002_broken")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = "不存在的状态"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    code, out, _ = _run(capsys, "migrate", "--all")
    assert code == 1 and f"{CASE}: 已把 " in out and "r002_broken: 迁移失败" in out
    assert st.load_state(root, CASE)["schema_version"] == 2  # 坏的那个不影响好的


# ---------------------------------------------------------------------------
# flow pack
# ---------------------------------------------------------------------------


@pytest.fixture()
def docs_root(root: Path) -> Path:
    """带全套文书的案例，直接用切片测试的夹具内容。"""
    st.init_state(root, "demo", "reports/demo.pdf")
    st.set_field(root, "demo", "type", "factor")
    ws = root / "workspace" / "demo"
    (ws / "spec" / "spec.md").write_text(tp.SPEC, encoding="utf-8")
    (ws / "spec" / "coverage_matrix.md").write_text(tp.MATRIX, encoding="utf-8")
    (ws / "assumptions.md").write_text(tp.ASSUMPTIONS, encoding="utf-8")
    (ws / "plan.md").write_text(tp.PLAN, encoding="utf-8")
    (root / "templates").mkdir()
    (root / "templates" / "factor.md").write_text("# factor 模板\n", encoding="utf-8")
    (root / "templates" / "standards.json").write_text(json.dumps({"factor": {"metrics": {}}}), encoding="utf-8")
    (root / "common").mkdir()
    (root / "common" / "utils.py").write_text(tp.COMMON_UTILS, encoding="utf-8")
    return root


def test_pack_build_prints_writes_and_lists(docs_root: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    before = _snapshot(docs_root)
    code, out, _ = _run(capsys, "pack", "build", "demo", "coder", "m1")
    assert code == 0 and out.startswith("<!-- flow-pack v1 · demo · coder · m1 -->") and "# 任务上下文：编码 · m1" in out
    code, manifest, _ = _run(capsys, "pack", "build", "demo", "coder", "m1", "--manifest")
    data = json.loads(manifest)
    assert code == 0 and (data["role"], data["step"], data["format"]) == ("coder", "m1", "flow-pack v1") and data["segments"]
    assert _snapshot(docs_root) == before  # 不给 --out 就什么都不写

    target = tmp_path / "out" / "pack.md"
    code, line, _ = _run(capsys, "pack", "build", "demo", "verifier", "final", "--out", str(target))
    assert code == 0 and target.read_text(encoding="utf-8").startswith("<!-- flow-pack v1 · demo · verifier · final -->") and "现行合同全量" in line
    code, _, err = _run(capsys, "pack", "build", "demo", "coder", "m9")
    assert code == 1 and "错误" in err


def test_pack_stats_and_lint(docs_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(docs_root, "r002_nodocs")  # 没有文书的案例：跳过而不是报错
    before = _snapshot(docs_root)
    code, out, _ = _run(capsys, "pack", "stats")
    assert code == 0 and "片都是原文子串" in out and "auditor_result(final)" in out
    assert "跳过 r002_nodocs" in out and "没有投喂给任何 agent" in out
    code, out, _ = _run(capsys, "pack", "stats", "demo", "--json")
    data = json.loads(out)
    assert code == 0 and len(data["cases"]) == 1 and len(data["cases"][0]["packs"]) == 8 and "coder" in data["summary"]

    code, out, _ = _run(capsys, "pack", "lint")
    assert code == 0 and "demo: " in out and "r002_nodocs: 1 条告警" in out and "没有 spec/spec.md" in out
    code, out, _ = _run(capsys, "pack", "lint", "demo", "--json")
    findings = json.loads(out)["demo"]
    assert code == 0 and all(set(f) == {"level", "code", "message"} for f in findings)
    assert _snapshot(docs_root) == before


# ---------------------------------------------------------------------------
# flow data probe
# ---------------------------------------------------------------------------


def test_data_probe_writes_registry_and_compares_catalog(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    data = root / "data"
    data.mkdir()
    rows = [(f"{c:06d}", datetime(year, 1 + d // 28, 1 + d % 28)) for year, n in ((2020, 2), (2021, 2), (2022, 80), (2023, 80)) for d in range(200) for c in range(n)]
    pq.write_table(pa.table({"stock_code": [r[0] for r in rows], "date": [r[1] for r in rows], "close": [1.0] * len(rows)}), data / "hk_quote.parquet")
    (root / "templates").mkdir()
    (root / "templates" / "data_catalog.md").write_text(
        "# 数据目录\n\n| 文件 | 内容 | 关键字段 | 覆盖 |\n|---|---|---|---|\n"
        "| `hk_quote.parquet` | 港股行情 | stock_code, date, close | 2020-01 ~ 至今(日) |\n"
        "| `missing_table.parquet` | 不存在的表 | a | 2010 至今 |\n",
        encoding="utf-8",
    )
    _make_case(root)

    code, out, _ = _run(capsys, "data", "probe", "--data-root", str(data))
    assert code == 0 and "1 个文件" in out and "本次实测 1 个" in out
    assert "hk_quote.parquet" in out and "2022" in out  # 截面塌陷被报出
    assert "missing_table.parquet" in out and "数据实况表" in out
    assert "目录写「2020-01 ~ 至今(日)」，实测 2020–2021 年每年只有 2 个标的" in out  # 与手写目录对不上
    registry = root / "workspace" / "_registry"
    saved = json.loads((registry / "data_probe.json").read_text(encoding="utf-8"))
    assert saved["files"]["hk_quote.parquet"]["flags"] and saved["catalog_findings"]
    assert "hk_quote.parquet" in (registry / "data_probe.md").read_text(encoding="utf-8")
    assert st.list_case_ids(root) == [CASE]  # 登记目录不会被当成案例

    code, out, _ = _run(capsys, "data", "probe", "--data-root", str(data))
    assert code == 0 and "本次实测 0 个，其余 1 个沿用缓存" in out
    code, out, _ = _run(capsys, "data", "probe", "--data-root", str(data), "--json")
    assert code == 0 and json.loads(out)["stats"]["files"] == 1

    code, _, err = _run(capsys, "data", "probe", "--data-root", str(root / "nowhere"))
    assert code == 1 and "不存在" in err


# ---------------------------------------------------------------------------
# flow cost / board
# ---------------------------------------------------------------------------


def _codex_session(home: Path, name: str, sid: str, cwd: Path, when: datetime, texts: list[str], total: int) -> None:
    """一个极简的 Codex 会话：每段文字一条用户消息，然后一次工具调用和一次模型调用。"""

    def ts(seconds: int) -> str:
        return (when + timedelta(seconds=seconds)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    usage = {"input_tokens": total, "cached_input_tokens": total // 2, "cache_write_input_tokens": 0, "output_tokens": 100, "reasoning_output_tokens": 10, "total_tokens": total + 100}
    records = [
        {"timestamp": ts(0), "type": "session_meta", "payload": {"id": sid, "cwd": str(cwd), "originator": "codex_exec", "source": "exec"}},
        {"timestamp": ts(1), "type": "turn_context", "payload": {"model": "gpt-test", "effort": "high"}},
        *({"timestamp": ts(2), "type": "event_msg", "payload": {"type": "user_message", "message": text}} for text in texts),
        {"timestamp": ts(3), "type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec"}},
        {"timestamp": ts(4), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage}}},
    ]
    path = home / ".codex" / "sessions" / when.strftime("%Y/%m/%d") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def test_cost_finds_only_sessions_dominated_by_the_case(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    _make_case(root, "r002_other")
    code, out, _ = _run(capsys, "cost", CASE)
    assert code == 0 and "没有找到对得上的会话" in out

    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
    home = root / "home"
    _codex_session(home, f"rollout-{stamp}-a.jsonl", "sess-a", root, now, [f"审查 workspace/{CASE}/spec"], 20_000)
    # 主要在跑另一个案例、顺带提到本案例的会话，不算本案例的
    _codex_session(home, f"rollout-{stamp}-b.jsonl", "sess-b", root, now, ["跑 r002_other", "r002_other 的 plan", f"参考了 {CASE}"], 70_000)
    _codex_session(home, f"rollout-{stamp}-c.jsonl", "sess-c", root / "elsewhere", now, [f"别的目录里提到 {CASE}"], 90_000)
    code, out, _ = _run(capsys, "cost", CASE)
    assert code == 0 and f"{CASE}：1 个相关会话，累计输入 2.0万（未缓存 1.0万、缓存写入 0、缓存读取 1.0万）" in out
    assert "codex/main" in out and "这是给旧案例的估计" in out
    code, out, _ = _run(capsys, "cost", CASE, "--sessions", "--json")
    data = json.loads(out)
    assert code == 0 and data["sessions"] == 1 and data["sessions_detail"][0]["session_id"] == "sess-a"
    assert data["total"]["calls"] == 1 and data["total"]["tool_calls"] == 1
    code, out, _ = _run(capsys, "cost", "r002_other")
    assert code == 0 and "1 个相关会话，累计输入 7.0万" in out
    code, out, _ = _run(capsys, "cost", CASE, "--host", "claude_code")
    assert code == 0 and "没有找到对得上的会话" in out


def test_board_command_writes_case_boards_and_index(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_case(root)
    _make_case(root, "r002_other")
    states = {rid: st.state_path(root, rid).read_bytes() for rid in (CASE, "r002_other")}
    code, out, _ = _run(capsys, "board", CASE, "--no-usage")
    ws = root / "workspace"
    assert code == 0 and (ws / CASE / "board.html").is_file() and (ws / "board.html").is_file()
    assert not (ws / "r002_other" / "board.html").exists()
    assert out.splitlines() == [str(ws / CASE / "board.html"), str(ws / "board.html")]

    code, out, _ = _run(capsys, "board", "--all", "--no-usage")
    assert code == 0 and (ws / "r002_other" / "board.html").is_file() and len(out.splitlines()) == 3
    (ws / "board.html").unlink()
    code, out, _ = _run(capsys, "board", "--index")
    assert code == 0 and out.strip() == str(ws / "board.html") and (ws / "board.html").is_file()
    assert {rid: st.state_path(root, rid).read_bytes() for rid in states} == states  # 看板不写状态
    assert not list(ws.rglob("*.tmp"))


# ---------------------------------------------------------------------------
# 仓库里的真实案例：全部只读
# ---------------------------------------------------------------------------


def _real_cases() -> list[str]:
    return st.list_case_ids(REPO_ROOT)


@pytest.mark.parametrize("report_id", _real_cases())
def test_real_cases_status_and_next_are_read_only(report_id: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(REPO_ROOT))
    path = st.state_path(REPO_ROOT, report_id)
    before = path.read_bytes()
    code, out, _ = _run(capsys, "status", report_id)
    assert code == 0 and out.startswith(report_id) and "下一步：" in out
    code, out, _ = _run(capsys, "next", report_id)
    data = json.loads(out)
    assert code == 0 and (bool(data["orders"]) != bool(data["halt"]))  # 要么有工单，要么说明停在哪
    state = json.loads(before)
    if state["status"] != "running":
        assert data["orders"] == [] and data["halt"]["reason"] in {"terminal", "paused_blocked", "awaiting_review"}
    code, out, _ = _run(capsys, "migrate", report_id, "--dry-run")
    assert code == 0 and ("将会把" in out or "已是 v2" in out)
    assert path.read_bytes() == before and not (path.parent / "events.jsonl").exists() or state["schema_version"] == 2
