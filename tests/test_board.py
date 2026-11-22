"""tools/board.py：单案例看板与全案例总览。只读状态与事件，只写看板文件本身。"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import board  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import events as ev  # noqa: E402
from tools.flowlib import reviewpacks as rp  # noqa: E402

CASE = "r001_demo"


def _checks(*results: tuple[str, str]) -> list[dict]:
    return [{"id": cid, "desc": f"{cid} 描述", "result": result, "detail": f"{cid} 的明细"} for cid, result in results]


class _Clock:
    """每取一次时间走一秒的假时钟，避免夹具里的事件挤在同一秒。"""

    def __init__(self) -> None:
        self.now = datetime.now(st.TZ_CN) - timedelta(minutes=5)

    def __call__(self) -> str:
        self.now += timedelta(seconds=1)
        return self.now.isoformat(timespec="seconds")


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # 宿主会话记录指到一个空目录
    monkeypatch.setattr(st, "now_iso", _Clock())
    return tmp_path


def _make_case(root: Path, report_id: str = CASE, schema_version: int = 1) -> None:
    """走到 verify 的案例：verify 门禁连败两次，有外审、迭代历史和 milestone。"""
    st.init_state(root, report_id, f"reports/{report_id}.pdf", schema_version=schema_version)
    st.set_stage(root, report_id, "init", "running")
    st.record_gate(root, report_id, "init", "PASS", _checks(("G-IN-1", "PASS")))
    st.set_stage(root, report_id, "init", "done")
    st.set_field(root, report_id, "type", "timing")
    st.set_field(root, report_id, "difficulty", "hard")
    milestones = [
        {"id": "m1", "name": "数据", "deps": [], "implement": "done", "code_review": "done", "verify": "done"},
        {"id": "m2", "name": "回测", "deps": ["m1"], "implement": "done", "code_review": "failed", "verify": "pending"},
    ]
    st.set_field(root, report_id, "milestones", json.dumps(milestones, ensure_ascii=False))
    for stage in ("extract", "plan", "spec_audit", "implement", "code_audit"):
        st.set_stage(root, report_id, stage, "running")
        st.set_stage(root, report_id, stage, "done")
    st.set_stage(root, report_id, "verify", "running")
    st.record_gate(root, report_id, "verify", "FAIL", _checks(("G-VF-1", "PASS"), ("G-VF-4", "FAIL")))
    st.set_stage(root, report_id, "verify", "running")
    st.record_gate(root, report_id, "verify", "FAIL", _checks(("G-VF-1", "PASS"), ("G-VF-4", "FAIL")))
    reviews = [
        {"checkpoint": "spec", "engine": "codex", "verdict": "pass", "critical": 0, "major": 2, "minor": 1, "note": "两处 major 已回应"},
        {"checkpoint": "code", "engine": "claude-fallback", "verdict": "revise", "critical": 1, "major": 0, "minor": 0, "note": "外审超时后降级"},
    ]
    st.set_field(root, report_id, "external_reviews", json.dumps(reviews, ensure_ascii=False))
    st.set_field(root, report_id, "iteration", json.dumps({"current": 1, "max": 6, "history": [{"iteration": 1, "trigger": "verify fail", "status": "continue", "summary": "修了换仓日"}]}, ensure_ascii=False))
    st.set_field(root, report_id, "verdict", json.dumps({"result": "partial", "comparison_file": None, "metrics_pass": 7, "metrics_total": 9, "decided_at": None}, ensure_ascii=False))
    st.set_field(root, report_id, "coverage_stats", json.dumps({"total": 20, "done": 17, "skipped": 2, "infeasible": 1, "pending": 0}))
    st.set_field(root, report_id, "assumptions", json.dumps({"total": 12, "assumed": 10, "confirmed": 1, "revised": 1}))
    ws = root / "workspace" / report_id
    (ws / "spec" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (ws / "plan.md").write_text("# plan\n", encoding="utf-8")
    (root / "output" / report_id / "verify_report.md").write_text("# verify\n", encoding="utf-8")


def _age(root: Path, report_id: str, hours: float) -> None:
    path = st.state_path(root, report_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    delta = timedelta(hours=hours)

    def shift(value: str) -> str:
        return (datetime.fromisoformat(value) - delta).isoformat(timespec="seconds")

    state["created_at"], state["updated_at"] = shift(state["created_at"]), shift(state["updated_at"])
    for item in state["events"] + state["gates"]:
        item["timestamp"] = shift(item["timestamp"])
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _text(page: str) -> str:
    """去掉样式、脚本和标签，只留正文，便于按文字断言。"""
    page = re.sub(r"<(style|script)\b.*?</\1>", "", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------


def test_gate_history_and_fail_streaks(root: Path) -> None:
    _make_case(root)
    history = board.gate_history(ev.timeline(root, CASE))
    assert set(history) == {"init", "verify"} and [r["verdict"] for r in history["verify"]] == ["FAIL", "FAIL"]
    assert board.fail_streaks(history) == {"verify:G-VF-4": 2}
    st.record_gate(root, CASE, "verify", "PASS", _checks(("G-VF-1", "PASS"), ("G-VF-4", "PASS")))
    assert board.fail_streaks(board.gate_history(ev.timeline(root, CASE))) == {}  # 通过即清零


def test_case_links_only_existing_files(root: Path) -> None:
    _make_case(root)
    labels = [label for label, _ in board.case_links(root, CASE)]
    assert labels == ["规格书 spec.md", "复现计划 plan.md", "验证报告 verify_report.md", "策略代码目录 src/", "结果目录 results/"]


# ---------------------------------------------------------------------------
# 单案例看板
# ---------------------------------------------------------------------------


def test_render_case_sections(root: Path) -> None:
    _make_case(root)
    before = st.state_path(root, CASE).read_bytes()
    page = board.render_case(root, CASE, with_usage=False)
    text = _text(page)
    assert page.startswith("<!doctype html>") and "<title>r001_demo · 复现看板</title>" in page
    assert "<meta http-equiv='refresh' content='60'>" in page and "本页每分钟自动刷新" in text  # 运行中才自动刷新
    assert "prefers-color-scheme: dark" in page  # 深色模式
    # 头部与状态条
    for piece in ("运行中", "择时", "难度：困难", "状态文件 v1", "现在 验证（第 2 次尝试，由执行卡推进）", "等谁 流程自己", "停在 验证 阶段", "距上次事件"):
        assert piece in text, piece
    # 指标卡
    for piece in ("指标达标 7/9", "要素覆盖 17/20", "跳过 2 · 不可行 1 · 未完成 0", "迭代轮次 1/6", "假设 12", "外审 2 次 其中降级 1 次"):
        assert piece in text, piece
    # 阶段表：verify 两次门禁都没过，milestone 状态列在对应阶段
    assert "共 2 次，未过 2 次" in text and "m2 失败" in text and "← 当前" in text
    # 门禁明细：最近一次的逐项结果，连败次数写在明细里
    assert "各阶段最近一次门禁的逐项结果（全部门禁记录共 3 次）" in text
    assert "已连续 2 次未过。G-VF-4 的明细" in text
    assert page.count("data-s='fail' class='f-row'") == 1 and page.count("data-s='pass'") == 2
    # 外审、返工、产物、事件
    assert "外审台账" in text and "两处 major 已回应" in text and "外审超时后降级" in text
    assert "重复进入的阶段：验证 2 次" in text and "修了换仓日" in text and "旧流程不记录每一次派发" in text
    assert "<a href='spec/spec.md'>规格书 spec.md</a>" in page and "<a href='../../output/r001_demo/verify_report.md'>" in page
    assert "事件" in text and "建立案例" in text and "门禁 验证：未过（G-VF-4）" in text
    assert "本次没有读取宿主的会话记录" in text
    assert st.state_path(root, CASE).read_bytes() == before  # 渲染不写任何东西
    assert sorted(p.name for p in (root / "workspace" / CASE).iterdir()) == ["audit", "iterations", "plan.md", "spec", "state.json"]


def test_render_waiting_case_shows_blockers_and_escapes_html(root: Path) -> None:
    _make_case(root)
    blockers = [{"stage": "verify", "code": "DATA_GAP", "message": "<script>alert(1)</script> 缺港股行情", "evidence": "audit/x.md"}, "一条不是对象的阻断"]
    st.set_field(root, CASE, "blockers", json.dumps(blockers, ensure_ascii=False))
    st.set_field(root, CASE, "pending_question", json.dumps("补数据 & 降级 <二选一>？", ensure_ascii=False))
    st.set_field(root, CASE, "status", "paused_blocked")
    page = board.render_case(root, CASE, with_usage=False)
    text = _text(page)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt; 缺港股行情" in page
    assert "补数据 &amp; 降级 &lt;二选一&gt;？" in page
    assert "待处理" in text and "等你回答" in text and "DATA_GAP" in text and "一条不是对象的阻断" in text
    assert "等谁 你来处理阻断" in text and "已等待" in text and "statusbar fail" in page
    assert "http-equiv='refresh'" not in page  # 不在运行中就不自动刷新

    st.set_field(root, CASE, "status", "awaiting_review")
    text = _text(board.render_case(root, CASE, with_usage=False))
    assert "状态里留着一条没有清掉的提问（案例已不在暂停状态）" in text and "等你回答" not in text


def test_render_fresh_case_without_history(root: Path) -> None:
    st.init_state(root, CASE, f"reports/{CASE}.pdf")
    text = _text(board.render_case(root, CASE, with_usage=False))
    assert "还没有门禁记录" in text and "现在 初始化（尚未开始，由执行卡推进）" in text
    assert "外审台账" not in text and "返工与迭代" not in text and "待处理" not in text


def test_render_v2_case_and_tampered_log(root: Path) -> None:
    _make_case(root)
    v1_text = _text(board.render_case(root, CASE, with_usage=False))
    st.migrate_to_v2(root, CASE)
    page = board.render_case(root, CASE, with_usage=False)
    text = _text(page)
    assert "状态文件 v2" in text and "事件流校验未通过" not in text
    assert "已连续 2 次未过。G-VF-4 的明细" in text and "共 2 次，未过 2 次" in text  # 门禁历史从 events.jsonl 来，内容不变
    assert "状态文件升级到 v2" in text and "旧流程不记录每一次派发" not in text
    assert v1_text.count("通过") == text.count("通过")

    log = st.events_path(root, CASE)
    lines = log.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("stage:init:running", "stage:init:done", 1)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert "事件流校验未通过" in _text(board.render_case(root, CASE, with_usage=False))


def test_usage_section_reads_host_sessions(root: Path) -> None:
    _make_case(root)
    assert "没有找到与这个案例对得上的会话" in _text(board.render_case(root, CASE))
    now = datetime.now().astimezone()

    def ts(seconds: int) -> str:
        return (now + timedelta(seconds=seconds)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    usage = {"input_tokens": 250_000, "cached_input_tokens": 200_000, "cache_write_input_tokens": 0, "output_tokens": 3_000, "reasoning_output_tokens": 0, "total_tokens": 253_000}
    records = [
        {"timestamp": ts(0), "type": "session_meta", "payload": {"id": "s1", "cwd": str(root), "originator": "codex_exec", "source": "exec"}},
        {"timestamp": ts(1), "type": "event_msg", "payload": {"type": "user_message", "message": f"审查 workspace/{CASE}/spec"}},
        {"timestamp": ts(2), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage}}},
    ]
    path = root / "home" / ".codex" / "sessions" / now.strftime("%Y/%m/%d") / f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-s1.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    text = _text(board.render_case(root, CASE))
    assert "从宿主会话记录里找到 1 个相关会话" in text and "累计输入 25.0 万 token" in text
    assert "未缓存 5.0 万" in text and "缓存读取 20.0 万" in text and "codex/main" in text and "这是给旧案例的估计" in text


def test_usage_failure_does_not_break_the_board(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_case(root)

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("宿主记录格式变了")

    monkeypatch.setattr(board.us, "collect_case_usage", boom)
    assert "没有找到与这个案例对得上的会话" in _text(board.render_case(root, CASE))


def test_write_case_is_atomic_and_overwrites(root: Path) -> None:
    _make_case(root)
    target = board.write_case(root, CASE, with_usage=False)
    assert target == root / "workspace" / CASE / "board.html" and target.read_text(encoding="utf-8").startswith("<!doctype html>")
    first = target.read_text(encoding="utf-8")
    st.set_field(root, CASE, "status", "awaiting_review")
    board.write_case(root, CASE, with_usage=False)
    assert target.read_text(encoding="utf-8") != first and not list(target.parent.glob("*.tmp"))


# ---------------------------------------------------------------------------
# 总览
# ---------------------------------------------------------------------------


def test_render_index_orders_and_flags(root: Path) -> None:
    for rid in ("r001_demo", "r002_wait", "r003_done", "r004_stale"):
        st.init_state(root, rid, f"reports/{rid}.pdf")
    st.set_field(root, "r002_wait", "status", "awaiting_review")
    st.set_field(root, "r003_done", "status", "done")
    st.set_field(root, "r003_done", "verdict", json.dumps({"result": "pass", "comparison_file": None, "metrics_pass": 9, "metrics_total": 9, "decided_at": None}))
    _age(root, "r004_stale", hours=40)
    (root / "workspace" / "r005_broken").mkdir()
    (root / "workspace" / "r005_broken" / "state.json").write_text("{不是 json", encoding="utf-8")
    (root / "workspace" / "_registry").mkdir()
    board.write_case(root, "r002_wait", with_usage=False)

    page = board.render_index(root)
    text = _text(page)
    order = [text.index(rid) for rid in ("r002_wait", "r001_demo", "r004_stale", "r003_done")]
    assert order == sorted(order)  # 等人处理的排最前，收尾的排最后
    assert "案例数 4" in text and "等待评审 1" in text and "运行中 2" in text and "已完成 1" in text and "疑似停滞 1" in text
    assert "<a href='r002_wait/board.html'>r002_wait</a>" in page  # 有看板的才给链接
    assert "<a href='r001_demo/board.html'>" not in page
    assert "距上次事件 40." in text and "9/9" in text and "达标" in text
    assert "读不了的案例" in text and "r005_broken" in text and "_registry" not in text
    assert "<meta http-equiv='refresh' content='60'>" in page  # 有案例在运行

    target = board.write_index(root)
    assert target == root / "workspace" / "board.html" and target.is_file()


def test_render_index_empty_workspace(root: Path) -> None:
    text = _text(board.render_index(root))
    assert "案例数 0" in text
    assert board.write_index(root).is_file()


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def test_cli(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    _make_case(root)
    assert board.main([CASE[:4], "--no-usage"]) == 0
    assert capsys.readouterr().out.strip() == str(root / "workspace" / CASE / "board.html")
    assert board.main(["--all", "--no-usage"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2
    assert board.main(["--index"]) == 0 and (root / "workspace" / "board.html").is_file()
    capsys.readouterr()
    assert board.main(["r999"]) == 1 and "错误" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        board.main([])


# ---------------------------------------------------------------------------
# 仓库里的真实案例：全部能渲染，且不写任何文件
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("report_id", st.list_case_ids(REPO_ROOT))
def test_real_cases_render(report_id: str) -> None:
    ws = REPO_ROOT / "workspace" / report_id
    before = {p.name: p.stat().st_mtime_ns for p in ws.iterdir()}
    page = board.render_case(REPO_ROOT, report_id, with_usage=False)
    text = _text(page)
    assert page.startswith("<!doctype html>") and report_id in text
    for section in ("阶段进度", "门禁明细", "事件"):
        assert section in text
    state = st.load_state(REPO_ROOT, report_id)
    assert ev.TOP_STATUS_CN[state["status"]] in text
    assert len(re.findall(r"<tr><td class='nowrap'><strong>", page)) == len(st.STAGE_ORDER)  # 十二个阶段各一行
    assert {p.name: p.stat().st_mtime_ns for p in ws.iterdir()} == before


def test_real_index_renders() -> None:
    cases = st.list_case_ids(REPO_ROOT)
    if not cases:
        pytest.skip("仓库里没有案例")
    text = _text(board.render_index(REPO_ROOT))
    assert f"案例数 {len(cases)}" in text and all(rid in text for rid in cases)


# ---------------------------------------------------------------------------
# v2：检查点、步骤、连败计数、执行卡
# ---------------------------------------------------------------------------

NEW_SECTION_MARKS = ("待决检查点", "检查点记录", "<h2>步骤</h2>", "返工与表外派发清单", "连败计数", ">执行卡</span>", "class='cp-card", "class='sb-wide")
DECIDE_ANY = "flow decide r001_demo {cp} --choice &lt;选项&gt; --quote &quot;&lt;你的原话&gt;&quot;"


def _edit_state(root: Path, report_id: str, **updates: object) -> dict:
    """直接改 state.json 里的内核字段（flow / counters 这些只有内核能写，测试里绕开守卫）。"""
    path = st.state_path(root, report_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key].update(value)
        else:
            state[key] = value
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def _make_checkpoint_case(root: Path, report_id: str = CASE) -> dict[str, dict]:
    """v2 案例：一个按策略自动放行的、一个凭钩子放行的、一个自述放行的，最后停在数据缺口这个中途检查点上。"""
    st.init_state(root, report_id, f"reports/{report_id}.pdf", schema_version=2)
    with st.transaction(root, report_id) as txn:
        auto = st.open_checkpoint_in(txn, "external_degraded", kind="auto", stage="spec_audit", reason="codex 两次超时，降级为同宿主盲审", pause_status=None)
        st.resolve_checkpoint_in(txn, auto, choice="auto", credential="policy", by="policy", resume_status=None)
        hooked = st.open_checkpoint_in(txn, "spec_final", stage="extract", reason="提取阶段已收口，请确认后继续", pause_status="awaiting_review")
        st.resolve_checkpoint_in(txn, hooked, choice="approve", quote="spec 没问题 <b>继续</b>", credential="hook")
        told = st.open_checkpoint_in(txn, "plan_final", stage="spec_audit", reason="规格审计已收口，请确认后继续", pause_status="awaiting_review")
        st.resolve_checkpoint_in(txn, told, choice="modify", quote="把窗口改成 21 日", credential="self_report", note="对话里转述")
        reason = "复现要用的数据有 1 处缺口，需要你决定怎么处置"
        gap = st.open_checkpoint_in(
            txn,
            "data_gap",
            stage="plan",
            reason=reason,
            options=[{"key": "supply", "label": "补数据：我去补"}, {"key": "mock", "label": "先用 mock 试跑 & 不出结论"}, {"key": "abort", "label": "终止"}],
            pause_status="paused_blocked",
            payload={"gaps": ["港股行情"], "gap_report": "| 数据需求 | 结论 |\n| --- | --- |\n| 港股行情 | 部分满足 |"},
            question=f"数据缺口处置：{reason}",
        )
        gap["pack"] = rp.write(root, report_id, gap, state=txn.state)
        txn.touch()
    return {"auto": auto, "hooked": hooked, "told": told, "gap": gap}


def test_v2_pending_checkpoint_in_status_bar_and_card(root: Path) -> None:
    cps = _make_checkpoint_case(root)
    gap = cps["gap"]
    page = board.render_case(root, CASE, with_usage=False)
    text = _text(page)
    title = rp.checkpoint_title("data_gap")
    # 状态条：停在哪个检查点、等了多久、审阅包链接、可复制的放行命令与短码
    bar = page[page.index("<div class='statusbar") : page.index("</header>")]
    assert "statusbar fail" in bar and re.search(rf"停在 {re.escape(title)}（cp_04），已等 \d+ 分钟", _text(bar))
    assert "现在 中途检查点" in _text(bar) and "等谁 你来决定" in _text(bar) and "所在阶段 计划 阶段" in _text(bar)
    assert "<a href='reviews/cp_04_data_gap.md'>reviews/cp_04_data_gap.md</a>" in bar and (root / "workspace" / CASE / "reviews" / "cp_04_data_gap.md").is_file()
    assert f"<code class='cmd'>{DECIDE_ANY.format(cp='cp_04')}</code>" in bar and f"放行短码</span> <code>{gap['code']}</code>" in bar
    assert "最终评审" not in bar and "flow accept" not in bar
    # 待决检查点：原因、逐个选项与命令、审阅包、短码
    card = page[page.index("<h2>待决检查点</h2>") : page.index("<h2>阶段进度</h2>")]
    assert page.index("<h2>待决检查点</h2>") < page.index("<h2>阶段进度</h2>") and card.count("class='cp-card") == 1
    assert f"<span class='cp-title'>{title}</span> <code>cp_04</code> <span class='pill warn'>中途检查点</span>" in card
    assert "原因</strong>：复现要用的数据有 1 处缺口，需要你决定怎么处置" in card and "计划 阶段 · 开出于" in card
    for key, label in (("supply", "补数据：我去补"), ("mock", "先用 mock 试跑 &amp; 不出结论"), ("abort", "终止")):
        assert f"<td class='nowrap'><code>{key}</code></td><td>{label}</td>" in card
        assert f"<code class='cmd'>flow decide r001_demo cp_04 --choice {key} --quote &quot;&lt;你的原话&gt;&quot;</code>" in card
    assert f"放行短码 <code>{gap['code']}</code>" in card and "没有它的放行会记为自述" in card
    assert "<a href='reviews/cp_04_data_gap.md'>" in card
    # 检查点自己的原因不在「待处理」里再说一遍
    assert "等你回答" not in text and "<h2>待处理</h2>" not in page
    assert "http-equiv='refresh'" not in page
    assert len(re.findall(r"<tr><td class='nowrap'><strong>", page)) == len(st.STAGE_ORDER)  # 阶段表还是十二行


def test_v2_resolved_and_auto_checkpoints_are_logged(root: Path) -> None:
    _make_checkpoint_case(root)
    page = board.render_case(root, CASE, with_usage=False)
    log = page[page.index("<h2>检查点记录</h2>") : page.index("<h2>用量</h2>")]
    decided, auto = log.split("<h3>按策略自动放行</h3>")
    assert "<h3>已处理</h3>" in decided
    assert "<th>时间</th><th>名称</th><th>选择</th><th>原话</th><th>凭据等级</th><th>谁放行</th>" in decided
    rows = re.findall(r"<tr[^>]*>.*?</tr>", decided, flags=re.S)[1:]
    assert len(rows) == 2  # 待决的、自动放行的都不在这张表里
    hooked, told = rows
    assert f"{rp.checkpoint_title('spec_final')}（cp_02）" in hooked and "<code>approve</code>" in hooked and hooked.startswith("<tr>")
    assert "spec 没问题 &lt;b&gt;继续&lt;/b&gt;" in hooked and "<b>继续</b>" not in page  # 原话转义
    assert f"<span class='pill pass'>{rp.credential_cn('hook')}</span>" in hooked and "钩子" in rp.credential_cn("hook") and "<td class='nowrap'>人</td>" in hooked
    # 自述级：整行标红，凭据写明「自述（没有人在场凭据）」，表头上方再提醒一次
    assert told.startswith("<tr class='f-row'>") and "<span class='pill fail'>自述（没有人在场凭据）</span>" in told
    assert f"{rp.checkpoint_title('plan_final')}（cp_03）" in told and "<code>modify</code>" in told and "把窗口改成 21 日" in told and "（对话里转述）" in told
    assert "有 1 次放行是自述级" in decided and "只有代理自己的说法" in decided
    # 自动放行的单列
    assert f"{rp.checkpoint_title('external_degraded')}（cp_01）" in auto and "codex 两次超时，降级为同宿主盲审" in auto and "规格审计" in auto
    assert "只留痕" in auto and "external_degraded" not in decided and "外审降级" not in decided

    # 全部放行之后：状态条回到平常的样子，待决检查点一节消失，记录里多一行
    with st.transaction(root, CASE) as txn:
        st.resolve_checkpoint_in(txn, st.find_checkpoint(txn.state, "cp_04"), choice="mock", quote="先用 mock", credential="terminal")
    page = board.render_case(root, CASE, with_usage=False)
    assert "<h2>待决检查点</h2>" not in page and "class='sb-wide" not in page and "等谁 流程自己" in _text(page)
    assert f"<span class='pill pass'>{rp.credential_cn('terminal')}</span>" in page and "终端" in rp.credential_cn("terminal") and "<code>mock</code>" in page


def test_v2_final_review_bar_after_migration(root: Path) -> None:
    _make_case(root)
    st.set_field(root, CASE, "status", "awaiting_review")
    st.migrate_to_v2(root, CASE)  # 等待评审的旧案例迁移后会带一个待决的最终评审检查点
    state = st.load_state(root, CASE)
    pending = board.pending_checkpoints(state)
    assert [c["name"] for c in pending] == ["final_review"]
    page = board.render_case(root, CASE, with_usage=False)
    bar = page[page.index("<div class='statusbar") : page.index("</header>")]
    assert "statusbar warn" in bar and "现在 最终评审" in _text(bar) and "等谁 你来评审最终结果" in _text(bar)
    assert f"停在 {rp.checkpoint_title('final_review')}（{pending[0]['id']}），已等" in _text(bar) and "所在阶段 人工评审 阶段" in _text(bar)
    quote = "--quote &quot;&lt;你的原话&gt;&quot;"
    # 状态条只放收尾与定向重跑两条命令（都带原话）；回退、终止在卡片里
    assert f"<code class='cmd'>flow accept r001_demo {quote}</code>" in bar
    assert f"<code class='cmd'>flow revise r001_demo --assumption &lt;假设编号&gt; --new-text &quot;&lt;新口径&gt;&quot; {quote}</code>" in bar
    assert "flow decide" not in bar and "flow reopen" not in bar and "尚未生成" in bar  # 迁移补的检查点没有审阅包
    card = page[page.index("<h2>待决检查点</h2>") : page.index("<h2>阶段进度</h2>")]
    assert "class='cp-card final'" in card and "<span class='pill gate'>最终评审</span>" in card
    assert f"<code class='cmd'>flow accept r001_demo {quote}</code>" in card
    assert f"<code class='cmd'>flow reopen r001_demo --from &lt;阶段或 milestone&gt; --reason &quot;&lt;原因&gt;&quot; {quote}</code>" in card
    assert f"<code class='cmd'>flow decide r001_demo {pending[0]['id']} --choice abort {quote}</code>" in card  # 终止没有专门的命令，走 flow decide

    # 同时有两个在等：状态条说第一个，并提示还有别的
    with st.transaction(root, CASE) as txn:
        st.open_checkpoint_in(txn, "stall", stage="verify", reason="在途步骤 30 小时没有新事件", pause_status="paused_blocked")
    page = board.render_case(root, CASE, with_usage=False)
    assert "另有 1 个检查点在等，见下方「待决检查点」" in _text(page) and page.count("class='cp-card") == 2
    assert "在途步骤 30 小时没有新事件" in page[page.index("<h2>待决检查点</h2>") : page.index("<h2>阶段进度</h2>")]
    assert "等你回答" not in _text(page)


def _make_step_case(root: Path) -> None:
    """内核驱动的 v2 案例：派出去三个步骤（一个返工在途）、内核自己做完两个机器步骤、一次表外派发、两处连败、验证阶段钉在执行卡上。"""
    _make_case(root, schema_version=2)
    steps = {
        "extract.main": {"status": "done", "attempt": 1, "kind": "dispatch", "role": "quant-extractor", "stage": "extract", "milestone": None, "issued_at": "2026-11-22T01:00:00+08:00", "done_at": "2026-11-22T01:20:00+08:00", "task_bytes": 20480, "reason": "首派"},
        "implement.m2.code": {"status": "inflight", "attempt": 2, "kind": "dispatch", "role": "quant-coder", "stage": "implement", "milestone": "m2", "issued_at": "2026-11-22T02:00:00+08:00", "done_at": None, "task_bytes": 41234, "reason": "门禁 G-IM-3 未过重派 <x>"},
        "spec_audit.external": {"status": "failed", "attempt": 1, "kind": "exec", "role": "external", "stage": "spec_audit", "milestone": None, "issued_at": "2026-11-22T01:30:00+08:00", "done_at": "2026-11-22T01:45:00+08:00", "task_bytes": 900, "reason": "首派"},
        "plan.seed@g0.2": {"status": "done", "kind": "kernel", "done_at": "2026-11-22T01:26:00+08:00", "result": {}},
        "plan.datacheck@g0.1": {"status": "done", "kind": "kernel", "done_at": "2026-11-22T01:25:00+08:00", "result": {}},
        "坏记录": "不是对象",
    }
    _edit_state(
        root,
        CASE,
        flow={
            "steps": steps,
            "inflight": ["implement.m2.code"],
            "adhoc": [{"id": "adhoc.01", "role": "quant-coder", "reason": "补一张图", "at": "2026-11-22T02:10:00+08:00", "status": "done"}, "坏记录"],
            "pinned": {"verify": {"mode": "card", "reason": "legacy_inflight：迁移时进行到一半", "at": "2026-11-22T00:00:00+08:00"}, "plan": {"mode": "kernel"}},
        },
        counters={"gate_fail_streak": {"verify:G-VF-4": 3, "implement:G-IM-3": 1, "init:G-IN-1": 0}, "redispatch": {"implement.m2.code": 1, "gate:plan": 2}, "review_rounds": {"result": 2}, "adhoc": 1, "false_fail": {"m2": 1}},
    )


def test_v2_steps_table_and_rework_list(root: Path) -> None:
    _make_step_case(root)
    page = board.render_case(root, CASE, with_usage=False)
    text = _text(page)
    assert page.index("<h2>阶段进度</h2>") < page.index("<h2>步骤</h2>") < page.index("<h2>门禁明细</h2>")
    section = page[page.index("<h2>步骤</h2>") : page.index("<h2>门禁明细</h2>")]
    table, rework = section.split("<h3>返工与表外派发清单</h3>")
    assert "内核派出的步骤共 3 个，在途 1 个：implement.m2.code" in table  # 形状不对的记录跳过，内核自己做的不算派出
    assert "<th>步骤</th><th>角色</th><th>第几次派发</th><th>状态</th><th>任务文件大小</th><th>派发时间</th><th>完成时间</th><th>原因</th>" in table
    table, _sep, own = table.partition("<details>")
    rows = re.findall(r"<tr><td class='nowrap'><code>.*?</tr>", table, flags=re.S)
    # 内核自己做完的机器步骤没有派发对象：折叠单列（按完成时间），不进上面的表，也不算返工
    assert "<summary>内核自己做完的机器步骤 2 个（没有派发对象）</summary>" in own and own.rstrip().endswith("</details>")
    assert re.findall(r"<code>(.*?)</code>", own) == ["plan.datacheck@g0.1", "plan.seed@g0.2"] and "kernel" not in _text(table)
    assert [re.search(r"<code>(.*?)</code>", r).group(1) for r in rows] == ["extract.main", "spec_audit.external", "implement.m2.code"]  # 按派发时间
    done, failed, flying = (_text(r) for r in rows)
    assert "quant-extractor 派发 1 完成 20.0 KB 2026-11-22 01:00 2026-11-22 01:20 首派" in done
    assert "external 执行 1 失败 900 B" in failed
    assert "quant-coder 派发 2 在途 40.3 KB 2026-11-22 02:00 - 门禁 G-IM-3 未过重派 <x>" not in flying  # 原因要转义
    assert "quant-coder 派发 2 在途 40.3 KB 2026-11-22 02:00 - 门禁 G-IM-3 未过重派" in flying and "未过重派 &lt;x&gt;" in rows[2]
    assert "<span class='pill gate'>在途</span>" in rows[2] and "<span class='pill fail'>失败</span>" in rows[1]
    # 返工（派了不止一次）与表外派发
    listed = [_text(r) for r in re.findall(r"<tr><td class='nowrap'>(?:返工|表外派发)</td>.*?</tr>", rework, flags=re.S)]
    assert len(listed) == 2
    assert "返工 implement.m2.code quant-coder 2 在途" in listed[0] and "表外派发 adhoc.01 quant-coder - 完成 2026-11-22 02:10 补一张图" in listed[1]
    assert "extract.main" not in rework
    assert "累计：重派：implement.m2.code 1 次、计划门禁修复 2 轮；复审轮数：result 2 次；假 FAIL 复跑：m2 1 次；表外派发 1 次。" in _text(rework)
    assert "plan.seed" not in rework
    # 泳道：在途步骤标在所属阶段那一行；钉在执行卡上的阶段标出来并写原因
    stage_rows = re.findall(r"<tr><td class='nowrap'><strong>.*?</tr>", page, flags=re.S)
    assert len(stage_rows) == len(st.STAGE_ORDER)
    by_stage = dict(zip(st.STAGE_ORDER, stage_rows))
    assert "<span class='pill gate'>在途 implement.m2.code（第 2 次）</span>" in by_stage["implement"]
    assert sum("在途 " in r for r in stage_rows) == 1
    assert "<span class='pill warn'>执行卡</span><div class='muted small'>legacy_inflight：迁移时进行到一半</div>" in by_stage["verify"]
    assert sum(">执行卡</span>" in r for r in stage_rows) == 1  # 钉成 kernel 的不标
    # 连败计数：不为零的列出来，到 3 的标红
    gate = page[page.index("<h2>门禁明细</h2>") : page.index("<div class='filter-bar'>")]
    assert "连败计数" in gate and "<span class='pill fail'>验证 G-VF-4 连续 3 次未过，已到熔断线</span>" in gate
    assert "<span class='pill warn'>编码 G-IM-3 连续 1 次未过</span>" in gate and "G-IN-1" not in gate
    assert gate.index("G-VF-4 连续 3 次") < gate.index("G-IM-3 连续 1 次")
    # 原有的小节照旧
    assert "现在 验证（第 2 次尝试，由执行卡推进）" in text and "已连续 2 次未过。G-VF-4 的明细" in text and "外审台账" in text and "返工与迭代" in text

    # 没有返工也没有表外派发时说明一句；由内核推进的阶段在状态条上写明
    _edit_state(root, CASE, flow={"steps": {"extract.main": {"status": "inflight", "attempt": 1, "kind": "dispatch", "role": "quant-extractor", "stage": "extract"}}, "inflight": ["extract.main"], "adhoc": [], "pinned": {}}, counters={"gate_fail_streak": {}, "redispatch": {}, "review_rounds": {}, "adhoc": 0, "false_fail": {}})
    page = board.render_case(root, CASE, with_usage=False)
    assert "没有返工，也没有表外派发。" in page and "累计：" not in page and "连败计数" not in page and ">执行卡</span>" not in page
    assert "现在 验证（由内核推进，在途 1 步）" in _text(page)


def test_v2_steps_in_the_same_second_keep_their_recorded_order(root: Path) -> None:
    _make_case(root, schema_version=2)
    at = "2026-11-22T01:00:00+08:00"
    steps = {sid: {"status": "done", "attempt": 1, "kind": "dispatch", "role": "r", "stage": "plan", "issued_at": at, "done_at": at} for sid in ("plan.main", "extract.main", "code_audit.ext.r1")}
    steps["verify.main"] = {**steps["plan.main"], "issued_at": "2026-11-22T00:59:59+08:00"}
    steps["plan.seed@g0.1"] = {"status": "done", "kind": "kernel", "done_at": at}
    _edit_state(root, CASE, flow={"steps": steps})
    state = st.load_state(root, CASE)
    # 时间戳只到秒：先按派发时间，同一秒内按登记先后，不按编号的字母序
    assert [sid for sid, _rec in board.step_records(state)] == ["verify.main", "plan.main", "extract.main", "code_audit.ext.r1"]
    assert [sid for sid, _rec in board.kernel_marks(state)] == ["plan.seed@g0.1"]


def test_new_sections_absent_for_v1_and_plain_v2(root: Path) -> None:
    _make_case(root)
    page = board.render_case(root, CASE, with_usage=False)
    for mark in NEW_SECTION_MARKS:
        assert mark not in page, mark
    # 旧案例就算状态里混进了这些键也不看
    original = st.state_path(root, CASE).read_bytes()
    _edit_state(root, CASE, checkpoints=[{"id": "cp_01", "name": "spec_final", "kind": "human", "status": "pending", "reason": "x"}], flow={"steps": {"a.b": {"status": "inflight", "attempt": 2}}}, counters={"gate_fail_streak": {"verify:G-VF-4": 5}})
    page = board.render_case(root, CASE, with_usage=False)
    for mark in NEW_SECTION_MARKS:
        assert mark not in page, mark
    st.state_path(root, CASE).write_bytes(original)

    # 刚迁移的 v2 案例：没有检查点、没有步骤，只多出连败计数与「执行卡」标记
    st.migrate_to_v2(root, CASE)
    _edit_state(root, CASE, checkpoints=[], flow={"steps": {}})
    page = board.render_case(root, CASE, with_usage=False)
    for mark in ("待决检查点", "检查点记录", "<h2>步骤</h2>", "返工与表外派发清单"):
        assert mark not in page, mark
    assert "<span class='pill warn'>验证 G-VF-4 连续 2 次未过</span>" in page and ">执行卡</span>" in page

    # 形状不对的检查点、计数、步骤不让看板失败
    _edit_state(root, CASE, checkpoints=["坏的", {"id": "cp_01"}, {"id": "cp_02", "name": "spec_final", "kind": "human", "status": "pending", "options": "不是数组", "pack": "../../etc/passwd", "decision": "不是对象"}, {"id": "cp_03", "name": "x", "kind": "human", "status": "resolved", "decision": None}], flow={"steps": ["不是对象"], "pinned": "不是对象", "adhoc": "不是数组"}, counters={"gate_fail_streak": {"verify:G-VF-4": "三次", "a": True}, "redispatch": "x", "adhoc": "y"})
    page = board.render_case(root, CASE, with_usage=False)
    assert "<h2>待决检查点</h2>" in page and "<code>../../etc/passwd</code>" in page and "href='../../etc/passwd'" not in page  # 工作区外的路径只显示不给链接
    assert "连败计数" not in page and "<h2>步骤</h2>" not in page and "<h2>检查点记录</h2>" in page


def test_index_shows_which_checkpoint_each_case_is_stopped_at(root: Path) -> None:
    st.init_state(root, "r001_v1", "reports/r001_v1.pdf")
    st.init_state(root, "r003_run", "reports/r003_run.pdf", schema_version=2)
    _make_checkpoint_case(root, "r002_gap")
    page = board.render_index(root)
    assert "<th>停在</th><th>停在哪个检查点</th><th>等了多久</th>" in page
    rows = {m.group(1): m.group(0) for m in re.finditer(r"<tr><td>(?:<a [^>]*>)?(r\d{3}_\w+?)(?:</a>)?</td>.*?</tr>", page, flags=re.S)}
    assert set(rows) == {"r001_v1", "r002_gap", "r003_run"}
    assert f"<td class='nowrap'>{rp.checkpoint_title('data_gap')}（cp_04）</td>" in rows["r002_gap"]
    for rid in ("r001_v1", "r003_run"):  # 旧案例、没有停在检查点上的案例显示「-」
        cells = re.findall(r"<td[^>]*>(.*?)</td>", rows[rid], flags=re.S)
        assert cells[4] == "-" and len(cells) == 9
    assert _text(page).index("r002_gap") < _text(page).index("r001_v1")  # 等人处理的仍排最前
