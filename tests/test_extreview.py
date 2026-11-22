"""tools/flowlib/extreview.py：异构外审引擎。

外审引擎一律用临时目录里的假可执行文件（排在 PATH 最前面），不会真的调用任何模型；
案例是 tmp_path 下的最小目录，真实案例只在「r010 三轮合并」里只读地取三份原件。
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import check_gates as cg  # noqa: E402
from tools.flowlib import extreview as x  # noqa: E402

pytestmark = pytest.mark.skipif(os.name == "nt", reason="假可执行文件依赖 shebang 与 POSIX 信号")

RID = "r901_demo"
WS = f"workspace/{RID}"
FAST = {"external_review": {"timeout_seconds": 1}}

# ---------------------------------------------------------------------------
# 假的外审命令行
# ---------------------------------------------------------------------------

FAKE_ENGINE = r'''
"""假的外审命令行：行为由同目录的 control.json 决定，每次调用记到 calls.jsonl。"""
import hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

here = Path(__file__).resolve().parent
name = Path(sys.argv[0]).name
argv = sys.argv[1:]
prompt = sys.stdin.read()
control = json.loads((here / "control.json").read_text(encoding="utf-8")) if (here / "control.json").is_file() else {}
calls_path = here / "calls.jsonl"
index = len(calls_path.read_text(encoding="utf-8").splitlines()) if calls_path.is_file() else 0


def option(flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


effort = option("--effort")
for i, arg in enumerate(argv[:-1]):
    if arg == "-c" and argv[i + 1].startswith("model_reasoning_effort="):
        effort = argv[i + 1].split("=", 1)[1]
first = prompt.splitlines()[0] if prompt else ""
tag = re.match(r"<!-- extreview (\S+)/(\S+) (\S+) -->", first)
call = tag.group(2) if tag else "main"
(here / f"stdin_{index}.txt").write_text(prompt, encoding="utf-8")
record = {
    "engine": name, "argv": argv, "effort": effort, "call": call, "pid": os.getpid(), "cwd": os.getcwd(),
    "root_env": os.environ.get("REPORT_REPRODUCE_ROOT"), "bytes": len(prompt.encode("utf-8")),
    "sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
}
with calls_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

plan = control.get("plan") or []
step = plan[index] if index < len(plan) else ((control.get("by_effort") or {}).get(effort or "") or control.get("default") or {})
mode = step.get("mode", "ok")
if step.get("delay"):
    time.sleep(step["delay"])
if mode == "sleep":
    time.sleep(step.get("seconds", 120))
if mode in ("quota", "auth", "fail"):
    print({"quota": "ERROR: You've hit your usage limit.", "auth": "ERROR: 401 Unauthorized, please login", "fail": "stream disconnected"}[mode], file=sys.stderr)
    sys.exit(1)
if mode == "empty":
    sys.exit(0)

default_review = json.dumps({"checkpoint": "x", "verdict": "pass", "dimensions_checked": [], "findings": []}, ensure_ascii=False)
text = (control.get("outputs") or {}).get(call, "要素甲 | F | p5 | 窗口 20 日" if call == "blind" else default_review)

if name == "codex":
    session = control.get("session")
    if session:
        now = datetime.now()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        sid = f"sess-{os.getpid()}-{index}"
        base = Path(os.environ["HOME"]) / ".codex" / "sessions" / now.strftime("%Y/%m/%d")
        base.mkdir(parents=True, exist_ok=True)

        def tool(cmd):
            payload = {"type": "custom_tool_call", "name": "exec", "input": "tools.exec_command(" + json.dumps({"cmd": cmd}) + ")"}
            return {"timestamp": stamp, "type": "response_item", "payload": payload}

        def tokens(total):
            pack = {"input_tokens": total[0], "cached_input_tokens": total[1], "cache_write_input_tokens": 0, "output_tokens": total[2], "reasoning_output_tokens": total[3], "total_tokens": total[0] + total[2]}
            return {"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": pack, "last_token_usage": pack}}}

        def write(suffix, records):
            path = base / (now.strftime("rollout-%Y-%m-%dT%H-%M-%S-") + sid + suffix + ".jsonl")
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")

        cwd = session.get("cwd") or option("-C") or os.getcwd()
        records = [
            {"timestamp": stamp, "type": "session_meta", "payload": {"id": sid, "cwd": cwd, "originator": "codex_exec", "source": "exec"}},
            {"timestamp": stamp, "type": "turn_context", "payload": {"model": "fake-model", "effort": effort}},
            {"timestamp": stamp, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": first}]}},
        ]
        records += [tool(f"sed -n '1,200p' some/file_{n}.md") for n in range(session.get("reads", 0))]
        if call == "blind" and session.get("blind_reads_spec"):
            records.append(tool("nl -ba " + session["blind_reads_spec"]))
        if call == "review" and session.get("review_peeks_blind_prompt"):
            # 第二次调用的会话里读到了第一次调用的提示词文件（里面有第一次的标记），随后正常地读规格书
            blind_tag = (here / f"stdin_{index - 1}.txt").read_text(encoding="utf-8").splitlines()[0]
            records.append(tool("cat prompt_blind.md"))
            records.append({"timestamp": stamp, "type": "response_item", "payload": {"type": "custom_tool_call_output", "output": blind_tag + "\n# 角色"}})
            records.append(tool("sed -n '1,80p' " + session["review_peeks_blind_prompt"]))
        records.append(tokens((1000, 400, 50, 20)))
        write("", records)
        if session.get("spawn"):
            source = {"subagent": {"thread_spawn": {"parent_thread_id": sid}}}
            write("-sub", [{"timestamp": stamp, "type": "session_meta", "payload": {"id": sid + "-sub", "cwd": cwd, "originator": "codex_exec", "source": source}}, tokens((300, 0, 10, 0))])
    last = option("-o")
    if last:
        Path(last).write_text(text + "\n", encoding="utf-8")
    print("[过程日志] 不属于结论的输出")
    print(text)
elif option("--output-format") == "json":
    envelope = {
        "type": "result", "subtype": "success", "is_error": False, "result": text, "num_turns": 3, "total_cost_usd": 0.05,
        "usage": {"input_tokens": 100, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 30000, "output_tokens": 400},
    }
    if option("--json-schema"):
        try:
            envelope["structured_output"] = json.loads(text)
        except ValueError:
            pass
    print(json.dumps(envelope, ensure_ascii=False))
else:
    print(text)
'''


class Engines:
    """假引擎的遥控器：写行为配置、读调用记录。"""

    def __init__(self, bindir: Path, home: Path) -> None:
        self.bindir, self.home = bindir, home

    def control(self, **settings: Any) -> None:
        (self.bindir / "control.json").write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> None:
        for path in [self.bindir / "calls.jsonl", self.bindir / "control.json", *self.bindir.glob("stdin_*.txt")]:
            path.unlink(missing_ok=True)

    def calls(self) -> list[dict]:
        path = self.bindir / "calls.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []

    def stdin(self, index: int) -> str:
        return (self.bindir / f"stdin_{index}.txt").read_text(encoding="utf-8")


@pytest.fixture
def engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Engines:
    bindir, home = tmp_path / "fakebin", tmp_path / "home"
    bindir.mkdir()
    home.mkdir()
    for name in ("codex", "claude"):
        script = bindir / name
        script.write_text(f"#!{sys.executable}\n" + FAKE_ENGINE, encoding="utf-8")
        script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HOME", str(home))  # 假引擎把会话记录写到这里，不碰真实的 ~/.codex
    return Engines(bindir, home)


# ---------------------------------------------------------------------------
# 最小案例
# ---------------------------------------------------------------------------

SPEC = """---
report_id: r901_demo
market: A股
type_hint: timing
exhibit_declared: 3
---

# 突破比例择时 复现规格书

## 二、数据要求（D 类）

### [D1] 指数日行情
- 页码: p3
- 原文: > "沪深300 成分股日收盘价 SPEC_ONLY_MARKER"

## 三、因子定义（F 类）

### [F1] 突破比例
- 页码: p5
- 原文: > "创 20 日新高的成分股占比"
- 公式（转写）: ratio = count(close >= rolling_max(20)) / n

## 五、研报核心数值结果基准（R 类）

