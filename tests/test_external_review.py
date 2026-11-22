"""双宿主外审执行器单测：命令只读性、失败分类与原子输出。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
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


# ---------------------------------------------------------------------------
# v3 调用方式：显式推理强度、关闭多代理、输出落盘、进程看管
# ---------------------------------------------------------------------------

posix_only = pytest.mark.skipif(os.name == "nt", reason="假可执行文件依赖 shebang 与 POSIX 信号")


def _pairs(cmd: list[str]) -> list[tuple[str, str]]:
    return list(zip(cmd, cmd[1:]))


def _fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, body: str) -> Path:
    """在临时目录里放一个假的命令行脚本，并把该目录排到 PATH 最前面。"""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / name
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return script


def test_build_command_without_new_arguments_is_unchanged(tmp_path):
    assert er._build_command("codex", "/bin/codex", tmp_path) == [
        "/bin/codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-C", str(tmp_path), "--color", "never", "-",
    ]
    assert er._build_command("claude", "/bin/claude", tmp_path) == [
        "/bin/claude", "-p", "--no-session-persistence", "--tools", "Read,Glob,Grep",
    ]
    with pytest.raises(ValueError):
        er._build_command("gemini", "/bin/gemini", tmp_path)


def test_build_command_codex_new_arguments(tmp_path):
    schema, last = tmp_path / "schema.json", tmp_path / "last.txt"
    cmd = er._build_command("codex", "/bin/codex", tmp_path, effort="high", model="gpt-x", schema_path=schema, last_message_path=last)
    assert cmd[:4] == ["/bin/codex", "exec", "-s", "read-only"] and cmd[-1] == "-"
    pairs = _pairs(cmd)
    assert ("-c", "model_reasoning_effort=high") in pairs
    assert ("-c", "features.multi_agent=false") in pairs and ("-c", "features.multi_agent_v2=false") in pairs
    assert ("-m", "gpt-x") in pairs and ("--output-schema", str(schema)) in pairs and ("-o", str(last)) in pairs
    assert ("-C", str(tmp_path)) in pairs
    assert "--disable" not in cmd  # 关特性用配置键，不用 --disable

    only_effort = er._build_command("codex", "/bin/codex", tmp_path, effort="medium")
    assert ("-c", "model_reasoning_effort=medium") in _pairs(only_effort)
    assert ("-c", "features.multi_agent=false") in _pairs(only_effort)  # 只要是新式调用就关多代理
    assert not {"-o", "--output-schema", "-m"} & set(only_effort)


def test_build_command_claude_new_arguments(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object", "properties": {"verdict": {"type": "string"}}}, indent=2), encoding="utf-8")
    cmd = er._build_command("claude", "/bin/claude", tmp_path, effort="medium", model="opus", schema_path=schema)
    assert cmd[:2] == ["/bin/claude", "-p"] and "--no-session-persistence" in cmd
    assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"  # 工具面里没有子代理
    assert cmd[cmd.index("--effort") + 1] == "medium" and cmd[cmd.index("--model") + 1] == "opus"
    inline = cmd[cmd.index("--json-schema") + 1]
    assert "\n" not in inline and json.loads(inline)["properties"]["verdict"] == {"type": "string"}
    assert cmd[cmd.index("--output-format") + 1] == "json"

    only_effort = er._build_command("claude", "/bin/claude", tmp_path, effort="low")
    assert "--output-format" not in only_effort and "--json-schema" not in only_effort
    with_file = er._build_command("claude", "/bin/claude", tmp_path, last_message_path=tmp_path / "last.txt")
    assert with_file[with_file.index("--output-format") + 1] == "json"  # 要落盘就得走结果信封


def test_result_dict_keeps_old_keys_when_no_meta():
    old = er.ReviewResult("codex", "success", "", 0, "x.md", 0.1).to_dict()
    assert set(old) == {"engine", "status", "reason", "returncode", "output", "duration_seconds"}
    new = er.ReviewResult("codex", "success", "", 0, "x.md", 0.1, {"source": "last_message"}).to_dict()
    assert new["meta"] == {"source": "last_message"}


def test_cli_passes_new_options_only_when_given(tmp_path, monkeypatch, capsys):
    seen: list[dict] = []

    def fake(*args, **kwargs):
        seen.append(kwargs)
        return er.ReviewResult("codex", "success", "", 0, "x.md", 0.1)

    monkeypatch.setattr(er, "run_review", fake)
    base = ["--engine", "codex", "--prompt", str(_prompt(tmp_path)), "--output", str(tmp_path / "out.md"), "--cwd", str(tmp_path)]
    assert er.main(base) == 0
    assert seen[-1] == {}  # 旧式调用不带任何新参数
    schema = tmp_path / "schema.json"
    assert er.main(base + ["--effort", "medium", "--model", "m1", "--schema", str(schema)]) == 0
    assert seen[-1] == {"effort": "medium", "model": "m1", "schema_path": schema}
    first = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    assert "meta" not in first and first["status"] == "success"


CODEX_OK = """
    import json, pathlib, sys
    argv = sys.argv[1:]
    here = pathlib.Path(__file__).resolve().parent
    (here / "argv.json").write_text(json.dumps(argv), encoding="utf-8")
    (here / "stdin.txt").write_text(sys.stdin.read(), encoding="utf-8")
    mode = (here / "mode.txt").read_text(encoding="utf-8").strip() if (here / "mode.txt").is_file() else "write"
    if "-o" in argv and mode == "write":
        pathlib.Path(argv[argv.index("-o") + 1]).write_text("最后一条消息\\n", encoding="utf-8")
    if mode != "silent":
        print("过程日志：读了 3 个文件")
        print("标准输出里的正文")
