"""Claude Markdown 角色合同 → Codex TOML 同步测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sync_codex_agents as sca  # noqa: E402


tomllib = pytest.importorskip("tomllib")  # 3.11 起才有；3.10 上跳过需要解析 TOML 的用例


def test_all_markdown_agents_generate_valid_toml(tmp_path):
    written = sca.sync_agents(ROOT, tmp_path)
    assert len(written) == 8 + len(sca.ECONOMY_ROLES)
    for path in written:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        base = data["name"].removesuffix(sca.ECONOMY_SUFFIX)
        source = ROOT / "agents" / f"{base}.md"
        assert sca.parse_agent(source).body == data["developer_instructions"]


def test_repo_toml_matches_markdown_contracts():
    """仓库里随插件分发的 .codex/agents 必须与 agents/*.md 逐字一致（改了合同要重跑同步脚本）。"""
    assert sca.drifted_agents(ROOT) == []
    sca.check_agents(ROOT)


def test_economy_variants_lower_reasoning_only(tmp_path):
    from tools.flowlib import core

    assert set(sca.ECONOMY_ROLES) == core.ECONOMY_ROLES
    sca.sync_agents(ROOT, tmp_path)
    for role in sca.ECONOMY_ROLES:
        base = tomllib.loads((tmp_path / f"{role}.toml").read_text(encoding="utf-8"))
        economy = tomllib.loads((tmp_path / f"{role}{sca.ECONOMY_SUFFIX}.toml").read_text(encoding="utf-8"))
        assert economy["name"] == role + sca.ECONOMY_SUFFIX
        assert economy["developer_instructions"] == base["developer_instructions"]
        assert base["model_reasoning_effort"] == "high" and economy["model_reasoning_effort"] == "medium"
    assert not (tmp_path / f"quant-coder{sca.ECONOMY_SUFFIX}.toml").exists()


def test_drift_list_names_missing_and_changed_files(tmp_path):
    sca.sync_agents(ROOT, tmp_path)
    assert sca.drifted_agents(ROOT, tmp_path) == []
    (tmp_path / "quant-planner.toml").unlink()
    (tmp_path / "quant-verifier-economy.toml").write_text("name = \"x\"\n", encoding="utf-8")
    assert sorted(Path(p).name for p in sca.drifted_agents(ROOT, tmp_path)) == ["quant-planner.toml", "quant-verifier-economy.toml"]


def test_model_is_mapped_to_reasoning_not_slug(tmp_path):
    sca.sync_agents(ROOT, tmp_path)
    for path in tmp_path.glob("*.toml"):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert "model" not in data
        assert data["model_reasoning_effort"] in {"high", "medium"}


def test_reporter_sonnet_maps_to_medium(tmp_path):
    sca.sync_agents(ROOT, tmp_path)
    data = tomllib.loads((tmp_path / "quant-reporter.toml").read_text(encoding="utf-8"))
    assert data["model_reasoning_effort"] == "medium"


def test_check_detects_generated_drift(tmp_path):
    sca.sync_agents(ROOT, tmp_path)
    (tmp_path / "quant-coder.toml").write_text("name = \"wrong\"\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="不同步"):
        sca.check_agents(ROOT, tmp_path)
