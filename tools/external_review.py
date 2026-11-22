"""异构外审 CLI 统一执行器。

只负责安全调用 Codex / Claude Code、分类执行失败并原子落盘；审查意见是否
通过仍由 check_gates.py 判定。本模块不导入任何管线状态代码。

两种调用方式：

- 旧式：``run_review(engine, prompt_path, output_path, cwd, timeout)``。命令、子进程
  的启动方式和返回值都与 v2 相同。
- v3：再带上任一关键字参数（effort / model / schema_path / last_message_path / env /
  log_path / pid_path）。此时命令里显式指定推理强度、关闭多代理特性、让引擎把最后
  一条消息单独落盘；子进程由本模块自己看管，超时先发终止信号（Codex 的包装脚本会把
  它转给真正的子进程），再连同后代进程一起杀掉，不留下继续消耗额度的孤儿进程。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ENGINES = ("codex", "claude")
QUOTA_RE = re.compile(r"usage limit|quota|rate limit|\b429\b", re.IGNORECASE)
AUTH_RE = re.compile(r"unauthorized|authentication|login|required.*auth|\b40[13]\b", re.IGNORECASE)
# 输入超出引擎的上下文窗口：状态仍是 failed，原因单列，调用方据此提示调小输入包而不是原样重试
CONTEXT_RE = re.compile(
    r"context[_ ](?:length|window)[^\n]{0,40}exceed|exceed[^\n]{0,40}context[_ ](?:length|window)|maximum context length|prompt is too long|input is too long|too many tokens",
    re.IGNORECASE,
)

# 调用时要关掉的 Codex 多代理特性。用 -c 写配置键而不是 --disable：将来特性改名时，
# 写一个不认识的配置键不会报错，--disable 一个不认识的特性名会让整条命令失败。
CODEX_MULTI_AGENT_FEATURES = ("multi_agent", "multi_agent_v2")
TERMINATE_GRACE_SECONDS = 5.0  # 超时后先发终止信号，等这么久再强杀
LOG_TAIL_BYTES = 200_000  # 每次调用写进日志的标准输出、标准错误各自最多留这么多
FAILURE_TAIL_LINES = 40  # v3 调用方式下，失败分类只看每路输出结尾的这么多行
FAILURE_TAIL_CHARS = 4000


@dataclass(frozen=True)
class ReviewResult:
    """一次外审 CLI 调用的机器可读结果。

    meta 只在 v3 调用方式下才有：正文取自哪里（last_message / envelope / stdout），以及
    Claude 的结果信封里带的用量。旧式调用时它是 None，``to_dict`` 的键与 v2 相同。
    """

    engine: str
    status: str
    reason: str
    returncode: int | None
    output: str | None
    duration_seconds: float
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        if data.get("meta") is None:
            data.pop("meta", None)
        return data


def _build_command(
    engine: str,
    executable: str,
    cwd: Path,
    *,
    effort: str | None = None,
    model: str | None = None,
    schema_path: Path | None = None,
    last_message_path: Path | None = None,
) -> list[str]:
    """拼外审命令。四个关键字参数都不给时，命令与 v2 逐项相同。

    给了任意一个即为 v3 调用：Codex 一律关闭多代理特性，并按所给参数加上推理强度、
    模型、输出约束和「最后一条消息」的落盘位置；Claude 的工具面本来就只有
    Read / Glob / Grep（没有子代理），按所给参数加上推理强度、模型和输出约束，
    要求落盘或给了输出约束时改用 JSON 结果信封（正文与用量从信封里取）。
    """
    hardened = any(value is not None for value in (effort, model, schema_path, last_message_path))
    if engine == "codex":
        command = [
            executable,
            "exec",
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            str(cwd),
            "--color",
            "never",
        ]
        if hardened:
            for feature in CODEX_MULTI_AGENT_FEATURES:
                command += ["-c", f"features.{feature}=false"]
        if effort is not None:
            command += ["-c", f"model_reasoning_effort={effort}"]
        if model is not None:
            command += ["-m", model]
        if schema_path is not None:
            command += ["--output-schema", str(schema_path)]
        if last_message_path is not None:
            command += ["-o", str(last_message_path)]
        return command + ["-"]
    if engine == "claude":
        command = [
            executable,
            "-p",
            "--no-session-persistence",
            "--tools",
            "Read,Glob,Grep",
        ]
        if effort is not None:
            command += ["--effort", effort]
        if model is not None:
            command += ["--model", model]
        if schema_path is not None:
            command += ["--json-schema", _compact_schema(schema_path)]
        if schema_path is not None or last_message_path is not None:
            command += ["--output-format", "json"]
        return command
    raise ValueError(f"不支持的外审引擎: {engine}")


def _compact_schema(schema_path: Path) -> str:
    """Claude 的输出约束要内联成一个参数：读文件并压成单行 JSON。"""
    return json.dumps(json.loads(Path(schema_path).read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))


def _classify_failure(output: str) -> tuple[str, str]:
    if QUOTA_RE.search(output):
        return "quota_error", "quota_or_rate_limit"
    if AUTH_RE.search(output):
        return "auth_error", "authentication_failed"
    if CONTEXT_RE.search(output):
        return "failed", "context_overflow"
    return "failed", "nonzero_exit"


def _failure_text(prompt_text: str, *streams: str | None) -> str:
    """v3 调用方式下供失败分类用的文字：每路输出去掉与提示词相同的行，只留结尾的一小段。

    引擎会把提示词原样回显到标准错误。v3 的提示词带着几百 KB 的输入包，里面的行号和数字
    （401、403、429）以及 login、quota 之类的字样会撞上分类用的关键词，把所有失败都判成
    额度或鉴权问题；而真正的报错总是在输出的结尾。分类规则本身（_classify_failure）不变。
    """
    echoed = {line.strip() for line in prompt_text.splitlines() if line.strip()}
    parts: list[str] = []
    for stream in streams:
        kept = [line for line in (stream or "").splitlines() if line.strip() and line.strip() not in echoed]
        parts.append("\n".join(kept[-FAILURE_TAIL_LINES:])[-FAILURE_TAIL_CHARS:])
    return "\n".join(parts)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            temp_name = handle.name
        Path(temp_name).replace(path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 进程看管（v3 调用方式）
# ---------------------------------------------------------------------------


def pid_alive(pid: int) -> bool:
    """进程是否还在。Windows 上无法安全探活（os.kill(pid, 0) 会终止目标），一律当作还在。"""
    if os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _descendants(pid: int) -> list[int]:
    """一个进程的全部后代（先近后远）。拿不到进程表时返回空列表。"""
    if os.name == "nt":
        return []
    try:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found: list[int] = []
    queue = [pid]
    while queue:
        for child in children.get(queue.pop(0), []):
            if child not in found:
                found.append(child)
                queue.append(child)
    return found


def _signal_all(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def terminate_process_tree(pid: int, grace: float = TERMINATE_GRACE_SECONDS, proc: subprocess.Popen | None = None) -> None:
    """结束一个进程和它的全部后代：先发终止信号，过了宽限期还在的再强杀。

    后代名单在发信号之前取——父进程一死，子进程会被过继，再也顺着父子关系找不到。
    proc 是本进程启动的子进程对象时一并传入，用它等待退出（顺带收尸）。
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    family = [pid] + _descendants(pid)

    def alive(member: int) -> bool:
        if proc is not None and member == pid:
            return proc.poll() is None  # 自己的子进程用 poll 判断，退出后不会被僵尸状态骗过
        return pid_alive(member)

    _signal_all(family, signal.SIGTERM)
    deadline = time.monotonic() + max(grace, 0.0)
    while time.monotonic() < deadline and any(alive(member) for member in family):
        time.sleep(0.05)
    _signal_all([member for member in family if alive(member)], signal.SIGKILL)


