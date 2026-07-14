"""Claude Markdown 角色合同 → Codex TOML 同步测试。"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import sync_codex_agents as sca  # noqa: E402


def test_all_markdown_agents_generate_valid_toml(tmp_path):
    written = sca.sync_agents(ROOT, tmp_path)
    assert len(written) == 8
    for path in written:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        source = ROOT / "agents" / f"{data['name']}.md"
        assert sca.parse_agent(source).body == data["developer_instructions"]


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