"""


@posix_only
def test_codex_last_message_file_is_preferred_over_stdout(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "codex", CODEX_OK)
    out, last = tmp_path / "out.md", tmp_path / "job" / "last.txt"
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path, 30, effort="high", last_message_path=last)
    assert (result.status, result.reason, result.returncode) == ("success", "", 0)
    assert out.read_text(encoding="utf-8") == "最后一条消息\n"  # 不带过程日志
    assert result.meta == {"source": "last_message"} and result.duration_seconds >= 0
    argv = json.loads((script.parent / "argv.json").read_text(encoding="utf-8"))
    assert ("-c", "model_reasoning_effort=high") in _pairs(argv) and ("-o", str(last)) in _pairs(argv)
    assert ("-c", "features.multi_agent=false") in _pairs(argv) and argv[-1] == "-"
    assert (script.parent / "stdin.txt").read_text(encoding="utf-8") == "请只读审查。"


@posix_only
def test_codex_falls_back_to_stdout_when_last_message_is_missing(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "codex", CODEX_OK)
    (script.parent / "mode.txt").write_text("stdout_only", encoding="utf-8")
    out, last = tmp_path / "out.md", tmp_path / "last.txt"
    last.write_text("上一次尝试留下的旧消息", encoding="utf-8")
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path, 30, effort="high", last_message_path=last)
    assert result.status == "success" and result.meta == {"source": "stdout"}
    assert out.read_text(encoding="utf-8") == "过程日志：读了 3 个文件\n标准输出里的正文\n"
    assert not last.exists()  # 旧消息在调用前就清掉了，不会被当成这一次的输出


@posix_only
def test_supervised_empty_output_and_log(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "codex", CODEX_OK)
    (script.parent / "mode.txt").write_text("silent", encoding="utf-8")
    out, log = tmp_path / "out.md", tmp_path / "job" / "stdout.log"
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path, 30, effort="low", last_message_path=tmp_path / "last.txt", log_path=log)
    assert (result.status, result.reason) == ("empty_output", "stdout_empty") and not out.exists()
    text = log.read_text(encoding="utf-8")
    assert "status=empty_output" in text and "model_reasoning_effort=low" in text


@posix_only
def test_supervised_failure_is_classified_and_logged(tmp_path, monkeypatch):
    _fake_cli(
        tmp_path,
        monkeypatch,
        "codex",
        """
        import sys
        sys.stdin.read()
        print("partial", flush=True)
        print("ERROR: You've hit your usage limit.", file=sys.stderr)
        sys.exit(1)
        """,
    )
    out, log, pid_file = tmp_path / "out.md", tmp_path / "stdout.log", tmp_path / "engine.pid"
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path, 30, effort="high", log_path=log, pid_path=pid_file)
    assert (result.status, result.reason, result.returncode) == ("quota_error", "quota_or_rate_limit", 1)
    assert not out.exists() and not pid_file.exists()
    assert "usage limit" in log.read_text(encoding="utf-8")


ECHOING_CODEX = """
    import pathlib, sys
    prompt = sys.stdin.read()
    here = pathlib.Path(__file__).resolve().parent
    print("OpenAI Codex (research preview)\\n--------\\nuser", file=sys.stderr)
    print(prompt, file=sys.stderr)  # 真实的引擎会把提示词原样回显到标准错误
    print((here / "last_words.txt").read_text(encoding="utf-8"), file=sys.stderr)
    sys.exit(1)
