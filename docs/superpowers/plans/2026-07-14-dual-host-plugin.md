# Claude Code / Codex Dual-Host Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让同一研报复现插件同时在 Claude Code 与 Codex 中运行，并由另一宿主的 CLI 默认执行异构外审。

**Architecture:** 保留一份共享 `reproduce` 技能和阶段卡，用两张宿主适配卡收口代理派发差异；新增 Python 外审执行器统一调用 `codex`/`claude`；Claude Markdown 代理是角色合同正本，脚本生成 Codex 项目代理。门禁优先读取新的宿主无关产物名，同时兼容历史 `*_codex.md`。

**Tech Stack:** Python 3.12、pytest、Markdown/YAML、TOML、Claude Code plugin manifest、Codex plugin manifest、GitHub Actions-compatible CLI tests

## Global Constraints

- 不改 `tools/state.py` 的 12 阶段顺序与状态语义。
- 不改 `templates/standards.json` 或任何达标容差。
- 不修改或迁移历史 `workspace/`、`src/`、`output/` 案例产物。
- 自动测试不得调用真实 Codex 或 Claude 模型。
- 所有用户文案与代码注释使用中文；命令、枚举和文件名保持英文精确值。
- `agents/*.md` 是角色合同正本；生成的 `.codex/agents/*.toml` 不允许手工漂移。
- 新产物使用 `*_external.md`，门禁必须继续接受 `*_codex.md`。

---

### Task 1: 统一外审执行器

**Files:**
- Create: `tools/external_review.py`
- Create: `tests/test_external_review.py`

**Interfaces:**
- Produces: `run_review(engine: str, prompt_path: Path, output_path: Path, cwd: Path, timeout: int = 600) -> ReviewResult`
- Produces: `ReviewResult.to_dict() -> dict[str, object]`
- CLI stdout: one JSON object with `engine/status/reason/returncode/output/duration_seconds`

- [ ] **Step 1: Write failing command-construction tests**

```python
def test_codex_command_is_read_only(tmp_path, monkeypatch):
    seen = install_fake_run(monkeypatch, stdout="ok")
    result = er.run_review("codex", prompt(tmp_path), tmp_path / "out.md", tmp_path)
    assert result.status == "success"
    assert seen[0][0:4] == ["/fake/codex", "exec", "-s", "read-only"]

def test_claude_command_has_read_only_tool_surface(tmp_path, monkeypatch):
    seen = install_fake_run(monkeypatch, stdout="ok")
    er.run_review("claude", prompt(tmp_path), tmp_path / "out.md", tmp_path)
    cmd = seen[0]
    assert cmd[:2] == ["/fake/claude", "-p"]
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_external_review.py -q`
Expected: FAIL because `tools/external_review.py` does not exist.

- [ ] **Step 3: Implement the minimal executor**

Implement a frozen `ReviewResult` dataclass, `_build_command()`, `_classify_failure()` and `run_review()`. Feed prompt text through `subprocess.run(input=...)`; capture stdout/stderr; write with `NamedTemporaryFile` plus `Path.replace()` only on non-empty success. Match quota terms `usage limit|quota|rate limit|429` and auth terms `unauthorized|authentication|login|401|403` case-insensitively.

- [ ] **Step 4: Add failing classification tests**

```python
@pytest.mark.parametrize((stderr, expected), [
    ("usage limit reached", "quota_error"),
    ("HTTP 401 login required", "auth_error"),
])
def test_failure_classification(tmp_path, monkeypatch, stderr, expected):
    install_fake_run(monkeypatch, returncode=1, stderr=stderr)
    assert er.run_review("claude", prompt(tmp_path), tmp_path / "out.md", tmp_path).status == expected

def test_missing_cli_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(er.shutil, "which", lambda _: None)
    assert er.run_review("codex", prompt(tmp_path), tmp_path / "out.md", tmp_path).status == "unavailable"

def test_empty_success_does_not_write_output(tmp_path, monkeypatch):
    install_fake_run(monkeypatch, stdout="  ")
    out = tmp_path / "out.md"
    assert er.run_review("codex", prompt(tmp_path), out, tmp_path).status == "empty_output"
    assert not out.exists()
```

