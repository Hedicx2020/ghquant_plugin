"""异构外审 CLI 统一执行器。

只负责安全调用 Codex / Claude Code、分类执行失败并原子落盘；审查意见是否
通过仍由 check_gates.py 判定。本模块不导入任何管线状态代码。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ENGINES = ("codex", "claude")
QUOTA_RE = re.compile(r"usage limit|quota|rate limit|\b429\b", re.IGNORECASE)
AUTH_RE = re.compile(r"unauthorized|authentication|login|required.*auth|\b40[13]\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReviewResult:
    """一次外审 CLI 调用的机器可读结果。"""

    engine: str
    status: str
    reason: str
    returncode: int | None
    output: str | None
    duration_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _build_command(engine: str, executable: str, cwd: Path) -> list[str]:
    if engine == "codex":
        return [
            executable,
            "exec",
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            str(cwd),
            "--color",
            "never",
            "-",
        ]
    if engine == "claude":
        return [
            executable,
            "-p",
            "--no-session-persistence",
            "--tools",
            "Read,Glob,Grep",
        ]
    raise ValueError(f"不支持的外审引擎: {engine}")


def _classify_failure(output: str) -> tuple[str, str]:
    if QUOTA_RE.search(output):
        return "quota_error", "quota_or_rate_limit"
    if AUTH_RE.search(output):
        return "auth_error", "authentication_failed"
    return "failed", "nonzero_exit"


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


def run_review(
    engine: str,
    prompt_path: Path,
    output_path: Path,
    cwd: Path,
    timeout: int = 600,
) -> ReviewResult:
    """调用指定外审引擎；只有非空成功结果才写入 ``output_path``。"""

    if engine not in ENGINES:
        raise ValueError(f"engine 必须是 {ENGINES} 之一，收到: {engine}")
    started = time.monotonic()
    executable = shutil.which(engine)
    if executable is None:
        return ReviewResult(engine, "unavailable", "cli_missing", None, None, 0.0)

    prompt_text = prompt_path.read_text(encoding="utf-8")
    command = _build_command(engine, executable, cwd.resolve())
    try:
        proc = subprocess.run(
            command,
            input=prompt_text,
            capture_output=True,
            text=True,
            cwd=str(cwd.resolve()),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="研报复现：运行只读异构外审")
    parser.add_argument("--engine", required=True, choices=ENGINES)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cwd", default=".", type=Path)
    parser.add_argument("--timeout", default=600, type=int)
    args = parser.parse_args(argv)

    result = run_review(args.engine, args.prompt, args.output, args.cwd, args.timeout)
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.status == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