### [R1] 策略绩效
- 页码: p9
- 原文: > "年化收益 12.34%，夏普 0.871，最大回撤 -25.6%，胜率 36%"
- 数值表: 年化 12.34% / 夏普 0.871 / 回撤 -25.6% / 调仓 12 次 / 换手 0.5
"""

STRATEGY = '''"""突破比例择时策略。"""
from common.utils import winsorize

WINDOW = 20
TARGET_SHARPE = 0.871  # 只作对照
# 研报年化 12.34%


def breakout_ratio(close):
    """创 N 日新高的成分股占比。"""
    high = close.rolling(WINDOW).max()
    return (close >= high).mean(axis=1)


def signal(ratio, threshold=0.36):
    return (winsorize(ratio) > threshold).astype(int)
'''

COMMON_UTILS = '''def winsorize(series, lower=0.01, upper=0.99):
    """缩尾处理。"""
    return series.clip(series.quantile(lower), series.quantile(upper))


def _private_helper():
    return 1
'''

COMPARISON = {
    "report_id": RID,
    "metrics": [
        {"key": "annual_return", "report_value": 0.1234, "reproduced_value": 0.1228, "pass": True},
        {"key": "sharpe", "report_value": 0.87, "reproduced_value": 0.52, "pass": False},
    ],
}


def make_case(tmp_path: Path, **state_overrides: Any) -> Path:
    """在 tmp_path/proj 下建一个最小案例，返回工作区根。"""
    root = tmp_path / "proj"
    ws = root / WS
    files = {
        ws / "spec" / "report_text.md": "===== PAGE 1 =====\n突破比例择时研报正文 REPORT_TEXT_MARKER\n===== PAGE 9 =====\n年化收益 12.34%，夏普 0.87\n",
        ws / "spec" / "tables_extracted.md": "## 表1 策略绩效（p9）\n\n| 指标 | 数值 |\n| --- | --- |\n| 年化 | 12.34% |\n| 回撤 | -25.6% |\n\nTABLE_MARKER\n",
        ws / "spec" / "spec.md": SPEC,
        ws / "spec" / "coverage_matrix.md": "| 要素ID | 类别 | 状态 |\n| --- | --- | --- |\n| F1 | F | implemented |\n\nMATRIX_MARKER\n",
        ws / "spec" / "ambiguities.md": "### [AMB1] 新高是否含当日\n- status: resolved\n\nAMBIG_MARKER\n",
        ws / "assumptions.md": "### [AS1] 成分股用当前名单\n- 状态: active\n\nASSUME_MARKER\n",
        ws / "audit" / "evidence_manifest.md": "# 证据清单\n\nEVIDENCE_MARKER\n",
        root / "src" / RID / "strategy.py": STRATEGY,
        root / "src" / RID / "config.py": "START = \"2015-01-01\"\nEND = \"2024-12-31\"\n",
        root / "src" / RID / "main.py": "from .strategy import breakout_ratio, signal\n\n\ndef main():\n    return 0\n",
        root / "common" / "utils.py": COMMON_UTILS,
        root / "output" / RID / "results" / "comparison.json": json.dumps(COMPARISON, ensure_ascii=False, indent=2),
        root / "output" / RID / "verify_report.md": "# 验证报告\n\n复现年化 12.28%。VERIFY_MARKER\n",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (ws / "iterations").mkdir(exist_ok=True)
    state = {
        "report_id": RID,
        "type": "timing",
        "tags": ["etf"],
        "difficulty": "medium",
        "reproduction_mode": "strict",
        "iteration": {"current": 0, "max": 3},
        "status": "running",
    }
    state.update(state_overrides)
    (ws / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return root


def review_json(findings: list[tuple[str, str, str]], verdict: str = "fail", **extra: Any) -> str:
    """一份结论 JSON；findings 里每项是（编号, 严重度, 描述）。"""
    data = {
        "checkpoint": "x",
        "verdict": verdict,
        "dimensions_checked": [{"dimension": "逐项核对", "result": "no_findings"}],
        "findings": [
            {"id": fid, "severity": severity, "category": "类别", "location": "src/a.py:3", "description": text, "suggestion": "改掉", "confidence": "high"}
            for fid, severity, text in findings
        ],
        **extra,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def leftover(text: str) -> list[str]:
    """文中残留的已知占位符。"""
    return [m.group(0) for m in x._TOKEN_RE.finditer(text) if (m.group(1) or m.group(2)) in x.KNOWN_PLACEHOLDERS]


def gate(results: list) -> dict:
    return {r.id: r for r in results}


def response_rows(root: Path, prefix: str) -> dict[str, dict[str, str]]:
    rows = cg._parse_audit_responses(root / WS / "audit" / "audit_responses.md", prefix)
    return {cg._row_id(r, r"^CDX-[A-Z]-"): r for r in rows}


def wait_for(predicate: Callable[[], Any], timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("等待超时")


def prepare(root: Path, kind: str, round_no: int = 1, **kwargs: Any) -> dict:
    kwargs.setdefault("engine", "codex")
    kwargs.setdefault("host", "claude_code")
    return x.prepare(root, RID, kind, round_no, **kwargs)


def run(root: Path, job: dict) -> dict:
    return x.launch(root, RID, job["job_id"], detach=False)


def run_round(root: Path, engines: Engines, kind: str, round_no: int, output: str, **kwargs: Any) -> tuple[dict, dict]:
    """准备并前台跑完一轮，假引擎的结论是 output。"""
    engines.reset()
    engines.control(outputs={"main": output, "review": output})
    job = prepare(root, kind, round_no, **kwargs)
    result = run(root, job)
    assert result["state"] == "success", result
    return job, result


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def original(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / "originals" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 模板与配置
# ---------------------------------------------------------------------------


def test_render_fills_known_placeholders_and_keeps_other_braces():
    text = '{report_id} 的示例 {"verdict": "pass"}，见 iter_{N-1}/diagnosis.md，引擎 <EXTERNAL_ENGINE>，{not_a_placeholder}'
    out = x.render(text, {"report_id": "r1", "EXTERNAL_ENGINE": "codex"})
    assert out == 'r1 的示例 {"verdict": "pass"}，见 iter_{N-1}/diagnosis.md，引擎 codex，{not_a_placeholder}'
    assert x.render("{report_id}", {"report_id": "{market}"}) == "{market}"  # 填进去的值不会被再扫一遍
    assert x.render("第 {iteration_current} 轮", {"iteration_current": 0}) == "第 0 轮"


def test_render_raises_on_unfilled_known_placeholder():
    with pytest.raises(x.PromptError) as err:
        x.render("{report_id} {market} <EXTERNAL_ENGINE>", {"report_id": "r1"})
    assert "{market}" in str(err.value) and "<EXTERNAL_ENGINE>" in str(err.value)


def test_every_template_placeholder_is_known():
    names: set[str] = set()
    for path in sorted((REPO_ROOT / "tools" / "flowlib" / "prompts").glob("*.md")):
        names |= set(re.findall(r"\{([a-z_][a-z0-9_]*)\}", path.read_text(encoding="utf-8")))
    for path in sorted((REPO_ROOT / "templates" / "codex_prompts").glob("*.md")):
        names |= set(re.findall(r"\{([a-z_][a-z0-9_]*)\}", x.strip_template_header(path.read_text(encoding="utf-8"))))
    assert names and names <= x.KNOWN_PLACEHOLDERS, sorted(names - x.KNOWN_PLACEHOLDERS)


def test_spec_seed_lists_new_leak_surfaces_and_keeps_its_placeholders():
    text = (REPO_ROOT / "templates" / "codex_prompts" / "spec_audit.md").read_text(encoding="utf-8")
    for needle in ("{workspace}/flow/", "{workspace}/reviews/", "{workspace}/events.jsonl", "{workspace}/board.html", "workspace/board.html"):
        assert needle in text
    assert set(re.findall(r"\{([a-z_]+)\}", text)) == {"difficulty", "market", "report_id", "type_hint", "workspace"}
    assert "<EXTERNAL_ENGINE>" in text and "external_review.py" in text and "command codex exec" not in text


def test_kernel_assets_do_not_spell_out_the_engine_command():
    files = [REPO_ROOT / "tools" / "flowlib" / "extreview.py", *sorted((REPO_ROOT / "tools" / "flowlib" / "prompts").glob("*.md"))]
    assert len(files) > 5 and all("codex exec" not in path.read_text(encoding="utf-8") for path in files)


def test_settings_defaults_and_per_checkpoint_overrides():
    default = x.settings(None, "code", "codex")
    assert default["timeout_seconds"] == 1800 and default["budget_bytes"] == x.DEFAULT_BUDGET_KB["codex"] * 1024 == 320 * 1024
    assert (default["effort_first"], default["effort_recheck"], default["model"]) == ("high", "medium", None)
    assert default["delta_max_changed_ratio"] == 0.3 and default["output_schema"] is True
    assert x.settings({}, "result", "claude")["budget_bytes"] == x.DEFAULT_BUDGET_KB["claude"] * 1024 == 200 * 1024

    config = {
        "external_review": {
            "engine": "codex",
            "effort_first": "xhigh",
            "timeout_seconds": 60,
            "model": {"codex": "gpt-x"},
            "checkpoints": {"code": {"effort_first": "low", "input_budget_kb": {"codex": 100, "claude": 50}, "output_schema": False}},
        }
    }
    code = x.settings(config, "code", "claude")
    assert (code["effort_first"], code["budget_bytes"], code["output_schema"], code["model"]) == ("low", 50 * 1024, False, None)
    spec = x.settings(config, "spec", "codex")
    assert (spec["effort_first"], spec["budget_bytes"], spec["timeout_seconds"], spec["model"]) == ("xhigh", 320 * 1024, 60, "gpt-x")
    for bad in ({"effort_first": "turbo"}, {"timeout_seconds": 0}, {"delta_max_changed_ratio": 1.5}, {"input_budget_kb": -1}, {"model": 3}):
        with pytest.raises(x.ExtReviewError):
            x.settings({"external_review": bad}, "code", "codex")


def test_effort_ladder():
    assert x.normalize_effort("claude", "ultra") == "max" and x.normalize_effort("codex", "MAX") == "ultra"
    assert x.normalize_effort("claude", "minimal") == "low"
    assert [x.downgrade_effort("codex", e) for e in ("ultra", "xhigh", "high", "medium", "low", "minimal")] == ["xhigh", "high", "medium", "low", "low", "minimal"]
    assert [x.downgrade_effort("claude", e) for e in ("max", "high", "low")] == ["xhigh", "medium", "low"]


# ---------------------------------------------------------------------------
# 输入包
# ---------------------------------------------------------------------------


def test_r_literals_take_decimals_and_percent_fractions_only():
    literals = x.r_literals(SPEC)  # 只看 R 类要素；整数、页码、有效数字不足两位的（0.5）不取
    assert literals == {"12.34": ["R1"], "0.1234": ["R1"], "0.871": ["R1"], "25.6": ["R1"], "0.256": ["R1"], "0.36": ["R1"]}
    hits = [
        {"file": "src/a/ref.py", "line": n, "literal": f"1.{n:03d}", "elements": ["R1", "R2", "R3", "R4", "R5"], "comment": False, "text": f"V{n} = 1.{n:03d}"}
        for n in range(1, 16)
    ]
    hits.insert(1, {**hits[0], "literal": "2.345", "elements": ["R6"]})  # 同一行上的第二个字面量
    section = x._literal_section({h["literal"]: h["elements"] for h in hits} | {"9.99": ["R9"]}, hits)
    assert "命中 16 处，分布在 1 个文件" in section and "`src/a/ref.py`：16 处（15 行），16 个不同的字面量" in section
    assert "第 1 行 `1.001`、`2.345`（见于 R1、R2、R3、R4 等）：`V1 = 1.001`" in section  # 同一行只列一次
    assert "第 12 行 `1.012`（见于 R1、R2、R3、R4 等）" in section and "第 13 行" not in section
    assert "……该文件其余 3 行未逐条列出" in section and "其余 1 个字面量在 `src/` 下没有出现" in section


def test_build_pack_numbers_lines_and_downgrades_by_priority():
    items = [
        x.PackItem("a.md", "第一行\n第二行\n"),
        x.PackItem("big.md", "\n".join(f"第 {i} 行" for i in range(400))),
        x.PackItem("small.md", "尾巴\n"),
        x.PackItem("gone.md", None),
        x.PackItem("@备料", "备料正文", generated=True, title="内核备料"),
    ]
    text, manifest = x.build_pack("测试", items, 2000)
    assert "<<<FILE a.md（2 行）>>>\n     1\t第一行\n     2\t第二行\n<<<END FILE a.md>>>" in text
    assert "<<<FILE big.md" not in text and "| `big.md` | 400 |" in text and "只列路径" in text
    assert "<<<FILE small.md" in text  # 排在后面、放得下的文件仍然入包
    assert "## 内核备料\n\n备料正文" in text
    by_path = {f["path"]: f for f in manifest["files"]}
    assert by_path["big.md"]["included"] == "path_only" and by_path["big.md"]["lines"] == 400
    assert by_path["a.md"]["included"] == "full" and by_path["gone.md"]["included"] == "missing"
    assert manifest["downgraded"] == ["big.md"] and manifest["missing"] == ["gone.md"]
    assert manifest["bytes"] == len(text.encode("utf-8")) <= 2000


def test_prepare_code_renders_prompt_and_numbered_pack(tmp_path):
    root = make_case(tmp_path)
    job = prepare(root, "code")
    assert (job["job_id"], job["kind"], job["round"], job["mode"], job["engine_state"]) == ("code_r1", "code", 1, "full", "codex_external")
    assert job["dir"] == f"{WS}/audit/external/code_r1"
    (call,) = job["calls"]
    assert (call["name"], call["effort"], call["schema"]) == ("main", "high", "schema_main.json")

    prompt, pack = read(root, f"{job['dir']}/prompt_main.md"), read(root, f"{job['dir']}/input_main.md")
    assert prompt.startswith("<!-- extreview code_r1/main ") and not leftover(prompt)
    assert "不必再逐段读取" in prompt and "自己打开" in prompt
    assert f"{WS}/audit/common_signatures.md" in prompt and "12.34, 0.1234, 0.871, 25.6, 0.256, 0.36" in prompt  # R 类字面量清单填进了提示词
    assert prompt.endswith(read(root, f"{WS}/audit/external_prompt_code.md"))  # 首轮提示词按旧文件名另存一份

    assert f"<<<FILE src/{RID}/strategy.py（16 行）>>>" in pack and "     5\tTARGET_SHARPE = 0.871  # 只作对照" in pack
    assert f"`src/{RID}/strategy.py`：2 处（2 行），2 个不同的字面量" in pack
    assert "第 5 行 `0.871`（见于 R1）：`TARGET_SHARPE = 0.871  # 只作对照`" in pack
    assert "第 6 行 `12.34`（见于 R1）［在注释里］：`# 研报年化 12.34%`" in pack
    assert "两位有效数字的字面量另命中 1 处（多半是参数取值的巧合，未逐条列出）：`0.36`×1。" in pack  # 36% 的小数形式
    assert job["prep"] == {"r_literals": 6, "r_literal_hits": 3}
    assert "def winsorize(series, lower=0.01, upper=0.99):" in pack and "_private_helper" not in pack
    assert "SPEC_ONLY_MARKER" in pack and "MATRIX_MARKER" in pack and "ASSUME_MARKER" in pack
    assert "def winsorize" in read(root, f"{WS}/audit/common_signatures.md")

    assert job["input_bytes"] == call["bytes"] == len((prompt.rstrip("\n") + "\n\n" + pack).encode("utf-8"))  # 实际发出去的字节数
    assert json.loads(read(root, f"{job['dir']}/job.json")) == json.loads(json.dumps(job))
    schema = json.loads(read(root, f"{job['dir']}/schema_main.json"))
    assert schema["required"] == ["checkpoint", "verdict", "dimensions_checked", "findings"] and schema["additionalProperties"] is False
    assert (root / job["dir"] / "baseline.json.gz").is_file()
    pending = x.status(root, RID, "code_r1")
    assert (pending["state"], pending["reason"], pending["mode"], pending["input_bytes"]) == ("pending", None, "full", job["input_bytes"])
    assert pending["attempts"] == [] and pending["usage"] is None and pending["subsessions"] is None


def test_failed_literal_prefilter_degrades_to_a_note(tmp_path, monkeypatch):
    root = make_case(tmp_path)

    def broken(_text):
        raise RuntimeError("解析失败")

    monkeypatch.setattr(x, "r_literals", broken)
    job = prepare(root, "code")  # 备料做不出来不该让整道外审退成替身
    prompt, pack = read(root, f"{job['dir']}/prompt_main.md"), read(root, f"{job['dir']}/input_main.md")
    assert any("预筛没有做成" in w for w in job["warnings"]) and job["prep"] == {"r_literals": 0, "r_literal_hits": 0}
    assert "未能自动生成" in prompt and "预筛没有做成" in pack and not leftover(prompt)
    assert f"<<<FILE src/{RID}/strategy.py" in pack


def test_prepare_downgrades_oversized_files_to_path_only(tmp_path):
    root = make_case(tmp_path)
    big = root / "src" / RID / "big_module.py"
    big.write_text("\n".join(f"VALUE_{i} = {i}  # 占位行" for i in range(4000)) + "\n", encoding="utf-8")
    job = prepare(root, "code", config={"external_review": {"input_budget_kb": {"codex": 40}}})
    pack = read(root, f"{job['dir']}/input_main.md")
    entry = {f["path"]: f for f in job["calls"][0]["manifest"]["files"]}[f"src/{RID}/big_module.py"]
    assert entry["included"] == "path_only" and entry["lines"] == 4000
    assert "VALUE_3999 = 3999" not in pack and f"| `src/{RID}/big_module.py` | 4000 |" in pack
    order = [f["path"] for f in job["calls"][0]["manifest"]["files"] if not f.get("generated")]
    assert order == [
        f"src/{RID}/strategy.py",
        f"src/{RID}/config.py",
        f"src/{RID}/main.py",
        f"{WS}/spec/spec.md",  # 每个审查维度都要对照的文书排在其余源码之前
        f"{WS}/spec/coverage_matrix.md",
        f"{WS}/assumptions.md",
        f"src/{RID}/big_module.py",
    ]
    small = root / "src" / RID / "zz_small.py"
    small.write_text("X = 1\n", encoding="utf-8")
    again = prepare(root, "code", config={"external_review": {"input_budget_kb": {"codex": 40}}})
    included = {f["path"]: f["included"] for f in again["calls"][0]["manifest"]["files"]}
    assert included[f"src/{RID}/big_module.py"] == "path_only" and included[f"src/{RID}/zz_small.py"] == "full"  # 排在后面但放得下的照常入包
    small.unlink()

    # 其余源码按覆盖矩阵里被引用的次数排：承载规格要素多的先入包，没被引用的排最后
    for name in ("aaa_reference.py", "signals.py", "weights.py"):
        (root / "src" / RID / name).write_text(f"NAME = '{name}'\n", encoding="utf-8")
    matrix = root / WS / "spec" / "coverage_matrix.md"
    matrix.write_text(
        matrix.read_text(encoding="utf-8") + f"| F2 | F | src/{RID}/weights.py:alloc |\n| F3 | F | weights.py:cap；signals.py:build |\n", encoding="utf-8"
    )
    ranked = [f["path"].rsplit("/", 1)[-1] for f in prepare(root, "code")["calls"][0]["manifest"]["files"] if not f.get("generated")]
    assert ranked[:3] == ["strategy.py", "config.py", "main.py"] and ranked[6:] == ["weights.py", "signals.py", "aaa_reference.py", "big_module.py"]
    for name in ("aaa_reference.py", "signals.py", "weights.py"):
        (root / "src" / RID / name).unlink()
    job = prepare(root, "code", config={"external_review": {"input_budget_kb": {"codex": 40}}})
    assert job["input_bytes"] <= 40 * 1024 and job["budget_bytes"] == 40 * 1024
    assert job["warnings"] and "1 个文件只列路径" in read(root, f"{job['dir']}/prompt_main.md")
    assert x.status(root, RID, "code_r1")["input_bytes"] == job["input_bytes"]


def test_prepare_rejects_invalid_requests(tmp_path):
    root = make_case(tmp_path)
    bad_calls = [
        dict(kind="code", engine="codex", host="codex"),  # 外审必须与宿主不同家族
        dict(kind="code", engine="claude", host="claude_code"),
        dict(kind="plan"),
        dict(kind="code", round_no=0),
        dict(kind="code", engine="gemini"),
        dict(kind="code", config={"external_review": {"effort_first": "turbo"}}),
        dict(kind="second_opinion"),  # 迭代轮次还是 0
    ]
    for kwargs in bad_calls:
        with pytest.raises(x.ExtReviewError):
            prepare(root, **kwargs)
    assert prepare(root, "code", host="generic")["engine"] == "codex"
    (root / "src" / RID / "strategy.py").unlink()
    (root / "src" / RID / "config.py").unlink()
    (root / "src" / RID / "main.py").unlink()
    with pytest.raises(x.ExtReviewError):
        prepare(root, "code")  # 没有可审的源码


def test_user_seed_with_unfillable_placeholder_is_rejected(tmp_path):
    root = make_case(tmp_path)
    seed = root / "templates" / "codex_prompts" / "code_audit.md"
    seed.parent.mkdir(parents=True)
    seed.write_text("<!-- 头部说明 {NN} -->\n\n===== 传给 codex 的正文开始 =====\n\n审 {report_id}，原因 {trigger_reason}\n", encoding="utf-8")
    with pytest.raises(x.PromptError) as err:
        prepare(root, "code")
    assert "{trigger_reason}" in str(err.value)
    seed.write_text(
        '<!-- 头部说明 {NN} -->\n\n===== 传给 codex 的正文开始 =====\n\n审 {report_id}，引擎 <EXTERNAL_ENGINE>（<EXTERNAL_ENGINE_STATE>），示例 {"a": 1}\n', encoding="utf-8"
    )
    prompt = read(root, f"{prepare(root, 'code')['dir']}/prompt_main.md")
    assert f'审 {RID}，引擎 codex（codex_external），示例 {{"a": 1}}' in prompt and "头部说明" not in prompt


def test_experimental_result_review_gets_boundary_note(tmp_path):
    strict = make_case(tmp_path / "a")
    assert "实验模式审查边界" not in read(strict, f"{prepare(strict, 'result')['dir']}/prompt_main.md")
    experimental = make_case(tmp_path / "b", reproduction_mode="experimental")
    job = prepare(experimental, "result", extra={"notes": "只看图表一致性 NOTE_MARKER"})
    prompt, pack = read(experimental, f"{job['dir']}/prompt_main.md"), read(experimental, f"{job['dir']}/input_main.md")
    assert "实验模式审查边界" in prompt and "NOTE_MARKER" in prompt and not leftover(prompt)
    assert f"output/{RID}/results/comparison.json" in prompt
    assert '"reproduced_value": 0.52' in pack and "VERIFY_MARKER" in pack and "EVIDENCE_MARKER" in pack
    order = [f["path"] for f in job["calls"][0]["manifest"]["files"]]
    assert order[:6] == [  # 种子模板点名的六份输入排在最前
        f"output/{RID}/results/comparison.json",
        f"output/{RID}/verify_report.md",
        f"{WS}/assumptions.md",
        f"{WS}/spec/coverage_matrix.md",
        f"{WS}/spec/ambiguities.md",
        "templates/data_catalog.md",
    ]
    catalog = {f["path"]: f for f in job["calls"][0]["manifest"]["files"]}["templates/data_catalog.md"]
    assert catalog["included"] == "full" and "<<<FILE templates/data_catalog.md" in pack  # 工作区没有这份模板，用插件自带的
    (experimental / "templates").mkdir()
    (experimental / "templates" / "data_catalog.md").write_text("# 本工作区自己的数据目录 OWN_CATALOG\n", encoding="utf-8")
    assert "OWN_CATALOG" in read(experimental, f"{prepare(experimental, 'result')['dir']}/input_main.md")  # 工作区有就用工作区的


# ---------------------------------------------------------------------------
# 盲提取两次调用
# ---------------------------------------------------------------------------

BLIND = "突破比例 | F | p5 | 窗口 20 日\n策略绩效 | R | p9 | 年化 12.34%、夏普 0.87"


def test_spec_review_runs_blind_then_review(tmp_path, engines):
    root = make_case(tmp_path)
    diffs = [{"id": "D-01", "category": "数值不一致", "pages": "p9", "description": "回撤", "resolution": "corrected", "basis": "tables_extracted.md:6", "finding_id": "CDX-S-01"}]
    engines.control(outputs={"blind": BLIND, "review": review_json([("CDX-S-01", "major", "R1 回撤抄错。应为 -25.6%")], "pass_with_issues", diffs=diffs)}, session={"reads": 2})
    job = prepare(root, "spec")
    assert [c["name"] for c in job["calls"]] == ["blind", "review"] and job["job_id"] == "spec_r1"
    blind_prompt, blind_pack = read(root, f"{job['dir']}/prompt_blind.md"), read(root, f"{job['dir']}/input_blind.md")
    for text in (blind_prompt, blind_pack):  # 第一次调用看不到规格书的路径，更看不到内容
        assert "spec.md" not in text and "SPEC_ONLY_MARKER" not in text and "MATRIX_MARKER" not in text and "AMBIG_MARKER" not in text
    assert "REPORT_TEXT_MARKER" in blind_pack and "TABLE_MARKER" in blind_pack
    for needle in (f"{WS}/flow/", f"{WS}/reviews/", f"{WS}/events.jsonl", f"{WS}/board.html", "workspace/board.html", f"src/{RID}/"):
        assert needle in blind_prompt
    assert not (root / job["dir"] / "input_review.md").exists()  # 第二次的输入包等盲提取跑完再拼
    review_prompt = read(root, f"{job['dir']}/prompt_review.md")
    assert not leftover(blind_prompt) and not leftover(review_prompt) and "CDX-S-01" in review_prompt
    legacy = read(root, f"{WS}/audit/external_prompt_spec.md")
    assert "第一次调用：盲提取" in legacy and "第二次调用" in legacy

    result = run(root, job)
    assert result["state"] == "success" and result["completed_calls"] == ["blind", "review"]
    calls = engines.calls()
    assert [c["call"] for c in calls] == ["blind", "review"] and [c["effort"] for c in calls] == ["high", "high"]
    first, second = engines.stdin(0), engines.stdin(1)
    assert "spec.md" not in first and "SPEC_ONLY_MARKER" not in first and "REPORT_TEXT_MARKER" in first
    assert BLIND in second and "SPEC_ONLY_MARKER" in second and f"<<<FILE {WS}/spec/spec.md" in second and "MATRIX_MARKER" in second
    assert "--output-schema" not in calls[0]["argv"] and "--output-schema" in calls[1]["argv"]
    assert ["-c", "features.multi_agent=false"] == calls[0]["argv"][calls[0]["argv"].index("features.multi_agent=false") - 1:][:2]
    assert Path(calls[0]["cwd"]).resolve() == root.resolve()

    raw = root / result["output"]
    assert result["output"] == f"{job['dir']}/output.md"
    parsed = cg.parse_review(raw)
    assert (parsed.issues, parsed.verdict) == (1, "pass_with_issues")
    assert x.split_blind_block(raw.read_text(encoding="utf-8")) == BLIND
    assert "过程日志" not in raw.read_text(encoding="utf-8")  # 取的是落盘的最后一条消息

    # 用量取自外审引擎自己的会话记录：两次调用各一个会话，没有子会话，盲提取没碰规格书
    usage = result["usage"]
    assert (usage["source"], usage["sessions"], usage["subsessions"], usage["read_commands"]) == ("codex_sessions", 2, 0, 4)
    assert (usage["uncached_input"], usage["cache_read"], usage["output"]) == (1200, 800, 100)
    assert set(usage["per_call"]) == {"blind", "review"} and usage["per_call"]["blind"]["read_commands"] == 2
    assert result["subsessions"] == 0 and result["blind_read_spec"] is False
    assert result["input_bytes"] == len(first.encode("utf-8")) + len(second.encode("utf-8"))  # 包大小以实际发出去的为准

    summary = x.collect(root, RID, "spec", engine_state="codex_external")
    assert read(root, f"{WS}/spec/spec_external.md") == BLIND + "\n"
    assert summary["raw"] == f"{WS}/audit/spec_audit_external.md" and cg.parse_review(root / summary["raw"]).issues == 1
    document = json.loads(read(root, summary["raw"]))
    assert document["rounds"][0]["blind_read_spec"] is False and document["diffs"][0]["finding_id"] == "CDX-S-01"


def test_blind_call_that_touches_spec_and_spawns_is_flagged(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"blind": BLIND}, session={"reads": 1, "blind_reads_spec": f"{WS}/spec/spec.md", "spawn": True})
    result = run(root, prepare(root, "spec"))
    assert result["state"] == "success"
    assert result["blind_read_spec"] is True and result["subsessions"] == 2 and result["usage"]["subsessions"] == 2
    assert result["usage"]["read_commands"] == 3 and result["usage"]["output"] == 120  # 子会话的用量也算进来


def test_review_session_that_reads_the_blind_prompt_is_not_mistaken_for_the_blind_call(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"blind": BLIND}, session={"reads": 1, "review_peeks_blind_prompt": f"{WS}/spec/spec.md"})
    result = run(root, prepare(root, "spec"))
    usage = result["usage"]
    assert result["state"] == "success" and usage["sessions"] == 2
    assert usage["per_call"]["blind"]["read_commands"] == 1 and usage["per_call"]["review"]["read_commands"] == 3
    assert result["blind_read_spec"] is False  # 会话归属只认用户消息开头的标记，第二次调用读规格书不算盲提取违规


def test_sessions_from_another_directory_are_not_attributed(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"blind": BLIND}, session={"reads": 5, "cwd": "/somewhere/else"})
    result = run(root, prepare(root, "spec"))
    assert result["state"] == "success"  # 取不到用量不影响外审结果
    assert result["usage"] is None and result["subsessions"] is None and result["blind_read_spec"] is None


def test_relaunch_after_failure_does_not_redo_the_blind_call(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(plan=[{}, {"mode": "quota"}], outputs={"blind": BLIND}, session={"reads": 1})
    job = prepare(root, "spec")
    failed = run(root, job)
    assert (failed["state"], failed["reason"], failed["completed_calls"]) == ("failed", "quota_error", ["blind"])
    assert failed["output"] is None and "review" in failed["message"]
    engines.reset()
    engines.control(outputs={"review": review_json([], "pass")}, session={"reads": 2})
    done = run(root, job)
    assert done["state"] == "success" and [c["call"] for c in engines.calls()] == ["review"]
    assert done["usage"]["sessions"] == 2 and done["usage"]["read_commands"] == 3  # 用量把之前跑完的盲提取也算在内
    assert done["blind_read_spec"] is False
    assert x.split_blind_block(read(root, done["output"])) == BLIND
    assert [(a["call"], a["status"]) for a in done["attempts"]] == [("blind", "success"), ("review", "quota_error"), ("review", "success")]
    assert run(root, job)["state"] == "success" and len(engines.calls()) == 1  # 已经跑完的 job 不重跑


# ---------------------------------------------------------------------------
# 超时、重试与失败分类
# ---------------------------------------------------------------------------


def test_timeout_downgrades_effort_and_retries_once_with_same_input(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(by_effort={"high": {"mode": "sleep"}})
    job = prepare(root, "code", config=FAST)
    result = run(root, job)
    assert (result["state"], result["reason"]) == ("success", None)
    assert [(a["call"], a["effort"], a["status"]) for a in result["attempts"]] == [("main", "high", "timeout"), ("main", "medium", "success")]
    assert all(a["seconds"] > 0 for a in result["attempts"]) and result["seconds"] >= 1
    calls = engines.calls()
    assert [c["effort"] for c in calls] == ["high", "medium"]
    assert calls[0]["sha"] == calls[1]["sha"]  # 重试时输入原样，不缩减
    assert calls[0]["bytes"] == job["input_bytes"]
    assert not x.er.pid_alive(calls[0]["pid"])  # 超时的那个进程已经被结束


def test_second_timeout_ends_the_job_as_failed_timeout(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(default={"mode": "sleep"})
    result = run(root, prepare(root, "result", config=FAST))
    assert (result["state"], result["reason"], result["output"]) == ("failed", "timeout", None)
    assert [(a["effort"], a["status"]) for a in result["attempts"]] == [("high", "timeout"), ("medium", "timeout")]
    assert len(engines.calls()) == 2 and result["finished_at"]
    assert x.completed_rounds(root, RID, "result") == []


@pytest.mark.parametrize(("mode", "reason"), [("quota", "quota_error"), ("auth", "auth_error")])
def test_quota_and_auth_errors_are_not_retried(tmp_path, engines, mode, reason):
    root = make_case(tmp_path)
    engines.control(default={"mode": mode})
    result = run(root, prepare(root, "code"))
    assert (result["state"], result["reason"]) == ("failed", reason)
    assert len(engines.calls()) == 1 and [a["status"] for a in result["attempts"]] == [reason]


def test_missing_engine_is_unavailable_without_retry(tmp_path, engines, monkeypatch):
    root = make_case(tmp_path)
    monkeypatch.setattr(x.er.shutil, "which", lambda _name: None)
    result = run(root, prepare(root, "code"))
    assert (result["state"], result["reason"]) == ("failed", "unavailable")
    assert len(result["attempts"]) == 1 and engines.calls() == []


def test_empty_output_is_retried_once(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(plan=[{"mode": "empty"}])
    result = run(root, prepare(root, "code"))
    assert result["state"] == "success"
    assert [(a["effort"], a["status"], a["schema"]) for a in result["attempts"]] == [("high", "empty_output", True), ("high", "success", True)]
    calls = engines.calls()
    assert len(calls) == 2 and calls[0]["sha"] == calls[1]["sha"]

    engines.reset()
    engines.control(default={"mode": "empty"})
    again = run(root, prepare(root, "code"))
    assert (again["state"], again["reason"]) == ("failed", "empty_output") and len(engines.calls()) == 2


def test_failed_call_is_retried_once_without_schema(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(plan=[{"mode": "fail"}])
    result = run(root, prepare(root, "code"))
    assert result["state"] == "success"
    assert [(a["effort"], a["status"], a["schema"]) for a in result["attempts"]] == [("high", "failed", True), ("high", "success", False)]
    calls = engines.calls()
    assert "--output-schema" in calls[0]["argv"] and "--output-schema" not in calls[1]["argv"] and calls[0]["sha"] == calls[1]["sha"]

    engines.reset()
    engines.control(default={"mode": "fail"})
    again = run(root, prepare(root, "code"))
    assert (again["state"], again["reason"]) == ("failed", "failed") and len(engines.calls()) == 2


def test_unparseable_conclusion_is_not_accepted(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"main": "看了一遍，感觉没什么大问题。"})
    job = prepare(root, "code")
    result = run(root, job)
    assert (result["state"], result["reason"]) == ("failed", "failed") and len(engines.calls()) == 2
    assert all("unparseable_output" in a["reason"] for a in result["attempts"])
    assert [a["schema"] for a in result["attempts"]] == [True, True]  # 结论不合格时重试仍带输出约束（去掉约束只针对进程失败）
    assert not (root / job["dir"] / "output.md").exists() and (root / job["dir"] / "rejected_main_1.md").is_file()


# ---------------------------------------------------------------------------
# 后台启动与崩溃识别
# ---------------------------------------------------------------------------


def stop_runner(root: Path, job_id: str, pid: int) -> dict:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return wait_for(lambda: (s := x.status(root, RID, job_id))["state"] != "running" and s)


def test_detached_launch_goes_from_running_to_success(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(default={"delay": 1.0})
    job = prepare(root, "result")
    started = x.launch(root, RID, job["job_id"])
    assert started["job_id"] == "result_r1" and isinstance(started["pid"], int) and started["started_at"]
    running = x.status(root, RID, "result_r1")
    assert (running["state"], running["pid"], running["reason"]) == ("running", started["pid"], None)
    again = x.launch(root, RID, "result_r1")
    assert again["already_running"] is True and again["pid"] == started["pid"]  # 同一个 job 不重复启动

    done = wait_for(lambda: (s := x.status(root, RID, "result_r1"))["state"] != "running" and s)
    assert (done["state"], done["reason"]) == ("success", None)
    assert done["seconds"] >= 1 and done["finished_at"] and done["started_at"] == started["started_at"]
    assert [(a["call"], a["effort"], a["status"]) for a in done["attempts"]] == [("main", "high", "success")]
    (call,) = engines.calls()
    assert call["root_env"] == str(root) and Path(call["cwd"]).resolve() == root.resolve()
    log = read(root, f"{job['dir']}/stdout.log")
    assert "status=success" in log and "过程日志" in log
    assert x.launch(root, RID, "result_r1").get("already_done") is True and len(engines.calls()) == 1


def test_killed_runner_is_reported_as_crashed_and_engine_is_cleaned_up(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(default={"mode": "sleep"})
    job = prepare(root, "result")
    started = x.launch(root, RID, job["job_id"])
    engine_pid = wait_for(lambda: (x._read_json(root / job["dir"] / "engine.pid") or {}).get("pid"))
    wait_for(lambda: len(engines.calls()) == 1)
    assert x.status(root, RID, "result_r1")["state"] == "running"

    crashed = stop_runner(root, "result_r1", started["pid"])
    assert (crashed["state"], crashed["reason"]) == ("failed", "crashed") and crashed["finished_at"]
    wait_for(lambda: not x.er.pid_alive(engine_pid), timeout=15)  # 留下的外审进程被清掉，不再消耗额度
    assert x.status(root, RID, "result_r1")["reason"] == "crashed"
    assert x.completed_rounds(root, RID, "result") == []


def test_reused_pid_is_not_mistaken_for_a_live_runner(tmp_path):
    root = make_case(tmp_path)
    job = prepare(root, "result")
    stale = {"job_id": job["job_id"], "state": "running", "pid": os.getppid(), "launch_token": "deadbeefcafe", "started_at": "2026-11-22T10:00:00+08:00", "started_epoch": time.time() - 30}
    (root / job["dir"] / "status.json").write_text(json.dumps(stale), encoding="utf-8")
    status = x.status(root, RID, job["job_id"])  # 进程号还在，但命令行不是这个 job 的后台进程
    assert (status["state"], status["reason"]) == ("failed", "crashed")


def test_prepare_overrides_a_running_job_and_cancel_stops_one(tmp_path, engines):
    root = make_case(tmp_path)
    first = prepare(root, "code")
    (root / first["dir"] / "output_main.md").write_text("上一次的输出", encoding="utf-8")
    second = prepare(root, "code")
    assert not (root / first["dir"] / "output_main.md").exists() and second["warnings"] == []
    assert first["calls"][0]["nonce"] != second["calls"][0]["nonce"]

    engines.control(default={"mode": "sleep"})
    started = x.launch(root, RID, "code_r1")
    try:
        wait_for(lambda: len(engines.calls()) == 1)
        with pytest.raises(x.ExtReviewError):
            x.fallback_task(root, RID, "code_r1")  # 还在跑，不能改派替身
        third = prepare(root, "code")  # 覆盖同名 job：先把在跑的那一份连同外审进程停掉
        assert any("已终止" in w for w in third["warnings"])
        wait_for(lambda: not x.er.pid_alive(engines.calls()[0]["pid"]), timeout=15)
        assert x.status(root, RID, "code_r1")["state"] == "pending" and x._CHILDREN.get(started["pid"]) is None

        started = x.launch(root, RID, "code_r1")
        wait_for(lambda: len(engines.calls()) == 2)
        cancelled = x.cancel(root, RID, "code_r1")
        assert (cancelled["state"], cancelled["reason"], cancelled["message"]) == ("failed", "failed", "已取消")
        wait_for(lambda: not x.er.pid_alive(engines.calls()[1]["pid"]), timeout=15)
        assert x.cancel(root, RID, "code_r1")["state"] == "failed"  # 没在跑时原样返回
    finally:
        stop_runner(root, "code_r1", started["pid"])


def test_command_line_status_and_run(tmp_path, engines, monkeypatch, capsys):
    root = make_case(tmp_path)
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    prepare(root, "result")
    assert x.main(["status", RID, "result_r1"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "pending"
    assert x.main(["run", RID, "result_r1"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "success"
    assert x.main(["status", RID, "code_r7"]) == 1 and "error" in json.loads(capsys.readouterr().out)
    engines.reset()
    engines.control(default={"mode": "quota"})
    prepare(root, "code")
    assert x.main(["run", RID, "code_r1"]) == 2


# ---------------------------------------------------------------------------
# 差量复审
# ---------------------------------------------------------------------------


def test_second_round_is_a_delta_review_with_stable_ids(tmp_path, engines):
    root = make_case(tmp_path)
    first = review_json([("CDX-C-01", "critical", "阈值硬编码成研报数值。应改为参数"), ("CDX-C-02", "major", "信号没有滞后一期")])
    run_round(root, engines, "code", 1, first)
    x.collect(root, RID, "code", engine_state="codex_external")
    rulings = {
        "CDX-C-01": {"处置": "accepted", "回应": "strategy.py:15 改为读配置"},
        "CDX-C-02": {"处置": "rejected", "回应": "信号在 main.py 统一滞后 RESPONSE_MARKER"},
    }
    x.write_responses(root, RID, "code", rulings)
    strategy = root / "src" / RID / "strategy.py"
    strategy.write_text(strategy.read_text(encoding="utf-8").replace("threshold=0.36", "threshold=THRESHOLD_FROM_CONFIG"), encoding="utf-8")

    job = prepare(root, "code", 2)
    assert (job["mode"], job["mode_reason"], job["prev_round"]) == ("delta", "delta", 1)
    assert job["calls"][0]["effort"] == "medium" and 0 < job["delta"]["ratio"] < 0.3
    prompt, pack = read(root, f"{job['dir']}/prompt_main.md"), read(root, f"{job['dir']}/input_main.md")
    assert not leftover(prompt) and "第 2 轮（差量复审）" in prompt
    assert "沿用原编号" in prompt and "从 `CDX-C-03` 起顺序编号" in prompt and "未来函数" in prompt  # 判据沿用该审查点的种子
    assert "差量复审包" in pack and "仍未闭环的意见与回应（2 条）" in pack
    assert "strategy.py:15 改为读配置" in pack and "RESPONSE_MARKER" in pack and "被审方的处置：rejected" in pack
    assert "-def signal(ratio, threshold=0.36):" in pack and "+def signal(ratio, threshold=THRESHOLD_FROM_CONFIG):" in pack
    assert "<<<FILE" not in pack and "SPEC_ONLY_MARKER" not in pack and "ASSUME_MARKER" not in pack  # 没改的文件不再整份送
    assert f"| `{WS}/spec/spec.md` | 未变 |" in pack and f"| `src/{RID}/strategy.py` | 有改动 |" in pack
    assert job["input_bytes"] < x.status(root, RID, "code_r1")["input_bytes"]
    assert "差量复审" not in read(root, f"{WS}/audit/external_prompt_code.md")  # 首轮提示词的副本不被覆盖

    second = review_json([("CDX-C-02", "major", "滞后仍未落实"), ("CDX-C-03", "minor", "改动处少了类型注解")], "pass_with_issues")
    engines.reset()
    engines.control(outputs={"main": second})
    result = run(root, job)
    assert (result["state"], result["mode"]) == ("success", "delta") and engines.calls()[0]["effort"] == "medium"

    summary = x.collect(root, RID, "code", engine_state="codex_external")
    got = {f["id"]: (f["severity"], f["first_round"], f["last_round"], f["open"]) for f in summary["findings"]}
    assert got == {"CDX-C-01": ("critical", 1, 1, False), "CDX-C-02": ("major", 1, 2, True), "CDX-C-03": ("minor", 2, 2, True)}
    assert (summary["verdict"], summary["rounds"], summary["counts"]) == ("pass_with_issues", 2, {"critical": 1, "major": 1, "minor": 1})
    assert cg.parse_review(root / summary["raw"]).issues == 3
    document = json.loads(read(root, summary["raw"]))
    assert [(r["round"], r["mode"], r["listed"]) for r in document["rounds"]] == [(1, "full", ["CDX-C-01", "CDX-C-02"]), (2, "delta", ["CDX-C-02", "CDX-C-03"])]
    assert {f["id"]: f["detail"] for f in summary["findings"]}["CDX-C-02"] == "滞后仍未落实"  # 描述取最新一轮的
    assert {f["id"]: f["title"] for f in summary["findings"]}["CDX-C-02"] == "类别：信号没有滞后一期"  # 摘要保持首次出现时的

    responses = x.write_responses(root, RID, "code")
    assert (responses["rows"], responses["unruled"], responses["open_critical"]) == (3, ["CDX-C-03"], [])
    rows = response_rows(root, "CDX-C-")
    assert [cg._row_get(rows[i], "复核") for i in ("CDX-C-01", "CDX-C-02", "CDX-C-03")] == ["pass", "-", "open"]
    assert cg._row_get(rows["CDX-C-02"], "回应") == "信号在 main.py 统一滞后 RESPONSE_MARKER"
    gates = gate(cg.check_code_audit(root, RID))
    assert gates["G-CA-1"].passed and gates["G-CA-4"].passed and gates["G-CA-5"].passed and gates["G-CA-6"].passed

    third = prepare(root, "code", 3)
    third_prompt = read(root, f"{third['dir']}/prompt_main.md")
    assert third["mode"] == "delta" and "从 `CDX-C-04` 起顺序编号" in third_prompt and third["prev_round"] == 2
    assert "此前已闭环的意见（1 条" in read(root, f"{third['dir']}/input_main.md")


def test_large_change_falls_back_to_full_review_that_knows_old_ids(tmp_path, engines):
    root = make_case(tmp_path)
    run_round(root, engines, "code", 1, review_json([("CDX-C-01", "major", "问题一")]))
    for name in ("strategy.py", "main.py", "config.py"):
        (root / "src" / RID / name).write_text("\n".join(f"REWRITTEN_{i} = {i}" for i in range(120)) + "\n", encoding="utf-8")
    job = prepare(root, "code", 2)
    assert (job["mode"], job["mode_reason"]) == ("full", "changed_ratio") and job["delta"]["ratio"] > 0.3
    assert job["calls"][0]["effort"] == "high"
    prompt, pack = read(root, f"{job['dir']}/prompt_main.md"), read(root, f"{job['dir']}/input_main.md")
    assert "本轮是整体重审（第 2 轮）" in prompt and "`CDX-C-01`（major，第 1 轮提出，未闭环）" in prompt and "从 `CDX-C-02` 起顺序编号" in prompt
    assert not leftover(prompt) and f"<<<FILE src/{RID}/strategy.py" in pack and "REWRITTEN_119 = 119" in pack


def test_force_full_and_configurable_threshold(tmp_path, engines):
    root = make_case(tmp_path)
    run_round(root, engines, "result", 1, review_json([("CDX-R-01", "minor", "摘要不准")], "pass_with_issues"))
    report = root / "output" / RID / "verify_report.md"
    report.write_text(report.read_text(encoding="utf-8") + "补一行说明\n", encoding="utf-8")
    forced = prepare(root, "result", 2, force_full=True)
    assert (forced["mode"], forced["mode_reason"]) == ("full", "force_full")
    strict = prepare(root, "result", 2, config={"external_review": {"delta_max_changed_ratio": 0.0001}})
    assert (strict["mode"], strict["mode_reason"]) == ("full", "changed_ratio")
    relaxed = {"external_review": {"delta_max_changed_ratio": 0.0001, "checkpoints": {"result": {"delta_max_changed_ratio": 0.9, "effort_recheck": "low"}}}}
    delta = prepare(root, "result", 2, config=relaxed)
    assert (delta["mode"], delta["calls"][0]["effort"]) == ("delta", "low")
    assert "+补一行说明" in read(root, f"{delta['dir']}/input_main.md")


def test_spec_delta_round_is_a_single_call_and_keeps_the_blind_block(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"blind": BLIND, "review": review_json([("CDX-S-01", "major", "漏了敏感性分析 SA1")])})
    assert run(root, prepare(root, "spec"))["state"] == "success"
    x.collect(root, RID, "spec", engine_state="codex_external")
    spec = root / WS / "spec" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n### [SA1] 窗口敏感性\n- 页码: p12\n", encoding="utf-8")

    job = prepare(root, "spec", 2)
    assert job["mode"] == "delta" and [c["name"] for c in job["calls"]] == ["main"]
    assert "+### [SA1] 窗口敏感性" in read(root, f"{job['dir']}/input_main.md")
    engines.reset()
    engines.control(outputs={"main": review_json([], "pass")})
    assert run(root, job)["state"] == "success" and [c["call"] for c in engines.calls()] == ["main"]
    summary = x.collect(root, RID, "spec", engine_state="codex_external")
    assert summary["verdict"] == "pass" and [(f["id"], f["open"]) for f in summary["findings"]] == [("CDX-S-01", False)]
    assert read(root, f"{WS}/spec/spec_external.md") == BLIND + "\n"  # 差量轮不重做盲提取，沿用首轮的


# ---------------------------------------------------------------------------
# 多轮合并、回应表
# ---------------------------------------------------------------------------

def test_later_rounds_left_by_a_reset_counter_are_retired(tmp_path, engines):
    root = make_case(tmp_path)
    for number, findings in ((1, [("CDX-C-01", "critical", "上一次生命周期的第 1 轮")]), (2, []), (3, [])):
        x.import_round(root, RID, "code", number, original(tmp_path, f"old{number}.md", review_json(findings, "fail" if findings else "pass")))
    assert x.collect(root, RID, "code", engine_state="codex_external")["findings"][0]["open"] is False

    engines.control(outputs={"main": review_json([("CDX-C-01", "critical", "轮次计数回到 1 之后的新意见")])})
    job = prepare(root, "code")
    assert job["superseded"] == ["code_r2", "code_r3"] and any("_superseded" in w for w in job["warnings"])
    assert (job["mode"], job["prev_round"]) == ("full", None)
    assert run(root, job)["state"] == "success"
    merged = x.collect(root, RID, "code", engine_state="codex_external")
    assert merged["rounds"] == 1 and merged["findings"][0]["open"] is True  # 旧的后续轮次不会把新意见判成已闭环
    assert x.write_responses(root, RID, "code")["open_critical"] == ["CDX-C-01"]
    kept = sorted(p.name.split("__")[0] for p in (root / WS / "audit" / "external" / "_superseded").iterdir())
    assert kept == ["code_r2", "code_r3"] and [r["round"] for r in x.completed_rounds(root, RID, "code")] == [1]
    assert "superseded" not in prepare(root, "code", 2)  # 正常递增时什么都不挪


TABLE_ORIGINAL = """## 复审意见