- [ ] **Step 5: Run focused tests and full regression**

Run: `uv run pytest tests/test_external_review.py -q`
Expected: all tests pass.
Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add tools/external_review.py tests/test_external_review.py
git commit -m "feat: 增加双引擎外审执行器"
```

---

### Task 2: 生成并安装 Codex 子代理

**Files:**
- Create: `tools/sync_codex_agents.py`
- Create: `tests/test_sync_codex_agents.py`
- Generate: `.codex/agents/quant-*.toml`
- Modify: `tools/setup_workspace.py`
- Modify: `tests/test_setup_workspace.py`

**Interfaces:**
- Produces: `parse_agent(path: Path) -> AgentDefinition`
- Produces: `render_toml(agent: AgentDefinition) -> str`
- Produces: `sync_agents(root: Path, output_dir: Path | None = None) -> list[Path]`
- `setup_workspace.SEED_DIRS` remains for normal seeds; Codex agents use explicit `copy_codex_agents()` so target path stays `.codex/agents/`.

- [ ] **Step 1: Write failing sync tests**

```python
def test_all_markdown_agents_generate_valid_toml(tmp_path):
    written = sca.sync_agents(ROOT, tmp_path)
    assert len(written) == 8
    for path in written:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        source = ROOT / "agents" / f"{data['name']}.md"
        assert sca.parse_agent(source).body == data["developer_instructions"]

