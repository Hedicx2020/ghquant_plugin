"""tools/state.py 的测试：目录骨架、schema 校验、状态流转、原子写、legacy 归档。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import state as st  # noqa: E402


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_directory_skeleton(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")

    assert (tmp_path / "workspace" / "demo" / "spec").is_dir()
    assert (tmp_path / "workspace" / "demo" / "audit").is_dir()
    assert (tmp_path / "workspace" / "demo" / "iterations").is_dir()
    assert (tmp_path / "output" / "demo" / "results").is_dir()
    assert (tmp_path / "src" / "demo").is_dir()
    assert (tmp_path / "workspace" / "demo" / "state.json").is_file()


def test_init_produces_valid_schema(tmp_path: Path) -> None:
    state = st.init_state(tmp_path, "demo", "reports/demo.pdf")
    errors = st.validate_state(state)
    assert errors == []
    assert state["schema_version"] == st.SCHEMA_VERSION
    assert state["report_id"] == "demo"
    assert state["mode"] == "auto"
    assert state["status"] == "running"
    assert state["current_stage"] == st.STAGE_ORDER[0]
    assert set(state["stages"].keys()) == set(st.STAGE_ORDER)
    assert all(entry["status"] == "pending" for entry in state["stages"].values())
    assert state["pdf_path"] == "reports/demo.pdf"
    assert state["paths"]["workspace"] == "workspace/demo"
    assert state["paths"]["src"] == "src/demo"
    assert state["paths"]["output"] == "output/demo"


def test_init_reload_matches_saved_state(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    loaded = st.load_state(tmp_path, "demo")
    assert st.validate_state(loaded) == []
    assert loaded["report_id"] == "demo"


def test_init_legacy_all_stages_skipped_and_status_done(tmp_path: Path) -> None:
    state = st.init_state(tmp_path, "legacy_case", "reports/legacy.pdf", legacy=True)
    assert st.validate_state(state) == []
    assert state["status"] == "done"
    assert all(entry["status"] == "skipped" for entry in state["stages"].values())
    assert state["current_stage"] == st.STAGE_ORDER[-1]


def test_init_legacy_accepts_missing_pdf_path(tmp_path: Path) -> None:
    """T5 迁移场景回归用例：momentum_factor/long_term_momentum 等旧案例的原始 PDF
    已不在 reports/ 下，init --legacy 不得做存在性校验，只需如实记录传入路径。"""
    pdf_path = "reports/momentum_factor.pdf"
    assert not (tmp_path / pdf_path).exists()
    state = st.init_state(tmp_path, "momentum_factor", pdf_path, legacy=True)
    assert st.validate_state(state) == []
    assert state["pdf_path"] == pdf_path
    assert state["status"] == "done"


def test_init_invalid_mode_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        st.init_state(tmp_path, "demo", "reports/demo.pdf", mode="bogus")


# ---------------------------------------------------------------------------
# set-stage
# ---------------------------------------------------------------------------


def test_set_stage_running_increments_attempts_and_updates_current(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state = st.set_stage(tmp_path, "demo", "extract", "running")

    assert state["stages"]["extract"]["status"] == "running"
    assert state["stages"]["extract"]["attempts"] == 1
    assert state["current_stage"] == "extract"
    assert state["stages"]["extract"]["updated_at"] is not None
    assert state["updated_at"] == state["stages"]["extract"]["updated_at"]

    events = [e["event"] for e in state["events"]]
    assert "stage:extract:running" in events


def test_set_stage_done_does_not_increment_attempts_again(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "extract", "running")
    state = st.set_stage(tmp_path, "demo", "extract", "done")

    assert state["stages"]["extract"]["status"] == "done"
    assert state["stages"]["extract"]["attempts"] == 1  # running 时才 +1


def test_set_stage_retry_increments_attempts_again(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "extract", "running")
    st.set_stage(tmp_path, "demo", "extract", "failed")
    state = st.set_stage(tmp_path, "demo", "extract", "running")
    assert state["stages"]["extract"]["attempts"] == 2


def test_set_stage_invalid_stage_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.set_stage(tmp_path, "demo", "not_a_stage", "running")


def test_set_stage_invalid_status_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.set_stage(tmp_path, "demo", "extract", "not_a_status")


def test_set_stage_persists_across_reload(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "extract", "running")
    reloaded = st.load_state(tmp_path, "demo")
    assert reloaded["stages"]["extract"]["status"] == "running"


# ---------------------------------------------------------------------------
# set（顶层/嵌套字段）
# ---------------------------------------------------------------------------


def test_set_field_json_parses_list_and_int(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(tmp_path, "demo", "tags", '["ml", "factor"]')
    state = st.set_field(tmp_path, "demo", "max_iter", "5")
    assert state["tags"] == ["ml", "factor"]
    assert state["max_iter"] == 5


def test_set_field_plain_string_fallback(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state = st.set_field(tmp_path, "demo", "type", "factor")
    assert state["type"] == "factor"


def test_set_field_nested_verdict_result(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state = st.set_field(tmp_path, "demo", "verdict.result", "pass")
    assert state["verdict"]["result"] == "pass"


def test_set_field_invalid_enum_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.set_field(tmp_path, "demo", "difficulty", "impossible")
    with pytest.raises(ValueError):
        st.set_field(tmp_path, "demo", "feasibility", "totally_fine")
    with pytest.raises(ValueError):
        st.set_field(tmp_path, "demo", "type", "not_a_type")


def test_set_field_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.set_field(tmp_path, "demo", "made_up_field", "1")


# ---------------------------------------------------------------------------
# record-event
# ---------------------------------------------------------------------------


def test_record_event_appends_with_payload(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state = st.record_event(tmp_path, "demo", "custom_event", payload={"foo": "bar"})
    last = state["events"][-1]
    assert last["event"] == "custom_event"
    assert last["payload"] == {"foo": "bar"}
    assert last["timestamp"].endswith("+08:00")


# ---------------------------------------------------------------------------
# milestone
# ---------------------------------------------------------------------------


def test_milestone_field_update(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(
        tmp_path,
        "demo",
        "milestones",
        json.dumps(
            [{"id": "M1", "name": "因子实现", "deps": [], "implement": "pending", "code_review": "pending", "verify": "pending"}]
        ),
    )
    state = st.set_milestone_field(tmp_path, "demo", "M1", "implement", "done")
    assert state["milestones"][0]["implement"] == "done"


def test_milestone_field_invalid_field_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(
        tmp_path,
        "demo",
        "milestones",
        json.dumps(
            [{"id": "M1", "name": "x", "deps": [], "implement": "pending", "code_review": "pending", "verify": "pending"}]
        ),
    )
    with pytest.raises(ValueError):
        st.set_milestone_field(tmp_path, "demo", "M1", "not_a_field", "done")


def test_milestone_not_found_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.set_milestone_field(tmp_path, "demo", "M_MISSING", "implement", "done")


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


def test_record_gate_appends(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    checks = [{"id": "G-IN-1", "desc": "state schema 合法", "result": "PASS"}]
    state = st.record_gate(tmp_path, "demo", "init", "PASS", checks)
    assert state["gates"][-1]["stage"] == "init"
    assert state["gates"][-1]["verdict"] == "PASS"
    assert state["gates"][-1]["checks"] == checks


def test_record_gate_invalid_verdict_rejected(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    with pytest.raises(ValueError):
        st.record_gate(tmp_path, "demo", "init", "MAYBE", [])


# ---------------------------------------------------------------------------
# 原子写：不残留临时文件
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    for i in range(5):
        st.set_stage(tmp_path, "demo", "extract", "running" if i % 2 == 0 else "failed")

    workspace = tmp_path / "workspace" / "demo"
    leftover = list(workspace.glob("*.tmp")) + list(workspace.glob(".state_*"))
    assert leftover == []
    assert (workspace / "state.json").is_file()


def test_atomic_write_cleans_up_tmp_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "sub" / "state.json"
    target.parent.mkdir(parents=True)

    import json as json_module

    def boom(*args, **kwargs):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr(json_module, "dump", boom)
    with pytest.raises(RuntimeError):
        st.atomic_write_json(target, {"a": 1})

    leftover = list(target.parent.glob("*"))
    assert leftover == []  # 临时文件必须被清理，且未产生半成品正式文件


def test_atomic_write_rename_semantics_not_corrupt_existing(tmp_path: Path) -> None:
    """写入失败不得破坏已存在的合法 state.json（rename 语义：要么整体替换，要么保持原状）。"""
    state = st.init_state(tmp_path, "demo", "reports/demo.pdf")
    path = st.state_path(tmp_path, "demo")
    original_bytes = path.read_bytes()

    with pytest.raises(st.StateValidationError):
        # 顶层字段被人为破坏，校验应拒绝写入
        broken = dict(state)
        broken.pop("status")
        st.save_state(tmp_path, "demo", broken)

    assert path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# validate_state 细节
# ---------------------------------------------------------------------------


def test_validate_state_rejects_missing_fields() -> None:
    errors = st.validate_state({"report_id": "x"})
    assert errors  # 应报出缺字段


def test_validate_state_rejects_bad_stage_status(tmp_path: Path) -> None:
    state = st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state["stages"]["extract"]["status"] = "not_valid"
    errors = st.validate_state(state)
    assert any("stages.extract.status" in e for e in errors)


def test_validate_state_rejects_extra_top_level_field(tmp_path: Path) -> None:
    state = st.init_state(tmp_path, "demo", "reports/demo.pdf")
    state["unexpected_field"] = 1
    errors = st.validate_state(state)
    assert any("未声明的顶层字段" in e for e in errors)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_summary_contains_key_sections(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    text = st.show_summary(tmp_path, "demo")
    assert "report_id: demo" in text
    assert "stage 状态:" in text
    assert "verdict:" in text
    assert "blockers:" in text
    assert "pending_question:" in text


def test_show_summary_warns_when_recently_running(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "extract", "running")
    state = st.load_state(tmp_path, "demo")
    assert state["status"] == "running"
    text = st.show_summary(tmp_path, "demo")
    assert "疑似另一会话在跑" in text


def test_show_summary_no_warning_when_done(tmp_path: Path) -> None:
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(tmp_path, "demo", "status", "done")
    text = st.show_summary(tmp_path, "demo")
    assert "疑似另一会话在跑" not in text


# ---------------------------------------------------------------------------
# CLI（argparse + main，用 REPORT_REPRODUCE_ROOT 环境变量隔离到 tmp_path）
# ---------------------------------------------------------------------------


def test_cli_init_and_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    rc = st.main(["init", "cli_demo", "--pdf", "reports/cli_demo.pdf"])
    assert rc == 0
    rc = st.main(["show", "cli_demo"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "report_id: cli_demo" in captured.out


def test_cli_set_stage_and_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    st.main(["init", "cli_demo", "--pdf", "reports/cli_demo.pdf"])
    rc = st.main(["set-stage", "cli_demo", "init", "running"])
    assert rc == 0
    rc = st.main(["gate", "cli_demo", "init", "PASS", "--checks", '[{"id":"G-IN-1","desc":"x","result":"PASS"}]'])
    assert rc == 0
    state = st.load_state(tmp_path, "cli_demo")
    assert state["gates"][-1]["verdict"] == "PASS"


def test_cli_invalid_command_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    rc = st.main(["set-stage", "no_such_report", "extract", "running"])
    assert rc == 1


# ---------------------------------------------------------------------------
# oos stage 与 migrate（STAGE_ORDER 演进的旧 state 兼容）
# ---------------------------------------------------------------------------


def test_stage_order_contains_oos_between_result_audit_and_report():
    order = st.STAGE_ORDER
    assert order.index("oos") == order.index("result_audit") + 1
    assert order.index("report") == order.index("oos") + 1


def test_migrate_backfills_missing_stage_as_skipped_for_terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    root = tmp_path
    state = st.init_state(root, "demo", "reports/demo.pdf")
    # 模拟旧 state：删掉 oos 键并置终态（绕过 validate 直接写文件模拟历史版本）
    del state["stages"]["oos"]
    state["status"] = "done_partial"
    p = st.state_path(root, "demo")
    p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    added = st.migrate_stages(root, "demo")
    assert added == ["oos"]
    migrated = json.loads(p.read_text(encoding="utf-8"))
    assert migrated["stages"]["oos"]["status"] == "skipped"
    # 幂等
    assert st.migrate_stages(root, "demo") == []


def test_migrate_backfills_as_pending_for_running(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    root = tmp_path
    state = st.init_state(root, "demo2", "reports/demo2.pdf")
    del state["stages"]["oos"]
    p = st.state_path(root, "demo2")
    p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    st.migrate_stages(root, "demo2")
    migrated = json.loads(p.read_text(encoding="utf-8"))
    assert migrated["stages"]["oos"]["status"] == "pending"


# ---------------------------------------------------------------------------
# 案例统一编号：next-id / resolve
# ---------------------------------------------------------------------------


def test_next_id_starts_from_r001(tmp_path: Path) -> None:
    """空 workspace 或仅有无编号旧案例时，从 r001 起。"""
    assert st.next_numbered_id(tmp_path, "alpha") == "r001_alpha"
    st.init_state(tmp_path, "ssrn_6115073", "reports/x.pdf")  # 旧式无编号 id 不参与计数
    assert st.next_numbered_id(tmp_path, "alpha") == "r001_alpha"


def test_next_id_increments_from_max(tmp_path: Path) -> None:
    st.init_state(tmp_path, "r001_alpha", "reports/a.pdf")
    st.init_state(tmp_path, "r007_beta", "reports/b.pdf")
    assert st.next_numbered_id(tmp_path, "gamma") == "r008_gamma"


def test_next_id_ignores_dirs_without_state(tmp_path: Path) -> None:
    (tmp_path / "workspace" / "r099_ghost").mkdir(parents=True)  # 无 state.json 的目录不算案例
    assert st.next_numbered_id(tmp_path, "alpha") == "r001_alpha"


def test_next_id_rejects_bad_slug(tmp_path: Path) -> None:
    for bad in ("1abc", "Has_Upper", "with-dash", "", "x" * 41):
        with pytest.raises(ValueError):
            st.next_numbered_id(tmp_path, bad)


def test_resolve_exact_number_abbrev_and_prefix(tmp_path: Path) -> None:
    st.init_state(tmp_path, "r001_alpha", "reports/a.pdf")
    st.init_state(tmp_path, "r012_beta", "reports/b.pdf")
    st.init_state(tmp_path, "ssrn_6115073", "reports/c.pdf")
    assert st.resolve_case_id(tmp_path, "r001_alpha") == "r001_alpha"      # 完整 id
    for q in ("r12", "r012", "12"):                                        # 编号缩写三种写法
        assert st.resolve_case_id(tmp_path, q) == "r012_beta"
    assert st.resolve_case_id(tmp_path, "ssrn") == "ssrn_6115073"          # 旧式 id 唯一前缀


def test_resolve_rejects_ambiguous_and_missing(tmp_path: Path) -> None:
    st.init_state(tmp_path, "r001_alpha", "reports/a.pdf")
    st.init_state(tmp_path, "r002_alpha_v2", "reports/b.pdf")
    with pytest.raises(ValueError, match="多个案例"):
        st.resolve_case_id(tmp_path, "r00")
    with pytest.raises(ValueError, match="未找到"):
        st.resolve_case_id(tmp_path, "r9")