| ID | severity | category | location | description | suggestion |
| --- | --- | --- | --- | --- | --- |
| CDX-R-02 | major | 类别 | p3 | 乙还在 | 改 |
| CDX-R-R1-01 | minor | 新问题 | p4 | 丁 | 改 |

VERDICT: pass_with_issues
"""


def test_merge_keeps_ids_stable_and_renumbers_unusable_ones(tmp_path):
    root = make_case(tmp_path)
    first = review_json([("CDX-R-1", "critical", "甲"), ("R1-乱写", "weird", "乙"), ("CDX-R-1", "minor", "丙")])
    x.import_round(root, RID, "result", 1, original(tmp_path, "r1.md", first))
    x.import_round(root, RID, "result", 2, original(tmp_path, "r2.md", TABLE_ORIGINAL))  # 退化成表格的旧原件
    summary = x.collect(root, RID, "result", engine_state="codex_external")
    got = [(f["id"], f["severity"], f["first_round"], f["last_round"], f["open"]) for f in summary["findings"]]
    assert got == [
        ("CDX-R-01", "critical", 1, 1, False),
        ("CDX-R-02", "major", 1, 2, True),  # 编号不合规：重新编号；认不出的严重度按 major
        ("CDX-R-03", "minor", 1, 1, False),  # 同一轮里重复的编号：重新编号
        ("CDX-R-04", "minor", 2, 2, True),
    ]
    parsed = cg.parse_review(root / summary["raw"])
    assert (parsed.issues, parsed.verdict, parsed.source) == (4, "pass_with_issues", "json")
    document = json.loads(read(root, summary["raw"]))
    by_id = {f["id"]: f for f in document["findings"]}
    assert by_id["CDX-R-02"]["orig_id"] == "R1-乱写" and len(by_id["CDX-R-02"]["history"]) == 2
    assert by_id["CDX-R-04"]["orig_id"] == "CDX-R-R1-01" and document["counts"]["open"] == 2
    assert [r["source"] for r in document["rounds"]] == ["json", "table"]

    job = prepare(root, "result", 3)  # 导入的轮次没有文件快照：下一轮整体重审
    assert (job["mode"], job["mode_reason"], job["next_finding_no"]) == ("full", "no_baseline", 5)
    with pytest.raises(x.ExtReviewError):
        x.import_round(root, RID, "result", 4, original(tmp_path, "bad.md", "一段没有结论的文字"))
    with pytest.raises(x.ExtReviewError):
        x.collect(root, RID, "code", engine_state="codex_external")  # 这个审查点还没有完成的轮次


EXISTING_RESPONSES = """# 审计回应总表

