"""只读案例上下文：原状态、缺失、历史门禁和边界。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import state as st
from tools.research_context import build_context


def tree_bytes(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_context_reads_real_case_without_mutation(tmp_path):
    st.init_state(tmp_path, "r003_demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "r003_demo", "verify", "running")
    st.record_gate(tmp_path, "r003_demo", "verify", "FAIL", [
        {"id": "G-VF-3", "result": "FAIL", "desc": "原报告0.1，复现0.2"},
    ])
    st.record_gate(tmp_path, "r003_demo", "verify", "PASS", [{"id": "ASSERT-DONE", "result": "PASS"}])
    file = st.output_dir(tmp_path, "r003_demo") / "results/comparison.json"
    file.write_text('{"metrics": []}')
    (st.workspace_dir(tmp_path, "r003_demo") / "oos_report.md").write_text("样本外分析")
    before = tree_bytes(tmp_path)
    result = build_context(tmp_path, "r3")
    assert result["available"] and result["report_id"] == "r003_demo"
    assert result["next_action"]["kind"] == "inspect_deviation"
    assert result["latest_gates"]["verify"]["verdict"] == "FAIL"
    assert result["latest_stage_assertions"]["verify"]["verdict"] == "PASS"
    assert next(a for a in result["artifacts"] if a["path"].endswith("oos_report.md"))["available"]
    assert result["state_sha256"] == hashlib.sha256(before[Path("workspace/r003_demo/state.json")]).hexdigest()
    assert next(a for a in result["artifacts"] if a["path"].endswith("comparison.json"))["available"]
    assert not next(a for a in result["artifacts"] if a["path"].endswith("final_report.md"))["available"]
    assert tree_bytes(tmp_path) == before


def test_missing_and_corrupt_state_stay_unknown(tmp_path):
    root = tmp_path / "absent"
    assert not build_context(root, "demo")["available"]
    assert not root.exists()
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.state_path(tmp_path, "demo").write_text("{broken")
    before = tree_bytes(tmp_path)
    result = build_context(tmp_path, "demo")
    assert not result["available"] and "stages" not in result
    assert tree_bytes(tmp_path) == before


def test_blocker_and_configuration_failure_do_not_suggest_iteration(tmp_path):
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "verify", "running")
    st.record_gate(tmp_path, "demo", "verify", "FAIL", [{"id": "G-VF-0", "result": "FAIL"}])
    assert build_context(tmp_path, "demo")["next_action"]["kind"] == "inspect_gate"
    st.set_field(tmp_path, "demo", "pending_question", "缺少标准文件，请核对")
    assert build_context(tmp_path, "demo")["next_action"]["kind"] == "resolve_blocker"


def test_awaiting_review_preserves_human_decision(tmp_path):
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_field(tmp_path, "demo", "status", "awaiting_review")
    before = tree_bytes(tmp_path)
    result = build_context(tmp_path, "demo")
    assert result["next_action"]["kind"] == "await_review"
    assert tree_bytes(tmp_path) == before


def test_artifact_symlinks_are_not_followed(tmp_path):
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    external = tmp_path / "private.txt"
    external.write_text("private fixture")
    plan = st.workspace_dir(tmp_path, "demo") / "plan.md"
    plan.symlink_to(external)
    result = build_context(tmp_path, "demo")
    item = next(a for a in result["artifacts"] if a["path"].endswith("plan.md"))
    assert not item["available"] and "private fixture" not in json.dumps(result)


@pytest.mark.parametrize("query", ["../x", "/tmp/x", "", "bad/id"])
def test_invalid_case_does_not_create_paths(tmp_path, query):
    before = tree_bytes(tmp_path)
    assert not build_context(tmp_path, query)["available"]
    assert tree_bytes(tmp_path) == before


def test_cli_uses_configured_user_root(tmp_path, monkeypatch):
    st.init_state(tmp_path, "demo", "reports/demo.pdf")
    st.set_stage(tmp_path, "demo", "verify", "running")
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    gates = Path(__file__).resolve().parents[1] / "tools/check_gates.py"
    check = subprocess.run([sys.executable, str(gates), "demo", "--stage", "verify", "--record"], capture_output=True, text=True)
    assert check.returncode == 1 and "G-VF-0" in check.stdout
    before = tree_bytes(tmp_path)
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools/research_context.py"), "demo"], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["available"]
    assert json.loads(result.stdout)["next_action"]["kind"] == "inspect_gate"
    assert tree_bytes(tmp_path) == before
