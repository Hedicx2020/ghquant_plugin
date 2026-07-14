"""双宿主外审执行器单测：命令只读性、失败分类与原子输出。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import external_review as er  # noqa: E402


def _prompt(tmp_path: Path) -> Path:
    path = tmp_path / "prompt.md"
    path.write_text("请只读审查。", encoding="utf-8")
    return path


def _install_fake_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str = "审查完成",
    stderr: str = "",
    returncode: int = 0,
) -> list[list[str]]:
    seen: list[list[str]] = []
    monkeypatch.setattr(er.shutil, "which", lambda name: f"/fake/{name}")

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        assert kwargs["input"] == "请只读审查。"
        assert kwargs["cwd"]
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(er.subprocess, "run", fake_run)
    return seen


def test_codex_command_is_read_only(tmp_path, monkeypatch):
    seen = _install_fake_run(monkeypatch)
    result = er.run_review("codex", _prompt(tmp_path), tmp_path / "out.md", tmp_path)
    assert result.status == "success"
    assert seen[0][0:4] == ["/fake/codex", "exec", "-s", "read-only"]
    assert "--skip-git-repo-check" in seen[0]
    assert seen[0][-1] == "-"


def test_claude_command_has_read_only_tool_surface(tmp_path, monkeypatch):
    seen = _install_fake_run(monkeypatch)
    result = er.run_review("claude", _prompt(tmp_path), tmp_path / "out.md", tmp_path)
    assert result.status == "success"
    cmd = seen[0]
    assert cmd[:2] == ["/fake/claude", "-p"]
    assert "--no-session-persistence" in cmd
    assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [("usage limit reached", "quota_error"), ("HTTP 401 login required", "auth_error")],
)
def test_failure_classification(tmp_path, monkeypatch, stderr, expected):
    _install_fake_run(monkeypatch, returncode=1, stderr=stderr)
    result = er.run_review("claude", _prompt(tmp_path), tmp_path / "out.md", tmp_path)
    assert result.status == expected
    assert not (tmp_path / "out.md").exists()


def test_missing_cli_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(er.shutil, "which", lambda _: None)
    result = er.run_review("codex", _prompt(tmp_path), tmp_path / "out.md", tmp_path)
    assert result.status == "unavailable"
    assert result.reason == "cli_missing"


def test_empty_success_does_not_write_output(tmp_path, monkeypatch):
    _install_fake_run(monkeypatch, stdout="  ")
    out = tmp_path / "out.md"
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path)
    assert result.status == "empty_output"
    assert not out.exists()


def test_timeout_is_classified(tmp_path, monkeypatch):
    monkeypatch.setattr(er.shutil, "which", lambda name: f"/fake/{name}")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(er.subprocess, "run", raise_timeout)
    result = er.run_review("codex", _prompt(tmp_path), tmp_path / "out.md", tmp_path, timeout=7)
    assert result.status == "timeout"
    assert result.reason == "timeout_7s"


def test_success_atomically_writes_output(tmp_path, monkeypatch):
    _install_fake_run(monkeypatch, stdout="  审查正文\n")
    out = tmp_path / "nested" / "out.md"
    result = er.run_review("claude", _prompt(tmp_path), out, tmp_path)
    assert out.read_text(encoding="utf-8") == "审查正文\n"
    assert result.output == str(out)


def test_cli_prints_machine_readable_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        er,
        "run_review",
        lambda *args, **kwargs: er.ReviewResult("codex", "success", "", 0, "x.md", 0.1),
    )
    rc = er.main([
        "--engine", "codex", "--prompt", str(_prompt(tmp_path)),
        "--output", str(tmp_path / "out.md"), "--cwd", str(tmp_path),
    ])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "success"