说明文字一行，表外文字不许动。

## spec 审查

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | minor | 图表编号缺口 | accepted | spec.md:88 已补 | pass |
| SA-A01 | major | 内审意见 | accepted | 已补 | pass |

## code 审查

| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |
|---|---|---|---|---|---|
| CDX-C-01 | major |   硬编码  | rejected | 理由 \\| 带竖线 | - |

结尾的一段话。
"""


def test_write_responses_recheck_column_and_untouched_neighbours(tmp_path):
    root = make_case(tmp_path)
    x.import_round(root, RID, "result", 1, original(tmp_path, "r1.md", review_json([("CDX-R-01", "critical", "数字不符"), ("CDX-R-02", "major", "归因证据不足"), ("CDX-R-03", "minor", "措辞")])))
    x.import_round(root, RID, "result", 2, original(tmp_path, "r2.md", review_json([("CDX-R-02", "major", "归因证据仍不足")], "pass_with_issues")))
    x.collect(root, RID, "result", engine_state="codex_external")
    path = root / WS / "audit" / "audit_responses.md"
    path.write_text(EXISTING_RESPONSES, encoding="utf-8")

    out = x.write_responses(root, RID, "result", {"CDX-R-01": {"处置": "accepted", "回应": "verify_report.md:12 已改"}, "CDX-R-02": {"处置": "rejected", "回应": "口径如此 | 见 AS3"}})
    assert (out["rows"], out["open_critical"], out["unanswered_major"], out["unruled"]) == (3, [], [], ["CDX-R-03"])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert all(line in lines for line in EXISTING_RESPONSES.splitlines())  # 别的审查点的行、表头、表外文字原样保留
    assert lines.index("结尾的一段话。") > max(i for i, line in enumerate(lines) if line.startswith("| CDX-R-"))
    rows = response_rows(root, "CDX-R-")
    assert [(cg._row_get(r, "severity"), cg._row_get(r, "处置"), cg._row_get(r, "复核")) for r in rows.values()] == [
        ("critical", "accepted", "pass"),  # 最新一轮不再列出：已闭环
        ("major", "rejected", "-"),  # 非 critical 的 rejected
        ("minor", "", "pass"),
    ]
    assert cg._row_get(rows["CDX-R-02"], "回应") == "口径如此 | 见 AS3" and cg._row_get(rows["CDX-R-01"], "摘要") == "类别：数字不符"
    assert len(response_rows(root, "CDX-S-")) == 1 and len(response_rows(root, "CDX-C-")) == 1

    snapshot = path.read_text(encoding="utf-8")
    assert x.write_responses(root, RID, "result")["unruled"] == ["CDX-R-03"] and path.read_text(encoding="utf-8") == snapshot  # 没给的保留已有值
    x.write_responses(root, RID, "result", {"CDX-R-02": {"处置": "accepted"}, "CDX-R-03": {"处置": "deferred", "回应": "留到报告阶段"}})
    rows = response_rows(root, "CDX-R-")
    assert cg._row_get(rows["CDX-R-02"], "复核") == "open" and cg._row_get(rows["CDX-R-02"], "回应") == "口径如此 | 见 AS3"
    assert cg._row_get(rows["CDX-R-03"], "复核") == "-"

    stale_row = "| CDX-R-09 | minor | 规范文件里没有的旧行 | accepted | x | pass |"
    path.write_text(re.sub(r"(?m)^(\| CDX-R-03 .*)$", lambda m: m.group(1) + "\n" + stale_row, path.read_text(encoding="utf-8")), encoding="utf-8")
    assert len(response_rows(root, "CDX-R-")) == 4
    assert x.write_responses(root, RID, "result")["dropped"] == ["CDX-R-09"]
    assert "CDX-R-09" not in path.read_text(encoding="utf-8")
    gates = gate(cg.check_result_audit(root, RID))
    assert gates["G-RA-1"].passed and gates["G-RA-2"].passed and gates["G-RA-5"].passed

    for bad in ({"CDX-R-77": {"处置": "accepted"}}, {"CDX-R-01": {"处置": "maybe"}}):
        with pytest.raises(x.ExtReviewError):
            x.write_responses(root, RID, "result", bad)
    with pytest.raises(x.ExtReviewError):
        x.write_responses(root, RID, "code")  # 还没有规范文件


def test_open_critical_blocks_the_gate_and_new_file_uses_template_header(tmp_path):
    root = make_case(tmp_path)
    x.import_round(root, RID, "result", 1, original(tmp_path, "r1.md", review_json([("CDX-R-01", "critical", "数字不符"), ("CDX-R-02", "major", "证据不足")])))
    x.collect(root, RID, "result", engine_state="codex_external")
    out = x.write_responses(root, RID, "result", {"CDX-R-01": {"处置": "rejected", "回应": "不认同"}})
    assert (out["open_critical"], out["unanswered_major"], out["unruled"]) == (["CDX-R-01"], ["CDX-R-02"], ["CDX-R-02"])
    text = read(root, f"{WS}/audit/audit_responses.md")
    assert "| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |" in text
    rows = response_rows(root, "CDX-R-")
    assert cg._row_get(rows["CDX-R-01"], "复核") == "open"  # critical 被拒也必须等外审不再列出
    gates = gate(cg.check_result_audit(root, RID))
    assert not gates["G-RA-2"].passed and gates["G-RA-5"].passed


def test_human_ruling_on_recheck_is_remembered(tmp_path):
    root = make_case(tmp_path)
    x.import_round(root, RID, "code", 1, original(tmp_path, "c1.md", review_json([("CDX-C-01", "critical", "疑似前视"), ("CDX-C-02", "critical", "硬编码")])))
    x.collect(root, RID, "code", engine_state="codex_external")
    waive = {"处置": "rejected", "回应": "人工裁定意见不成立（cp_03）：信号确为 T+1 执行", "复核": "pass"}
    out = x.write_responses(root, RID, "code", {"CDX-C-01": waive, "CDX-C-02": {"处置": "accepted", "回应": "删掉常量"}})
    assert (out["open_critical"], out["overridden"]) == (["CDX-C-02"], ["CDX-C-01"])
    assert cg._row_get(response_rows(root, "CDX-C-")["CDX-C-01"], "复核") == "pass"

    # 之后每次重写（不带裁决、只补回应、下一轮合并之后）都沿用人工结论，哪怕外审仍然列着这条意见
    x.write_responses(root, RID, "code")
    x.write_responses(root, RID, "code", {"CDX-C-02": {"回应": "删掉常量；修复：strategy.py:5"}})
    x.import_round(root, RID, "code", 2, original(tmp_path, "c2.md", review_json([("CDX-C-01", "critical", "仍认为是前视")])))
    x.collect(root, RID, "code", engine_state="codex_external")
    out = x.write_responses(root, RID, "code")
    assert (out["open_critical"], out["overridden"]) == ([], ["CDX-C-01"])
    rows = response_rows(root, "CDX-C-")
    assert [(cg._row_get(rows[i], "处置"), cg._row_get(rows[i], "复核")) for i in ("CDX-C-01", "CDX-C-02")] == [("rejected", "pass"), ("accepted", "pass")]
    assert gate(cg.check_code_audit(root, RID))["G-CA-5"].passed

    # 重新处置（只给处置、不给复核）就不再沿用；编号被另一条意见占用时也不沿用
    assert x.write_responses(root, RID, "code", {"CDX-C-01": {"处置": "accepted"}})["open_critical"] == ["CDX-C-01"]
    x.write_responses(root, RID, "code", {"CDX-C-01": waive})
    engines_free = review_json([("CDX-C-01", "critical", "轮次重来之后的另一条意见")])
    x.import_round(root, RID, "code", 1, original(tmp_path, "c1b.md", engines_free))
    (root / WS / "audit" / "external" / "code_r2" / "status.json").unlink()  # 第 2 轮作废
    x.collect(root, RID, "code", engine_state="codex_external")
    out = x.write_responses(root, RID, "code")
    assert (out["open_critical"], out["overridden"], out["reset"], out["unruled"]) == (["CDX-C-01"], [], ["CDX-C-01"], ["CDX-C-01"])
    row = response_rows(root, "CDX-C-")["CDX-C-01"]
    assert (cg._row_get(row, "处置"), cg._row_get(row, "回应"), cg._row_get(row, "复核")) == ("", "", "open")  # 旧意见的处置不算在新意见头上
    assert x.write_responses(root, RID, "code")["reset"] == []  # 只作废一次

    with pytest.raises(x.ExtReviewError):
        x.write_responses(root, RID, "code", {"CDX-C-01": {"复核": "done"}})


LEGACY_SUMMARY = """# 代码外审汇总（三轮，主会话手写）