def _tail(text: str | None, limit: int = LOG_TAIL_BYTES) -> str:
    text = text or ""
    return text if len(text) <= limit else f"…（前面省略 {len(text) - limit} 个字符）\n{text[-limit:]}"


def _append_log(log_path: Path | None, engine: str, command: list[str], result: "ReviewResult", stdout: str | None, stderr: str | None) -> None:
    """把这次调用的命令、结论和引擎输出追加到日志；写日志失败不影响结果。"""
    if log_path is None:
        return
    shown = [arg if len(arg) <= 200 else arg[:200] + "…" for arg in command]
    lines = [
        f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} 外审调用 engine={engine} status={result.status} reason={result.reason} "
        f"returncode={result.returncode} seconds={result.duration_seconds} =====",
        "命令: " + json.dumps(shown, ensure_ascii=False),
        "----- 标准错误 -----",
        _tail(stderr).rstrip(),
        "----- 标准输出 -----",
        _tail(stdout).rstrip(),
        "",
    ]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _read_last_message(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _parse_claude_envelope(stdout: str) -> tuple[str, dict[str, Any], bool] | None:
    """解析 Claude 的 JSON 结果信封，返回（正文, 附加信息, 是否报错）；不是信封时返回 None。

    信封可能是单个对象，也可能是事件数组（取其中 type=result 的那一项）。带输出约束时
    正文取 structured_output，否则取 result。
    """
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list):
        results = [item for item in data if isinstance(item, dict) and item.get("type") == "result"]
        data = results[-1] if results else None
    if not isinstance(data, dict) or not ({"result", "structured_output", "is_error"} & data.keys()):
        return None
    structured = data.get("structured_output")
    if isinstance(structured, (dict, list)):
        text = json.dumps(structured, ensure_ascii=False, indent=2)
    else:
        text = data.get("result") if isinstance(data.get("result"), str) else ""
    meta: dict[str, Any] = {"source": "envelope"}
    for key in ("usage", "num_turns", "total_cost_usd", "duration_ms", "duration_api_ms", "session_id", "subtype"):
        if data.get(key) is not None:
            meta[key] = data[key]
    return text.strip(), meta, bool(data.get("is_error"))