"""


@posix_only
def test_supervised_failure_classification_ignores_the_echoed_prompt(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "codex", ECHOING_CODEX)
    # 带行号的输入包：行号 401 / 403 / 429 和正文里的 login、quota 都会撞上分类用的关键词
    pack = "\n".join(f"{n}\t第 {n} 行：login 之后检查 quota 与 rate limit" for n in range(1, 600))
    prompt = tmp_path / "big_prompt.md"
    prompt.write_text("请只读审查。\n\n" + pack + "\n", encoding="utf-8")
    out = tmp_path / "out.md"

    def run(last_words: str) -> er.ReviewResult:
        (script.parent / "last_words.txt").write_text(last_words, encoding="utf-8")
        return er.run_review("codex", prompt, out, tmp_path, 30, effort="high")

    plain = run("ERROR: stream disconnected before completion")
    assert (plain.status, plain.reason, plain.returncode) == ("failed", "nonzero_exit", 1)  # 不被回显里的 429、login 带偏
    assert run("ERROR: You've hit your usage limit. Try again later.").status == "quota_error"
    assert run("ERROR: unexpected status 401 Unauthorized").status == "auth_error"
    assert run("ERROR: exceeded retry limit, last status: 429 Too Many Requests").status == "quota_error"


@posix_only
def test_relative_paths_are_handed_to_the_engine_as_absolute(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "codex", CODEX_OK)
    work = tmp_path / "elsewhere"
    work.mkdir()
    (tmp_path / "schema.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = er.run_review("codex", _prompt(tmp_path), Path("out.md"), work, 30, schema_path=Path("schema.json"), last_message_path=Path("job/last.txt"))
    assert result.status == "success" and (tmp_path / "out.md").read_text(encoding="utf-8") == "最后一条消息\n"
    argv = json.loads((script.parent / "argv.json").read_text(encoding="utf-8"))
    given = {flag: argv[argv.index(flag) + 1] for flag in ("--output-schema", "-o")}
    assert all(os.path.isabs(value) for value in given.values())  # 引擎的工作目录是 work，相对路径会被它解析到别处
    assert os.path.samefile(given["--output-schema"], tmp_path / "schema.json")


CLAUDE_ENVELOPE = """
    import json, pathlib, sys
    argv = sys.argv[1:]
    here = pathlib.Path(__file__).resolve().parent
    (here / "argv.json").write_text(json.dumps(argv), encoding="utf-8")
    sys.stdin.read()
    envelope = json.loads((here / "envelope.json").read_text(encoding="utf-8"))
    print(json.dumps(envelope, ensure_ascii=False))