| ID | severity | category | location | description | suggestion |
| --- | --- | --- | --- | --- | --- |
| CDX-C-01 | critical | 前视 | src/a.py:10 | 信号当日生效 | 改为 T+1 |
| CDX-C-02 | major | 参数 | src/a.py:22 | 窗口与规格不符 | 改成 20 |
| CDX-C-03 | minor | 风格 | src/a.py:40 | 魔法数字 | 提成常量 |
| CDX-C-04 | minor | 注释 | src/a.py:55 | 注释与实现不符 | 改注释 |

VERDICT: pass_with_issues
"""

LEGACY_RESPONSES = """# 审计回应总表

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | minor | 页码格式 | accepted | spec.md:12 | pass |
| CDX-C-01 | critical | 信号当日生效 | accepted | a.py:10 已改 T+1 | pass |
| CDX-C-02 | major | 窗口与规格不符 | accepted | a.py:22 | open |
| CDX-C-03 | minor | 魔法数字 | deferred | 留到重构 | - |
| CDX-C-04 | minor | 注释与实现不符 | accepted | a.py:55 | pass（外部增量复核） |
"""


def legacy_case(tmp_path: Path) -> Path:
    root = make_case(tmp_path, external_reviews=[{"checkpoint": "code", "engine": "same_host_fallback", "verdict": "pass_with_issues"}])
    (root / WS / "audit" / "code_audit_codex.md").write_text(LEGACY_SUMMARY, encoding="utf-8")  # 旧文件名
    (root / WS / "audit" / "audit_responses.md").write_text(LEGACY_RESPONSES, encoding="utf-8")
    return root


def test_hand_written_canonical_keeps_its_recheck_column(tmp_path):
    root = legacy_case(tmp_path)
    out = x.write_responses(root, RID, "code", {"CDX-C-02": {"回应": "a.py:22；已核"}})
    assert (out["rows"], out["open_critical"], out["dropped"]) == (4, [], [])
    text = read(root, f"{WS}/audit/audit_responses.md")
    expected = LEGACY_RESPONSES.replace("| a.py:22 |", "| a.py:22；已核 |")
    assert text == expected  # 手工维护的复核（按在列算会变成 open）与手写的摘要都不动，只落了给定的回应
    assert gate(cg.check_code_audit(root, RID))["G-CA-5"].passed

    path = root / WS / "audit" / "audit_responses.md"
    os.utime(path, (1_000_000_000, 1_000_000_000))
    assert x.write_responses(root, RID, "code")["rows"] == 4 and path.stat().st_mtime == 1_000_000_000  # 内容没变就不重写

    # 重新处置的行不再沿用手写的复核
    x.write_responses(root, RID, "code", {"CDX-C-02": {"处置": "rejected", "回应": "口径如此"}, "CDX-C-01": {"处置": "accepted"}})
    rows = response_rows(root, "CDX-C-")
    assert cg._row_get(rows["CDX-C-02"], "复核") == "-" and cg._row_get(rows["CDX-C-01"], "复核") == "open"


def test_legacy_canonical_is_adopted_as_round_zero_before_a_new_round(tmp_path, engines):
    root = legacy_case(tmp_path)
    x.write_responses(root, RID, "code")  # 收编之前内核已经在手写的规范文件上写过回应表：之后不能因此把旧处置判成「换主」
    engines.control(outputs={"main": review_json([("CDX-C-02", "major", "窗口仍与规格不符"), ("CDX-C-05", "major", "新发现：费率没计入")], "pass_with_issues")})
    job = prepare(root, "code", 2)  # 旧案例重开：轮次从 2 续编
    assert job["adopted_legacy"] == "code_r0" and any("第 0 轮" in w for w in job["warnings"])
    assert (job["mode"], job["mode_reason"], job["prev_round"], job["next_finding_no"]) == ("full", "no_baseline", 0, 5)
    prompt = read(root, f"{job['dir']}/prompt_main.md")
    assert "`CDX-C-01`（critical，第 0 轮提出，已闭环）" in prompt and "`CDX-C-02`（major，第 0 轮提出，未闭环）" in prompt and "CDX-C-05" in prompt
    assert read(root, f"{WS}/audit/external/code_r0/output.md") == LEGACY_SUMMARY  # 旧汇总原样存档
    assert x.status(root, RID, "code_r0")["engine_state"] == "same_host_fallback"  # 取自旧台账

    assert run(root, job)["state"] == "success"
    merged = x.collect(root, RID, "code", engine_state="codex_external")
    assert [(f["id"], f["first_round"], f["last_round"], f["open"]) for f in merged["findings"]] == [
        ("CDX-C-01", 0, 0, False),
        ("CDX-C-02", 0, 2, True),
        ("CDX-C-03", 0, 0, False),
        ("CDX-C-04", 0, 0, False),
        ("CDX-C-05", 2, 2, True),
    ]
    out = x.write_responses(root, RID, "code")
    assert (out["rows"], out["dropped"], out["unruled"], out["open_critical"], out["reset"]) == (5, [], ["CDX-C-05"], [], [])
    rows = response_rows(root, "CDX-C-")
    assert [(cg._row_get(rows[i], "处置"), cg._row_get(rows[i], "复核")) for i in sorted(rows)] == [
        ("accepted", "pass"),
        ("accepted", "open"),
        ("deferred", "-"),
        ("accepted", "pass（外部增量复核）"),  # 结论没变，括注保留
        ("", "open"),
    ]
    gates = gate(cg.check_code_audit(root, RID))
    assert gates["G-CA-4"].passed and gates["G-CA-5"].passed  # 行数与并集条数一致，旧意见没有丢
    assert "adopted_legacy" not in prepare(root, "code", 3)  # 只收编一次


def test_skip_does_not_overwrite_a_legacy_canonical(tmp_path):
    root = legacy_case(tmp_path)
    out = x.skip(root, RID, "code", "按审计档位不触发")
    assert (out["rounds"], out["verdict"], out["skipped_round_reason"], out["ledger"]["engine"]) == (1, "pass_with_issues", "按审计档位不触发", "same_host_fallback")
    assert [(f["id"], f["open"]) for f in out["findings"]] == [("CDX-C-01", False), ("CDX-C-02", True), ("CDX-C-03", True), ("CDX-C-04", False)]
    assert x.write_responses(root, RID, "code")["dropped"] == []
    rows = response_rows(root, "CDX-C-")
    assert [cg._row_get(rows[i], "复核") for i in sorted(rows)] == ["pass", "open", "-", "pass（外部增量复核）"]
    assert cg.parse_review(root / out["raw"]).issues == 4 and out["raw"].endswith("code_audit_external.md")

    # 旧流程留下的 skipped 占位没有可保留的成果：照常被新的占位覆盖；零意见的真实结论则保留
    audit = root / WS / "audit"
    (audit / "result_audit_external.md").write_text('{"verdict": "skipped", "findings": []}\n', encoding="utf-8")
    placeholder = x.skip(root, RID, "result", "未触发")
    assert (placeholder["verdict"], placeholder["rounds"], placeholder["ledger"]["engine"]) == ("skipped", 0, "skipped")
    (audit / "spec_audit_external.md").write_text("外审没有发现问题。\n\nVERDICT: pass\n", encoding="utf-8")
    kept = x.skip(root, RID, "spec", "未触发")
    assert (kept["verdict"], kept["rounds"], kept["findings"], kept["unruled_diffs"]) == ("pass", 1, [], [])
    assert "占位" in read(root, f"{WS}/spec/spec_external.md")  # 旧结论里没有盲提取块，也没有现成的盲提取文件
    x.write_responses(root, RID, "spec")
    gates = gate(cg.check_spec_audit(root, RID))
    assert gates["G-SA-1"].passed and gates["G-SA-3"].passed and gates["G-SA-4"].passed


R010 = REPO_ROOT / "workspace" / "r010_breakout_ratio_timing" / "audit"
R010_ROUNDS = ["result_audit_external_round1.md", "result_audit_external_recheck.md", "result_audit_external_recheck3.md"]
R010_FILES = [*R010_ROUNDS, "audit_responses.md"]


@pytest.mark.skipif(not all((R010 / name).is_file() for name in R010_FILES), reason="r010 的真实外审原件不在")
def test_r010_three_result_rounds_merge_into_five_findings(tmp_path):
    root = make_case(tmp_path)
    before = {name: (R010 / name).read_bytes() for name in R010_FILES}
    for round_no, name in enumerate(R010_ROUNDS, 1):
        assert x.import_round(root, RID, "result", round_no, R010 / name)["state"] == "success"
    summary = x.collect(root, RID, "result", engine_state="codex_external")
    assert (summary["rounds"], summary["verdict"], summary["counts"]) == (3, "pass", {"critical": 2, "major": 2, "minor": 1})
    got = [(f["id"], f["severity"], f["first_round"], f["last_round"], f["open"]) for f in summary["findings"]]
    assert got == [
        ("CDX-R-01", "critical", 1, 1, False),
        ("CDX-R-02", "major", 1, 1, False),
        ("CDX-R-03", "major", 1, 1, False),
        ("CDX-R-04", "minor", 1, 2, False),
        ("CDX-R-05", "critical", 2, 2, False),
    ]
    raw = f"{WS}/audit/result_audit_external.md"
    assert summary["ledger"] == {"checkpoint": "result", "engine": "codex_external", "verdict": "pass", "critical": 2, "major": 2, "minor": 1, "raw": raw}
    parsed = cg.parse_review(root / raw)
    assert (parsed.issues, parsed.verdict, parsed.source) == (5, "pass", "json")

    real = {cg._row_id(r, r"^CDX-[A-Z]-"): r for r in cg._parse_audit_responses(R010 / "audit_responses.md", "CDX-R-")}
    rulings = {fid: {"处置": cg._row_get(r, "处置"), "回应": cg._row_get(r, "回应")} for fid, r in real.items()}
    out = x.write_responses(root, RID, "result", rulings)
    assert (out["rows"], out["open_critical"], out["unanswered_major"], out["unruled"]) == (5, [], [], [])
    rows = response_rows(root, "CDX-R-")
    assert list(rows) == [f"CDX-R-0{i}" for i in range(1, 6)]
    assert all(cg._row_get(r, "复核") == "pass" for r in rows.values())
    assert all(cg._row_get(rows[fid], "回应") == cg._row_get(real[fid], "回应") for fid in rows)
    gates = gate(cg.check_result_audit(root, RID))
    assert gates["G-RA-5"].passed and gates["G-RA-2"].passed and gates["G-RA-1"].passed
    assert before == {name: (R010 / name).read_bytes() for name in R010_FILES}  # 真实案例只读


# ---------------------------------------------------------------------------
# 占位、差异裁决表
# ---------------------------------------------------------------------------

EXTRACT_AUDIT = """# 提取审计 extract_audit.md

