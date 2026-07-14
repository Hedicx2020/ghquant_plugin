"""双宿主插件的静态分发与编排合同。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_codex_manifest_points_to_shared_skill():
    data = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "quant-report-reproduce"
    assert data["version"] == "2.12.0"
    assert data["skills"] == "./skills/"


def test_legacy_marketplace_carries_codex_policy_without_second_catalog():
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = data["plugins"][0]
    assert entry["source"] == "./"
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    assert entry["category"] == "Developer Tools"
    assert not (ROOT / ".agents" / "plugins" / "marketplace.json").exists()


def test_stage_cards_use_external_executor():
    for name in ("spec_audit", "code_audit", "result_audit", "iterate"):
        text = (ROOT / "skills" / "reproduce" / "stages" / f"{name}.md").read_text(encoding="utf-8")
        assert "external_review.py" in text
        assert "command codex exec" not in text


def test_shared_skill_routes_both_hosts():
    text = (ROOT / "skills" / "reproduce" / "SKILL.md").read_text(encoding="utf-8")
    assert "adapters/claude_code.md" in text
    assert "adapters/codex.md" in text
    assert "EXTERNAL_ENGINE" in text


def test_host_adapters_define_dispatch_and_fallback():
    claude = (ROOT / "skills" / "reproduce" / "adapters" / "claude_code.md").read_text(encoding="utf-8")
    codex = (ROOT / "skills" / "reproduce" / "adapters" / "codex.md").read_text(encoding="utf-8")
    assert "EXTERNAL_ENGINE=codex" in claude
    assert "EXTERNAL_ENGINE=claude" in codex
    assert "same_host_fallback" in claude
    assert "same_host_fallback" in codex


def test_external_prompt_templates_do_not_hardcode_cli_command():
    for path in sorted((ROOT / "templates" / "codex_prompts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "command codex exec" not in text
        assert "external_review.py" in text