"""


@posix_only
def test_claude_envelope_gives_text_and_usage(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "claude", CLAUDE_ENVELOPE)
    usage = {"input_tokens": 12, "cache_read_input_tokens": 3400, "cache_creation_input_tokens": 560, "output_tokens": 78}
    envelope = {"type": "result", "subtype": "success", "is_error": False, "result": "审查结论正文\n", "usage": usage, "num_turns": 4, "total_cost_usd": 0.21}
    (script.parent / "envelope.json").write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    out, last = tmp_path / "out.md", tmp_path / "last.txt"
    result = er.run_review("claude", _prompt(tmp_path), out, tmp_path, 30, effort="medium", last_message_path=last)
    assert result.status == "success"
    assert out.read_text(encoding="utf-8") == "审查结论正文\n" == last.read_text(encoding="utf-8")
    assert result.meta["source"] == "envelope" and result.meta["usage"] == usage and result.meta["num_turns"] == 4
    argv = json.loads((script.parent / "argv.json").read_text(encoding="utf-8"))
    assert argv[argv.index("--effort") + 1] == "medium" and argv[argv.index("--output-format") + 1] == "json"


@posix_only
def test_claude_structured_output_and_envelope_error(tmp_path, monkeypatch):
    script = _fake_cli(tmp_path, monkeypatch, "claude", CLAUDE_ENVELOPE)
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    structured = {"verdict": "pass", "findings": []}
    (script.parent / "envelope.json").write_text(
        json.dumps([{"type": "system"}, {"type": "result", "is_error": False, "result": "", "structured_output": structured}]), encoding="utf-8"
    )
    out = tmp_path / "out.md"
    result = er.run_review("claude", _prompt(tmp_path), out, tmp_path, 30, effort="high", schema_path=schema)
    assert result.status == "success" and json.loads(out.read_text(encoding="utf-8")) == structured
    argv = json.loads((script.parent / "argv.json").read_text(encoding="utf-8"))
    assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}

    (script.parent / "envelope.json").write_text(json.dumps({"type": "result", "is_error": True, "result": "Claude usage limit reached"}), encoding="utf-8")
    out2 = tmp_path / "out2.md"
    failed = er.run_review("claude", _prompt(tmp_path), out2, tmp_path, 30, effort="high", schema_path=schema)
    assert failed.status == "quota_error" and not out2.exists()

    (script.parent / "envelope.json").write_text(json.dumps({"type": "result", "is_error": True, "result": "boom"}), encoding="utf-8")
    assert er.run_review("claude", _prompt(tmp_path), out2, tmp_path, 30, effort="high", schema_path=schema).reason == "envelope_error"


@posix_only
def test_supervised_timeout_kills_the_whole_process_tree(tmp_path, monkeypatch):
    script = _fake_cli(
        tmp_path,
        monkeypatch,
        "codex",
        """
        import pathlib, subprocess, sys, time
        here = pathlib.Path(__file__).resolve().parent
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        (here / "child.pid").write_text(str(child.pid), encoding="utf-8")
        sys.stdin.read()
        time.sleep(120)
        """,
    )
    out, pid_file = tmp_path / "out.md", tmp_path / "engine.pid"
    started = time.monotonic()
    result = er.run_review("codex", _prompt(tmp_path), out, tmp_path, 2, effort="high", pid_path=pid_file)
    assert (result.status, result.reason, result.returncode) == ("timeout", "timeout_2s", None)
    assert time.monotonic() - started < 20 and not out.exists() and not pid_file.exists()
    child_pid = int((script.parent / "child.pid").read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10
    while er.pid_alive(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not er.pid_alive(child_pid)  # 外审进程自己起的子进程也一并结束，不留孤儿


def test_unavailable_engine_in_supervised_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(er.shutil, "which", lambda _: None)
    result = er.run_review("claude", _prompt(tmp_path), tmp_path / "out.md", tmp_path, effort="high")
    assert (result.status, result.reason) == ("unavailable", "cli_missing")


def test_context_overflow_is_classified_separately_but_stays_a_plain_failure():
    """输入超出引擎的上下文窗口：状态仍是 failed（降级链照旧），原因单列，调用方据此提示调小输入包。"""
    for text in (
        "ERROR: This model's maximum context length is 272000 tokens. However, your messages resulted in 301245 tokens.",
        "Error: prompt is too long: 215034 tokens > 200000 maximum",
        "stream error: context_length_exceeded",
        "the request exceeds the context window of this model",
    ):
        assert er._classify_failure(text) == ("failed", "context_overflow"), text
    assert er._classify_failure("Traceback ...\nValueError: boom") == ("failed", "nonzero_exit")
    assert er._classify_failure("HTTP 429 rate limit; context length exceeded")[0] == "quota_error"  # 额度问题优先