## 一、覆盖统计

| 项目 | 数量 |
| --- | --- |
| 要素 | 12 |

## 二、遗漏清单

| ID | 检查项 | 严重度 | 页码 | 描述 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| GAP-01 | 遗漏检查 | major | p7 | 漏登记换手率约束 | 补 B3 |
| GAP-02 | 页码核对 | minor | p11-p12 | R2 页码写错 | 订正 |

## 三、复核记录

| ID | 结论 |
| --- | --- |
| GAP-01 | 已补 |
"""


def test_skip_writes_placeholders_that_pass_the_gates(tmp_path):
    root = make_case(tmp_path)
    out = x.skip(root, RID, "spec", "easy 难度未触发外审")
    raw = f"{WS}/audit/spec_audit_external.md"
    assert (out["verdict"], out["findings"], out["rounds"], out["raw"], out["unruled_diffs"]) == ("skipped", [], 0, raw, [])
    assert out["ledger"] == {"checkpoint": "spec", "engine": "skipped", "verdict": "skipped", "critical": 0, "major": 0, "minor": 0, "raw": raw, "reason": "easy 难度未触发外审"}
    parsed = cg.parse_review(root / raw)
    assert (parsed.issues, parsed.verdict) == (0, "skipped")
    assert "占位" in read(root, f"{WS}/spec/spec_external.md") and "| ID | 类别 |" in read(root, f"{WS}/spec/extract_diff.md")
    gates = gate(cg.check_spec_audit(root, RID))
    assert all(gates[g].passed for g in ("G-SA-1", "G-SA-3", "G-SA-4", "G-SA-5", "G-SA-6")), gates

    for kind, ids in (("code", ("G-CA-1", "G-CA-4", "G-CA-5", "G-CA-6")), ("result", ("G-RA-1", "G-RA-2", "G-RA-5"))):
        skipped = x.skip(root, RID, kind, "降级链走到底")
        assert skipped["ledger"]["engine"] == "skipped" and skipped["ledger"]["reason"] == "降级链走到底"
        checks = gate(cg.check_code_audit(root, RID) if kind == "code" else cg.check_result_audit(root, RID))
        assert all(checks[g].passed for g in ids), checks
    assert x.write_responses(root, RID, "code")["rows"] == 0
    with pytest.raises(x.ExtReviewError):
        x.skip(root, RID, "second_opinion", "不适用")


def test_skip_still_asks_for_rulings_on_internal_findings_and_never_overwrites_real_rounds(tmp_path):
    root = make_case(tmp_path)
    (root / WS / "audit" / "extract_audit.md").write_text(EXTRACT_AUDIT, encoding="utf-8")
    out = x.skip(root, RID, "spec", "外审引擎与替身都不可用")
    assert out["unruled_diffs"] == ["DIF-01", "DIF-02"]
    assert not gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed
    x.write_extract_diff(root, RID, {"DIF-01": {"裁决": "adopted", "依据": "p7 确有约束"}, "DIF-02": {"裁决": "corrected"}})
    assert gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed

    x.import_round(root, RID, "code", 1, original(tmp_path, "c1.md", review_json([("CDX-C-01", "major", "问题")])))
    x.collect(root, RID, "code", engine_state="codex_external")
    kept = x.skip(root, RID, "code", "误调用")
    assert (kept["verdict"], kept["rounds"], kept["ledger"]["engine"]) == ("fail", 1, "codex_external")
    assert cg.parse_review(root / kept["raw"]).issues == 1


def spec_original(findings: list[tuple[str, str, str]], diffs: list[dict], verdict: str = "pass_with_issues") -> str:
    return f"{x.BLIND_BEGIN}\n{BLIND}\n{x.BLIND_END}\n\n```json\n{review_json(findings, verdict, diffs=diffs)}\n```\n"


def test_write_extract_diff_projects_rows_and_keeps_rulings(tmp_path):
    root = make_case(tmp_path)
    (root / WS / "audit" / "extract_audit.md").write_text(EXTRACT_AUDIT, encoding="utf-8")
    diffs = [
        {"id": "D-01", "category": "数值不一致", "pages": "p9", "description": "回撤数值", "resolution": "corrected", "basis": "tables_extracted.md:6", "finding_id": "CDX-S-01"},
        {"id": "D-02", "category": "仅盲提取有", "pages": "p4", "description": "盲提取多列了一条", "resolution": "dismissed", "basis": "p4 只是背景介绍", "finding_id": ""},
        {"id": "D-03", "category": "登记粒度", "pages": "p6", "description": "拆分粒度不同", "resolution": "", "basis": "", "finding_id": ""},
    ]
    findings = [("CDX-S-01", "major", "R1 回撤抄成 -26.5%"), ("CDX-S-02", "minor", "图表登记缺表3")]
    x.import_round(root, RID, "spec", 1, original(tmp_path, "s1.md", spec_original(findings, diffs)))
    x.collect(root, RID, "spec", engine_state="codex_external")

    out = x.write_extract_diff(root, RID)
    assert [(r["id"], r["source"], r["ref"], r["裁决"]) for r in out["rows"]] == [
        ("DIF-01", "external_finding", "CDX-S-01", "corrected"),  # 外审第二次调用已经给出结论
        ("DIF-02", "external_finding", "CDX-S-02", ""),
        ("DIF-03", "external_diff", "r1#D-02", "dismissed"),
        ("DIF-04", "external_diff", "r1#D-03", ""),
        ("DIF-05", "internal", "GAP-01", ""),  # 内审只取「遗漏清单」一节，复核记录里重复的编号不算
        ("DIF-06", "internal", "GAP-02", ""),
    ]
    assert out["unruled"] == ["DIF-02", "DIF-04", "DIF-05", "DIF-06"]
    assert out["rows"][0]["页码"] == "p9" and out["rows"][5]["页码"] == "p11-p12"
    assert set(out["rows"][0]) == {"id", "类别", "描述", "页码", "裁决", "依据", "source", "ref"}  # 前六项与表里的列同名
    assert out["rows"][4]["类别"] == "内审 遗漏检查" and out["rows"][4]["描述"] == "漏登记换手率约束"
    path = root / WS / "spec" / "extract_diff.md"
    assert "| ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |" in path.read_text(encoding="utf-8")
    assert not gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed

    rulings = {
        "DIF-02": {"裁决": "adopted", "依据": "p14 确有表3"},
        "DIF-04": {"裁决": "dismissed", "依据": "粒度不同不构成问题"},
        "DIF-5": {"裁决": "adopted"},
        "DIF-06": {"裁决": "corrected", "依据": "以 p12 为准"},
    }
    ruled = x.write_extract_diff(root, RID, rulings)
    assert ruled["unruled"] == [] and [r["裁决"] for r in ruled["rows"]] == ["corrected", "adopted", "dismissed", "dismissed", "adopted", "corrected"]
    assert ruled["rows"][1]["依据"] == "[外审 CDX-S-02] p14 确有表3"
    gates = gate(cg.check_spec_audit(root, RID))
    assert gates["G-SA-1"].passed and gates["G-SA-3"].passed

    snapshot = path.read_text(encoding="utf-8")
    again = x.write_extract_diff(root, RID)  # 没给的保留已有值，文件一个字符都不变
    assert again["rows"] == ruled["rows"] and path.read_text(encoding="utf-8") == snapshot

    path.write_text(snapshot + "| DIF-07 | 人工 | 手写的一行 | p2 | dismissed | 人工核对过 |\n", encoding="utf-8")
    x.import_round(root, RID, "spec", 2, original(tmp_path, "s2.md", review_json([("CDX-S-03", "minor", "新发现的页码问题")], "pass_with_issues")))
    x.collect(root, RID, "spec", engine_state="codex_external")
    grown = x.write_extract_diff(root, RID)
    assert [(r["id"], r["source"], r["裁决"]) for r in grown["rows"]][-2:] == [("DIF-07", "manual", "dismissed"), ("DIF-08", "external_finding", "")]
    assert grown["unruled"] == ["DIF-08"] and [r["裁决"] for r in grown["rows"]][:6] == [r["裁决"] for r in ruled["rows"]]
    assert "| DIF-07 | 人工 | 手写的一行 | p2 | dismissed | 人工核对过 |" in path.read_text(encoding="utf-8")
    assert read(root, f"{WS}/spec/spec_external.md") == BLIND + "\n"

    for bad in ({"DIF-99": {"裁决": "adopted"}}, {"DIF-08": {"裁决": "maybe"}}):
        with pytest.raises(x.ExtReviewError):
            x.write_extract_diff(root, RID, bad)


def test_extract_diff_rows_are_reset_when_their_source_is_replaced(tmp_path):
    root = make_case(tmp_path)
    audit = root / WS / "audit" / "extract_audit.md"
    audit.write_text(EXTRACT_AUDIT, encoding="utf-8")
    x.import_round(root, RID, "spec", 1, original(tmp_path, "s1.md", spec_original([("CDX-S-01", "major", "R1 回撤抄错")], [])))
    x.collect(root, RID, "spec", engine_state="codex_external")
    ruled = x.write_extract_diff(root, RID, {"DIF-01": {"裁决": "corrected", "依据": "以 p9 为准"}, "DIF-02": {"裁决": "adopted"}, "DIF-03": {"裁决": "dismissed"}})
    assert ruled["unruled"] == [] and ruled["reset"] == []

    # 同一条意见在下一轮换了措辞：还是它，裁决保留
    x.import_round(root, RID, "spec", 2, original(tmp_path, "s2.md", review_json([("CDX-S-01", "major", "R1 回撤仍与原表不符（措辞更新）")])))
    x.collect(root, RID, "spec", engine_state="codex_external")
    kept = x.write_extract_diff(root, RID)
    assert kept["reset"] == [] and kept["unruled"] == [] and kept["rows"][0]["裁决"] == "corrected"

    # 第 1 轮重做后 CDX-S-01 是另一条意见，内审 GAP-02 的内容也换了：这两行按新内容重写、旧裁决作废
    (root / WS / "audit" / "external" / "spec_r2" / "status.json").unlink()
    x.import_round(root, RID, "spec", 1, original(tmp_path, "s1b.md", spec_original([("CDX-S-01", "critical", "漏了核心结果表")], [])))
    x.collect(root, RID, "spec", engine_state="codex_external")
    audit.write_text(EXTRACT_AUDIT.replace("R2 页码写错", "SA1 未登记"), encoding="utf-8")
    out = x.write_extract_diff(root, RID)
    rows = {r["id"]: r for r in out["rows"]}
    assert (out["reset"], out["unruled"]) == (["DIF-01", "DIF-03"], ["DIF-01", "DIF-03"])
    assert "漏了核心结果表" in rows["DIF-01"]["描述"] and rows["DIF-01"]["依据"].startswith("[外审 CDX-S-01] critical")
    assert rows["DIF-02"]["裁决"] == "adopted" and "SA1 未登记" in rows["DIF-03"]["描述"]
    assert not gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed
    assert x.write_extract_diff(root, RID, {"DIF-01": {"裁决": "adopted"}, "DIF-03": {"裁决": "adopted"}})["reset"] == []  # 只作废一次
    assert gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed


def test_write_extract_diff_reads_a_hand_written_table_by_its_headers(tmp_path):
    root = make_case(tmp_path)
    path = root / WS / "spec" / "extract_diff.md"
    path.write_text(
        "# 差异裁决\n\n| ID | 页码 | 类别 | 差异描述 | 裁决 | 依据 |\n| --- | --- | --- | --- | --- | --- |\n| DIF-01 | p3 | 口径 | 手写的差异 |  | 待定 |\n",
        encoding="utf-8",
    )
    out = x.write_extract_diff(root, RID)
    row = out["rows"][0]
    assert (row["类别"], row["描述"], row["页码"], row["裁决"], row["source"]) == ("口径", "手写的差异", "p3", "", "manual")
    assert out["unruled"] == ["DIF-01"]
    x.write_extract_diff(root, RID, {"DIF-01": {"裁决": "dismissed", "依据": "核对过原文"}})
    assert "| DIF-01 | p3 | 口径 | 手写的差异 | dismissed | 核对过原文 |" in path.read_text(encoding="utf-8")
    assert gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed


def test_write_extract_diff_keeps_a_legacy_header_that_looks_like_a_row(tmp_path):
    root = make_case(tmp_path)
    path = root / WS / "spec" / "extract_diff.md"
    legacy = (
        "# extract_diff\n\n"
        "| DIF-01 | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |\n"  # 旧执行卡规定的表头，首格就是 DIF-01
        "| --- | --- | --- | --- | --- | --- |\n"
        "| DIF-01 | B | 绩效指标口径 | p33 |  | 待核 |\n"
        "| DIF-02 | B | 费率未说明 | 全文 | dismissed | B4 已覆盖 |\n"
        "\n表外的一行：| DIF-09 | 不在表里 |\n"
    )
    path.write_text(legacy, encoding="utf-8")
    out = x.write_extract_diff(root, RID)
    assert [(r["id"], r["类别"], r["裁决"], r["source"]) for r in out["rows"]] == [("DIF-01", "B", "", "manual"), ("DIF-02", "B", "dismissed", "manual")]
    assert out["unruled"] == ["DIF-01"] and path.read_text(encoding="utf-8") == legacy
    x.write_extract_diff(root, RID, {"DIF-01": {"裁决": "dismissed", "依据": "口径一致"}})
    text = path.read_text(encoding="utf-8")
    assert text.splitlines()[2] == legacy.splitlines()[2]  # 表头没有被当成 DIF-01 改写
    assert "| DIF-01 | B | 绩效指标口径 | p33 | dismissed | 口径一致 |" in text
    assert gate(cg.check_spec_audit(root, RID))["G-SA-3"].passed

    # 手写的行在文字里点到了意见编号：这些意见不再另起一行，没被点到的照常补行
    path.write_text(text.replace("B4 已覆盖", "CDX-S-01、GAP-01 一致确认，B4 已覆盖"), encoding="utf-8")
    (root / WS / "audit" / "extract_audit.md").write_text(EXTRACT_AUDIT, encoding="utf-8")
    x.import_round(root, RID, "spec", 1, original(tmp_path, "s1.md", spec_original([("CDX-S-01", "major", "费率"), ("CDX-S-12", "minor", "页码")], [])))
    x.collect(root, RID, "spec", engine_state="codex_external")
    grown = x.write_extract_diff(root, RID)
    assert [(r["id"], r["source"], r["ref"]) for r in grown["rows"]] == [
        ("DIF-01", "manual", ""),
        ("DIF-02", "manual", ""),
        ("DIF-03", "external_finding", "CDX-S-12"),  # CDX-S-01 已被手写行点到；CDX-S-12 不会因为含有 CDX-S-1 的字样而被当成点到
        ("DIF-04", "internal", "GAP-02"),
    ]


def test_write_extract_diff_without_any_source_writes_header_only(tmp_path):
    root = make_case(tmp_path)
    out = x.write_extract_diff(root, RID)  # 没有外审规范文件，也没有内审文件
    assert out["rows"] == [] and out["unruled"] == []
    text = read(root, f"{WS}/spec/extract_diff.md")
    assert text.count("| ID | 类别 |") == 1
    x.import_round(root, RID, "spec", 1, original(tmp_path, "s1.md", spec_original([("CDX-S-01", "major", "漏了一张表")], [])))
    x.collect(root, RID, "spec", engine_state="codex_external")
    assert [r["id"] for r in x.write_extract_diff(root, RID)["rows"]] == ["DIF-01"]
    assert read(root, f"{WS}/spec/extract_diff.md").count("| ID | 类别 |") == 1  # 接在已有表头下面，不另起一张表


# ---------------------------------------------------------------------------
# 同宿主替身
# ---------------------------------------------------------------------------


def test_fallback_for_a_failed_code_review(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(default={"mode": "quota"})
    job = prepare(root, "code")
    assert run(root, job)["reason"] == "quota_error"
    task = x.fallback_task(root, RID, job["job_id"])
    assert task == {"prompt_file": f"{job['dir']}/prompt_fallback.md", "output": f"{job['dir']}/output_fallback.md"}
    prompt = read(root, task["prompt_file"])
    assert f"{job['dir']}/prompt_main.md" in prompt and f"{job['dir']}/input_main.md" in prompt and task["output"] in prompt
    assert "audit_responses.md" in prompt and "不派发子代理" in prompt and f"{WS}/flow/" in prompt and not leftover(prompt)

    with pytest.raises(x.ExtReviewError):
        x.accept_fallback(root, RID, job["job_id"])  # 替身还没交
    (root / task["output"]).write_text("替身没有按格式写", encoding="utf-8")
    with pytest.raises(x.ExtReviewError):
        x.accept_fallback(root, RID, job["job_id"])
    assert x.status(root, RID, job["job_id"])["state"] == "failed"

    (root / task["output"]).write_text("```json\n" + review_json([("CDX-C-01", "major", "替身发现的问题")]) + "\n```\n", encoding="utf-8")
    accepted = x.accept_fallback(root, RID, job["job_id"])
    assert (accepted["state"], accepted["reason"], accepted["engine_state"], accepted["fallback_of"]) == ("success", None, "same_host_fallback", "quota_error")
    summary = x.collect(root, RID, "code", engine_state="same_host_fallback")
    assert summary["ledger"]["engine"] == "same_host_fallback" and summary["counts"] == {"critical": 0, "major": 1, "minor": 0}
    assert json.loads(read(root, summary["raw"]))["rounds"][0]["engine_state"] == "same_host_fallback"
    with pytest.raises(x.ExtReviewError):
        x.collect(root, RID, "code", engine_state="gemini_external")


def test_fallback_for_spec_reuses_a_finished_blind_call(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(plan=[{}, {"mode": "quota"}], outputs={"blind": BLIND})
    job = prepare(root, "spec")
    assert run(root, job)["completed_calls"] == ["blind"]
    task = x.fallback_task(root, RID, job["job_id"])
    prompt = read(root, task["prompt_file"])
    assert "盲提取已经由外部审查引擎完成" in prompt and f"{job['dir']}/prompt_review.md" in prompt and f"{job['dir']}/input_review.md" in prompt
    pack = read(root, f"{job['dir']}/input_review.md")
    assert BLIND in pack and "SPEC_ONLY_MARKER" in pack

    (root / task["output"]).write_text(review_json([("CDX-S-01", "minor", "页码格式")], "pass_with_issues"), encoding="utf-8")
    accepted = x.accept_fallback(root, RID, job["job_id"])
    assert accepted["state"] == "success" and accepted["engine_state"] == "same_host_fallback"
    assert x.accept_fallback(root, RID, job["job_id"])["state"] == "success"  # 重复点收不出错
    text = read(root, accepted["output"])
    assert x.split_blind_block(text) == BLIND and cg.parse_review(root / accepted["output"]).issues == 1
    x.collect(root, RID, "spec", engine_state="same_host_fallback")
    assert read(root, f"{WS}/spec/spec_external.md") == BLIND + "\n"


def test_fallback_for_spec_does_both_steps_when_blind_call_failed(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(default={"mode": "auth"})
    job = prepare(root, "spec")
    assert run(root, job)["reason"] == "auth_error"
    task = x.fallback_task(root, RID, job["job_id"])
    prompt = read(root, task["prompt_file"])
    for needle in ("prompt_blind.md", "input_blind.md", "prompt_review.md", "input_fallback_review.md", x.BLIND_BEGIN, x.BLIND_END, "不得打开"):
        assert needle in prompt
    assert "SPEC_ONLY_MARKER" in read(root, f"{job['dir']}/input_fallback_review.md")

    conclusion = review_json([], "pass")
    (root / task["output"]).write_text(conclusion, encoding="utf-8")
    with pytest.raises(x.ExtReviewError):
        x.accept_fallback(root, RID, job["job_id"])  # 缺盲提取块
    (root / task["output"]).write_text(f"{x.BLIND_BEGIN}\n替身的盲提取 | F | p5 | x\n{x.BLIND_END}\n\n{conclusion}\n", encoding="utf-8")
    accepted = x.accept_fallback(root, RID, job["job_id"])
    assert accepted["state"] == "success" and accepted["fallback_of"] == "auth_error"
    x.collect(root, RID, "spec", engine_state="same_host_fallback")
    assert read(root, f"{WS}/spec/spec_external.md") == "替身的盲提取 | F | p5 | x\n"


def test_fallback_is_refused_for_a_job_the_engine_finished(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"main": review_json([("CDX-C-01", "major", "外审引擎发现的问题")])})
    job = prepare(root, "code")
    assert run(root, job)["state"] == "success"
    with pytest.raises(x.ExtReviewError):
        x.fallback_task(root, RID, job["job_id"])
    (root / job["dir"] / "output_fallback.md").write_text(review_json([], "pass"), encoding="utf-8")
    with pytest.raises(x.ExtReviewError):
        x.accept_fallback(root, RID, job["job_id"])  # 外审引擎的结论不会被替身的覆盖
    assert cg.parse_review(root / job["dir"] / "output.md").issues == 1
    assert x.status(root, RID, job["job_id"])["engine_state"] == "codex_external"

    with pytest.raises(x.ExtReviewError):
        x.fallback_task(root, RID, None)  # 准备阶段没成功时没有 job，报本模块自己的错
    x.import_round(root, RID, "result", 1, original(tmp_path, "r1.md", review_json([], "pass")), engine_state="same_host_fallback")
    with pytest.raises(x.ExtReviewError):
        x.fallback_task(root, RID, "result_r1")  # 导入的原件没有可以改派的调用


def test_fallback_without_launch_and_for_second_opinion(tmp_path, engines):
    root = make_case(tmp_path, iteration={"current": 2, "max": 3})
    job = prepare(root, "result")  # 没启动过外审引擎，直接改派替身
    task = x.fallback_task(root, RID, job["job_id"])
    (root / task["output"]).write_text(review_json([("CDX-R-01", "minor", "结论措辞过度")], "pass_with_issues"), encoding="utf-8")
    accepted = x.accept_fallback(root, RID, job["job_id"])
    assert (accepted["state"], accepted["engine_state"], accepted["fallback_of"], accepted["attempts"]) == ("success", "same_host_fallback", None, [])
    assert x.launch(root, RID, job["job_id"]).get("already_done") is True and engines.calls() == []  # 点收之后不会再把外审引擎拉起来
    assert x.collect(root, RID, "result", engine_state="same_host_fallback")["counts"]["minor"] == 1

    iteration = root / WS / "iterations" / "iter_02"
    iteration.mkdir(parents=True)
    (iteration / "comparison.json").write_text(json.dumps(COMPARISON, ensure_ascii=False), encoding="utf-8")
    engines.control(default={"mode": "quota"})
    second = prepare(root, "second_opinion", iteration=2)
    assert run(root, second)["reason"] == "quota_error" and not (iteration / "second_opinion_external.md").exists()
    task = x.fallback_task(root, RID, second["job_id"])
    assert task == {"prompt_file": f"{second['dir']}/prompt_fallback.md", "output": f"{second['dir']}/output_fallback.md"}
    prompt = read(root, task["prompt_file"])
    assert f"{second['dir']}/prompt_main.md" in prompt and f"{second['dir']}/input_main.md" in prompt and "输出契约" in prompt
    assert "findings" not in prompt and not leftover(prompt)  # 第二意见是自由文本，不要求结论 JSON
    (root / task["output"]).write_text("## 第二意见\n\n替身的判断：先核对信号滞后。", encoding="utf-8")
    accepted = x.accept_fallback(root, RID, second["job_id"])
    assert (accepted["state"], accepted["engine_state"], accepted["fallback_of"]) == ("success", "same_host_fallback", "quota_error")
    assert read(root, f"{WS}/iterations/iter_02/second_opinion_external.md") == "## 第二意见\n\n替身的判断：先核对信号滞后。\n"
    assert x.collect(root, RID, "second_opinion", engine_state="same_host_fallback")["raw"] == f"{WS}/iterations/iter_02/second_opinion_external.md"


# ---------------------------------------------------------------------------
# 第二意见、另一个引擎
# ---------------------------------------------------------------------------


def test_second_opinion_job_layout_and_copies(tmp_path, engines):
    root = make_case(tmp_path, iteration={"current": 2, "max": 3})
    iterations = root / WS / "iterations"
    for rel, text in {
        "iter_01/diagnosis.md": "# 第 1 轮诊断\n\nDIAG1_MARKER\n",
        "iter_02/comparison.json": json.dumps(COMPARISON, ensure_ascii=False),
        "iteration_log.md": "# 迭代记录\n\nLOG_MARKER\n",
    }.items():
        (iterations / rel).parent.mkdir(parents=True, exist_ok=True)
        (iterations / rel).write_text(text, encoding="utf-8")
    (root / "templates").mkdir()
    (root / "templates" / "standards.json").write_text((REPO_ROOT / "templates" / "standards.json").read_text(encoding="utf-8"), encoding="utf-8")
    opinion = "## 第二意见\n\n判断：归因方向不对，先查信号滞后。"
    engines.control(outputs={"main": opinion})

    job = prepare(root, "second_opinion", iteration=2, extra={"trigger_reason": "连续两轮无改善", "notes": "重点看 AS1"})
    assert (job["job_id"], job["dir"], job["iteration"]) == ("second_opinion_i02", f"{WS}/iterations/iter_02/external", 2)
    assert job["calls"][0]["schema"] is None
    prompt, pack = read(root, f"{job['dir']}/prompt_main.md"), read(root, f"{job['dir']}/input_main.md")
    assert not leftover(prompt) and "连续两轮无改善" in prompt and "重点看 AS1" in prompt
    assert f"{WS}/iterations/iter_02/comparison.json" in prompt and f"{WS}/iterations/iter_01/diagnosis.md" in prompt
    assert "sharpe：研报 0.87 / 复现 0.52" in prompt and "annual_return：" not in prompt  # 未收敛指标按 standards.json 重算
    assert "DIAG1_MARKER" in pack and "LOG_MARKER" in pack and f"<<<FILE src/{RID}/strategy.py" in pack
    assert prompt.endswith(read(root, f"{WS}/iterations/iter_02/external_prompt_second_opinion.md"))

    result = run(root, job)
    assert result["state"] == "success" and "--output-schema" not in engines.calls()[0]["argv"]
    assert read(root, f"{WS}/iterations/iter_02/second_opinion_external.md") == opinion + "\n"
    summary = x.collect(root, RID, "second_opinion", engine_state="codex_external")
    assert summary["ledger"] is None and summary["findings"] == [] and summary["rounds"] == 1
    assert summary["raw"] == f"{WS}/iterations/iter_02/second_opinion_external.md"
    assert not (root / WS / "audit" / "second_opinion_audit_external.md").exists()  # 第二意见不合并、不入台账


def test_claude_engine_for_a_codex_host(tmp_path, engines):
    root = make_case(tmp_path)
    engines.control(outputs={"main": review_json([("CDX-R-01", "minor", "结论措辞过度")], "pass_with_issues")})
    config = {"external_review": {"model": {"claude": "opus"}, "effort_first": "ultra"}}
    job = prepare(root, "result", engine="claude", host="codex", config=config)
    assert (job["engine_state"], job["calls"][0]["effort"], job["budget_bytes"], job["model"]) == ("claude_external", "max", 200 * 1024, "opus")
    assert "引擎" not in leftover(read(root, f"{job['dir']}/prompt_main.md"))
    result = run(root, job)
    assert (result["state"], result["engine"]) == ("success", "claude")
    argv = engines.calls()[0]["argv"]
    assert argv[argv.index("--effort") + 1] == "max" and argv[argv.index("--model") + 1] == "opus"
    assert "--json-schema" in argv and argv[argv.index("--tools") + 1] == "Read,Glob,Grep"
    usage = result["usage"]
    assert (usage["source"], usage["uncached_input"], usage["cache_read"], usage["output"]) == ("claude_envelope", 100, 30000, 400)
    assert usage["read_commands"] is None and result["subsessions"] is None  # Claude 这边取不到的如实记 None
    assert cg.parse_review(root / result["output"]).issues == 1
    assert x.collect(root, RID, "result", engine_state="claude_external")["ledger"]["engine"] == "claude_external"
