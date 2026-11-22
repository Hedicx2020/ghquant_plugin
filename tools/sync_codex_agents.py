"""从 Claude Code agent Markdown 正本生成 Codex 项目级 TOML。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

MODEL_REASONING = {"opus": "high", "sonnet": "medium"}
# 经济档：这几个角色另生成一份 <角色>-economy.toml，推理强度按 sonnet 一档。
# 与内核 tools/flowlib/core.py 的 ECONOMY_ROLES 保持一致（tests/test_sync_codex_agents.py 有断言）。
ECONOMY_ROLES = ("quant-extractor", "quant-verifier", "quant-oos-analyst")
ECONOMY_SUFFIX = "-economy"


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    body: str
    model_reasoning_effort: str


def parse_agent(path: Path) -> AgentDefinition:
    """读取带 YAML frontmatter 的 Claude Code agent 文件。"""

    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"agent 缺少合法 frontmatter: {path}")
    meta = yaml.safe_load(parts[1]) or {}
    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    body = parts[2].lstrip("\n").rstrip() + "\n"
    model = str(meta.get("model") or "opus").strip()
    if not name or not description or not body.strip():
        raise ValueError(f"agent 必填字段缺失: {path}")
    if model not in MODEL_REASONING:
        raise ValueError(f"agent model 无映射: {path}: {model}")
    return AgentDefinition(name, description, body, MODEL_REASONING[model])


def _toml_string(value: str) -> str:
    """JSON 字符串字面量是 TOML basic string 的安全子集。"""

    return json.dumps(value, ensure_ascii=False)


def render_toml(agent: AgentDefinition) -> str:
    return (
        f"name = {_toml_string(agent.name)}\n"
        f"description = {_toml_string(agent.description)}\n"
        f"model_reasoning_effort = {_toml_string(agent.model_reasoning_effort)}\n"
        f"developer_instructions = {_toml_string(agent.body)}\n"
    )


def _source_agents(root: Path) -> list[Path]:
    return sorted((root / "agents").glob("quant-*.md"))


def economy_variant(agent: AgentDefinition) -> AgentDefinition:
    """经济档变体：合同正文不变，只是名字带后缀、推理强度降到 sonnet 一档。"""

    return AgentDefinition(agent.name + ECONOMY_SUFFIX, agent.description + "（经济档）", agent.body, MODEL_REASONING["sonnet"])


def expected_files(root: Path) -> dict[str, str]:
    """按 Markdown 正本应当生成的全部文件：{文件名: 内容}。"""

    files: dict[str, str] = {}
    for source in _source_agents(root.resolve()):
        agent = parse_agent(source)
        files[f"{agent.name}.toml"] = render_toml(agent)
        if agent.name in ECONOMY_ROLES:
            variant = economy_variant(agent)
            files[f"{variant.name}.toml"] = render_toml(variant)
    return files


def sync_agents(root: Path, output_dir: Path | None = None) -> list[Path]:
    root = root.resolve()
    destination = (output_dir or root / ".codex" / "agents").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, text in expected_files(root).items():
        target = destination / name
        target.write_text(text, encoding="utf-8")
        written.append(target)
    return written


def drifted_agents(root: Path, output_dir: Path | None = None) -> list[str]:
    """与 Markdown 正本对不上的文件清单（缺失或内容不同）；一致时返回空列表。"""

    root = root.resolve()
    destination = (output_dir or root / ".codex" / "agents").resolve()
    drift: list[str] = []
    for name, expected in expected_files(root).items():
        target = destination / name
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            drift.append(str(target.relative_to(root)) if target.is_relative_to(root) else str(target))
    return drift


def check_agents(root: Path, output_dir: Path | None = None) -> None:
    drift = drifted_agents(root, output_dir)
    if drift:
        raise SystemExit(f"Codex agent 与 Markdown 正本不同步: {', '.join(drift)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 Claude/Codex 量化子代理定义")
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check_agents(args.root, args.output_dir)
        print("Codex agents: 与 Markdown 正本一致")
    else:
        written = sync_agents(args.root, args.output_dir)
        print(f"已生成 {len(written)} 个 Codex agents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