def test_model_is_mapped_to_reasoning_not_slug(tmp_path):
    data = tomllib.loads((sca.sync_agents(ROOT, tmp_path)[0]).read_text(encoding="utf-8"))
    assert "model" not in data
    assert data["model_reasoning_effort"] in {"high", "medium"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_sync_codex_agents.py -q`
Expected: FAIL because sync module does not exist.

- [ ] **Step 3: Implement generator and generate TOML files**

Parse frontmatter with `yaml.safe_load`; render TOML string values using `json.dumps(..., ensure_ascii=False)`; map `opus -> high`, `sonnet -> medium`; reject missing `name`, `description`, or empty body. Run:

```bash
uv run python tools/sync_codex_agents.py --root .
```

- [ ] **Step 4: Add failing setup-copy tests**

```python
def test_fresh_setup_installs_codex_agents(tmp_path):
    report = _run(tmp_path)
    installed = sorted((tmp_path / ".codex" / "agents").glob("quant-*.toml"))
    assert len(installed) == 8
    assert any(p.startswith(".codex/agents/") for p in report.copied)

def test_setup_detects_both_review_clis(tmp_path, monkeypatch):
    monkeypatch.setattr(sw.shutil, "which", lambda name: f"/fake/{name}" if name in {"uv", "codex", "claude"} else None)
    report = sw.SetupReport(target=str(tmp_path))
    sw.check_env(tmp_path, report)
    assert report.env["codex"] == "/fake/codex"
    assert report.env["claude"] == "/fake/claude"
```

- [ ] **Step 5: Implement setup integration and environment copy**

Add `copy_codex_agents()` using the same no-overwrite and plugin-newer behavior as `copy_seeds()`. Add `env["claude"] = shutil.which("claude")` and render both directions explicitly. Do not add a fixed host field to `.reproduce.json`.

- [ ] **Step 6: Verify and commit Task 2**

Run: `uv run pytest tests/test_sync_codex_agents.py tests/test_setup_workspace.py -q`
Expected: all tests pass.
Run: `uv run python tools/sync_codex_agents.py --check --root .`
Expected: exit 0 and no drift.

```bash
git add tools/sync_codex_agents.py tools/setup_workspace.py tests/test_sync_codex_agents.py tests/test_setup_workspace.py .codex/agents
git commit -m "feat: 同步并安装 Codex 量化子代理"
```

---

### Task 3: 外审产物和展示向后兼容

**Files:**
- Modify: `tools/check_gates.py`
- Modify: `tests/test_check_gates.py`
- Modify: `tools/render_report.py`
- Modify: `tests/test_render_report.py`

**Interfaces:**
- Produces: `_external_audit_path(audit_dir: Path, checkpoint: str) -> Path`
- New engine enums: `codex_external|claude_external|same_host_fallback|skipped`
- Legacy engine enums remain readable: `codex|claude_fallback`

- [ ] **Step 1: Write failing gate compatibility tests**

For each of G-SA, G-CA and G-RA, extend the existing valid fixture by renaming only the external review file from `*_codex.md` to `*_external.md`, then assert the gate result has no regression. Add a focused helper test:

```python
def test_external_audit_path_prefers_new_name(tmp_path):
    old = tmp_path / "code_audit_codex.md"
    new = tmp_path / "code_audit_external.md"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    assert cg._external_audit_path(tmp_path, "code") == new
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_check_gates.py -q`
Expected: new-name tests fail because gates only read legacy names.

- [ ] **Step 3: Implement canonical-path lookup**

Implement `_external_audit_path()` with checkpoint whitelist `spec|code|result`; prefer `<checkpoint>_audit_external.md`, fall back to `<checkpoint>_audit_codex.md`. Update human-facing gate labels to “外部审查产物”，without changing `CDX-*` parsing.

- [ ] **Step 4: Write failing renderer tests and implement mappings**

```python
@pytest.mark.parametrize((engine, label), [
    ("codex_external", "Codex 异构外审"),
    ("claude_external", "Claude Code 异构外审"),
    ("same_host_fallback", "同宿主替身（降级外审）"),
])
def test_render_external_engine_labels(tmp_path, engine, label):
    _fixture(tmp_path)
    replace_review_engine(tmp_path, engine)
    assert label in rr.render(tmp_path, "demo").read_text(encoding="utf-8")
```

Keep `codex` and `claude_fallback` mappings. Add `same_host_fallback` to warning-style engines.

- [ ] **Step 5: Verify and commit Task 3**

Run: `uv run pytest tests/test_check_gates.py tests/test_render_report.py -q`
Expected: all tests pass.

```bash
git add tools/check_gates.py tools/render_report.py tests/test_check_gates.py tests/test_render_report.py
git commit -m "feat: 兼容宿主无关外审产物"
```

---

### Task 4: 双插件清单与共享技能适配

**Files:**
- Create: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Create: `.agents/plugins/marketplace.json`
- Create: `skills/reproduce/adapters/claude_code.md`
- Create: `skills/reproduce/adapters/codex.md`
- Modify: `skills/reproduce/SKILL.md`
- Modify: `skills/reproduce/stages/spec_audit.md`
- Modify: `skills/reproduce/stages/code_audit.md`
- Modify: `skills/reproduce/stages/result_audit.md`
- Modify: `skills/reproduce/stages/iterate.md`
- Modify: `skills/reproduce/stages/setup.md`
- Modify: `templates/codex_prompts/*.md`
- Modify: `.claude-plugin/plugin.json`

**Interfaces:**
- `skills/reproduce/SKILL.md` establishes `HOST`, `EXTERNAL_ENGINE`, `HOST_ADAPTER` once per run.
- Stage cards invoke `external_review.py`; output file names are engine-neutral.
- Adapter cards fully specify dispatch and same-host fallback contracts.

- [ ] **Step 1: Add manifest and text-contract tests**

Create `tests/test_dual_host_contract.py` asserting:

```python
def test_codex_manifest_points_to_shared_skill():
    data = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert data["name"] == "quant-report-reproduce"
    assert data["skills"] == "./skills/"

def test_stage_cards_use_external_executor():
    for name in ("spec_audit", "code_audit", "result_audit", "iterate"):
        text = (ROOT / "skills/reproduce/stages" / f"{name}.md").read_text()
        assert "external_review.py" in text
        assert "command codex exec" not in text

def test_shared_skill_routes_both_hosts():
    text = (ROOT / "skills/reproduce/SKILL.md").read_text()
    assert "adapters/claude_code.md" in text
    assert "adapters/codex.md" in text
```

- [ ] **Step 2: Run contract tests and verify RED**

Run: `uv run pytest tests/test_dual_host_contract.py -q`
Expected: FAIL because Codex manifest/adapters do not exist and stage cards call Codex directly.

- [ ] **Step 3: Implement manifests and adapters**

Codex manifest must contain `name/version/description/author/skills/interface`. Keep Claude marketplace strict-clean at `.claude-plugin/marketplace.json`; create `.agents/plugins/marketplace.json` with local source `./` (the current marketplace snapshot root), `policy.installation=AVAILABLE`, `policy.authentication=ON_INSTALL`, and category `Developer Tools`. Claude manifest version becomes `2.12.0` with dual-host description.

Claude adapter specifies Agent tool dispatch and Claude same-host fallback. Codex adapter specifies collaboration dispatch with no inherited history for blind reviews and Codex same-host fallback. Both explicitly prohibit subagent nesting and state writes.

- [ ] **Step 4: Replace engine-specific stage prose**

Use `external_review.py --engine "$EXTERNAL_ENGINE"` in four stage cards. Rename prompt/output paths to `external_*`/`*_external.md`; record `engine` as `${EXTERNAL_ENGINE}_external`, or `same_host_fallback` on degradation. Keep CDX opinion IDs and marker blocks for gate compatibility. Update setup card to explain both CLI checks.

- [ ] **Step 5: Make review prompt headings engine-neutral**

Change user-facing headings such as “Codex 审查” to “异构外部审查”, while keeping required marker strings and `CDX-*` IDs unchanged. Do not change JSON schema.

- [ ] **Step 6: Validate manifests, contracts and commit Task 4**

Run: `uv run pytest tests/test_dual_host_contract.py -q`
Expected: all tests pass.
Run: `python3 /Users/hedi/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .`
Expected: validation succeeds.
Run: `python3 /Users/hedi/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/reproduce`
Expected: skill validation succeeds.

```bash
git add .codex-plugin .claude-plugin .agents/plugins/marketplace.json skills/reproduce templates/codex_prompts tests/test_dual_host_contract.py
git commit -m "feat: 增加 Claude 与 Codex 双宿主入口"
```

---

### Task 5: 文档、全量验收和发布

**Files:**
- Modify: `README.md`
- Modify: `docs/specs/2026-07-09-plugin-packaging-design.md`
- Modify: `docs/specs/2026-07-14-claude-codex-dual-host-design.md`

**Interfaces:**
- README must provide separate install/use sections for Claude Code and Codex.
- Version history adds v2.12.0 and explains symmetric external review.

- [ ] **Step 1: Update user documentation**

Document both install surfaces, `/reproduce setup`, Codex project-agent installation behavior, both external CLI prerequisites, the symmetric fallback table, and backward compatibility. Change the new design status from `已确认，待实施` to `已实施` only after validation passes.

- [ ] **Step 2: Run documentation consistency scan**

Run:

```bash
rg -n "codex 三审查点|codex 全难度必跑|调 codex|claude_fallback" README.md skills/reproduce templates/codex_prompts
```

Expected: only intentional legacy-compatibility explanations remain.

- [ ] **Step 3: Run full verification**

```bash
uv run pytest -q
uv run python tools/sync_codex_agents.py --check --root .
python3 /Users/hedi/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 -m compileall -q tools tests
git diff --check
```

Expected: every command exits 0; pytest reports zero failures; generated agents have no drift; plugin validates; no whitespace errors.

- [ ] **Step 4: Review scope and request independent review**

Compare `git diff 41ec1a0...HEAD` against `docs/specs/2026-07-14-claude-codex-dual-host-design.md`. Review must reject changes to stage order, standards, historical workspaces, strategy code, or result data.

- [ ] **Step 5: Commit documentation and review fixes**

```bash
git add README.md docs/specs/2026-07-09-plugin-packaging-design.md docs/specs/2026-07-14-claude-codex-dual-host-design.md
git commit -m "docs: 说明双宿主安装与异构外审"
```

- [ ] **Step 6: Push the isolated branch**

```bash
git status --short
git push -u origin codex/dual-host-plugin
```

Expected: only intended compatibility files are committed; push succeeds and remote tracking is configured.
