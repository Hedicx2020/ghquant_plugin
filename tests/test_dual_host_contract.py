"""双宿主插件的静态分发与编排合同。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SKILL_DIR = ROOT / "skills" / "reproduce"
SKILL_MAX_BYTES = 6144  # 薄壳：流程在内核里，主技能只留角色、硬规则、主循环与路由


def test_codex_manifest_points_to_shared_skill():
    data = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "quant-report-reproduce"
    assert data["version"] == "3.0.0"
    assert data["skills"] == "./skills/"
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert claude["version"] == data["version"] and claude["name"] == data["name"]


def test_host_specific_marketplaces_point_to_same_plugin():
    claude = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    claude_entry = claude["plugins"][0]
    assert claude_entry["source"] == "./"
    assert "policy" not in claude_entry

    codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    codex_entry = codex["plugins"][0]
    assert codex["name"] == "hedi-quant-codex"
    assert codex_entry["name"] == claude_entry["name"] == "quant-report-reproduce"
    assert codex_entry["source"] == {"source": "local", "path": "./"}
    assert codex_entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert codex_entry["category"] == "Developer Tools"


def test_legacy_cards_still_use_the_shared_executor():
    """旧执行卡挪到了 stages/legacy/（旧案例与被退回执行卡的阶段还在用），外审仍只经统一执行器。"""
    legacy = SKILL_DIR / "stages" / "legacy"
    for name in ("spec_audit", "code_audit", "result_audit", "iterate"):
        text = (legacy / f"{name}.md").read_text(encoding="utf-8")
        assert "external_review.py" in text
        assert "command codex exec" not in text
    assert (legacy / "README.md").is_file() and (SKILL_DIR / "stages" / "setup.md").is_file()
    assert sorted(p.name for p in (SKILL_DIR / "stages").glob("*.md")) == ["setup.md"]


def test_every_external_review_step_runs_through_run_review(tmp_path, monkeypatch):
    """步骤表里的外审步骤（三个审查点与第二意见）都由内核经 external_review.run_review 执行。"""
    import flow_harness as fh

    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch)
    scenario = fh.Scenario(difficulty="hard", milestones=3, verify_values=[(0.02, 0.04), (0.021, 0.04), (0.052, 0.041)], diagnose=["continue", "continue"])
    stub = fh.Stub(root, rid, scenario)
    fh.install_fake_review(monkeypatch, stub)  # 把 run_review 换成假的：没走它的外审会去调真的命令行而失败
    out = fh.drive(root, rid, stub)
    assert out["halt"]["checkpoints"][0]["name"] == "final_review"
    assert {entry["kind"] for entry in stub.review_log} == {"spec", "code", "result", "second_opinion"}
    assert all(entry["engine"] == "codex" for entry in stub.review_log)  # 夹具的宿主是 Claude Code


def test_no_hardcoded_review_command_in_skill_or_kernel_assets():
    paths = [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "adapters").glob("*.md")), *sorted((SKILL_DIR / "explain").glob("*.md"))]
    paths += [p for p in sorted((ROOT / "tools" / "flowlib").glob("*.py"))] + [ROOT / "tools" / "flow.py"]
    assert len(paths) > 30
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "codex exec" not in text and "claude -p " not in text, path.name


def test_shared_skill_is_a_thin_shell_that_routes_three_hosts():
    raw = (SKILL_DIR / "SKILL.md").read_bytes()
    text = raw.decode("utf-8")
    assert len(raw) <= SKILL_MAX_BYTES, f"SKILL.md {len(raw)} 字节，超过 {SKILL_MAX_BYTES}"
    for adapter in ("adapters/claude_code.md", "adapters/codex.md", "adapters/generic.md"):
        assert adapter in text and (SKILL_DIR / adapter).is_file()
    assert "EXTERNAL_ENGINE" in text
    # 推进只经 flow：主技能不再教人直接写状态、手工跑门禁
    for banned in ("set-stage", "state.py set", "record-event", "check_gates.py"):
        assert banned not in text, banned
    for needed in ("flow next", "flow done", "flow decide", "flow explain", "--quote", "prompt_inline", "halt"):
        assert needed in text, needed
    assert "宿主 agent 名兼容" in text and "general-purpose" in text
    # 本仓库直跑时技能经符号链接加载，Base directory 上两级不一定是仓库根：要有兜底的定位办法
    assert "tools/flow.py" in text and "$PWD" in text and "plugin_root" in text


def test_external_engine_is_never_the_hosts_own_family():
    from tools.flowlib import core

    assert core.external_engine("claude_code") == ("codex", "codex_external")
    assert core.external_engine("codex") == ("claude", "claude_external")
    # 配置里写了同家族的引擎也不采纳
    assert core.external_engine("claude_code", {"external_review": {"engine": "claude"}})[0] == "codex"
    assert core.external_engine("codex", {"external_review": {"engine": "codex"}})[0] == "claude"
    # 通用宿主默认 codex，可以由配置改成 claude
    assert core.external_engine("generic")[0] == "codex"
    assert core.external_engine("generic", {"external_review": {"engine": "claude"}})[0] == "claude"


def test_orders_name_the_host_agent_and_fall_back_when_codex_roles_drift(tmp_path, monkeypatch):
    import shutil

    import flow_harness as fh
    from tools.flowlib import tasks
    from tools.flowlib.engine import Engine

    root = fh.make_root(tmp_path, {"economy": True})
    rid = fh.new_case(root, monkeypatch)
    order = Engine(root, rid, host="claude_code").advance()["orders"][0]
    assert order["agent"] == "quant-extractor" and order["model"] == "sonnet" and order["model_tier"] == "economy"
    assert order["contract"]["sha"] == tasks.contract_sha("quant-extractor")

    # Codex：工作区里没有角色文件 → 退回通用子代理
    monkeypatch.setattr(tasks, "_CODEX_EXPECTED", None)
    root2 = fh.make_root(tmp_path / "codex", {"economy": True})
    rid2 = fh.new_case(root2, monkeypatch)
    order = Engine(root2, rid2, host="codex").advance()["orders"][0]
    assert order["agent"] is None and "通用子代理" in order["agent_fallback"] and "model" not in order

    # 角色文件与合同正本一致 → 用命名角色；经济档优先用 -economy 变体
    shutil.copytree(ROOT / ".codex" / "agents", root2 / ".codex" / "agents")
    ctx = Engine(root2, rid2, host="codex").ctx()
    assert tasks.host_agent(ctx, "quant-extractor", "economy") == {"agent": "quant-extractor-economy"}
    assert tasks.host_agent(ctx, "quant-coder", "default") == {"agent": "quant-coder"}
    assert tasks.host_agent(ctx, "general-purpose", "default") == {}

    # 角色文件漂移（插件升级后工作区里还是旧的）→ 退回通用子代理
    stale = root2 / ".codex" / "agents" / "quant-coder.toml"
    stale.write_text(stale.read_text(encoding="utf-8").replace("量化", "量 化", 1), encoding="utf-8")
    assert tasks.host_agent(ctx, "quant-coder", "default")["agent"] is None
    (root2 / ".codex" / "agents" / "quant-extractor-economy.toml").unlink()
    assert tasks.host_agent(ctx, "quant-extractor", "economy") == {"agent": "quant-extractor"}  # 没有经济档变体就用原角色


def test_host_adapters_define_dispatch_and_fallback():
    claude = (ROOT / "skills" / "reproduce" / "adapters" / "claude_code.md").read_text(encoding="utf-8")
    codex = (ROOT / "skills" / "reproduce" / "adapters" / "codex.md").read_text(encoding="utf-8")
    assert "EXTERNAL_ENGINE=codex" in claude
    assert "EXTERNAL_ENGINE=claude" in codex
    assert "same_host_fallback" in claude
    assert "same_host_fallback" in codex
    generic = (ROOT / "skills" / "reproduce" / "adapters" / "generic.md").read_text(encoding="utf-8")
    assert "HOST=generic" in generic and "same_host_fallback" in generic and "external_review.engine" in generic
    for text in (claude, codex, generic):
        # 三张卡回答同样的四件事：怎么派发、怎么后台执行与等待、怎么向人提问并取得凭据
        assert "prompt_inline" in text and "step_id" in text and "flow wait" in text and "凭据" in text
    assert "python3" in claude and "不继承主会话历史" in codex


def test_external_prompt_templates_do_not_hardcode_cli_command():
    for path in sorted((ROOT / "templates" / "codex_prompts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "command codex exec" not in text
        assert "external_review.py" in text