def _run_supervised(
    command: list[str],
    prompt_text: str,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None,
    pid_path: Path | None,
) -> tuple[int | None, str, str, bool]:
    """启动并看管外审进程，返回（退出码, 标准输出, 标准错误, 是否超时）。"""
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        env=env,
    )
    if pid_path is not None:
        try:
            _write_atomic(pid_path, json.dumps({"pid": proc.pid, "executable": command[0], "started": time.time()}))
        except OSError:
            pass
    timed_out = False
    try:
        try:
            stdout, stderr = proc.communicate(prompt_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_process_tree(proc.pid, proc=proc)
            try:
                stdout, stderr = proc.communicate(timeout=TERMINATE_GRACE_SECONDS + 5)
            except subprocess.TimeoutExpired:  # 后代进程还攥着管道：不再等输出
                proc.kill()
                stdout, stderr = "", ""
        except BaseException:  # 本进程被打断（如 Ctrl-C）：不能把外审进程留在后台继续跑
            terminate_process_tree(proc.pid, grace=1.0, proc=proc)
            raise
    finally:
        if pid_path is not None:
            pid_path.unlink(missing_ok=True)
    return (None if timed_out else proc.returncode), stdout or "", stderr or "", timed_out


def run_review(
    engine: str,
    prompt_path: Path,
    output_path: Path,
    cwd: Path,
    timeout: int = 600,
    *,
    effort: str | None = None,
    model: str | None = None,
    schema_path: Path | None = None,
    last_message_path: Path | None = None,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
    pid_path: Path | None = None,
) -> ReviewResult:
    """调用指定外审引擎；只有非空成功结果才写入 ``output_path``。

    关键字参数全部不给时行为与 v2 完全一致。给了任意一个即为 v3 调用：

    - effort / model：显式指定推理强度与模型，不再跟随引擎的全局配置。
    - schema_path：约束最终输出的 JSON Schema 文件。
    - last_message_path：让引擎把最后一条消息单独落盘。Codex 写到这个文件，取到就用它
      作正文，取不到再退回标准输出；Claude 改用 JSON 结果信封，正文与用量从信封里取，
      并把正文同样写到这个文件。
    - env：子进程的环境变量（不给则继承当前进程的）。
    - log_path：把每次调用的命令、结论、标准输出与标准错误追加到这个日志。
    - pid_path：进程在跑的时候把它的进程号写在这里，结束后删除（供外部在本进程意外
      退出后清理残留的外审进程）。
    """

    if engine not in ENGINES:
        raise ValueError(f"engine 必须是 {ENGINES} 之一，收到: {engine}")
    started = time.monotonic()
    executable = shutil.which(engine)
    if executable is None:
        return ReviewResult(engine, "unavailable", "cli_missing", None, None, 0.0)

    prompt_text = prompt_path.read_text(encoding="utf-8")
    resolved_cwd = cwd.resolve()
    supervised = any(
        value is not None for value in (effort, model, schema_path, last_message_path, env, log_path, pid_path)
    )
    if not supervised:
        command = _build_command(engine, executable, resolved_cwd)
        try:
            proc = subprocess.run(
                command,
                input=prompt_text,
                capture_output=True,
                text=True,
                cwd=str(resolved_cwd),
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            duration = round(time.monotonic() - started, 3)
            return ReviewResult(engine, "timeout", f"timeout_{timeout}s", None, None, duration)
        except OSError as exc:
            duration = round(time.monotonic() - started, 3)
            return ReviewResult(engine, "failed", f"os_error:{exc.__class__.__name__}", None, None, duration)

        duration = round(time.monotonic() - started, 3)
        if proc.returncode != 0:
            status, reason = _classify_failure(f"{proc.stdout}\n{proc.stderr}")
            return ReviewResult(engine, status, reason, proc.returncode, None, duration)

        review_text = proc.stdout.strip()
        if not review_text:
            return ReviewResult(engine, "empty_output", "stdout_empty", proc.returncode, None, duration)

        normalized = review_text + "\n"
        _write_atomic(output_path, normalized)
        return ReviewResult(engine, "success", "", proc.returncode, str(output_path), duration)

    # 引擎在 cwd 下运行：交给它的路径一律换成绝对路径，免得它按自己的工作目录去解析
    if schema_path is not None:
        schema_path = Path(os.path.abspath(schema_path))
    if last_message_path is not None:
        last_message_path = Path(os.path.abspath(last_message_path))
    command = _build_command(
        engine,
        executable,
        resolved_cwd,
        effort=effort,
        model=model,
        schema_path=schema_path,
        last_message_path=last_message_path,
    )
    if last_message_path is not None:
        last_message_path.parent.mkdir(parents=True, exist_ok=True)
        last_message_path.unlink(missing_ok=True)  # 上一次尝试留下的旧消息不能被当成这一次的

    def finish(result: ReviewResult, stdout: str | None = None, stderr: str | None = None) -> ReviewResult:
        _append_log(log_path, engine, command, result, stdout, stderr)
        return result

    try:
        returncode, stdout, stderr, timed_out = _run_supervised(command, prompt_text, resolved_cwd, timeout, env, pid_path)
    except OSError as exc:
        duration = round(time.monotonic() - started, 3)
        return finish(ReviewResult(engine, "failed", f"os_error:{exc.__class__.__name__}", None, None, duration))

    duration = round(time.monotonic() - started, 3)
    if timed_out:
        return finish(ReviewResult(engine, "timeout", f"timeout_{timeout}s", None, None, duration), stdout, stderr)
    if returncode != 0:
        status, reason = _classify_failure(_failure_text(prompt_text, stdout, stderr))
        return finish(ReviewResult(engine, status, reason, returncode, None, duration), stdout, stderr)

    meta: dict[str, Any] = {"source": "stdout"}
    review_text = ""
    if engine == "codex":
        review_text = _read_last_message(last_message_path)
        if review_text:
            meta["source"] = "last_message"
    elif "--output-format" in command:
        envelope = _parse_claude_envelope(stdout)
        if envelope is not None:
            review_text, meta, is_error = envelope
            if is_error:
                status, reason = _classify_failure(_failure_text(prompt_text, review_text, stderr))
                reason = "envelope_error" if status == "failed" else reason
                return finish(ReviewResult(engine, status, reason, returncode, None, duration, meta), stdout, stderr)
    if not review_text:
        review_text = stdout.strip()
        meta["source"] = "stdout"
    if not review_text:
        return finish(ReviewResult(engine, "empty_output", "stdout_empty", returncode, None, duration, meta), stdout, stderr)

    normalized = review_text + "\n"
    _write_atomic(output_path, normalized)
    if engine == "claude" and last_message_path is not None:
        try:
            _write_atomic(last_message_path, normalized)
        except OSError:
            pass
    return finish(ReviewResult(engine, "success", "", returncode, str(output_path), duration, meta), stdout, stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="研报复现：运行只读异构外审")
    parser.add_argument("--engine", required=True, choices=ENGINES)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cwd", default=".", type=Path)
    parser.add_argument("--timeout", default=600, type=int)
    parser.add_argument("--effort", default=None, help="推理强度（如 low / medium / high）；给了即显式指定并关闭多代理")
    parser.add_argument("--model", default=None, help="外审引擎使用的模型；不给则用引擎自己的默认值")
    parser.add_argument("--schema", default=None, type=Path, help="约束最终输出的 JSON Schema 文件")
    args = parser.parse_args(argv)

    extras: dict[str, Any] = {
        key: value
        for key, value in (("effort", args.effort), ("model", args.model), ("schema_path", args.schema))
        if value is not None
    }
    result = run_review(args.engine, args.prompt, args.output, args.cwd, args.timeout, **extras)
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
