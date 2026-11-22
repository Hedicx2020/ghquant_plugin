"""异构外审引擎：三个审查点（spec / code / result）与迭代期第二意见共用。

一个 job 是「某个审查点的某一轮」。内核按下面的顺序调用：

    prepare → launch（后台）→ status（轮询）→ collect → write_responses / write_extract_diff
                                └ 失败时：fallback_task → 宿主派替身 → accept_fallback，再不行 skip

本模块只写外审相关的文件，不写 state.json、不写 events.jsonl；台账条目由 collect / skip
的返回值给出，由内核入账。

一、对 r010 实测问题的五项对策（设计文档 4.11）
  1. 输入包随提示词送入：所需文件带行号的全文，code 另附 R 类数值字面量在 src/ 的命中
     清单与 common/ 公共函数签名。按引擎设字节预算，超出的按优先级改为只列路径和行数。
  2. 推理强度显式指定：整体审查用 effort_first（默认 high），差量复审用 effort_recheck
     （默认 medium）。
  3. 关闭多代理：由 tools/external_review.py 在命令里关掉；事后从外审引擎自己的会话记录
     核对子会话数。
  4. 差量复审：第二轮起只给「上一轮意见与回应 + 上一轮输入与当前文件的差异」。改动面超过
     阈值、拿不到上一轮的输入快照、或 force_full=True 时整体重审。
  5. 超时：降一档推理强度、原输入重试一次，仍超时即以 failed / timeout 结束。额度、鉴权、
     引擎缺失不重试；failed / empty_output 原输入重试一次（进程失败后的重试不带输出约束，
     防止约束本身被引擎拒绝；结论解析不出来的重试仍带）。任何情况下都不缩减输入。

二、盲提取拆成两次调用（kind="spec" 的整体审查）
  blind：输入包只有 report_text.md 与 tables_extracted.md，提示词不出现规格书的路径；
  review：这时才给 spec.md、coverage_matrix.md、ambiguities.md 与 blind 的产出。review 的
  输入包在 blind 跑完之后才落盘。两次的输出拼成一个原件：盲提取块用 SPEC_CODEX 标记行
  包住，后面跟含 findings 的结论 JSON，门禁解析不变。

三、目录结构
  workspace/<id>/audit/external/<kind>_r<轮次>/      job_id = spec_r1 / code_r2 / result_r3
  workspace/<id>/iterations/iter_NN/external/        job_id = second_opinion_iNN
      job.json            job 描述（引擎、模式、各次调用、输入清单）
      prompt_<调用>.md     渲染好的提示词（调用名：main；spec 整体审查为 blind、review）
      input_<调用>.md      输入包（整体审查）或差量复审包
      schema_<调用>.json   输出约束
      output_<调用>.md     各次调用的原件
      output.md           这一轮的原件（多次调用时由它们拼成）
      baseline.json.gz    这一轮所见文件的快照，下一轮据此算差异
      status.json         运行状态
      stdout.log          后台进程与外审引擎的输出
      prompt_fallback.md / output_fallback.md   同宿主替身的任务与交回
  workspace/<id>/audit/external/_superseded/         轮次计数被回拨时，编号更大的旧轮次挪到这里，不再参与合并
  workspace/<id>/audit/external/responses_meta.json  回应表的底账：每行对应哪条意见、人工给定的复核结论
  workspace/<id>/audit/<kind>_audit_external.md      规范文件：各轮意见的并集
  workspace/<id>/audit/external_prompt_<kind>.md     首轮提示词的副本（沿用旧文件名）
  workspace/<id>/spec/spec_external.md               盲提取块
  workspace/<id>/spec/extract_diff.md                差异裁决表
  workspace/<id>/audit/audit_responses.md            回应表

四、规范文件格式
  整份是一个 JSON 对象：checkpoint、verdict（最新一轮的结论）、format、engine_state、
  summary、counts、rounds（各轮的引擎、模式、结论、在列的意见编号）、dimensions_checked
  （最新一轮）、diffs（spec 第二次调用给出的差异）、findings（并集）。每条意见带稳定编号
  CDX-S/C/R-NN、title、first_round、last_round、open（最新一轮是否仍在列）；多轮出现过的
  意见另带 history。

五、.reproduce.json 的 external_review 段（都可省略；engine 键由内核读取，这里不用）
  {
    "timeout_seconds": 1800,                       每次调用的时限
    "effort_first": "high",                        整体审查的推理强度
    "effort_recheck": "medium",                    差量复审的推理强度
    "model": null | "名字" | {"codex": …, "claude": …},   不给则用引擎自己的默认模型
    "input_budget_kb": 320 | {"codex": 320, "claude": 200},  提示词加输入包的字节预算
    "delta_max_changed_ratio": 0.3,                改动面超过它就整体重审
    "output_schema": true,                         是否用 JSON Schema 约束结论的输出
    "checkpoints": {"spec": {…}, "code": {…}, "result": {…}, "second_opinion": {…}}
  }                                                checkpoints 里按审查点覆盖上面任意一项

六、旧案例与手写的规范文件
  规范文件不是本模块生成的（旧案例里主会话手写的多轮汇总，或执行卡驱动的阶段里宿主写的），
  prepare / skip 会先把它原样收编为第 0 轮（job_id 如 code_r0），意见编号沿用，新一轮接着
  往后编；其中哪些意见已经闭环，按回应表里手工维护的「复核」列认。要逐轮保留旧原件时改用
  import_round 逐轮导入（r010 的三轮结果外审即如此）。

七、prepare 的 extra 参数
  已知占位符名（如 trigger_reason、failing_metrics_summary、market）→ 覆盖自动取值；
  notes：追加到提示词末尾的本案例说明；files：额外放进输入包的文件（相对工作区根）。
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from tools import check_gates as cg
from tools import external_review as er
from tools import state as st

from . import mdslice as ms
from . import packs, usage

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

KINDS = ("spec", "code", "result", "second_opinion")
REVIEW_KINDS = ("spec", "code", "result")
ID_LETTER = {"spec": "S", "code": "C", "result": "R"}
ENGINE_STATES = ("codex_external", "claude_external", "same_host_fallback", "skipped")
SEVERITIES = ("critical", "major", "minor")
VERDICTS = ("pass", "pass_with_issues", "fail")
DISPOSITIONS = ("accepted", "rejected", "deferred")
DIFF_RULINGS = ("adopted", "dismissed", "corrected")
NO_RETRY = ("quota_error", "auth_error", "unavailable")

JOB_FORMAT = "extreview-job v1"
CANONICAL_FORMAT = "extreview-canonical v1"
BLIND_BEGIN = "=== SPEC_CODEX_BEGIN ==="
BLIND_END = "=== SPEC_CODEX_END ==="
SKIP_NOTE = "（本审查点的外审未执行，本文件是占位）"

SEED_DIR = "templates/codex_prompts"
SEED_NAMES = {
    "spec": "spec_audit.md",
    "code": "code_audit.md",
    "result": "result_audit.md",
    "second_opinion": "second_opinion.md",
}
# 各引擎认得的推理强度，由低到高；超时降档时不低于 low
EFFORT_LADDER = {
    "codex": ("minimal", "low", "medium", "high", "xhigh", "ultra"),
    "claude": ("low", "medium", "high", "xhigh", "max"),
}
EFFORT_ALIASES = {"codex": {"max": "ultra"}, "claude": {"minimal": "low", "ultra": "max"}}
# 提示词加输入包的字节预算。实测口径：r010 的代码审查 288KB 的输入包，Codex 侧上下文峰值约 15.6 万 token，
# 即中文文书加代码大约 2 字节一个 token。预算要给审查方自己的推理和读文件留出余量：超出窗口整次调用作废
# （再走降级链、评级封顶），而放不进包的文件只是改为列路径、审查方按需自己读，所以宁小勿大。
# 默认按「输入包不超过约 16 万 / 10 万 token」取值；引擎的窗口更大时在 .reproduce.json 的
# external_review.input_budget_kb 里调高。
DEFAULT_BUDGET_KB = {"codex": 320, "claude": 200}
DEFAULTS: dict[str, Any] = {
    "timeout_seconds": 1800,
    "effort_first": "high",
    "effort_recheck": "medium",
    "model": None,
    "delta_max_changed_ratio": 0.3,
    "output_schema": True,
}
HOST_FAMILY = {"claude_code": "claude", "codex": "codex"}

# 模板里可能出现的占位符；渲染后其中任何一个还留在文中就报错。不在这张表里的花括号内容
# （JSON 示例、`iter_{N-1}` 这类说明文字）原样保留。
KNOWN_PLACEHOLDERS = frozenset(
    {
        # 种子模板（templates/codex_prompts/）
        "report_id", "workspace", "market", "type_hint", "difficulty", "type", "tags",
        "common_signatures_path", "r_class_values_list", "comparison_path",
        "iteration_current", "iteration_max", "trigger_reason", "failing_metrics_summary",
        "iteration_history_paths", "NN",
        # 插件根的模板（tools/flowlib/prompts/）
        "pack_note", "pack_summary", "next_finding_id", "checkpoint", "round", "prev_round",
        "open_findings_count", "example_old_id", "severity_rules", "previous_findings_brief",
        "job_id", "output_path", "steps_block", "format_block",
        # 尖括号形式
        "EXTERNAL_ENGINE", "EXTERNAL_ENGINE_STATE",
    }
)
_TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}|<(EXTERNAL_ENGINE(?:_STATE)?)>")
_BODY_MARK_RE = re.compile(r"^=====\s*传给.{0,24}正文开始\s*=====[ \t]*$", re.MULTILINE)

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sql", ".sh"}
MAX_FILE_BYTES = 2_000_000  # 单个文件超过它就不读进输入包，只列路径
PROMPT_RESERVE_BYTES = 2_048  # 提示词末尾「关于输入包」那段话的余量
PACK_HEAD_BYTES = 400  # 输入包包头（标题、说明、清单表表头）的估计大小
PACK_ROW_BYTES = 110  # 清单表每行除路径外的估计大小
LITERAL_HITS_PER_FILE = 12  # R 类字面量命中清单里每个文件逐条列出的上限
DIFF_CONTEXT_LINES = 5
DIFF_MAX_LINES = 20_000  # 行数超过它的文件不做逐行比对，按整份改动计
RUNNER_GRACE_SECONDS = 60.0  # 已登记启动、进程号还没写进来时，这么久之内算作在启动
LOCK_STALE_SECONDS = 60.0

_CHILDREN: dict[int, subprocess.Popen] = {}  # 本进程启动的后台 job，用来判断它们是否还在


class ExtReviewError(ValueError):
    """外审模块的输入或当前状态不允许这个操作。"""


class PromptError(ExtReviewError):
    """提示词模板渲染后仍有未填充的占位符。"""


# ---------------------------------------------------------------------------
# 路径、读写、时间
# ---------------------------------------------------------------------------


def _ws(report_id: str) -> str:
    return f"workspace/{report_id}"


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_text(path: Path, text: str) -> None:
    er._write_atomic(path, text)


def _write_json(path: Path, data: Any) -> None:
    er._write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _write_if_changed(path: Path, text: str) -> None:
    """内容没变就不落盘：回应表、差异裁决表会被反复重写，不让修改时间无谓地跳动。"""
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return
    except (OSError, UnicodeDecodeError):
        pass
    _write_text(path, text)


def _nbytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _line_count(text: str) -> int:
    return len(text.splitlines())


def job_id_for(kind: str, round_no: int, iteration: Optional[int] = None) -> str:
    """spec_r1 / code_r2 / result_r3；第二意见按迭代轮次编号：second_opinion_i02。"""
    if kind == "second_opinion":
        if not iteration or iteration < 1:
            raise ExtReviewError("second_opinion 需要迭代轮次（iteration >= 1）")
        return f"second_opinion_i{iteration:02d}"
    return f"{kind}_r{round_no}"


def parse_job_id(job_id: str) -> tuple[str, int]:
    """返回（审查点, 轮次或迭代轮次）。"""
    if not isinstance(job_id, str):
        raise ExtReviewError(f"无法识别的外审 job 编号: {job_id!r}（准备阶段没有成功时没有 job 可用）")
    m = re.fullmatch(r"(spec|code|result)_r(\d+)", job_id)
    if m:
        return m.group(1), int(m.group(2))
    m = re.fullmatch(r"second_opinion_i(\d+)", job_id)
    if m:
        return "second_opinion", int(m.group(1))
    raise ExtReviewError(f"无法识别的外审 job 编号: {job_id}")


def job_dir(root: Path, report_id: str, job_id: str) -> Path:
    kind, number = parse_job_id(job_id)
    base = Path(root) / "workspace" / report_id
    if kind == "second_opinion":
        return base / "iterations" / f"iter_{number:02d}" / "external"
    return base / "audit" / "external" / job_id


def canonical_path(root: Path, report_id: str, kind: str) -> Path:
    return Path(root) / "workspace" / report_id / "audit" / f"{kind}_audit_external.md"


def _iter_dir(root: Path, report_id: str, iteration: int) -> Path:
    return Path(root) / "workspace" / report_id / "iterations" / f"iter_{iteration:02d}"


def _load_state(root: Path, report_id: str) -> dict[str, Any]:
    try:
        state = st.load_state(Path(root), report_id)
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def settings(config: Optional[dict], kind: str, engine: str) -> dict[str, Any]:
    """这个审查点、这个引擎实际生效的外审参数（checkpoints.<审查点> 覆盖段内同名键）。"""
    section = (config or {}).get("external_review")
    section = section if isinstance(section, dict) else {}
    per = (section.get("checkpoints") or {}).get(kind) if isinstance(section.get("checkpoints"), dict) else None
    per = per if isinstance(per, dict) else {}

    def pick(key: str) -> Any:
        if per.get(key) is not None:
            return per[key]
        if section.get(key) is not None:
            return section[key]
        return DEFAULTS.get(key)

    def number(key: str, low: float, high: Optional[float] = None, inclusive: bool = False) -> float:
        value = pick(key)
        too_low = isinstance(value, (int, float)) and (value < low if inclusive else value <= low)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or too_low or (high is not None and value > high):
            raise ExtReviewError(f"external_review.{key} 取值不合法: {value!r}")
        return value

    budget = pick("input_budget_kb")
    if isinstance(budget, dict):
        budget = budget.get(engine)
    if budget is None:
        budget = DEFAULT_BUDGET_KB[engine]
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        raise ExtReviewError(f"external_review.input_budget_kb 取值不合法: {budget!r}")
    model = pick("model")
    if isinstance(model, dict):
        model = model.get(engine)
    if model is not None and not (isinstance(model, str) and model.strip()):
        raise ExtReviewError(f"external_review.model 取值不合法: {model!r}")
    return {
        "timeout_seconds": number("timeout_seconds", 0),
        "effort_first": normalize_effort(engine, pick("effort_first")),
        "effort_recheck": normalize_effort(engine, pick("effort_recheck")),
        "model": model.strip() if isinstance(model, str) else None,
        "budget_bytes": int(budget * 1024),
        "delta_max_changed_ratio": float(number("delta_max_changed_ratio", 0, 1, inclusive=True)),  # 0 = 有改动就整体重审
        "output_schema": bool(pick("output_schema")),
    }


def normalize_effort(engine: str, effort: Any) -> str:
    """把推理强度换成这个引擎认得的写法；认不出来就报错，不带着错的值去调用。"""
    value = str(effort or "").strip().lower()
    ladder = EFFORT_LADDER[engine]
    value = EFFORT_ALIASES[engine].get(value, value)
    if value not in ladder:
        raise ExtReviewError(f"推理强度 {effort!r} 不在 {engine} 支持的范围内: {ladder}")
    return value


def downgrade_effort(engine: str, effort: str) -> str:
    """降一档（high → medium → low）；已经是 low 或更低时不再降。"""
    ladder = EFFORT_LADDER[engine]
    floor = ladder.index("low")
    index = ladder.index(effort) if effort in ladder else floor
    return ladder[index - 1] if index > floor else effort


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------


def strip_template_header(text: str) -> str:
    """种子模板在「正文开始」标记之前是给人看的说明，发给外审引擎的只有标记之后的部分。"""
    m = _BODY_MARK_RE.search(text)
    return text[m.end():].lstrip("\n") if m else text


def render(text: str, values: dict[str, Any]) -> str:
    """填充占位符。只扫模板一遍，填进去的值不会被当作模板再扫；已知占位符没有取值即报错。"""
    missing: list[str] = []

    def replace(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if values.get(name) is not None:
            return str(values[name])
        if name in KNOWN_PLACEHOLDERS:
            missing.append(m.group(0))
        return m.group(0)

    out = _TOKEN_RE.sub(replace, text)
    if missing:
        raise PromptError(f"提示词模板仍有未填充的占位符: {sorted(set(missing))}")
    return out


def _plugin_template(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _seed_template(root: Path, kind: str) -> str:
    """种子模板先取工作目录里的（可能是用户改过的旧版），没有再取插件自带的。"""
    for base in (Path(root), PLUGIN_ROOT):
        path = base / SEED_DIR / SEED_NAMES[kind]
        if path.is_file():
            return strip_template_header(path.read_text(encoding="utf-8"))
    raise ExtReviewError(f"找不到外审提示词模板: {SEED_DIR}/{SEED_NAMES[kind]}")


def _severity_rules(root: Path, kind: str, values: dict[str, Any]) -> str:
    """差量复审沿用该审查点种子模板里的 severity 判据一节；取不到时给通用口径。"""
    try:
        seed = _seed_template(root, kind)
        for section in ms.sections(seed):
            if section.level == 1 and section.title.lower().startswith("severity"):
                body = section.text.split("\n", 1)[1] if "\n" in section.text else ""
                if body.strip():
                    return render(body.strip(), values)
    except (ExtReviewError, OSError):
        pass
    return (
        "- **critical**：会让复现结论失真的问题（数字与原始产物不符、未来函数、核心要素遗漏等）。\n"
        "- **major**：必须回应的实质性问题。\n"
        "- **minor**：登记即可的次要问题。"
    )


# ---------------------------------------------------------------------------
# 案例信息
# ---------------------------------------------------------------------------


def _spec_frontmatter(root: Path, report_id: str) -> dict[str, Any]:
    path = Path(root) / _ws(report_id) / "spec" / "spec.md"
    if not path.is_file():
        return {}
    data, _body = cg.parse_frontmatter(_read_text(path))
    return data or {}


def _base_values(root: Path, report_id: str, engine: str, state: dict[str, Any]) -> dict[str, Any]:
    fm = _spec_frontmatter(root, report_id)
    iteration = state.get("iteration") if isinstance(state.get("iteration"), dict) else {}
    tags = [str(t) for t in state.get("tags") or [] if str(t).strip()]
    current = iteration.get("current")
    return {
        "report_id": report_id,
        "workspace": _ws(report_id),
        "difficulty": state.get("difficulty") or "medium",
        "type": state.get("type") or fm.get("type_hint") or "未定",
        "tags": "、".join(tags) if tags else "无",
        "market": fm.get("market") or "未注明",
        "type_hint": fm.get("type_hint") or state.get("type") or "未注明",
        "iteration_current": current if current is not None else 0,
        "iteration_max": iteration.get("max") or state.get("max_iter") or "未设定",
        "EXTERNAL_ENGINE": engine,
        "EXTERNAL_ENGINE_STATE": f"{engine}_external",
    }


# ---------------------------------------------------------------------------
# 输入包
# ---------------------------------------------------------------------------


@dataclass
class PackItem:
    """输入包里的一项：一个文件（text 为 None 表示文件不存在），或一段内核生成的备料。"""

    rel: str
    text: Optional[str]
    generated: bool = False
    title: str = ""
    note: str = ""  # 不读进包的原因（过大、非文本等）


def _file_item(root: Path, rel: str) -> PackItem:
    path = Path(root) / rel
    if not path.is_file() and rel.startswith("templates/") and (PLUGIN_ROOT / rel).is_file():
        path = PLUGIN_ROOT / rel  # 模板是种子：工作区里没有就用插件自带的那份
    if not path.is_file():
        return PackItem(rel, None)
    try:
        size = path.stat().st_size
    except OSError:
        return PackItem(rel, None)
    if size > MAX_FILE_BYTES:
        return PackItem(rel, None, note=f"文件过大（{size} 字节），需要时自行读取")
    return PackItem(rel, _read_text(path))


def _numbered(text: str) -> str:
    return "\n".join(f"{no:>6}\t{line}" for no, line in enumerate(text.splitlines(), 1))


def _file_block(item: PackItem) -> str:
    assert item.text is not None
    return f"<<<FILE {item.rel}（{_line_count(item.text)} 行）>>>\n{_numbered(item.text)}\n<<<END FILE {item.rel}>>>\n"


def build_pack(title: str, items: list[PackItem], budget_bytes: int) -> tuple[str, dict[str, Any]]:
    """按优先级拼输入包。返回（包正文, 清单）。

    items 的顺序就是优先级：预算先给前面的；放不下的文件改为只列路径和行数，后面更小的
    文件只要还放得下仍会入包。内核生成的备料（generated）同样占预算，包头的清单表也算在内。
    """
    used = PACK_HEAD_BYTES + _nbytes(title) + sum(_nbytes(item.rel) + PACK_ROW_BYTES for item in items)
    blocks: list[str] = []
    files: list[dict[str, Any]] = []
    rows: list[str] = []
    for item in items:
        if item.text is None:
            files.append({"path": item.rel, "included": "missing", "note": item.note})
            rows.append(f"| `{item.rel}` | - | - | {item.note or '文件不存在'} |")
            continue
        block = f"## {item.title or item.rel}\n\n{item.text.rstrip()}\n" if item.generated else _file_block(item)
        size = _nbytes(block)
        entry = {
            "path": item.rel,
            "lines": _line_count(item.text),
            "bytes": _nbytes(item.text),
            "sha256": _sha(item.text),
            "generated": item.generated,
        }
        if used + size <= budget_bytes:
            used += size
            blocks.append(block)
            entry["included"] = "full"
            rows.append(f"| `{item.rel}` | {entry['lines']} | {entry['bytes']} | {'内核备料' if item.generated else '全文'} |")
        else:
            entry["included"] = "path_only"
            rows.append(f"| `{item.rel}` | {entry['lines']} | {entry['bytes']} | 只列路径（超出预算，需要时自行读取） |")
        files.append(entry)
    downgraded = [f["path"] for f in files if f.get("included") == "path_only"]
    head = [
        f"# 输入包（{title}）",
        "",
        "> 由内核按磁盘上的当前内容拼成。文件全文每行行首是行号与制表符，引用时写 `文件路径:行号`。",
        "",
        "## 清单",
        "",
        "| 文件 | 行数 | 字节 | 入包情况 |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
    ]
    text = "\n".join(head) + "\n" + "\n".join(blocks)
    manifest = {
        "bytes": _nbytes(text),
        "budget_bytes": budget_bytes,
        "files": files,
        "downgraded": downgraded,
        "missing": [f["path"] for f in files if f.get("included") == "missing"],
    }
    return text, manifest


def _pack_summary(manifest: dict[str, Any]) -> str:
    full = sum(1 for f in manifest["files"] if f.get("included") == "full")
    parts = [f"{full} 项全文，约 {manifest['bytes'] // 1024}KB"]
    if manifest["downgraded"]:
        parts.append(f"{len(manifest['downgraded'])} 个文件只列路径")
    return "；".join(parts)


CORE_SOURCE_NAMES = ("strategy.py", "config.py", "main.py")


def _src_files(root: Path, report_id: str) -> list[str]:
    """src/<id>/ 下的文本文件：strategy / config / main 在前，其余按路径排序。"""
    base = Path(root) / "src" / report_id
    if not base.is_dir():
        return []
    head = CORE_SOURCE_NAMES
    found = [
        p
        for p in sorted(base.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in TEXT_SUFFIXES
        and "__pycache__" not in p.parts
        and not any(part.startswith(".") for part in p.relative_to(base).parts)
    ]
    ranked = sorted(found, key=lambda p: (head.index(p.name) if p.parent == base and p.name in head else len(head), p.as_posix()))
    return [_rel(root, p) for p in ranked]


def _ranked_source(root: Path, report_id: str) -> tuple[list[str], list[str]]:
    """源码按入包的先后分成两段：（核心三件, 其余文件）。

    其余文件按覆盖矩阵里被引用的次数从多到少排：矩阵的「实现位置」指向哪个文件越多，
    这个文件承载的规格要素就越多，预算紧张时越该留在包里；一次都没被引用的（对照基准
    数据、报表辅助之类）排在最后。引用次数相同的保持路径顺序。
    """
    source = _src_files(root, report_id)
    core_paths = {f"src/{report_id}/{name}" for name in CORE_SOURCE_NAMES}
    core = [rel for rel in source if rel in core_paths]
    matrix_path = Path(root) / _ws(report_id) / "spec" / "coverage_matrix.md"
    matrix = _read_text(matrix_path) if matrix_path.is_file() else ""

    def cited(rel: str) -> int:
        name = re.escape(rel.rsplit("/", 1)[-1])
        return len(re.findall(rf"(?<![\w.]){name}(?!\w)", matrix))

    rest = sorted((rel for rel in source if rel not in core_paths), key=lambda rel: -cited(rel))
    return core, rest


def _write_baseline(jdir: Path, files: dict[str, str]) -> None:
    """这一轮所见文件的快照（压缩存放），下一轮据此算差异。"""
    raw = json.dumps({"files": files}, ensure_ascii=False).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as handle:
        handle.write(raw)
    path = jdir / "baseline.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(buffer.getvalue())
    tmp.replace(path)


def _load_baseline(jdir: Path) -> Optional[dict[str, str]]:
    path = jdir / "baseline.json.gz"
    try:
        data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError, EOFError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in files.items()} if isinstance(files, dict) else None


def _review_file_list(root: Path, report_id: str, kind: str, call: str, iteration: Optional[int], extra_files: Iterable[str]) -> list[str]:
    """这次调用要放进输入包的文件，按优先级排列。"""
    ws = _ws(report_id)
    out_dir = f"output/{report_id}"
    if kind == "spec" and call == "blind":
        files = [f"{ws}/spec/report_text.md", f"{ws}/spec/tables_extracted.md"]
    elif kind == "spec":
        files = [
            f"{ws}/spec/spec.md",
            f"{ws}/spec/tables_extracted.md",
            f"{ws}/spec/report_text.md",
            f"{ws}/spec/coverage_matrix.md",
            f"{ws}/spec/ambiguities.md",
        ]
    elif kind == "code":
        # 核心代码最先；规格书、覆盖矩阵、假设登记簿是每个审查维度都要对照的，排在其余源码之前：
        # 放不下时宁可让次要的源码文件只列路径（审查方按覆盖矩阵的「实现位置」定向去读）
        core, rest = _ranked_source(root, report_id)
        files = core + [f"{ws}/spec/spec.md", f"{ws}/spec/coverage_matrix.md", f"{ws}/assumptions.md"] + rest
    elif kind == "result":
        iterations = Path(root) / ws / "iterations"
        diagnoses = sorted(iterations.glob("iter_*/diagnosis.md")) if iterations.is_dir() else []
        files = [
            # 种子模板点名的六份输入在前
            f"{out_dir}/results/comparison.json",
            f"{out_dir}/verify_report.md",
            f"{ws}/assumptions.md",
            f"{ws}/spec/coverage_matrix.md",
            f"{ws}/spec/ambiguities.md",
            "templates/data_catalog.md",
            # 其后是核对归因与证据时多半用得上的材料
            f"{ws}/audit/evidence_manifest.md",
            *([_rel(root, diagnoses[-1])] if diagnoses else []),
            f"{ws}/iterations/iteration_log.md",
            f"{out_dir}/results/metrics.json",
            f"{out_dir}/results/run_log.md",
            f"{ws}/spec/spec.md",
        ]
    else:  # second_opinion：始终全历史
        n = iteration or 0
        core, rest = _ranked_source(root, report_id)
        files = [
            _second_opinion_comparison(root, report_id, n),
            f"{ws}/iterations/iteration_log.md",
            *_history_diagnoses(root, report_id, n),
            *core,
            *rest,
            f"{ws}/assumptions.md",
        ]
    optional = {f"{ws}/iterations/iteration_log.md", f"{out_dir}/results/run_log.md", f"{out_dir}/results/metrics.json"}
    seen: list[str] = []
    for rel in [*files, *(str(f) for f in extra_files)]:
        if rel in seen or (rel in optional and not (Path(root) / rel).is_file()):
            continue
        seen.append(rel)
    return seen


def _second_opinion_comparison(root: Path, report_id: str, iteration: int) -> str:
    snapshot = _iter_dir(root, report_id, iteration) / "comparison.json"
    return _rel(root, snapshot) if snapshot.is_file() else f"output/{report_id}/results/comparison.json"


def _history_diagnoses(root: Path, report_id: str, iteration: int) -> list[str]:
    return [
        _rel(root, path)
        for i in range(1, max(iteration, 1))
        for path in [_iter_dir(root, report_id, i) / "diagnosis.md"]
        if path.is_file()
    ]


# ---------------------------------------------------------------------------
# 代码审查的备料：R 类数值字面量的命中、common/ 签名
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"(?<![\w.])-?(\d+(?:\.\d+)?)(%?)")
_COMMON_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+common\.(\w+)\s+import|import\s+common\.(\w+)|from\s+common\s+import\s+([\w, ]+))", re.MULTILINE
)


def _significant_digits(number: str) -> int:
    digits = number.rstrip("0").rstrip(".") if "." in number else number
    return len(digits.replace(".", "").lstrip("0"))


def r_literals(spec_text: str) -> dict[str, list[str]]:
    """spec.md 里 R 类要素出现的数值字面量 → 出现在哪些要素里。

    只取带小数点的数和百分数：年份、页码、计数这类整数到处都是，查了全是噪音。百分数
    另外带上它的小数形式（62.5% → 62.5 与 0.625）；整数百分数只查小数形式（36% → 0.36）。
    有效数字不足两位的（0.5、1.0）不查。
    """
    found: dict[str, list[str]] = {}

    def add(literal: str, element: str) -> None:
        if _significant_digits(literal) >= 2:
            bucket = found.setdefault(literal, [])
            if element not in bucket:
                bucket.append(element)

    for block in ms.parse_blocks(spec_text):
        if block.prefix != "R":
            continue
        for number, percent in _NUMBER_RE.findall(block.text):
            if "." in number:
                add(number, block.id)
            if percent:
                try:
                    fraction = format((Decimal(number) / 100).normalize(), "f")
                except InvalidOperation:
                    continue
                add(fraction, block.id)
    return found


def literal_hits(root: Path, report_id: str, literals: dict[str, list[str]]) -> list[dict[str, Any]]:
    """这些字面量在 src/<id>/ 的 Python 代码里出现在哪：只列事实，是不是硬编码由审查方判断。"""
    if not literals:
        return []
    pattern = re.compile(
        r"(?<![\w.])(" + "|".join(re.escape(lit) for lit in sorted(literals, key=len, reverse=True)) + r")(?![\w.])"
    )
    hits: list[dict[str, Any]] = []
    for rel in _src_files(root, report_id):
        if not rel.endswith(".py"):
            continue
        for lineno, line in enumerate(_read_text(Path(root) / rel).splitlines(), 1):
            for m in pattern.finditer(line):
                hits.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "literal": m.group(1),
                        "elements": literals[m.group(1)],
                        "comment": "#" in line[: m.start()],
                        "text": line.strip()[:160],
                    }
                )
    return hits


def _literal_section(literals: dict[str, list[str]], hits: list[dict[str, Any]], per_file: int = LITERAL_HITS_PER_FILE) -> str:
    """命中清单：三位及以上有效数字的按文件、按行列出（每个文件列前若干行），两位的只给合计。

    两位有效数字的数（0.52、0.75）和阈值、分位数之类的参数取值撞上的机会太大，逐条列出来
    只会淹没真正要看的命中。
    """
    strong = [h for h in hits if _significant_digits(h["literal"]) >= 3]
    weak = [h for h in hits if _significant_digits(h["literal"]) < 3]
    by_file: dict[str, list[dict[str, Any]]] = {}
    for hit in strong:
        by_file.setdefault(hit["file"], []).append(hit)
    lines = [
        "机器预筛，只列事实：命中不等于硬编码（代码里的参数可能恰好与研报数值相同，也可能是只用来对照的基准值），是否在计算路径上由你判断。",
        "",
        f"- 取自 spec.md 各 R 要素的数值字面量共 {len(literals)} 个（带小数点的数；百分数另含其小数形式）。",
        f"- 三位及以上有效数字的字面量在 `src/` 的 Python 代码里命中 {len(strong)} 处"
        + (f"，分布在 {len(by_file)} 个文件：" if strong else "。"),
    ]
    for file, items in sorted(by_file.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        by_line: dict[int, list[dict[str, Any]]] = {}
        for hit in items:
            by_line.setdefault(hit["line"], []).append(hit)
        lines.append(f"  - `{file}`：{len(items)} 处（{len(by_line)} 行），{len({h['literal'] for h in items})} 个不同的字面量")
        for line_no, group in list(by_line.items())[:per_file]:
            found = "、".join(f"`{literal}`" for literal in dict.fromkeys(h["literal"] for h in group))
            elements = list(dict.fromkeys(element for h in group for element in h["elements"]))
            where = "、".join(elements[:4]) + (" 等" if len(elements) > 4 else "")
            note = "［在注释里］" if all(h["comment"] for h in group) else ""
            lines.append(f"    - 第 {line_no} 行 {found}（见于 {where}）{note}：`{group[0]['text']}`")
        if len(by_line) > per_file:
            lines.append(f"    - ……该文件其余 {len(by_line) - per_file} 行未逐条列出")
    if weak:
        counts: dict[str, int] = {}
        for hit in weak:
            counts[hit["literal"]] = counts.get(hit["literal"], 0) + 1
        top = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        shown = "、".join(f"`{literal}`×{count}" for literal, count in top[:12]) + (" 等" if len(top) > 12 else "")
        lines.append(f"- 两位有效数字的字面量另命中 {len(weak)} 处（多半是参数取值的巧合，未逐条列出）：{shown}。")
    unhit = len(set(literals) - {h["literal"] for h in hits})
    lines.append(f"- 其余 {unhit} 个字面量在 `src/` 下没有出现。")
    return "\n".join(lines)


def _literal_list(literals: dict[str, list[str]], limit: int = 6000) -> str:
    if not literals:
        return "（spec.md 的 R 类要素里没有可检索的数值字面量）"
    text = ", ".join(literals)
    if len(text) > limit:
        text = text[:limit].rsplit(",", 1)[0] + f" …（共 {len(literals)} 个）"
    return text + "\n（这些字面量在 src/ 的命中清单已附在输入包里）"


def _common_modules(root: Path, report_id: str) -> list[str]:
    """策略代码实际导入的公共模块，加上通用三件；一个都认不出来时取全部。"""
    common = Path(root) / "common"
    if not common.is_dir():
        return []
    names = set(packs.BASE_COMMON_MODULES)
    for rel in _src_files(root, report_id):
        if rel.endswith(".py"):
            for a, b, c in _COMMON_IMPORT_RE.findall(_read_text(Path(root) / rel)):
                names |= {n.strip() for n in (a, b, *c.split(",")) if n.strip()}
    picked = sorted(f"common/{n}.py" for n in names if (common / f"{n}.py").is_file())
    return picked or sorted(f"common/{p.name}" for p in common.glob("*.py") if p.name != "__init__.py")


def common_signatures(root: Path, report_id: str) -> str:
    """策略代码用到的 common/ 模块的公开函数签名（def 行到文档串首行）。"""
    sections: list[str] = []
    for rel in _common_modules(root, report_id):
        try:
            segments = packs.signature_segments(Path(root), rel)
        except (OSError, SyntaxError, ValueError):
            continue
        if segments:
            sections.append(f"### {rel}\n\n```python\n" + "\n".join(seg.text.rstrip() for seg in segments) + "\n```")
    return "\n\n".join(sections) if sections else "（没有可列出的公共函数签名）"


def _failing_metrics_summary(root: Path, report_id: str, state: dict[str, Any], comparison_rel: str, limit: int = 15) -> str:
    """未收敛指标的摘要：按 standards.json 重算，不采信文件里自述的 pass。"""
    comparison = _read_json(Path(root) / comparison_rel)
    if not isinstance(comparison, dict):
        return "（comparison.json 不可用）"
    try:
        recalc = cg.recalc_comparison(comparison, cg.load_standards(Path(root)), state.get("type"), cg._is_experimental(state))
    except Exception:  # noqa: BLE001 - 摘要只是提示词里的一段话，算不出来就如实说
        return "（comparison.json 无法按 standards.json 重算）"
    metrics = comparison.get("metrics") or []
    failed = [
        (r.rel_dev if r.rel_dev is not None else -1.0, m)
        for m, r in zip(metrics, recalc.metrics)
        if r.passed is False and isinstance(m, dict)
    ]
    if not failed:
        return "（按 standards.json 重算没有未通过的数值指标）"
    failed.sort(key=lambda item: item[0], reverse=True)
    parts = [
        f"{m.get('key', '?')}：研报 {m.get('report_value')} / 复现 {m.get('reproduced_value')}"
        + (f"（偏差 {dev:.1%}）" if dev >= 0 else "")
        for dev, m in failed[:limit]
    ]
    more = f"；另有 {len(failed) - limit} 项未通过" if len(failed) > limit else ""
    return "；".join(parts) + more


# ---------------------------------------------------------------------------
# 原件解析
# ---------------------------------------------------------------------------


def extract_json_object(text: str) -> tuple[Optional[dict], Optional[str]]:
    """取出含 findings 的 JSON 对象。候选顺序与 check_gates.parse_review 相同：
    整份 → ```json 代码块 → 从后往前找行首的花括号。"""
    candidates = [("json", text), *(("fenced_json", m.group(1)) for m in re.finditer(r"```json\s*(.*?)```", text, re.DOTALL))]
    for source, candidate in candidates:
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and "findings" in data:
            return data, source
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"^[ \t]*\{", text, re.MULTILINE))):
        try:
            data, _end = decoder.raw_decode(text, m.end() - 1)
        except ValueError:
            continue
        if isinstance(data, dict) and "findings" in data:
            return data, "trailing_json"
    return None, None


def split_blind_block(text: str) -> Optional[str]:
    """SPEC_CODEX 标记行之间的盲提取块；没有标记时返回 None。"""
    m = re.search(re.escape(BLIND_BEGIN) + r"[ \t]*\n(.*?)\n?[ \t]*" + re.escape(BLIND_END), text, re.DOTALL)
    return m.group(1).strip("\n") if m else None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _severity(value: Any) -> str:
    """认不出的严重度按 major 处理：宁可要求回应，不能让它悄悄落到不用回应的一档。"""
    text = _text(value).lower()
    return text if text in SEVERITIES else "major"


def _normalize_finding(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"raw_id": "", "severity": "major", "category": "", "location": "", "description": _text(raw), "suggestion": "", "confidence": ""}
    return {
        "raw_id": _text(raw.get("id")),
        "severity": _severity(raw.get("severity")),
        "category": _text(raw.get("category")),
        "location": _text(raw.get("location")),
        "description": _text(raw.get("description") or raw.get("detail")),
        "suggestion": _text(raw.get("suggestion")),
        "confidence": _text(raw.get("confidence")),
        "title": _text(raw.get("title")),
    }


def parse_review_text(text: str) -> dict[str, Any]:
    """解析一份外审结论（JSON，或退化的 markdown 表格加 VERDICT 行）。

    ok 表示它是一份可用的结论：有含 findings 的 JSON，或有 VERDICT 行 / CDX 意见行。
    """
    data, source = extract_json_object(text)
    if data is not None:
        raw_findings = data.get("findings")
        raw_findings = raw_findings if isinstance(raw_findings, list) else []
        diffs = data.get("diffs") if isinstance(data.get("diffs"), list) else []
        dimensions = data.get("dimensions_checked") if isinstance(data.get("dimensions_checked"), list) else []
        return {
            "ok": True,
            "source": source,
            "data": data,
            "verdict": _text(data.get("verdict")).lower() or None,
            "findings": [_normalize_finding(f) for f in raw_findings],
            "diffs": [d for d in diffs if isinstance(d, dict)],
            "dimensions_checked": dimensions,
        }
    rows = [r for r in cg.parse_markdown_table_rows(text) if re.match(r"^CDX-", next(iter(r.values()), "") or "")]
    verdict = re.search(r"VERDICT:\s*(\w+)", text, re.IGNORECASE)
    findings = [
        _normalize_finding(
            {
                "id": next(iter(row.values()), ""),
                "severity": cg._row_get(row, "severity"),
                "category": cg._row_get(row, "category"),
                "location": cg._row_get(row, "location"),
                "description": cg._row_get(row, "description") or cg._row_get(row, "描述"),
                "suggestion": cg._row_get(row, "suggestion") or cg._row_get(row, "建议"),
            }
        )
        for row in rows
    ]
    return {
        "ok": bool(verdict or rows),
        "source": "table",
        "data": None,
        "verdict": verdict.group(1).lower() if verdict else None,
        "findings": findings,
        "diffs": [],
        "dimensions_checked": [],
    }


def _title(category: str, description: str, limit: int = 80) -> str:
    """意见的一行摘要：类别加描述的第一句。回应表的「摘要」列用它。"""
    first = re.split(r"[。；;\n]", description.strip(), maxsplit=1)[0].strip()
    text = f"{category}：{first}" if category and first else (category or first or "（无描述）")
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _canon_id(raw: Any, letter: str) -> tuple[Optional[str], Optional[int]]:
    m = re.fullmatch(rf"CDX-{letter}-0*(\d+)", _text(raw), re.IGNORECASE)
    if not m:
        return None, None
    number = int(m.group(1))
    return f"CDX-{letter}-{number:02d}", number


# ---------------------------------------------------------------------------
# 各轮原件与合并
# ---------------------------------------------------------------------------


def completed_rounds(root: Path, report_id: str, kind: str) -> list[dict[str, Any]]:
    """这个审查点已成功完成、原件在位的各轮（按轮次升序）。"""
    base = Path(root) / _ws(report_id) / "audit" / "external"
    found: list[dict[str, Any]] = []
    for path in sorted(base.glob(f"{kind}_r*")) if base.is_dir() else []:
        m = re.fullmatch(rf"{kind}_r(\d+)", path.name)
        status = _read_json(path / "status.json")
        if not m or not isinstance(status, dict) or status.get("state") != "success" or not (path / "output.md").is_file():
            continue
        job = _read_json(path / "job.json")
        job = job if isinstance(job, dict) else {}
        found.append(
            {
                "round": int(m.group(1)),
                "job_id": path.name,
                "dir": path,
                "output": path / "output.md",
                "mode": job.get("mode") or "full",
                "engine_state": status.get("engine_state") or job.get("engine_state"),
                "subsessions": status.get("subsessions"),
                "blind_read_spec": status.get("blind_read_spec"),
                "closed": [str(c) for c in job.get("closed") or []],
            }
        )
    return sorted(found, key=lambda r: r["round"])


def merge_rounds(root: Path, report_id: str, kind: str, upto: Optional[int] = None) -> dict[str, Any]:
    """把各轮原件合并成意见的并集（不落盘）。

    同一编号在各轮里是同一条意见。编号不合规或在同一轮里重复的意见，接在已有最大编号
    之后重新编号（原编号记在 orig_id）。open 表示最新一轮是否仍列出这条意见。
    """
    letter = ID_LETTER[kind]
    rounds = [r for r in completed_rounds(root, report_id, kind) if upto is None or r["round"] <= upto]
    entries: dict[str, dict[str, Any]] = {}
    numbers: dict[str, int] = {}
    max_no = 0
    infos: list[dict[str, Any]] = []
    diffs: list[dict[str, Any]] = []
    blind: Optional[dict[str, Any]] = None
    latest: dict[str, Any] = {}

    def absorb(cid: str, number: int, finding: dict[str, Any], round_no: int) -> None:
        version = {k: finding[k] for k in ("severity", "category", "location", "description", "suggestion", "confidence")}
        version["round"] = round_no
        entry = entries.get(cid)
        if entry is None:
            entry = entries[cid] = {
                "id": cid,
                "title": finding.get("title") or _title(finding["category"], finding["description"]),
                "first_round": round_no,
                "versions": [],
            }
            numbers[cid] = number
        entry["versions"].append(version)
        entry["last_round"] = round_no
        if finding.get("orig_id"):
            entry["orig_id"] = finding["orig_id"]

    for r in rounds:
        text = _read_text(r["output"])
        parsed = parse_review_text(text)
        listed: list[str] = []
        id_map: dict[str, str] = {}
        renumber: list[dict[str, Any]] = []
        for finding in parsed["findings"]:
            cid, number = _canon_id(finding["raw_id"], letter)
            if cid is None or number is None or cid in listed:
                renumber.append(finding)
                continue
            max_no = max(max_no, number)
            listed.append(cid)
            id_map[finding["raw_id"]] = cid
            absorb(cid, number, finding, r["round"])
        for finding in renumber:
            max_no += 1
            cid = f"CDX-{letter}-{max_no:02d}"
            finding["orig_id"] = finding["raw_id"]
            listed.append(cid)
            id_map.setdefault(finding["raw_id"], cid)
            absorb(cid, max_no, finding, r["round"])
        for index, diff in enumerate(parsed["diffs"], 1):
            local = _text(diff.get("id")) or f"D-{index:02d}"
            linked = _text(diff.get("finding_id") or diff.get("finding"))
            resolution = _text(diff.get("resolution")).lower()
            diffs.append(
                {
                    "key": f"r{r['round']}#{local}",
                    "round": r["round"],
                    "id": local,
                    "category": _text(diff.get("category")),
                    "pages": _text(diff.get("pages") or diff.get("page")),
                    "description": _text(diff.get("description")),
                    "resolution": resolution if resolution in DIFF_RULINGS else "",
                    "basis": _text(diff.get("basis")),
                    "finding_id": id_map.get(linked) or (_canon_id(linked, letter)[0] or ""),
                }
            )
        # 收编的旧汇总是各轮意见的并集，没有逐轮的在列信息：导入时认定已闭环的不算这一轮在列
        listed = [cid for cid in listed if cid not in set(r.get("closed") or [])]
        block = split_blind_block(text)
        if block is not None:
            blind = {"round": r["round"], "text": block}
        infos.append(
            {
                "round": r["round"],
                "job_id": r["job_id"],
                "mode": r["mode"],
                "engine_state": r["engine_state"],
                "verdict": parsed["verdict"],
                "listed": listed,
                "source": parsed["source"],
                "raw": _rel(root, r["output"]),
                "subsessions": r["subsessions"],
                **({"blind_read_spec": r["blind_read_spec"]} if kind == "spec" and block is not None else {}),
            }
        )
        latest = {"round": r["round"], "listed": listed, "verdict": parsed["verdict"], "dimensions_checked": parsed["dimensions_checked"]}

    last_listed = set(latest.get("listed") or [])
    findings: list[dict[str, Any]] = []
    for cid in sorted(entries, key=lambda key: numbers[key]):
        entry = entries[cid]
        current = entry["versions"][-1]
        finding = {
            "id": cid,
            "severity": current["severity"],
            "title": entry["title"],
            "category": current["category"],
            "location": current["location"],
            "description": current["description"],
            "suggestion": current["suggestion"],
            "confidence": current["confidence"],
            "first_round": entry["first_round"],
            "last_round": entry["last_round"],
            "open": cid in last_listed,
        }
        if entry.get("orig_id"):
            finding["orig_id"] = entry["orig_id"]
        if len(entry["versions"]) > 1:
            finding["history"] = entry["versions"]
        findings.append(finding)

    verdict = latest.get("verdict")
    if verdict not in VERDICTS:
        still_open = [f for f in findings if f["open"]]
        verdict = "fail" if any(f["severity"] == "critical" for f in still_open) else ("pass_with_issues" if still_open else "pass")
    return {
        "rounds": infos,
        "findings": findings,
        "verdict": verdict if rounds else None,
        "dimensions_checked": latest.get("dimensions_checked") or [],
        "diffs": diffs,
        "blind": blind,
        "max_no": max_no,
    }


def _counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return {severity: sum(1 for f in findings if f.get("severity") == severity) for severity in SEVERITIES}


# ---------------------------------------------------------------------------
# 差量复审
# ---------------------------------------------------------------------------


def _diff_file(old: str, new: str, rel: str, prev_round: int) -> tuple[int, int, str]:
    """返回（新增行数, 删除行数, unified diff 正文）。行数过多的文件不逐行比对。"""
    a, b = old.splitlines(), new.splitlines()
    if max(len(a), len(b)) > DIFF_MAX_LINES:
        return len(b), len(a), "（文件过大，未做逐行比对；按整份改动计，请直接阅读当前文件）"
    lines = list(difflib.unified_diff(a, b, fromfile=f"{rel}（第 {prev_round} 轮）", tofile=f"{rel}（当前）", n=DIFF_CONTEXT_LINES, lineterm=""))
    body = lines[2:]
    added = sum(1 for line in body if line.startswith("+"))
    removed = sum(1 for line in body if line.startswith("-"))
    return added, removed, "\n".join(lines)


def compute_delta(baseline: dict[str, str], current: dict[str, Optional[str]], prev_round: int) -> dict[str, Any]:
    """上一轮快照与当前文件逐个比对。

    改动面 = 各文件 max(新增行, 删除行) 之和 ÷ 各文件 max(上一轮行数, 当前行数) 之和。
    上一轮没见过的文件（没有快照可比）按整份改动计。
    """
    entries: list[dict[str, Any]] = []
    changed = total = 0
    for rel in [*current, *(r for r in baseline if r not in current)]:
        old, new = baseline.get(rel), current.get(rel)
        old_lines = _line_count(old) if old is not None else 0
        new_lines = _line_count(new) if new is not None else 0
        entry: dict[str, Any] = {"path": rel, "old_lines": old_lines, "new_lines": new_lines, "added": 0, "removed": 0, "diff": ""}
        if old is None and new is None:
            continue
        if old is None:
            entry.update(status="added", added=new_lines)
        elif new is None:
            entry.update(status="removed", removed=old_lines)
        elif old == new:
            entry.update(status="same")
        else:
            added, removed, diff = _diff_file(old, new, rel, prev_round)
            entry.update(status="changed", added=added, removed=removed, diff=diff)
        changed += max(entry["added"], entry["removed"])
        total += max(old_lines, new_lines)
        entries.append(entry)
    return {"files": entries, "changed_lines": changed, "total_lines": total, "ratio": (changed / total) if total else 0.0}


def _response_rows(root: Path, report_id: str, kind: str) -> dict[str, dict[str, str]]:
    """回应表里这个审查点已有的处置与回应（按规范编号索引）。"""
    letter = ID_LETTER[kind]
    path = Path(root) / _ws(report_id) / "audit" / "audit_responses.md"
    rows: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return rows
    for row in cg.parse_markdown_table_rows(_read_text(path)):
        cid, _number = _canon_id(cg._row_id(row, r"^CDX-[A-Z]-"), letter)
        if cid:
            rows[cid] = {"disposition": cg._row_get(row, "处置"), "response": cg._row_get(row, "回应"), "recheck": cg._row_get(row, "复核")}
    return rows


def _finding_brief(finding: dict[str, Any]) -> str:
    state = "未闭环" if finding.get("open") else "已闭环"
    return f"- `{finding['id']}`（{finding['severity']}，第 {finding['first_round']} 轮提出，{state}）{finding['title']}"


def build_delta_pack(
    kind: str,
    round_no: int,
    prev_round: int,
    merged: dict[str, Any],
    responses: dict[str, dict[str, str]],
    delta: dict[str, Any],
    current: dict[str, Optional[str]],
    budget_bytes: int,
) -> tuple[str, dict[str, Any]]:
    """差量复审包：仍未闭环的意见与回应、上一轮以来的改动、已闭环意见的清单。"""
    open_items = [f for f in merged["findings"] if f["open"]]
    closed_items = [f for f in merged["findings"] if not f["open"]]
    lines = [
        f"# 差量复审包（{kind} 审查点，第 {round_no} 轮；上一轮是第 {prev_round} 轮）",
        "",
        f"## 一、仍未闭环的意见与回应（{len(open_items)} 条）",
        "",
    ]
    if not open_items:
        lines += ["（上一轮没有留下未闭环的意见，本轮只需检查改动处有没有引入新问题。）", ""]
    for finding in open_items:
        reply = responses.get(finding["id"], {})
        lines += [
            f"### {finding['id']}｜{finding['severity']}｜{finding['title']}",
            "",
            f"- 首次提出：第 {finding['first_round']} 轮",
            f"- 位置：{finding['location'] or '（未给出）'}",
            f"- 描述：{finding['description'] or '（无）'}",
            f"- 建议：{finding['suggestion'] or '（无）'}",
            f"- 被审方的处置：{reply.get('disposition') or '（尚未处置）'}",
            f"- 被审方的回应：{reply.get('response') or '（无）'}",
            "",
        ]
    ratio = delta["ratio"]
    lines += [
        f"## 二、自第 {prev_round} 轮以来的改动",
        "",
        f"改动面：{delta['changed_lines']} 行 / 共 {delta['total_lines']} 行（{ratio:.1%}）。",
        "",
        "| 文件 | 状态 | 上一轮行数 | 当前行数 | 新增 | 删除 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    status_cn = {"same": "未变", "changed": "有改动", "added": "新增", "removed": "已删除"}
    lines += [
        f"| `{e['path']}` | {status_cn[e['status']]} | {e['old_lines']} | {e['new_lines']} | {e['added']} | {e['removed']} |"
        for e in delta["files"]
    ]
    lines.append("")
    head = "\n".join(lines)
    tail_lines = [f"## 三、此前已闭环的意见（{len(closed_items)} 条，仅供对照，不必复核）", ""]
    tail_lines += [_finding_brief(f) for f in closed_items] or ["（无）"]
    tail = "\n".join(tail_lines) + "\n"

    used = _nbytes(head) + _nbytes(tail)
    blocks: list[str] = []
    downgraded: list[str] = []
    for entry in delta["files"]:
        if entry["status"] == "changed":
            block = f"<<<DIFF {entry['path']}>>>\n{entry['diff']}\n<<<END DIFF {entry['path']}>>>\n"
        elif entry["status"] == "added" and current.get(entry["path"]) is not None:
            block = _file_block(PackItem(entry["path"], current[entry["path"]]))
        else:
            continue
        if used + _nbytes(block) <= budget_bytes:
            used += _nbytes(block)
            blocks.append(block)
        else:
            downgraded.append(entry["path"])
            blocks.append(f"<<<DIFF {entry['path']}>>>\n（差异超出预算，未附；请自行对照当前文件）\n<<<END DIFF {entry['path']}>>>\n")
    body = "### 差异（unified diff；新增文件给带行号的全文）\n\n" + ("\n".join(blocks) if blocks else "（没有文件改动）\n")
    text = head + "\n" + body + "\n" + tail
    manifest = {
        "bytes": _nbytes(text),
        "budget_bytes": budget_bytes,
        "files": [{k: e[k] for k in ("path", "status", "old_lines", "new_lines", "added", "removed")} for e in delta["files"]],
        "downgraded": downgraded,
        "missing": [],
        "open_findings": [f["id"] for f in open_items],
    }
    return text, manifest


# ---------------------------------------------------------------------------
# 输出约束
# ---------------------------------------------------------------------------


def review_schema(kind: str, with_diffs: bool = False) -> dict[str, Any]:
    """结论 JSON 的输出约束（每个属性都必填、不许多余属性，两个引擎都能接受的写法）。"""

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}

    text = {"type": "string"}
    properties: dict[str, Any] = {
        "checkpoint": {"type": "string", "enum": [kind]},
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "dimensions_checked": {"type": "array", "items": obj({"dimension": text, "result": text})},
    }
    if with_diffs:
        properties["diffs"] = {
            "type": "array",
            "items": obj(
                {
                    "id": text,
                    "category": text,
                    "pages": text,
                    "description": text,
                    "resolution": {"type": "string", "enum": list(DIFF_RULINGS)},
                    "basis": text,
                    "finding_id": text,
                }
            ),
        }
    properties["findings"] = {
        "type": "array",
        "items": obj(
            {
                "id": text,
                "severity": {"type": "string", "enum": list(SEVERITIES)},
                "category": text,
                "location": text,
                "description": text,
                "suggestion": text,
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            }
        ),
    }
    return obj(properties)


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def _validate_request(kind: str, round_no: int, engine: str, host: str) -> None:
    if kind not in KINDS:
        raise ExtReviewError(f"kind 必须是 {KINDS} 之一，收到: {kind}")
    if engine not in er.ENGINES:
        raise ExtReviewError(f"engine 必须是 {er.ENGINES} 之一，收到: {engine}")
    if not isinstance(round_no, int) or isinstance(round_no, bool) or round_no < 1:
        raise ExtReviewError(f"round_no 必须是正整数，收到: {round_no!r}")
    if HOST_FAMILY.get(host) == engine:
        raise ExtReviewError(f"外审引擎必须与宿主不同家族：宿主 {host} 不能用 {engine} 作外审（那是同宿主替身，走 fallback_task）")


def _retire_later_rounds(root: Path, report_id: str, kind: str, round_no: int) -> list[str]:
    """把编号大于本轮的既有轮次挪到 _superseded/ 下，返回被挪走的 job 编号。

    轮次只增不减；准备第 N 轮时目录里却有更大的编号，说明计数被回拨过（案例重新初始化、
    人工改了计数）。那些轮次留在原处会被当成「比本轮更新」，把本轮提出的意见误判为已闭环。
    """
    base = Path(root) / _ws(report_id) / "audit" / "external"
    later: list[tuple[int, Path]] = []
    for path in sorted(base.glob(f"{kind}_r*")) if base.is_dir() else []:
        m = re.fullmatch(rf"{kind}_r(\d+)", path.name)
        if m and path.is_dir() and int(m.group(1)) > round_no:
            later.append((int(m.group(1)), path))
    if not later:
        return []
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    retired: list[str] = []
    for _number, path in sorted(later):
        status = _read_json(path / "status.json")
        if isinstance(status, dict):
            _stop_runner(path, status)
        target = base / "_superseded" / f"{path.name}__{stamp}"
        suffix = 1
        while target.exists():
            suffix += 1
            target = base / "_superseded" / f"{path.name}__{stamp}_{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        retired.append(path.name)
    return retired


def _reset_job_dir(jdir: Path) -> bool:
    """清空一个 job 目录（job 目录只属于本模块）。同名 job 还在后台跑的，先停掉；返回是否停过。"""
    status = _read_json(jdir / "status.json")
    stopped = _stop_runner(jdir, status) if isinstance(status, dict) else False
    if jdir.is_dir():
        shutil.rmtree(jdir)
    jdir.mkdir(parents=True, exist_ok=True)
    return stopped


def _nonce() -> str:
    return "xr" + uuid.uuid4().hex[:14]


def _tag(job_id: str, call: str, nonce: str) -> str:
    """提示词首行的标记：事后凭它在外审引擎的会话记录里认出这次调用。"""
    return f"<!-- extreview {job_id}/{call} {nonce} -->\n\n"


def _append_notes(prompt: str, extra: dict[str, Any], experimental: bool) -> str:
    parts = [prompt.rstrip()]
    if experimental:
        parts.append(_plugin_template("experimental_note.md").rstrip())
    notes = _text(extra.get("notes"))
    if notes:
        parts.append("# 本案例附加说明\n\n" + notes)
    return "\n\n".join(parts) + "\n"


def _call(name: str, effort: str, validate: str, schema: Optional[str] = None, deferred: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "prompt": f"prompt_{name}.md",
        "input": f"input_{name}.md",
        "output": f"output_{name}.md",
        "effort": effort,
        "schema": schema,
        "validate": validate,
        "nonce": _nonce(),
        "deferred_input": deferred,
    }


def _write_schema(jdir: Path, name: str, schema: dict[str, Any], enabled: bool) -> Optional[str]:
    if not enabled:
        return None
    _write_json(jdir / f"schema_{name}.json", schema)
    return f"schema_{name}.json"


def _pack_note(manifest: dict[str, Any]) -> str:
    return render(_plugin_template("pack_note.md").strip(), {"pack_summary": _pack_summary(manifest)})


def _items(root: Path, files: list[str]) -> list[PackItem]:
    return [_file_item(root, rel) for rel in files]


def _require_file(root: Path, rel: str, why: str) -> None:
    if not (Path(root) / rel).is_file():
        raise ExtReviewError(f"{why}：缺少 {rel}")


def prepare(
    root: Path,
    report_id: str,
    kind: str,
    round_no: int,
    *,
    engine: str,
    host: str,
    config: Optional[dict] = None,
    iteration: Optional[int] = None,
    extra: Optional[dict] = None,
    force_full: bool = False,
) -> dict:
    """渲染提示词与输入包，写 job.json，返回 job 描述。不启动进程，可重复调用（覆盖同名 job）。"""
    root = Path(root)
    _validate_request(kind, round_no, engine, host)
    extra = dict(extra or {})
    state = _load_state(root, report_id)
    cfg = settings(config, kind, engine)
    values = _base_values(root, report_id, engine, state)
    if kind == "second_opinion":
        iteration = iteration or (state.get("iteration") or {}).get("current")
        if not isinstance(iteration, int) or iteration < 1:
            raise ExtReviewError("second_opinion 需要迭代轮次（iteration 参数或 state.iteration.current）")
        values["iteration_current"] = iteration
        values["NN"] = f"{iteration:02d}"
    job_id = job_id_for(kind, round_no, iteration)
    jdir = job_dir(root, report_id, job_id)
    replaced_running = _reset_job_dir(jdir)
    retired = _retire_later_rounds(root, report_id, kind, round_no) if kind in REVIEW_KINDS else []
    adopted = _adopt_legacy(root, report_id, kind, state) if kind in REVIEW_KINDS else None
    values["job_id"] = job_id

    job: dict[str, Any] = {
        "format": JOB_FORMAT,
        "job_id": job_id,
        "kind": kind,
        "round": round_no,
        "iteration": iteration if kind == "second_opinion" else None,
        "report_id": report_id,
        "engine": engine,
        "engine_state": f"{engine}_external",
        "host": host,
        "mode": "full",
        "mode_reason": "first_round",
        "prev_round": None,
        "timeout_seconds": cfg["timeout_seconds"],
        "model": cfg["model"],
        "budget_bytes": cfg["budget_bytes"],
        "output_schema": cfg["output_schema"],
        "dir": _rel(root, jdir),
        "created_at": st.now_iso(),
        "warnings": ["同名 job 还在后台运行，已终止并由这一份覆盖"] if replaced_running else [],
    }
    if adopted:
        job["adopted_legacy"] = adopted
        job["warnings"].append(f"已有的规范文件不是本模块生成的（旧案例的汇总或宿主手写），已作为第 0 轮收编（{adopted}），其中的意见编号沿用")
    if retired:
        job["superseded"] = retired
        job["warnings"].append(f"目录里有编号更大的既有轮次（{'、'.join(retired)}），已挪到 audit/external/_superseded/，不再参与合并")
    extra_files = [str(f) for f in extra.get("files") or []]

    if kind == "second_opinion":
        _prepare_second_opinion(root, job, jdir, values, extra, state, cfg, extra_files)
    else:
        merged, prev, baseline = _previous(root, report_id, kind, round_no)
        review_files = _review_file_list(root, report_id, kind, "review" if kind == "spec" else "main", None, extra_files)
        current_items = _items(root, review_files)
        current = {item.rel: item.text for item in current_items}
        delta = None
        if prev is not None:
            job["prev_round"] = prev["round"]
            if force_full:
                job["mode_reason"] = "force_full"
            elif baseline is None:
                job["mode_reason"] = "no_baseline"
            else:
                delta = compute_delta(baseline, current, prev["round"])
                job["delta"] = {k: delta[k] for k in ("changed_lines", "total_lines", "ratio")}
                if delta["ratio"] > cfg["delta_max_changed_ratio"]:
                    job["mode_reason"] = "changed_ratio"
                else:
                    job["mode"], job["mode_reason"] = "delta", "delta"
        next_no = (merged["max_no"] if merged else 0) + 1
        job["next_finding_no"] = next_no
        values["next_finding_id"] = f"CDX-{ID_LETTER[kind]}-{next_no:02d}"
        values["checkpoint"] = kind
        values["round"] = round_no
        if job["mode"] == "delta":
            assert merged is not None and prev is not None and delta is not None
            _prepare_delta(root, job, jdir, values, extra, state, cfg, merged, prev, delta, current)
        elif kind == "spec":
            _prepare_spec_full(root, job, jdir, values, extra, cfg, merged)
        else:
            _prepare_full(root, job, jdir, values, extra, state, cfg, merged, current_items)
        _write_baseline(jdir, {rel: text for rel, text in current.items() if text is not None})

    job["input_bytes"] = sum(c.get("bytes", 0) for c in job["calls"])
    _write_json(jdir / "job.json", job)
    return job


def _previous(root: Path, report_id: str, kind: str, round_no: int) -> tuple[Optional[dict], Optional[dict], Optional[dict[str, str]]]:
    """此前各轮的合并结果、最近一轮已完成的 job、它的文件快照。"""
    prior = [r for r in completed_rounds(root, report_id, kind) if r["round"] < round_no]
    if not prior:
        return None, None, None
    merged = merge_rounds(root, report_id, kind, upto=round_no - 1)
    return merged, prior[-1], _load_baseline(prior[-1]["dir"])


def _rereview_note(values: dict[str, Any], merged: Optional[dict]) -> str:
    """整体重审时附上此前的意见编号，让多轮意见对得上号。首轮没有这一段。"""
    if not merged or not merged["rounds"]:
        return ""
    brief = "\n".join(_finding_brief(f) for f in merged["findings"]) or "（此前各轮没有提出意见）"
    return "\n\n" + render(_plugin_template("rereview_note.md"), {**values, "previous_findings_brief": brief}).rstrip() + "\n"


def _request_text(prompt: str, pack: Optional[str]) -> str:
    """实际发给外审引擎的内容：提示词在前，输入包在后。"""
    return prompt if pack is None else prompt.rstrip("\n") + "\n\n" + pack


def _finish_call(jdir: Path, job: dict, call: dict, prompt: str, pack: Optional[str], manifest: Optional[dict]) -> None:
    """落盘一次调用的提示词与输入包，记下大小（bytes 是实际发出去的字节数）。"""
    prompt = _tag(job["job_id"], call["name"], call["nonce"]) + prompt
    _write_text(jdir / call["prompt"], prompt)
    call["prompt_bytes"] = _nbytes(prompt)
    if pack is not None:
        _write_text(jdir / call["input"], pack)
        call["input_bytes"] = _nbytes(pack)
    call["bytes"] = _nbytes(_request_text(prompt, pack))
    if manifest is not None:
        call["manifest"] = manifest
        if manifest.get("downgraded"):
            job["warnings"].append(f"{call['name']}: {len(manifest['downgraded'])} 个文件超出预算，只列了路径")
    job.setdefault("calls", []).append(call)


def _legacy_prompt_copy(root: Path, job: dict, text: str) -> None:
    """首轮渲染出的提示词按旧文件名另存一份。"""
    if job["kind"] == "second_opinion":
        target = _iter_dir(root, job["report_id"], job["iteration"]) / "external_prompt_second_opinion.md"
    elif job["round"] == 1:
        target = Path(root) / _ws(job["report_id"]) / "audit" / f"external_prompt_{job['kind']}.md"
    else:
        return
    _write_text(target, text)


def _prepare_full(
    root: Path, job: dict, jdir: Path, values: dict, extra: dict, state: dict, cfg: dict, merged: Optional[dict], file_items: list[PackItem]
) -> None:
    """code / result 的整体审查：种子模板加输入包，一次调用。"""
    kind, report_id = job["kind"], job["report_id"]
    ws = _ws(report_id)
    generated: list[PackItem] = []
    if kind == "code":
        _require_file(root, f"{ws}/spec/spec.md", "代码外审")
        if not _src_files(root, report_id):
            raise ExtReviewError(f"代码外审：src/{report_id}/ 下没有可审的源码")
        literal_list: Optional[str] = None
        literal_section: Optional[str] = None
        try:
            literals = r_literals(_read_text(root / ws / "spec" / "spec.md"))
            hits = literal_hits(root, report_id, literals)
        except Exception as exc:  # noqa: BLE001 - 预筛只是备料，做不出来不该让整道外审退成替身
            literals, hits = {}, []
            literal_list = "（R 类数值清单未能自动生成，请自行从 spec.md 第五节取数，在 src/ 下检索）"
            literal_section = "（预筛没有做成，本节为空；K1 硬编码排查请自行检索）"
            job["warnings"].append(f"R 类数值字面量的预筛没有做成（{type(exc).__name__}: {exc}），审查方需自行检索"[:300])
        signatures = common_signatures(root, report_id)
        signature_path = root / ws / "audit" / "common_signatures.md"
        if not signature_path.is_file():
            _write_text(signature_path, "# common/ 公共函数签名\n\n" + signatures + "\n")
        values.setdefault("common_signatures_path", f"{ws}/audit/common_signatures.md")
        values.setdefault("r_class_values_list", literal_list or _literal_list(literals))
        job["prep"] = {"r_literals": len(literals), "r_literal_hits": len(hits)}
        generated = [
            PackItem("@R类数值字面量命中", literal_section or _literal_section(literals, hits), generated=True, title="R 类数值字面量在 src/ 的命中"),
            PackItem("@common签名", signatures, generated=True, title="common/ 公共函数签名"),
        ]
    else:
        comparison = f"output/{report_id}/results/comparison.json"
        _require_file(root, comparison, "结果外审")
        values.setdefault("comparison_path", comparison)
    _apply_overrides(values, extra)
    prompt = render(_seed_template(root, kind), values).rstrip()
    experimental = kind == "result" and state.get("reproduction_mode") == "experimental"
    prompt = _append_notes(prompt, extra, experimental).rstrip() + _rereview_note(values, merged)
    budget = max(cfg["budget_bytes"] - _nbytes(prompt) - PROMPT_RESERVE_BYTES, 0)
    pack, manifest = build_pack(f"{kind} 审查点，第 {job['round']} 轮", generated + file_items, budget)
    prompt = prompt.rstrip() + "\n\n" + _pack_note(manifest) + "\n"
    schema = _write_schema(jdir, "main", review_schema(kind), cfg["output_schema"])
    call = _call("main", cfg["effort_first"], "review", schema)
    _finish_call(jdir, job, call, prompt, pack, manifest)
    _legacy_prompt_copy(root, job, prompt)


def _apply_overrides(values: dict, extra: dict) -> None:
    """extra 里与已知占位符同名的键覆盖自动取值。"""
    for key, value in extra.items():
        if key in KNOWN_PLACEHOLDERS and value is not None:
            values[key] = value


def _prepare_spec_full(root: Path, job: dict, jdir: Path, values: dict, extra: dict, cfg: dict, merged: Optional[dict]) -> None:
    """spec 的整体审查：盲提取与差异审查分两次调用，第二次的输入包等第一次跑完再拼。"""
    report_id = job["report_id"]
    ws = _ws(report_id)
    _require_file(root, f"{ws}/spec/report_text.md", "盲提取外审")
    _require_file(root, f"{ws}/spec/spec.md", "规格外审")
    _apply_overrides(values, extra)

    blind_items = _items(root, _review_file_list(root, report_id, "spec", "blind", None, []))
    blind_template = _plugin_template("spec_blind.md")
    probe = render(blind_template, {**values, "pack_note": ""})
    blind_pack, blind_manifest = build_pack(
        "spec 审查点，第一次调用：盲提取", blind_items, max(cfg["budget_bytes"] - _nbytes(probe) - PROMPT_RESERVE_BYTES, 0)
    )
    blind_prompt = render(blind_template, {**values, "pack_note": _pack_note(blind_manifest)})
    _finish_call(jdir, job, _call("blind", cfg["effort_first"], "text"), blind_prompt, blind_pack, blind_manifest)

    review_files = _review_file_list(root, report_id, "spec", "review", None, [str(f) for f in extra.get("files") or []])
    pack_note = (
        "**关于输入包**：本提示词末尾附有预先拼好的「输入包」：盲提取清单，以及上述文件在磁盘上的当前内容（每行带行号，"
        "可以直接按 `文件路径:行号` 引用，**不必再逐段读取这些文件**）。因超出预算而只列了路径的文件见包内清单，需要时自己打开；"
        "包外的内容你也可以自己读，你对整个工作目录有只读权限。"
    )
    review_prompt = render(_plugin_template("spec_review.md"), {**values, "pack_note": pack_note})
    review_prompt = _append_notes(review_prompt, extra, False).rstrip() + _rereview_note(values, merged) + "\n"
    schema = _write_schema(jdir, "review", review_schema("spec", with_diffs=True), cfg["output_schema"])
    review = _call("review", cfg["effort_first"], "review", schema, deferred=True)
    review["files"] = review_files
    review["budget_bytes"] = max(cfg["budget_bytes"] - _nbytes(review_prompt) - PROMPT_RESERVE_BYTES, 0)
    _finish_call(jdir, job, review, review_prompt, None, None)
    review["bytes"] += sum(_nbytes(item.text) for item in _items(root, review_files) if item.text is not None)  # 预估，实际值运行时回填
    _legacy_prompt_copy(
        root,
        job,
        "# 第一次调用：盲提取\n\n" + blind_prompt.rstrip() + "\n\n---\n\n# 第二次调用：差异比对与结构化审查\n\n" + review_prompt,
    )


def _build_spec_review_input(root: Path, job: dict, jdir: Path, call: dict, blind_text: str) -> tuple[str, dict]:
    """第二次调用的输入包：盲提取清单在前，其后是规格书与原文。"""
    items = [PackItem("@盲提取清单", blind_text, generated=True, title="盲提取清单（第一次调用的产出，产出时未见过 spec.md）")]
    items += _items(root, call.get("files") or [])
    return build_pack("spec 审查点，第二次调用：差异比对与结构化审查", items, call.get("budget_bytes") or job["budget_bytes"])


def _prepare_delta(
    root: Path,
    job: dict,
    jdir: Path,
    values: dict,
    extra: dict,
    state: dict,
    cfg: dict,
    merged: dict,
    prev: dict,
    delta: dict,
    current: dict[str, Optional[str]],
) -> None:
    """差量复审：一次调用，只给意见与回应、文件差异。"""
    kind, report_id = job["kind"], job["report_id"]
    open_items = [f for f in merged["findings"] if f["open"]]
    values.update(
        prev_round=prev["round"],
        open_findings_count=len(open_items),
        example_old_id=open_items[0]["id"] if open_items else f"CDX-{ID_LETTER[kind]}-01",
    )
    values["severity_rules"] = _severity_rules(root, kind, {**values, "common_signatures_path": "", "r_class_values_list": "", "comparison_path": ""})
    _apply_overrides(values, extra)
    prompt = render(_plugin_template("delta_review.md"), values)
    experimental = kind == "result" and state.get("reproduction_mode") == "experimental"
    prompt = _append_notes(prompt, extra, experimental)
    budget = max(cfg["budget_bytes"] - _nbytes(prompt) - PROMPT_RESERVE_BYTES, 0)
    pack, manifest = build_delta_pack(kind, job["round"], prev["round"], merged, _response_rows(root, report_id, kind), delta, current, budget)
    schema = _write_schema(jdir, "main", review_schema(kind), cfg["output_schema"])
    _finish_call(jdir, job, _call("main", cfg["effort_recheck"], "review", schema), prompt, pack, manifest)


def _prepare_second_opinion(root: Path, job: dict, jdir: Path, values: dict, extra: dict, state: dict, cfg: dict, extra_files: list[str]) -> None:
    report_id, iteration = job["report_id"], job["iteration"]
    comparison = _second_opinion_comparison(root, report_id, iteration)
    history = _history_diagnoses(root, report_id, iteration)
    values.setdefault("comparison_path", comparison)
    values.setdefault("iteration_history_paths", "、".join(history) if history else "（此前各轮没有 diagnosis.md）")
    values.setdefault("trigger_reason", f"第 {iteration} 轮迭代的常规第二意见（iter >= 2）")
    values.setdefault("failing_metrics_summary", _failing_metrics_summary(root, report_id, state, comparison))
    _apply_overrides(values, extra)
    prompt = _append_notes(render(_seed_template(root, "second_opinion"), values), extra, False).rstrip()
    budget = max(cfg["budget_bytes"] - _nbytes(prompt) - PROMPT_RESERVE_BYTES, 0)
    items = _items(root, _review_file_list(root, report_id, "second_opinion", "main", iteration, extra_files))
    pack, manifest = build_pack(f"第二意见，第 {iteration} 轮迭代", items, budget)
    prompt = prompt + "\n\n" + _pack_note(manifest) + "\n"
    _finish_call(jdir, job, _call("main", cfg["effort_first"], "text"), prompt, pack, manifest)
    _legacy_prompt_copy(root, job, prompt)


# ---------------------------------------------------------------------------
# 运行状态
# ---------------------------------------------------------------------------


def _load_job(root: Path, report_id: str, job_id: str) -> tuple[Path, dict[str, Any]]:
    jdir = job_dir(root, report_id, job_id)
    job = _read_json(jdir / "job.json")
    if not isinstance(job, dict):
        raise FileNotFoundError(f"外审 job 不存在: {report_id}/{job_id}（先 prepare）")
    return jdir, job


def _read_status(jdir: Path) -> dict[str, Any]:
    data = _read_json(jdir / "status.json")
    return data if isinstance(data, dict) else {}


def _write_status(jdir: Path, data: dict[str, Any]) -> None:
    _write_json(jdir / "status.json", data)


def _process_alive(pid: int) -> bool:
    proc = _CHILDREN.get(pid)
    if proc is not None:
        if proc.poll() is None:
            return True
        _CHILDREN.pop(pid, None)  # 自己启动的后台进程用 poll 判断，退出后不会被僵尸状态骗过
        return False
    return er.pid_alive(pid)


def _command_has(pid: int, text: str) -> bool:
    """进程的命令行里有没有这段文字；查不了进程表时当作有。"""
    if os.name == "nt":
        return True
    try:
        proc = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return True
    return text in proc.stdout


def _runner_alive(status: dict[str, Any]) -> bool:
    """执行这个 job 的进程是否还在。

    后台进程的命令行里带着启动标记：进程号还在、命令行却对不上，说明进程号已被别的
    进程复用，原来的进程其实已经不在了。
    """
    pid = status.get("pid")
    if isinstance(pid, int):
        if not _process_alive(pid):
            return False
        token = status.get("launch_token")
        if not token or pid in _CHILDREN or pid == os.getpid():
            return True
        return _command_has(pid, str(token))
    launched = status.get("launched_epoch")
    return isinstance(launched, (int, float)) and time.time() - launched < RUNNER_GRACE_SECONDS


def _lock_is_stale(path: Path) -> bool:
    """锁文件的持有者已经不在（或锁放了太久）：可以清掉。"""
    try:
        holder = path.read_text(encoding="utf-8").strip()
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False  # 刚被释放，回去重试
    if holder.isdigit() and os.name != "nt" and not er.pid_alive(int(holder)):
        return True
    return age > LOCK_STALE_SECONDS


@contextmanager
def _job_lock(jdir: Path, timeout: float = 15.0) -> Iterator[None]:
    """job 级的短锁：只护住「看状态 → 改状态」这一小段，不在外审运行期间持有。"""
    path = jdir / ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _lock_is_stale(path):
                path.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise ExtReviewError(f"等待外审 job 锁超时: {jdir.name}")
            time.sleep(0.05)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        break
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _cleanup_engine(jdir: Path) -> None:
    """后台进程意外退出后，把它留下的外审引擎进程清掉，免得继续消耗额度。

    只在进程号对应的命令确实还是那个引擎时才动手，防止进程号被别的进程复用。
    """
    info = _read_json(jdir / "engine.pid")
    (jdir / "engine.pid").unlink(missing_ok=True)
    if not isinstance(info, dict) or not isinstance(info.get("pid"), int) or os.name == "nt":
        return
    pid = info["pid"]
    try:
        command = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return
    name = Path(str(info.get("executable") or "")).name
    if name and name in command:
        er.terminate_process_tree(pid)


def _stop_runner(jdir: Path, data: dict[str, Any]) -> bool:
    """停掉正在执行这个 job 的后台进程，连同它起的外审进程。返回是否真的停了一个在跑的进程。

    只停后台启动的那种：它的命令行里带着启动标记，认得准。前台执行的进程不归这里管。
    """
    stopped = False
    if data.get("state") == "running" and _runner_alive(data):
        pid = data.get("pid")
        if not isinstance(pid, int) or not data.get("launch_token") or pid == os.getpid():
            raise ExtReviewError(f"外审 job 正在启动，或由一个前台进程执行，不能中途覆盖或取消: {jdir.name}")
        er.terminate_process_tree(pid, proc=_CHILDREN.get(pid))
        _CHILDREN.pop(pid, None)
        stopped = True
    _cleanup_engine(jdir)
    return stopped


def _reconcile(jdir: Path, data: dict[str, Any]) -> dict[str, Any]:
    """状态还是 running 而进程已经不在：判为 failed / crashed。"""
    if data.get("state") != "running" or _runner_alive(data):
        return data
    fresh = _read_status(jdir)  # 进程可能刚写完最终状态就退出了，以盘上的为准
    if fresh.get("state") != "running":
        return fresh
    fresh.update(state="failed", reason="crashed", finished_at=st.now_iso(), message="后台进程已不在，状态仍是运行中")
    if isinstance(fresh.get("started_epoch"), (int, float)):
        fresh["seconds"] = round(time.time() - fresh["started_epoch"], 1)
    _cleanup_engine(jdir)
    _write_status(jdir, fresh)
    return fresh


def _status_view(root: Path, jdir: Path, job: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    state = data.get("state") or "pending"
    seconds = data.get("seconds")
    if state == "running" and isinstance(data.get("started_epoch"), (int, float)):
        seconds = round(time.time() - data["started_epoch"], 1)
    usage_data = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return {
        "job_id": job["job_id"],
        "kind": job["kind"],
        "round": job["round"],
        "state": state,
        "reason": data.get("reason"),
        "engine": job["engine"],
        "mode": job.get("mode") or "full",
        "attempts": [
            {k: a.get(k) for k in ("call", "effort", "status", "seconds", "reason", "schema") if k in a}
            for a in data.get("attempts") or []
            if isinstance(a, dict)
        ],
        "seconds": seconds,
        "pid": data.get("pid"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "input_bytes": data.get("input_bytes", job.get("input_bytes")),
        "usage": usage_data,
        "subsessions": data.get("subsessions"),
        # 以下是约定之外的补充信息
        "iteration": job.get("iteration"),
        "engine_state": data.get("engine_state") or job.get("engine_state"),
        "fallback_of": data.get("fallback_of"),
        "message": data.get("message"),
        "completed_calls": list(data.get("completed_calls") or []),
        "blind_read_spec": data.get("blind_read_spec"),
        "output": _rel(root, jdir / "output.md") if state == "success" and (jdir / "output.md").is_file() else None,
        "dir": job.get("dir") or _rel(root, jdir),
    }


def status(root: Path, report_id: str, job_id: str) -> dict:
    """job 的当前状态；进程已不在而状态还是 running 的，判为 failed / crashed。"""
    root = Path(root)
    jdir, job = _load_job(root, report_id, job_id)
    return _status_view(root, jdir, job, _reconcile(jdir, _read_status(jdir)))


# ---------------------------------------------------------------------------
# 启动与执行
# ---------------------------------------------------------------------------


def launch(root: Path, report_id: str, job_id: str, *, detach: bool = True) -> dict:
    """启动外审。detach=True 时起一个脱离当前进程组的后台进程，立即返回
    {"job_id", "pid", "started_at"}；detach=False 时前台跑完再返回 status()。

    同一个 job 已在跑时不重复启动（返回里带 already_running=True）；已经成功跑完的 job
    也不重跑（already_done=True）——要重跑先重新 prepare。失败过的 job 再次启动时，
    已经成功的调用（如盲提取）不重跑。
    """
    root = Path(root)
    jdir, job = _load_job(root, report_id, job_id)
    if not detach:
        return _run_job(root, report_id, job_id)
    with _job_lock(jdir):
        current = _reconcile(jdir, _read_status(jdir))
        if current.get("state") == "running":
            return {"job_id": job_id, "pid": current.get("pid"), "started_at": current.get("started_at"), "already_running": True}
        if _is_done(jdir, current):
            return {"job_id": job_id, "pid": None, "started_at": current.get("started_at"), "already_done": True}
        token = uuid.uuid4().hex[:12]
        started_at = st.now_iso()
        carried = {k: current[k] for k in ("completed_calls", "attempts") if current.get("state") == "failed" and k in current}
        earlier = current.get("first_epoch") or current.get("started_epoch")
        if current.get("state") == "failed" and isinstance(earlier, (int, float)):
            carried["first_epoch"] = earlier  # 续跑：用量的时间窗从第一次启动算起
        _write_status(
            jdir,
            {
                **carried,
                "job_id": job_id,
                "state": "running",
                "reason": None,
                "pid": None,
                "launch_token": token,
                "launched_epoch": time.time(),
                "started_at": started_at,
                "started_epoch": time.time(),
                "finished_at": None,
                "engine_state": job.get("engine_state"),
            },
        )
        # 后台进程在插件根下启动：-m 先从当前目录找模块，这样工作区里即使另有一个叫 tools 的
        # 目录也不会挡住本模块。工作区根经环境变量传过去，外审引擎自己的工作目录另由执行时指定。
        env = dict(os.environ)
        env["REPORT_REPRODUCE_ROOT"] = str(root.resolve())
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(PLUGIN_ROOT), env.get("PYTHONPATH", "")) if p)
        command = [sys.executable, "-m", "tools.flowlib.extreview", "run", report_id, job_id, "--token", token]
        options: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        }
        try:
            with (jdir / "stdout.log").open("ab") as log:
                proc = subprocess.Popen(command, cwd=str(PLUGIN_ROOT), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options)
        except OSError as exc:
            failed = _read_status(jdir)
            failed.update(state="failed", reason="failed", message=f"后台进程没能启动: {exc}"[:300], finished_at=st.now_iso())
            _write_status(jdir, failed)
            raise ExtReviewError(f"外审后台进程没能启动: {exc}") from exc
        _CHILDREN[proc.pid] = proc
        latest = _read_status(jdir)
        if latest.get("launch_token") == token and latest.get("pid") is None:
            latest["pid"] = proc.pid
            _write_status(jdir, latest)
    return {"job_id": job_id, "pid": proc.pid, "started_at": started_at}


def run_job(root: Path, report_id: str, job_id: str) -> dict:
    """前台执行一个 job 的全部调用，写 status.json，返回最终 status()。"""
    return _run_job(Path(root), report_id, job_id)


def cancel(root: Path, report_id: str, job_id: str) -> dict:
    """停掉一个在后台运行的 job：状态记为 failed / failed，message 注明是取消。没在跑时原样返回 status()。"""
    root = Path(root)
    jdir, job = _load_job(root, report_id, job_id)
    with _job_lock(jdir):
        current = _reconcile(jdir, _read_status(jdir))
        if current.get("state") == "running" and _stop_runner(jdir, current):
            current = _read_status(jdir)  # 它可能恰好在被停掉之前写完了最终状态
            if current.get("state") == "running":
                current.update(state="failed", reason="failed", message="已取消", finished_at=st.now_iso())
                if isinstance(current.get("started_epoch"), (int, float)):
                    current["seconds"] = round(time.time() - current["started_epoch"], 1)
                _write_status(jdir, current)
    return _status_view(root, jdir, job, current)


def _validate_output(path: Path, mode: str) -> Optional[str]:
    """调用成功后的产物是否可用；不可用时返回原因。"""
    try:
        text = _read_text(path)
    except OSError:
        return "产物文件不存在"
    if not text.strip():
        return "产物为空"
    if mode == "review" and not parse_review_text(text)["ok"]:
        return "找不到含 findings 的 JSON，也没有 VERDICT 行"
    return None


def _run_call(root: Path, jdir: Path, job: dict, call: dict, record: Any) -> tuple[bool, Optional[str], str]:
    """执行一次调用（至多重试一次）。返回（是否成功, 失败原因, 说明）。"""
    engine = job["engine"]
    effort = call["effort"]
    schema: Optional[Path] = jdir / call["schema"] if call.get("schema") else None
    request = jdir / f".request_{call['name']}.md"
    pack_path = jdir / call["input"]
    _write_text(request, _request_text(_read_text(jdir / call["prompt"]), _read_text(pack_path) if pack_path.is_file() else None))
    output = jdir / call["output"]
    last_status, detail = "failed", ""
    try:
        for attempt in (1, 2):
            output.unlink(missing_ok=True)
            result = er.run_review(
                engine,
                request,
                output,
                root,
                job["timeout_seconds"],
                effort=effort,
                model=job.get("model"),
                schema_path=schema,
                last_message_path=jdir / f"last_message_{call['name']}.txt",
                log_path=jdir / "stdout.log",
                pid_path=jdir / "engine.pid",
            )
            last_status, detail = result.status, result.reason
            unparseable = False
            if result.status == "success":
                problem = _validate_output(output, call["validate"])
                if problem:
                    unparseable = True
                    last_status, detail = "failed", f"unparseable_output: {problem}"
                    if output.is_file():
                        output.replace(jdir / f"rejected_{call['name']}_{attempt}.md")
            record(
                {
                    "call": call["name"],
                    "effort": effort,
                    "status": last_status,
                    "seconds": result.duration_seconds,
                    "reason": detail,
                    "schema": schema is not None,
                    "meta": result.meta,
                }
            )
            if last_status == "success":
                return True, None, ""
            if last_status in NO_RETRY or attempt == 2 or detail == "context_overflow":
                break  # 输入超出引擎的上下文窗口时，原样重试只会再失败一次
            if last_status == "timeout":
                effort = downgrade_effort(engine, effort)  # 降一档推理强度，输入原样
            elif last_status == "failed" and not unparseable:
                schema = None  # 输入原样；去掉输出约束，防止失败是约束本身被引擎拒绝
    finally:
        request.unlink(missing_ok=True)
        (jdir / f"last_message_{call['name']}.txt").unlink(missing_ok=True)
    return False, last_status, detail


def _assemble(root: Path, jdir: Path, job: dict) -> None:
    """把各次调用的原件拼成这一轮的原件 output.md。"""
    calls = {c["name"]: c for c in job["calls"]}
    if "blind" in calls and "review" in calls:
        text = assemble_spec_output(_read_text(jdir / calls["blind"]["output"]), _read_text(jdir / calls["review"]["output"]))
    else:
        text = _read_text(jdir / calls["main"]["output"])
    _write_text(jdir / "output.md", text if text.endswith("\n") else text + "\n")
    if job["kind"] == "second_opinion":
        shutil.copyfile(jdir / "output.md", _iter_dir(root, job["report_id"], job["iteration"]) / "second_opinion_external.md")


def assemble_spec_output(blind_text: str, review_text: str) -> str:
    """两次调用的输出按现行格式拼成一个原件：标记行包住盲提取块，后面跟结论 JSON。"""
    blind = "\n".join(line for line in blind_text.strip().splitlines() if line.strip() not in (BLIND_BEGIN, BLIND_END))
    data, _source = extract_json_object(review_text)
    conclusion = "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```" if data is not None else review_text.strip()
    return f"{BLIND_BEGIN}\n{blind}\n{BLIND_END}\n\n{conclusion}\n"


def _is_done(jdir: Path, data: dict[str, Any]) -> bool:
    return data.get("state") == "success" and (jdir / "output.md").is_file()


def _run_job(root: Path, report_id: str, job_id: str, token: Optional[str] = None) -> dict:
    jdir, job = _load_job(root, report_id, job_id)
    with _job_lock(jdir):
        previous = _reconcile(jdir, _read_status(jdir))
        mine = token is not None and previous.get("launch_token") == token
        if (previous.get("state") == "running" and not mine) or _is_done(jdir, previous):
            return _status_view(root, jdir, job, previous)  # 别的进程正在跑，或已经跑完：不重复执行
        resumable = previous.get("state") == "failed" or mine
        data: dict[str, Any] = {
            "job_id": job_id,
            "state": "running",
            "reason": None,
            "message": None,
            "pid": os.getpid(),
            "launch_token": token,
            "started_at": previous.get("started_at") if mine else st.now_iso(),
            "started_epoch": previous.get("started_epoch") if mine else time.time(),
            "finished_at": None,
            "engine_state": job.get("engine_state"),
            "attempts": list(previous.get("attempts") or []) if resumable else [],
            "completed_calls": list(previous.get("completed_calls") or []) if resumable else [],
            "input_bytes": job.get("input_bytes"),
            "usage": None,
            "subsessions": None,
        }
        # 失败后续跑：用量的时间窗从第一次启动算起，之前跑完的调用（如盲提取）也算在内
        earlier = previous.get("first_epoch") or previous.get("started_epoch")
        data["first_epoch"] = earlier if resumable and isinstance(earlier, (int, float)) else data["started_epoch"]
        _write_status(jdir, data)
    begun = data["first_epoch"]

    def record(attempt: dict[str, Any]) -> None:
        data["attempts"].append(attempt)
        _write_status(jdir, data)

    def finish(state: str, reason: Optional[str], message: Optional[str]) -> dict:
        data.update(state=state, reason=reason, message=message, finished_at=st.now_iso(), seconds=round(time.time() - data["started_epoch"], 1))
        try:
            data.update(_collect_usage(root, job, jdir, data, begun, time.time()))
        except Exception as exc:  # noqa: BLE001 - 用量取不到不影响外审结果
            data.setdefault("usage_error", f"{type(exc).__name__}: {exc}"[:200])
        _write_status(jdir, data)
        return _status_view(root, jdir, job, data)

    try:
        for call in job["calls"]:
            name = call["name"]
            if name in data["completed_calls"] and (jdir / call["output"]).is_file():
                continue  # 上次已经跑完的调用（如盲提取）不重跑
            if call.get("deferred_input"):
                blind_call = next(c for c in job["calls"] if c["name"] == "blind")
                pack, manifest = _build_spec_review_input(root, job, jdir, call, _read_text(jdir / blind_call["output"]))
                _write_text(jdir / call["input"], pack)
                call["manifest"], call["input_bytes"] = manifest, _nbytes(pack)
                call["bytes"] = _nbytes(_request_text(_read_text(jdir / call["prompt"]), pack))
                _write_json(jdir / "job.json", {**job, "input_bytes": sum(c.get("bytes", 0) for c in job["calls"])})
                data["input_bytes"] = sum(c.get("bytes", 0) for c in job["calls"])
            ok, reason, detail = _run_call(root, jdir, job, call, record)
            if not ok:
                return finish("failed", reason, f"调用 {name} 未成功: {detail}")
            data["completed_calls"].append(name)
            _write_status(jdir, data)
        _assemble(root, jdir, job)
    except Exception as exc:  # noqa: BLE001 - 后台进程里的任何异常都要落到状态文件里，不能无声消失
        return finish("failed", "failed", f"{type(exc).__name__}: {exc}"[:500])
    return finish("success", None, None)


# ---------------------------------------------------------------------------
# 用量：取自外审引擎自己的会话记录
# ---------------------------------------------------------------------------

_READ_COMMAND_RE = re.compile(r"\b(?:sed|nl|cat|head|tail|rg|grep|less|more|awk|bat|wc)\b")
_SPEC_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])spec\.md")
_TAG_RE = re.compile(r"\s*<!-- extreview \S+/\S+ (\S+) -->")


def _user_text(record: dict[str, Any], payload: dict[str, Any]) -> str:
    """一条记录如果是用户消息，返回它的文字；不是则返回空串。"""
    if record.get("type") == "event_msg" and payload.get("type") == "user_message":
        return str(payload.get("message") or "")
    if record.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
        content = payload.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text") or "") for part in content if isinstance(part, dict))
    return ""


def _scan_codex_session(path: Path) -> dict[str, Any]:
    """一份 Codex 会话记录：它是哪次调用的（看哪条用户消息以本模块的标记开头）、读文件命令
    的次数、工具调用有没有碰过 spec.md。

    归属只认用户消息开头的标记——会话中途读到别的调用的提示词文件（里面也有标记）不算。
    """
    reads = 0
    spec_hits = 0
    nonce: Optional[str] = None
    for line in usage._iter_lines(path):
        if "_call" not in line and "extreview" not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if not isinstance(payload, dict):
            continue
        if nonce is None:
            tag = _TAG_RE.match(_user_text(record, payload))
            if tag:
                nonce = tag.group(1)
                continue
        if record.get("type") != "response_item":
            continue
        ptype = str(payload.get("type") or "")
        if ptype in usage.CODEX_TOOL_TYPES:
            text = json.dumps([payload.get(k) for k in ("name", "input", "arguments", "action")], ensure_ascii=False)
            reads += bool(_READ_COMMAND_RE.search(text))
            spec_hits += bool(_SPEC_PATH_RE.search(text))
        elif ptype.endswith("_call_output"):
            spec_hits += bool(re.search(r"spec/spec\.md[:\-]\d+", json.dumps(payload.get("output"), ensure_ascii=False)))
    return {"nonce": nonce, "read_commands": reads, "spec_hits": spec_hits}


def _codex_usage(root: Path, job: dict, begun: float, ended: float, home: Optional[Path] = None) -> dict[str, Any]:
    """按提示词首行的标记在 Codex 会话记录里认出这个 job 的会话；认不出就不算。"""
    low = datetime.fromtimestamp(begun) - timedelta(minutes=5)
    high = datetime.fromtimestamp(ended) + timedelta(minutes=5)
    nonces = {c["nonce"]: c["name"] for c in job["calls"] if c.get("nonce")}
    candidates = [
        p for p in usage.find_codex_sessions(low, high, home) if (when := usage.codex_session_time(p)) is None or low <= when <= high
    ]
    sessions = [usage.parse_codex_session(p, needles=list(nonces)) for p in candidates]
    root_real = os.path.realpath(root)
    scans: dict[str, dict[str, Any]] = {}

    def scan_of(session: Any) -> dict[str, Any]:
        if session.path not in scans:
            scans[session.path] = _scan_codex_session(Path(session.path))
        return scans[session.path]

    mains = [
        s
        for s in sessions
        if s.role == "main"
        and s.cwd
        and os.path.realpath(s.cwd) == root_real
        and any(s.mention_counts.get(n) for n in nonces)
        and scan_of(s)["nonce"] in nonces
    ]
    if not mains:
        return {}
    call_of = {s.session_id: nonces[scan_of(s)["nonce"]] for s in mains}
    subs: list[Any] = []
    grew = True
    while grew:  # 子会话跟着父会话走
        grew = False
        for s in sessions:
            if s.session_id not in call_of and s.parent_id in call_of:
                call_of[s.session_id] = call_of[s.parent_id]
                subs.append(s)
                grew = True
    total = usage.Usage()
    per_call: dict[str, dict[str, Any]] = {}
    read_commands = 0
    blind_hits: Optional[int] = None
    for s in [*mains, *subs]:
        total = total.add(s.usage)
        scan = scan_of(s)
        read_commands += scan["read_commands"]
        slot = per_call.setdefault(call_of[s.session_id], {"sessions": 0, "total_input": 0, "output": 0, "read_commands": 0})
        slot["sessions"] += 1
        slot["total_input"] += s.usage.total_input
        slot["output"] += s.usage.output
        slot["read_commands"] += scan["read_commands"]
        if call_of[s.session_id] == "blind":
            blind_hits = (blind_hits or 0) + scan["spec_hits"]
    usage_data = {
        "source": "codex_sessions",
        "sessions": len(mains),
        "subsessions": len(subs),
        "read_commands": read_commands,
        "model": mains[0].model,
        "effort": mains[0].effort,
        "per_call": per_call,
        **total.to_dict(),
    }
    out: dict[str, Any] = {"usage": usage_data, "subsessions": len(subs)}
    if "blind" in nonces.values():
        out["blind_read_spec"] = None if blind_hits is None else blind_hits > 0
    return out


def _claude_usage(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Claude 不留会话记录，用量取自每次调用的结果信封；子会话数与读文件次数取不到。"""
    keys = {"uncached_input": "input_tokens", "cache_write": "cache_creation_input_tokens", "cache_read": "cache_read_input_tokens", "output": "output_tokens"}
    total = {k: 0 for k in keys}
    turns = 0
    cost = 0.0
    seen = False
    for attempt in attempts:
        meta = attempt.get("meta") if isinstance(attempt.get("meta"), dict) else {}
        envelope = meta.get("usage") if isinstance(meta.get("usage"), dict) else None
        if envelope is None:
            continue
        seen = True
        for key, source in keys.items():
            value = envelope.get(source)
            total[key] += int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
        turns += int(meta.get("num_turns") or 0)
        cost += float(meta.get("total_cost_usd") or 0.0)
    if not seen:
        return {}
    return {
        "usage": {
            "source": "claude_envelope",
            **total,
            "total_input": total["uncached_input"] + total["cache_write"] + total["cache_read"],
            "calls": turns,
            "total_cost_usd": round(cost, 4),
            "read_commands": None,
            "subsessions": None,
        },
        "subsessions": None,
    }


def _collect_usage(root: Path, job: dict, jdir: Path, data: dict[str, Any], begun: float, ended: float) -> dict[str, Any]:
    if job["engine"] == "codex":
        return _codex_usage(root, job, begun, ended)
    return _claude_usage(data.get("attempts") or [])


# ---------------------------------------------------------------------------
# 同宿主替身
# ---------------------------------------------------------------------------

_REVIEW_FORMAT = (
    "一个 JSON 对象（可以放在标注 json 的代码块里），结构按上面提示词的「输出契约」：必须有 `verdict` 与 `findings`"
    "（没有问题时 `findings` 为空数组）。"
)


def fallback_task(root: Path, report_id: str, job_id: str) -> dict:
    """同宿主替身用：返回 {"prompt_file": 相对路径, "output": 相对路径}。

    内核据此派一个宿主的通用子代理，读 prompt_file 并把结论写到 output。spec 的整体审查里，
    盲提取如果已经由外审引擎完成，替身只做第二步，盲提取块沿用外审引擎的产出。
    """
    root = Path(root)
    jdir, job = _load_job(root, report_id, job_id)
    current = _reconcile(jdir, _read_status(jdir))
    if current.get("state") == "running":
        raise ExtReviewError(f"外审 job 还在运行，不能改派替身: {job_id}")
    if current.get("state") == "success" and current.get("engine_state") != "same_host_fallback":
        raise ExtReviewError(f"外审 job 已成功完成，不需要替身: {job_id}")
    calls = {c["name"]: c for c in job.get("calls") or []}
    if not calls:
        raise ExtReviewError(f"这个 job 是导入的原件，没有可以改派的调用: {job_id}")
    rel = lambda name: _rel(root, jdir / name)  # noqa: E731
    output_rel = rel("output_fallback.md")
    blind_done = "blind" in calls and "blind" in (current.get("completed_calls") or []) and (jdir / calls["blind"]["output"]).is_file()

    if "blind" in calls and not blind_done:
        blind_items = _items(root, _review_file_list(root, report_id, "spec", "blind", None, []))
        review_pack, _manifest = build_pack(
            "spec 审查点，第二步的材料（规格书与原文）", _items(root, calls["review"].get("files") or []), job["budget_bytes"]
        )
        _write_text(jdir / "input_fallback_review.md", review_pack)
        steps = [
            f"1. **盲提取**。读 `{rel(calls['blind']['prompt'])}` 并严格照做，材料只用 `{rel(calls['blind']['input'])}`"
            f"（共 {sum(1 for i in blind_items if i.text is not None)} 份文件的带行号全文）。这一步做完之前，"
            f"不得打开 `{rel('input_fallback_review.md')}`、`{rel(calls['review']['prompt'])}`，也不得打开该提示词「禁读清单」里的任何文件。",
            "2. 把盲提取清单定稿。定稿后不得因为后面读到的内容回头修改它。",
            f"3. **差异比对与结构化审查**。读 `{rel(calls['review']['prompt'])}` 并严格照做；其中「盲提取清单」指你在第 1 步写下的那份，"
            f"其余材料的带行号全文在 `{rel('input_fallback_review.md')}`。",
        ]
        fmt = (
            f"先是盲提取块：单独一行 `{BLIND_BEGIN}`，接着是第 1 步定稿的清单，再单独一行 `{BLIND_END}`；"
            "然后是第 3 步的结论——" + _REVIEW_FORMAT
        )
    elif "blind" in calls:
        pack, _manifest = _build_spec_review_input(root, job, jdir, calls["review"], _read_text(jdir / calls["blind"]["output"]))
        _write_text(jdir / calls["review"]["input"], pack)
        steps = [
            "1. 盲提取已经由外部审查引擎完成，你**不要**重做，也不要改动它。",
            f"2. 读 `{rel(calls['review']['prompt'])}` 并严格照做；盲提取清单和其余材料的带行号全文都在 `{rel(calls['review']['input'])}`。",
        ]
        fmt = "只写第 2 步的结论（盲提取块由内核拼上）——" + _REVIEW_FORMAT
    else:
        call = calls["main"]
        steps = [f"1. 读 `{rel(call['prompt'])}` 并严格照做；它所说的「输入包」（或「差量复审包」）在 `{rel(call['input'])}`。"]
        fmt = "按该提示词「输出契约」的格式写出完整结论。" if job["kind"] == "second_opinion" else _REVIEW_FORMAT
    prompt = render(
        _plugin_template("fallback.md"),
        {"job_id": job_id, "workspace": _ws(report_id), "output_path": output_rel, "steps_block": "\n".join(steps), "format_block": fmt},
    )
    _write_text(jdir / "prompt_fallback.md", prompt)
    (jdir / "output_fallback.md").unlink(missing_ok=True)
    return {"prompt_file": rel("prompt_fallback.md"), "output": output_rel}


def accept_fallback(root: Path, report_id: str, job_id: str) -> dict:
    """替身写完后调用：校验 output 可解析，把这一轮标为成功（engine_state 记 same_host_fallback）。"""
    root = Path(root)
    jdir, job = _load_job(root, report_id, job_id)
    source = jdir / "output_fallback.md"
    if not source.is_file() or not _read_text(source).strip():
        raise ExtReviewError(f"替身没有交回结论: {_rel(root, source)}")
    text = _read_text(source)
    calls = {c["name"]: c for c in job.get("calls") or []}
    with _job_lock(jdir):
        current = _reconcile(jdir, _read_status(jdir))
        if current.get("state") == "running":
            raise ExtReviewError(f"外审 job 还在运行，不能收替身的结论: {job_id}")
        if current.get("state") == "success" and current.get("engine_state") != "same_host_fallback":
            raise ExtReviewError(f"外审 job 已由外审引擎完成，不收替身的结论: {job_id}")
        if job["kind"] != "second_opinion":
            if not parse_review_text(text)["ok"]:
                raise ExtReviewError(f"替身交回的结论无法解析（要含 findings 的 JSON，或 VERDICT 行）: {_rel(root, source)}")
            if "blind" in calls and split_blind_block(text) is None:
                blind_output = jdir / calls["blind"]["output"]
                if "blind" not in (current.get("completed_calls") or []) or not blind_output.is_file():
                    raise ExtReviewError(f"替身交回的结论缺少盲提取块（{BLIND_BEGIN} … {BLIND_END}）")
                text = assemble_spec_output(_read_text(blind_output), text)
        _write_text(jdir / "output.md", text if text.endswith("\n") else text + "\n")
        if job["kind"] == "second_opinion":
            shutil.copyfile(jdir / "output.md", _iter_dir(root, report_id, job["iteration"]) / "second_opinion_external.md")
        current.update(
            job_id=job_id,
            state="success",
            fallback_of=current.get("reason") or current.get("fallback_of"),
            reason=None,
            message=None,
            engine_state="same_host_fallback",
            finished_at=st.now_iso(),
        )
        current.setdefault("attempts", [])
        current.setdefault("started_at", current["finished_at"])
        _write_status(jdir, current)
    return _status_view(root, jdir, job, current)


# ---------------------------------------------------------------------------
# 合并成规范文件、占位、导入旧原件
# ---------------------------------------------------------------------------


def _public_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": finding["id"],
        "severity": finding["severity"],
        "title": finding["title"],
        "detail": finding.get("description") or "",
        "location": finding.get("location") or "",
        "first_round": finding.get("first_round"),
        "last_round": finding.get("last_round"),
        "open": bool(finding.get("open")),
        "category": finding.get("category") or "",
        "suggestion": finding.get("suggestion") or "",
    }


def _ledger(kind: str, engine_state: str, verdict: Optional[str], findings: list[dict[str, Any]], raw: str, reason: Optional[str] = None) -> dict[str, Any]:
    entry = {"checkpoint": kind, "engine": engine_state, "verdict": verdict, **_counts(findings), "raw": raw}
    if reason:
        entry["reason"] = reason
    return entry


def collect(root: Path, report_id: str, kind: str, *, engine_state: str) -> dict:
    """把这个审查点已完成的各轮原件合并成规范文件并返回摘要。

    写 workspace/<id>/audit/<kind>_audit_external.md；spec 另写 spec/spec_external.md。
    second_opinion 不合并、不入台账，只返回最近一份原件的路径。
    """
    root = Path(root)
    if kind not in KINDS:
        raise ExtReviewError(f"kind 必须是 {KINDS} 之一，收到: {kind}")
    if engine_state not in ENGINE_STATES:
        raise ExtReviewError(f"engine_state 必须是 {ENGINE_STATES} 之一，收到: {engine_state}")
    if kind == "second_opinion":
        return _collect_second_opinion(root, report_id)
    merged = merge_rounds(root, report_id, kind)
    if not merged["rounds"]:
        raise ExtReviewError(f"{kind} 审查点还没有已完成的外审轮次，无从合并")
    findings = merged["findings"]
    counts = _counts(findings)
    open_count = sum(1 for f in findings if f["open"])
    path = canonical_path(root, report_id, kind)
    raw = _rel(root, path)
    document = {
        "checkpoint": kind,
        "verdict": merged["verdict"],
        "format": CANONICAL_FORMAT,
        "generated_by": "tools/flowlib/extreview.py：各轮外审原件的并集，由内核生成，不要手工修改",
        "engine_state": engine_state,
        "summary": (
            f"共 {len(merged['rounds'])} 轮；意见并集 {len(findings)} 条"
            f"（critical {counts['critical']} / major {counts['major']} / minor {counts['minor']}），其中最新一轮仍在列 {open_count} 条。"
        ),
        "counts": {**counts, "open": open_count},
        "rounds": merged["rounds"],
        "dimensions_checked": merged["dimensions_checked"],
        "diffs": merged["diffs"],
        "findings": findings,
    }
    _write_if_changed(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    if kind == "spec":
        spec_dir = root / _ws(report_id) / "spec"
        if merged["blind"] is not None:
            _write_if_changed(spec_dir / "spec_external.md", merged["blind"]["text"].rstrip("\n") + "\n")
        elif not cg._external_spec_path(spec_dir).is_file():
            # 各轮原件里都没有盲提取块（如收编的旧汇总），又没有现成的盲提取文件：如实留一份说明
            _write_text(spec_dir / "spec_external.md", "# 外部盲提取清单\n\n（已完成的各轮外审原件里没有盲提取块，本文件是占位）\n")
    return {
        "verdict": merged["verdict"],
        "counts": counts,
        "findings": [_public_finding(f) for f in findings],
        "raw": raw,
        "rounds": len(merged["rounds"]),
        "ledger": _ledger(kind, engine_state, merged["verdict"], findings, raw),
    }


def _collect_second_opinion(root: Path, report_id: str) -> dict:
    base = root / _ws(report_id) / "iterations"
    done = [
        path
        for path in (sorted(base.glob("iter_*/external")) if base.is_dir() else [])
        if (_read_json(path / "status.json") or {}).get("state") == "success" and (path.parent / "second_opinion_external.md").is_file()
    ]
    raw = _rel(root, done[-1].parent / "second_opinion_external.md") if done else None
    return {"verdict": None, "counts": {s: 0 for s in SEVERITIES}, "findings": [], "raw": raw, "rounds": len(done), "ledger": None}


def skip(root: Path, report_id: str, kind: str, reason: str) -> dict:
    """不跑外审（按档位未触发，或降级链走到底）：写占位文件，返回与 collect 同形的结果。

    占位的规范文件可解析、意见数为 0；spec 另落 spec_external.md 与 extract_diff.md，
    code / result 保证 audit_responses.md 存在。这个审查点如果已有完成的外审轮次，不覆盖
    已有成果，按已有轮次返回。
    """
    root = Path(root)
    if kind not in REVIEW_KINDS:
        raise ExtReviewError(f"只有 {REVIEW_KINDS} 可以落 skipped 占位，收到: {kind}")
    reason = _text(reason) or "未说明原因"
    _adopt_legacy(root, report_id, kind, _load_state(root, report_id))  # 旧案例已有的外审成果不能被占位覆盖
    done = completed_rounds(root, report_id, kind)
    if done:
        existing = _read_json(canonical_path(root, report_id, kind))
        engine_state = existing.get("engine_state") if isinstance(existing, dict) and existing.get("format") == CANONICAL_FORMAT else done[-1]["engine_state"]
        result = collect(root, report_id, kind, engine_state=engine_state if engine_state in ENGINE_STATES else "skipped")
        result["skipped_round_reason"] = reason
        if kind == "spec":
            result["unruled_diffs"] = write_extract_diff(root, report_id)["unruled"]
        return result
    path = canonical_path(root, report_id, kind)
    raw = _rel(root, path)
    _write_json(
        path,
        {
            "checkpoint": kind,
            "verdict": "skipped",
            "format": CANONICAL_FORMAT,
            "generated_by": "tools/flowlib/extreview.py：本审查点的外审未执行，本文件是占位",
            "engine_state": "skipped",
            "reason": reason,
            "summary": f"外审未执行：{reason}",
            "counts": {**{s: 0 for s in SEVERITIES}, "open": 0},
            "rounds": [],
            "dimensions_checked": [],
            "diffs": [],
            "findings": [],
        },
    )
    result: dict[str, Any] = {
        "verdict": "skipped",
        "counts": {s: 0 for s in SEVERITIES},
        "findings": [],
        "raw": raw,
        "rounds": 0,
        "ledger": _ledger(kind, "skipped", "skipped", [], raw, reason),
    }
    if kind == "spec":
        external = root / _ws(report_id) / "spec" / "spec_external.md"
        if not external.is_file() or SKIP_NOTE in _read_text(external):
            _write_text(external, f"# 外部盲提取清单\n\n{SKIP_NOTE}\n\n- 原因：{reason}\n")
        result["unruled_diffs"] = write_extract_diff(root, report_id)["unruled"]  # 内审意见仍要逐条裁决
    write_responses(root, report_id, kind)
    return result


def _is_own_canonical(path: Path) -> bool:
    data = _read_json(path)
    return isinstance(data, dict) and data.get("format") == CANONICAL_FORMAT


def _adopt_legacy(root: Path, report_id: str, kind: str, state: Optional[dict[str, Any]] = None) -> Optional[str]:
    """把不是本模块生成的规范文件收编为第 0 轮，返回收编出的 job 编号；不需要收编时返回 None。

    旧案例手写的各轮汇总、执行卡驱动的阶段里宿主写的规范文件都属于这种。不收编的话，下一轮
    合并会把它覆盖掉：旧意见从规范文件里消失，回应表里对应的行被当成过期行删掉，新一轮的编号
    还会与旧行撞号。旧文件没有逐轮的在列信息，哪些意见已经闭环按回应表里手工维护的「复核」
    列认（pass 即已闭环）。
    """
    if completed_rounds(root, report_id, kind):
        return None
    audit_dir = Path(root) / _ws(report_id) / "audit"
    path = cg._external_audit_path(audit_dir, kind)
    if not path.is_file() or _is_own_canonical(path):
        return None
    parsed = parse_review_text(_read_text(path))
    if not parsed["ok"] or parsed["verdict"] == "skipped":
        return None  # 解析不了的、旧流程留下的 skipped 占位，都没有可保留的外审成果
    letter = ID_LETTER[kind]
    closed = [
        cid
        for row in cg._parse_audit_responses(audit_dir / "audit_responses.md", f"CDX-{letter}-")
        for cid in [_canon_id(cg._row_id(row, r"^CDX-[A-Z]-"), letter)[0]]
        if cid and cg._row_get(row, "复核").strip().lower().startswith("pass")  # 旧表里也有「pass（外部增量复核）」这样的写法
    ]
    ledger = next(
        (e for e in reversed((state or {}).get("external_reviews") or []) if isinstance(e, dict) and e.get("checkpoint") == kind), {}
    )
    engine_state = {"codex": "codex_external", "claude": "claude_external"}.get(str(ledger.get("engine")), str(ledger.get("engine")))
    if engine_state not in ("codex_external", "claude_external", "same_host_fallback"):
        engine_state = "codex_external"
    return import_round(root, report_id, kind, 0, path, engine_state=engine_state, closed=closed)["job_id"]


def import_round(
    root: Path,
    report_id: str,
    kind: str,
    round_no: int,
    source: Path,
    *,
    engine_state: str = "codex_external",
    mode: str = "full",
    closed: Optional[Iterable[str]] = None,
) -> dict:
    """从既有原件导入某一轮（供旧案例迁移与测试用）：原件原样存为这一轮的 output.md。

    原件可以是 JSON，也可以是退化的 markdown 表格；导入的轮次没有文件快照，下一轮会整体重审。
    原件如果是多轮意见的汇总（没有逐轮的在列信息），用 closed 给出其中已经闭环的意见编号，
    合并时它们不算这一轮在列。
    """
    root = Path(root)
    if kind not in REVIEW_KINDS:
        raise ExtReviewError(f"只能导入 {REVIEW_KINDS} 的原件，收到: {kind}")
    if engine_state not in ENGINE_STATES:
        raise ExtReviewError(f"engine_state 必须是 {ENGINE_STATES} 之一，收到: {engine_state}")
    text = _read_text(Path(source))
    if not parse_review_text(text)["ok"]:
        raise ExtReviewError(f"原件无法解析为外审结论: {source}")
    job_id = job_id_for(kind, round_no)
    jdir = job_dir(root, report_id, job_id)
    _reset_job_dir(jdir)
    now = st.now_iso()
    job = {
        "format": JOB_FORMAT,
        "job_id": job_id,
        "kind": kind,
        "round": round_no,
        "iteration": None,
        "report_id": report_id,
        "engine": engine_state.split("_", 1)[0] if engine_state.endswith("_external") else None,
        "engine_state": engine_state,
        "host": None,
        "mode": mode,
        "mode_reason": "imported",
        "imported_from": str(source),
        "closed": sorted({cid for cid in (_canon_id(c, ID_LETTER[kind])[0] for c in closed or []) if cid}),
        "calls": [],
        "input_bytes": None,
        "dir": _rel(root, jdir),
        "created_at": now,
        "warnings": [],
    }
    _write_json(jdir / "job.json", job)
    _write_text(jdir / "output.md", text if text.endswith("\n") else text + "\n")
    _write_status(jdir, {"job_id": job_id, "state": "success", "reason": None, "engine_state": engine_state, "attempts": [], "started_at": now, "finished_at": now, "imported": True})
    return status(root, report_id, job_id)


# ---------------------------------------------------------------------------
# markdown 表格的按行改写（回应表与差异裁决表共用）
# ---------------------------------------------------------------------------

_SEP_RE = re.compile(r"^\|[\s:-]+(\|[\s:-]+)*\|\s*$")


def _is_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1


def _split_cells(line: str) -> list[str]:
    inner = line.strip()[1:-1]
    return [part.strip().replace("\\|", "|") for part in re.split(r"(?<!\\)\|", inner)]


def _cell(value: Any) -> str:
    """单元格内容：压成一行，竖线转义。"""
    return re.sub(r"\s+", " ", _text(value)).replace("\\|", "|").replace("|", "\\|")


def _join_cells(cells: list[Any]) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _scan_tables(lines: list[str]) -> list[dict[str, Any]]:
    """文中的表格：表头行下标、列名、数据行下标（识别口径同 check_gates.parse_markdown_table_rows）。"""
    tables: list[dict[str, Any]] = []
    i, n = 0, len(lines)
    while i < n:
        if _is_row(lines[i]) and i + 1 < n and _SEP_RE.match(lines[i + 1].strip()):
            rows: list[int] = []
            j = i + 2
            while j < n and _is_row(lines[j]):
                rows.append(j)
                j += 1
            tables.append({"header": i, "headers": _split_cells(lines[i]), "rows": rows})
            i = j
            continue
        i += 1
    return tables


def _column(headers: list[str], *keywords: str) -> Optional[int]:
    """按列名找列：先精确，再退化为「列名含全部关键词」（同 check_gates._row_get）。"""
    exact = " ".join(keywords).strip()
    for index, header in enumerate(headers):
        if header.strip() == exact:
            return index
    for index, header in enumerate(headers):
        if all(keyword.lower() in header.lower() for keyword in keywords):
            return index
    return None


def _rebuild(lines: list[str], replace: dict[int, Optional[str]], insert_after: dict[int, list[str]]) -> list[str]:
    """按行改写：replace 里值为 None 的行删除；insert_after 在指定行之后插入。"""
    out: list[str] = []
    for index, line in enumerate(lines):
        if index in replace:
            if replace[index] is not None:
                out.append(replace[index])  # type: ignore[arg-type]
        else:
            out.append(line)
        out.extend(insert_after.get(index, []))
    return out


def _table_of(tables: list[dict[str, Any]], line_index: int) -> Optional[dict[str, Any]]:
    return next((t for t in tables if line_index in t["rows"]), None)


# ---------------------------------------------------------------------------
# 回应表
# ---------------------------------------------------------------------------

DEFAULT_RESPONSE_HEADERS = ["意见ID", "severity", "摘要", "处置(accepted/rejected/deferred)", "回应（修复位置 文件:行号 或技术理由）", "复核"]


def _response_headers(root: Path) -> list[str]:
    """回应表的表头取自 templates/audit/audit_responses.md（先工作目录，再插件自带）。"""
    for base in (Path(root), PLUGIN_ROOT):
        path = base / "templates" / "audit" / "audit_responses.md"
        if not path.is_file():
            continue
        lines = _read_text(path).splitlines()
        for table in _scan_tables(lines):
            headers = table["headers"]
            if headers and headers[0].strip() == "意见ID" and _column(headers, "处置") is not None and _column(headers, "复核") is not None:
                return headers
    return list(DEFAULT_RESPONSE_HEADERS)


def load_canonical(root: Path, report_id: str, kind: str) -> Optional[dict[str, Any]]:
    """读这个审查点的规范文件（兼容旧文件名与手写的原件）；不存在时返回 None。

    返回 {"verdict", "findings", "diffs", "generated"}，findings 每条至少有 id、severity、title、open。
    generated 表示文件是不是本模块生成的；不是的话没有逐轮的在列信息，意见一律视为仍在列。
    """
    path = cg._external_audit_path(Path(root) / _ws(report_id) / "audit", kind)
    if not path.is_file():
        return None
    parsed = parse_review_text(_read_text(path))
    data = parsed["data"] if isinstance(parsed["data"], dict) else {}
    raw_findings = data.get("findings") if isinstance(data.get("findings"), list) else None
    findings: list[dict[str, Any]] = []
    for index, normalized in enumerate(parsed["findings"]):
        raw = raw_findings[index] if raw_findings is not None and index < len(raw_findings) and isinstance(raw_findings[index], dict) else {}
        cid, _number = _canon_id(normalized["raw_id"], ID_LETTER[kind])
        history = raw.get("history") if isinstance(raw.get("history"), list) and raw.get("history") else None
        first_text = _text(history[0].get("description")) if history and isinstance(history[0], dict) else normalized["description"]
        findings.append(
            {
                **normalized,
                "id": cid or normalized["raw_id"],
                "title": normalized.get("title") or _title(normalized["category"], normalized["description"]),
                "open": bool(raw.get("open", True)),
                "first_round": raw.get("first_round"),
                "last_round": raw.get("last_round"),
                # 意见的身份：首次提出的轮次与当时的描述。编号被别的意见重新占用时（轮次重来）指纹会变
                "fingerprint": _sha(f"{raw.get('first_round')}|{first_text}"),
            }
        )
    diffs = data.get("diffs") if isinstance(data.get("diffs"), list) else []
    return {
        "verdict": parsed["verdict"],
        "findings": findings,
        "diffs": [d for d in diffs if isinstance(d, dict)],
        "path": path,
        "generated": data.get("format") == CANONICAL_FORMAT,
    }


RECHECK_VALUES = ("pass", "open", "-")


def _responses_meta_path(root: Path, report_id: str) -> Path:
    return Path(root) / _ws(report_id) / "audit" / "external" / "responses_meta.json"


def _load_responses_meta(root: Path, report_id: str) -> dict[str, dict[str, dict[str, Any]]]:
    """回应表各行的底账：{审查点: {意见编号: {"fingerprint", ["recheck", "at", "note"]}}}。

    fingerprint 记的是这一行上次写入时对应的是哪条意见；recheck 是人工给定的复核结论。
    """
    data = _read_json(_responses_meta_path(root, report_id))
    if not isinstance(data, dict):
        return {}
    return {str(kind): {str(fid): entry for fid, entry in rows.items() if isinstance(entry, dict)} for kind, rows in data.items() if isinstance(rows, dict)}


def _recheck(severity: str, disposition: str, is_open: bool) -> str:
    """「复核」列：非 critical 的 rejected / deferred 填 -；其余按最新一轮是否仍在列。"""
    if disposition.strip().lower() in ("rejected", "deferred") and severity != "critical":
        return "-"
    return "open" if is_open else "pass"


def write_responses(root: Path, report_id: str, kind: str, rulings: Optional[dict[str, dict]] = None) -> dict:
    """生成或更新 audit_responses.md 里这个审查点的行：规范文件里的每条意见恰好一行。

    意见ID、severity、摘要取自规范文件；处置与回应取自 rulings，没给的保留表里已有的值；
    「复核」按最新一轮是否仍列出该意见填写。别的审查点的行、表头、表外文字原样保留；
    文件不存在时按 templates/audit/audit_responses.md 的表头新建。

    rulings 里可以带「复核」（pass / open / -）：这是人在检查点上的裁定（如 critical 争议裁定
    意见不成立），优先于按轮次算出的值，并记在 audit/external/responses_meta.json 里一直
    沿用——直到这条意见被重新处置（rulings 里只给「处置」而不给「复核」）。返回值的 overridden
    列出当前带人工复核结论的意见。

    同一份底账还记着每行对应的是哪条意见（首次提出的轮次加当时的描述）。某一轮重跑之后同一个
    编号换成了另一条意见时，表里旧的处置、回应与人工复核结论一并作废，这些编号列在返回值的
    reset 里，并重新出现在 unruled 里等待处置。
    """
    root = Path(root)
    if kind not in REVIEW_KINDS:
        raise ExtReviewError(f"kind 必须是 {REVIEW_KINDS} 之一，收到: {kind}")
    letter = ID_LETTER[kind]
    canonical = load_canonical(root, report_id, kind)
    if canonical is None:
        raise ExtReviewError(f"{kind} 审查点还没有规范文件（先 collect 或 skip）")
    findings = canonical["findings"]
    known = {f["id"] for f in findings}
    rulings = {str(k): v for k, v in (rulings or {}).items()}
    unknown = sorted(set(rulings) - known)
    if unknown:
        raise ExtReviewError(f"rulings 里有规范文件中不存在的意见编号: {unknown}")
    for fid, ruling in rulings.items():
        value = _ruling_value(ruling, "处置", "disposition")
        if value is not None and value.strip().lower() not in DISPOSITIONS:
            raise ExtReviewError(f"{fid} 的处置必须是 {DISPOSITIONS} 之一，收到: {value!r}")
        forced = _ruling_value(ruling, "复核", "recheck")
        if forced is not None and forced.strip().lower() not in RECHECK_VALUES:
            raise ExtReviewError(f"{fid} 的复核必须是 {RECHECK_VALUES} 之一，收到: {forced!r}")

    # 底账：每行上次写入时对应哪条意见、有没有人工给定的复核结论。
    # - 编号还在、指纹变了：这一轮重来过，编号被另一条意见占用，表里旧的处置与回应不能算在新意见头上；
    # - 人工给定的复核结论要记住：之后每次重写都按最新一轮重算「复核」，不记住就会被算回去。
    # 手写的规范文件里描述随时会被人改写，指纹不可靠：只有本模块生成的规范文件才记指纹、才判换主。
    meta_all = _load_responses_meta(root, report_id)
    stored = meta_all.get(kind, {})
    by_id = {f["id"]: f for f in findings}
    tracked = bool(canonical["generated"])
    reused = sorted(
        fid for fid, entry in stored.items() if tracked and fid in by_id and entry.get("fingerprint") not in (None, by_id[fid]["fingerprint"])
    )
    overrides = {fid: entry for fid, entry in stored.items() if fid in by_id and fid not in reused and entry.get("recheck") in RECHECK_VALUES}
    for fid, ruling in rulings.items():
        forced = _ruling_value(ruling, "复核", "recheck")
        if forced is not None:
            overrides[fid] = {"recheck": forced.strip().lower(), "at": st.now_iso(), "note": _clip(_ruling_value(ruling, "回应", "response") or "", 200)}
        elif _ruling_value(ruling, "处置", "disposition") is not None:
            overrides.pop(fid, None)  # 重新处置过：此前人工给的复核结论不再沿用
    meta = {
        fid: {
            **({"fingerprint": finding["fingerprint"]} if tracked else {}),
            **{k: overrides[fid][k] for k in ("recheck", "at", "note") if fid in overrides and k in overrides[fid]},
        }
        for fid, finding in by_id.items()
    }
    meta = {fid: entry for fid, entry in meta.items() if entry}
    if meta != stored:
        meta_all[kind] = meta
        _write_json(_responses_meta_path(root, report_id), {k: v for k, v in meta_all.items() if v})

    path = root / _ws(report_id) / "audit" / "audit_responses.md"
    existed = path.is_file()
    text = _read_text(path) if existed else ""
    lines = text.splitlines()
    tables = _scan_tables(lines)

    current: dict[str, tuple[int, list[str], dict[str, Any]]] = {}
    stale: list[int] = []
    dropped: list[str] = []
    for table in tables:
        for index in table["rows"]:
            cells = _split_cells(lines[index])
            raw_id = next((c for c in cells if re.match(r"^CDX-[A-Z]-", c)), "")
            if not raw_id.startswith(f"CDX-{letter}-"):
                continue
            cid, _number = _canon_id(raw_id, letter)
            if cid in known and cid not in current:
                current[cid] = (index, cells, table)
            else:
                stale.append(index)
                dropped.append(raw_id)

    target = current[next(iter(current))][2] if current else next(
        (t for t in reversed(tables) if _column(t["headers"], "处置") is not None and _column(t["headers"], "复核") is not None), None
    )
    headers = target["headers"] if target is not None else _response_headers(root)
    summary: dict[str, list[str]] = {"open_critical": [], "unanswered_major": [], "unruled": []}
    replace: dict[int, Optional[str]] = {index: None for index in stale}
    fresh: list[str] = []
    for finding in findings:
        fid = finding["id"]
        old = current.get(fid)
        row_headers = old[2]["headers"] if old else headers
        cells = list(old[1]) if old else [""] * len(row_headers)
        cells += [""] * (len(row_headers) - len(cells))
        if old and fid in reused:  # 同一个编号换了意见：旧的处置与回应作废
            for name in ("处置", "回应"):
                column = _column(row_headers, name)
                if column is not None:
                    cells[column] = ""
        id_column = _column(row_headers, "ID")
        cols = {
            "id": next((i for i, c in enumerate(cells) if re.match(r"^CDX-[A-Z]-", c)), None) if old else (id_column if id_column is not None else 0),
            "severity": _column(row_headers, "severity"),
            "summary": _column(row_headers, "摘要"),
            "disposition": _column(row_headers, "处置"),
            "response": _column(row_headers, "回应"),
            "recheck": _column(row_headers, "复核"),
        }
        ruling = rulings.get(fid) or {}
        disposition = _ruling_value(ruling, "处置", "disposition")
        response = _ruling_value(ruling, "回应", "response")
        disposition = disposition.strip().lower() if disposition is not None else (cells[cols["disposition"]] if cols["disposition"] is not None else "")
        response = response if response is not None else (cells[cols["response"]] if cols["response"] is not None else "")
        recheck = overrides[fid]["recheck"] if fid in overrides else _recheck(finding["severity"], disposition, finding["open"])
        written = cells[cols["recheck"]].strip() if old and cols["recheck"] is not None else ""
        if written and fid not in overrides:
            if not tracked and _ruling_value(ruling, "处置", "disposition") is None:
                recheck = written  # 手写的规范文件没有逐轮的在列信息：没有重新处置的行，手工维护的复核结论不重算
            elif tracked and finding["severity"] != "critical" and recheck in ("pass", "open") and written.lower().startswith(recheck):
                recheck = written  # 结论相同、只是多了括注（如「pass（外部增量复核）」）：原样保留；critical 的门禁要求一字不差，不保留括注
        summary_text = finding["title"]
        if old and not tracked and cols["summary"] is not None and cells[cols["summary"]].strip():
            summary_text = cells[cols["summary"]]  # 手写规范文件对应的行，手写的摘要不改
        for key, value in (("id", fid), ("severity", finding["severity"]), ("summary", summary_text), ("disposition", disposition), ("response", response), ("recheck", recheck)):
            if cols[key] is not None:
                cells[cols[key]] = value
        line = _join_cells(cells)
        if old:
            replace[old[0]] = line
        else:
            fresh.append(line)
        if finding["severity"] == "critical" and recheck != "pass":
            summary["open_critical"].append(fid)
        if finding["severity"] == "major" and not disposition.strip():
            summary["unanswered_major"].append(fid)
        if not disposition.strip():
            summary["unruled"].append(fid)

    insert_after: dict[int, list[str]] = {}
    if fresh:
        if current:
            insert_after[max(index for index, _cells, _table in current.values())] = fresh
        elif target is not None:
            insert_after[target["rows"][-1] if target["rows"] else target["header"] + 1] = fresh
    lines = _rebuild(lines, replace, insert_after)
    if not existed:
        lines = [
            f"# 审计回应总表（{report_id}）",
            "",
            "> 三道异构外审（spec / code / result）的意见逐条回应，一条意见一行。意见ID、severity、摘要与「复核」列由内核按外审规范文件生成，"
            "「处置」「回应」取自裁决与修复回执。",
        ]
    if target is None and (fresh or not existed):  # 文中还没有回应表：新起一张
        lines += ["", _join_cells(headers), "| " + " | ".join("---" for _ in headers) + " |", *fresh]
    _write_if_changed(path, "\n".join(lines) + "\n")
    return {"rows": len(findings), **summary, "dropped": dropped, "overridden": sorted(overrides), "reset": reused, "path": _rel(root, path)}


def _ruling_value(ruling: Any, *keys: str) -> Optional[str]:
    if not isinstance(ruling, dict):
        return None
    for key in keys:
        if ruling.get(key) is not None:
            return str(ruling[key])
    return None


# ---------------------------------------------------------------------------
# 差异裁决表
# ---------------------------------------------------------------------------

DIFF_HEADERS = ["ID", "类别", "描述", "页码", "裁决(adopted/dismissed/corrected)", "依据"]
_DIF_ID_RE = re.compile(r"^DIF-?0*(\d+)$")
_DIF_CELL_RE = re.compile(r"^DIF-?0*(\d+)")  # 表里认 DIF 行的口径同门禁：任意一格以 DIF-数字 开头
_SOURCE_TAG_RE = re.compile(r"^\[((?:外审差异|外审|内审) [^\]]+)\]\s*")
_PAGE_RE = re.compile(r"(?<![A-Za-z0-9_])p\d+(?:\s*[-–~]\s*p?\d+)?", re.IGNORECASE)


def internal_audit_items(root: Path, report_id: str) -> list[dict[str, str]]:
    """内审 extract_audit.md「遗漏清单」一节里带编号的条目。文件不存在时为空。"""
    path = Path(root) / _ws(report_id) / "audit" / "extract_audit.md"
    if not path.is_file():
        return []
    text = _read_text(path)
    section = next((s for s in ms.sections(text) if s.level == 2 and "遗漏" in s.title), None)
    if section is None:
        return []
    items: list[dict[str, str]] = []
    for row in cg.parse_markdown_table_rows(section.text):
        first = (next(iter(row.values()), "") or "").strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+", first) or any(i["id"] == first for i in items):
            continue
        items.append(
            {
                "id": first,
                "check": cg._row_get(row, "检查项"),
                "severity": cg._row_get(row, "严重度") or cg._row_get(row, "severity"),
                "pages": cg._row_get(row, "页码") or cg._row_get(row, "定位"),
                "description": cg._row_get(row, "描述") or cg._row_get(row, "依据"),
                "suggestion": cg._row_get(row, "处置建议") or cg._row_get(row, "建议"),
            }
        )
    return items


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _pages(location: str) -> str:
    pages = [re.sub(r"\s+", "", m.group(0)) for m in _PAGE_RE.finditer(location)]
    unique = list(dict.fromkeys(pages))
    return ", ".join(unique) if unique else _clip(location, 60)


def _diff_sources(root: Path, report_id: str) -> list[dict[str, str]]:
    """差异裁决表的来源：外审意见、外审第二次调用里没有对应意见的差异、内审条目。"""
    canonical = load_canonical(root, report_id, "spec") or {"findings": [], "diffs": [], "generated": False}
    tracked = bool(canonical.get("generated"))  # 手写的规范文件描述会被人改写，不拿它判「换主」
    finding_ids = {f["id"] for f in canonical["findings"]}
    by_finding: dict[str, dict[str, Any]] = {}
    for diff in canonical["diffs"]:
        linked = _text(diff.get("finding_id"))
        if linked in finding_ids:
            by_finding.setdefault(linked, diff)
    sources: list[dict[str, str]] = []
    for finding in canonical["findings"]:
        diff = by_finding.get(finding["id"], {})
        basis = f"{finding['severity']}"
        if diff.get("basis"):
            basis += f"；差异比对结论：{_clip(_text(diff.get('basis')), 160)}"
        elif finding.get("suggestion"):
            basis += f"；建议：{_clip(finding['suggestion'], 160)}"
        sources.append(
            {
                "key": f"外审 {finding['id']}",
                "source": "external_finding",
                "ref": finding["id"],
                "category": finding.get("category") or _text(diff.get("category")) or "外审意见",
                "description": _clip(finding.get("description") or finding["title"], 240),
                "pages": _text(diff.get("pages")) or _pages(finding.get("location") or ""),
                "ruling": _text(diff.get("resolution")) if _text(diff.get("resolution")) in DIFF_RULINGS else "",
                "basis": basis,
                "fingerprint": finding["fingerprint"] if tracked else None,
            }
        )
    for diff in canonical["diffs"]:
        if _text(diff.get("finding_id")) in finding_ids:
            continue
        key = _text(diff.get("key")) or f"r{diff.get('round', 1)}#{_text(diff.get('id'))}"
        sources.append(
            {
                "key": f"外审差异 {key}",
                "source": "external_diff",
                "ref": key,
                "category": _text(diff.get("category")) or "盲提取差异",
                "description": _clip(_text(diff.get("description")), 240),
                "pages": _text(diff.get("pages")),
                "ruling": _text(diff.get("resolution")) if _text(diff.get("resolution")) in DIFF_RULINGS else "",
                "basis": f"第二次调用的差异比对结论：{_clip(_text(diff.get('basis')), 160) or '（未给依据）'}",
                "fingerprint": _sha(f"{key}|{_text(diff.get('description'))}") if tracked else None,
            }
        )
    for item in internal_audit_items(root, report_id):
        sources.append(
            {
                "key": f"内审 {item['id']}",
                "source": "internal",
                "ref": item["id"],
                "category": f"内审 {item['check']}".strip(),
                "description": _clip(item["description"], 240),
                "pages": _pages(item["pages"]),
                "ruling": "",
                "basis": f"extract_audit.md {item['severity'] or '未标严重度'}；处置建议：{_clip(item['suggestion'], 160) or '（无）'}",
                "fingerprint": _sha(f"{item['id']}|{item['description']}"),
            }
        )
    return sources


def write_extract_diff(root: Path, report_id: str, rulings: Optional[dict[str, dict]] = None) -> dict:
    """把外审第二阶段的差异结论与内审意见投影成 DIF 行，写 spec/extract_diff.md。

    每个来源一行，编号稳定（来源写在「依据」列开头的方括号里，重复调用按它对号）。裁决的
    取值顺序：rulings 给的 → 表里已有的 → 外审第二次调用对这处差异给出的结论；都没有就留空，
    列在返回值的 unruled 里。表里没有来源标记的行（手写的）原样保留，只接受 rulings 的改写；
    手写的行在文字里点到了某条意见的编号时，这条意见不再另起一行。

    返回的 rows 每行是 {"id", "类别", "描述", "页码", "裁决", "依据", "source", "ref"}：前六项
    对应表里的六列；source 取 external_finding / external_diff / internal / manual / orphan，
    ref 是来源的编号（如 CDX-S-01、r1#D-02、SA-A01）。

    来源的编号还在、内容却换了（那一轮外审或内审重做过）的行，按新内容重写、旧裁决作废，
    编号列在返回值的 reset 里（底账同在 audit/external/responses_meta.json）。
    """
    root = Path(root)
    rulings = {_normalize_dif_id(k): v for k, v in (rulings or {}).items()}
    for dif_id, ruling in rulings.items():
        value = _ruling_value(ruling, "裁决", "ruling")
        if value is not None and value.strip().lower() not in DIFF_RULINGS:
            raise ExtReviewError(f"{dif_id} 的裁决必须是 {DIFF_RULINGS} 之一，收到: {value!r}")
    sources = _diff_sources(root, report_id)
    path = root / _ws(report_id) / "spec" / "extract_diff.md"
    existed = path.is_file()
    lines = _read_text(path).splitlines() if existed else []
    tables = _scan_tables(lines)

    # 只认表格里的数据行（口径同门禁）：表头行本身可能就写成「| DIF-01 | 类别 | … |」，不能当成一条差异
    rows: list[dict[str, Any]] = []
    for table in tables:
        headers = table["headers"]
        for index in table["rows"]:
            cells = _split_cells(lines[index])
            id_col = next((i for i, cell in enumerate(cells[: len(headers)]) if _DIF_CELL_RE.match(cell)), None)
            if id_col is None:
                continue
            number = int(_DIF_CELL_RE.match(cells[id_col]).group(1))  # type: ignore[union-attr]
            cols = {
                "id": id_col,
                "ruling": _column(headers, "裁决"),
                "basis": _column(headers, "依据"),
                "category": _column(headers, "类别"),
                "description": _column(headers, "描述"),
                "pages": _column(headers, "页码"),
            }
            for name, position in (("category", 1), ("description", 2), ("pages", 3)):
                if cols[name] is None and position not in cols.values():
                    cols[name] = position  # 表头里认不出这一列：按默认列序读，但不占已认出的列
            cols = {k: (v if v is not None and v < len(cells) else None) for k, v in cols.items()}
            basis = cells[cols["basis"]] if cols["basis"] is not None else ""
            tag = _SOURCE_TAG_RE.match(basis)
            rows.append({"line": index, "number": number, "id": f"DIF-{number:02d}", "cells": cells, "cols": cols, "key": tag.group(1) if tag else None})

    by_key = {r["key"]: r for r in rows if r["key"]}
    known_ids = {r["id"] for r in rows}
    next_no = max((r["number"] for r in rows), default=0)
    replace: dict[int, Optional[str]] = {}
    fresh: list[str] = []
    result_rows: list[dict[str, Any]] = []
    dropped: list[str] = []
    planned: list[tuple[str, dict[str, str]]] = []
    untagged = [" ".join(r["cells"]) for r in rows if r["key"] is None]

    def covered_by_hand(source: dict[str, str]) -> bool:
        """旧案例手写的行没有来源标记，但会在文字里点出意见编号（如「依据 … CDX-S-01」）：
        已经被这样的行点到的来源不再另起一行。"""
        cited = re.compile(rf"(?<![\w-]){re.escape(source['ref'])}(?![\w-])")
        return any(cited.search(text) for text in untagged)

    for source in sources:
        if source["key"] not in by_key and not covered_by_hand(source):
            next_no += 1
            planned.append((f"DIF-{next_no:02d}", source))
            known_ids.add(f"DIF-{next_no:02d}")
    unknown = sorted(set(rulings) - known_ids)
    if unknown:
        raise ExtReviewError(f"rulings 里有差异裁决表中不存在的编号: {unknown}")

    def apply(dif_id: str, ruling_now: str, basis_now: str, key: Optional[str]) -> tuple[str, str]:
        given = rulings.get(dif_id) or {}
        ruling_new = _ruling_value(given, "裁决", "ruling")
        basis_new = _ruling_value(given, "依据", "basis")
        ruling_out = ruling_new.strip().lower() if ruling_new is not None else ruling_now
        basis_out = basis_now
        if basis_new is not None:
            body = _SOURCE_TAG_RE.sub("", basis_new.strip())
            basis_out = f"[{key}] {body}" if key else body
        return ruling_out, basis_out

    # 底账记着每行上次写入时对应的是来源的哪一版：来源的编号还在、内容换了（那一轮外审或内审
    # 重做过），这一行按新内容重写，旧裁决作废。底账里没有记录的行（旧案例、手写的）不动。
    meta_all = _load_responses_meta(root, report_id)
    stored = meta_all.get("extract_diff", {})
    meta: dict[str, dict[str, Any]] = {}
    reset: list[str] = []
    source_by_key = {s["key"]: s for s in sources}
    for row in rows:
        cells, cols = row["cells"], row["cols"]
        ruling_now = cells[cols["ruling"]] if cols["ruling"] is not None else ""
        basis_now = cells[cols["basis"]] if cols["basis"] is not None else ""
        source = source_by_key.get(row["key"]) if row["key"] else None
        if row["key"] and source is None and not ruling_now.strip() and row["id"] not in rulings:
            replace[row["line"]] = None  # 来源已经不在、又没有裁决过的行不再保留
            dropped.append(row["id"])
            continue
        ruling_base, basis_base = ruling_now, basis_now
        refreshed = (
            source is not None
            and source["fingerprint"] is not None
            and (stored.get(row["id"]) or {}).get("fingerprint") not in (None, source["fingerprint"])
        )
        if refreshed and source is not None:
            for name in ("category", "description", "pages"):
                if cols[name] is not None:
                    cells[cols[name]] = source[name]
            ruling_base, basis_base = "", f"[{source['key']}] {source['basis']}"
            reset.append(row["id"])
        if source is not None and source["fingerprint"] is not None:
            meta[row["id"]] = {"fingerprint": source["fingerprint"], "key": source["key"]}
        proposed = source["ruling"] if source is not None and not ruling_base.strip() else ruling_base
        ruling_out, basis_out = apply(row["id"], proposed, basis_base, row["key"])
        if refreshed or (ruling_out, basis_out) != (ruling_now, basis_now):  # 没有变化的行一个字符都不动
            if cols["ruling"] is not None:
                cells[cols["ruling"]] = ruling_out
            if cols["basis"] is not None:
                cells[cols["basis"]] = basis_out
            replace[row["line"]] = _join_cells(cells)
        result_rows.append(
            {
                "id": row["id"],
                "类别": cells[cols["category"]] if cols["category"] is not None else "",
                "描述": cells[cols["description"]] if cols["description"] is not None else "",
                "页码": cells[cols["pages"]] if cols["pages"] is not None else "",
                "裁决": ruling_out,
                "依据": basis_out,
                "source": source["source"] if source else ("orphan" if row["key"] else "manual"),
                "ref": source["ref"] if source else (row["key"] or ""),
            }
        )
    for dif_id, source in planned:
        if source["fingerprint"] is not None:
            meta[dif_id] = {"fingerprint": source["fingerprint"], "key": source["key"]}
        ruling_out, basis_out = apply(dif_id, source["ruling"], f"[{source['key']}] {source['basis']}", source["key"])
        fresh.append(_join_cells([dif_id, source["category"], source["description"], source["pages"], ruling_out, basis_out]))
        result_rows.append(
            {
                "id": dif_id,
                "类别": source["category"],
                "描述": source["description"],
                "页码": source["pages"],
                "裁决": ruling_out,
                "依据": basis_out,
                "source": source["source"],
                "ref": source["ref"],
            }
        )

    # 新行接在最后一条 DIF 行之后；表里还没有 DIF 行时接在裁决表的表头下面；连表都没有就新起一张
    insert_after: dict[int, list[str]] = {}
    kept = [r["line"] for r in rows if replace.get(r["line"], "") is not None]
    empty_table = next((t for t in tables if _column(t["headers"], "裁决") is not None), None)
    anchor = max(kept) if kept else ((empty_table["rows"][-1] if empty_table["rows"] else empty_table["header"] + 1) if empty_table else None)
    if fresh and anchor is not None:
        insert_after[anchor] = fresh
    lines = _rebuild(lines, replace, insert_after)
    if not existed:
        lines = [
            f"# 提取差异裁决表 extract_diff.md（{report_id}）",
            "",
            "> 由内核把外审第二阶段的差异结论（`audit/spec_audit_external.md`）与内审意见（`audit/extract_audit.md`）投影而成，"
            "一处差异一行，「依据」列开头的方括号是来源。裁决取值：adopted（确有其事，交回补录）/ dismissed（不构成规格问题）/ corrected（以原文为准订正）。",
        ]
    if not existed or (fresh and anchor is None):
        lines += ["", _join_cells(DIFF_HEADERS), "| " + " | ".join("---" for _ in DIFF_HEADERS) + " |", *fresh]
    _write_if_changed(path, "\n".join(lines) + "\n")
    if meta != stored:
        meta_all["extract_diff"] = meta
        _write_json(_responses_meta_path(root, report_id), {k: v for k, v in meta_all.items() if v})
    result_rows.sort(key=lambda r: int(r["id"].split("-")[1]))
    return {
        "rows": result_rows,
        "unruled": [r["id"] for r in result_rows if not r["裁决"].strip()],
        "dropped": dropped,
        "reset": reset,
        "path": _rel(root, path),
    }


def _normalize_dif_id(raw: Any) -> str:
    m = _DIF_ID_RE.match(_text(raw))
    return f"DIF-{int(m.group(1)):02d}" if m else _text(raw)


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="研报复现：外审 job 的执行与状态查询")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="前台执行一个已准备好的外审 job（后台启动的子进程用）")
    run.add_argument("report_id")
    run.add_argument("job_id")
    run.add_argument("--token", default=None, help="launch 登记的启动标记")
    show = sub.add_parser("status", help="查询外审 job 的状态")
    show.add_argument("report_id")
    show.add_argument("job_id")
    args = parser.parse_args(argv)

    root = st.default_root()
    try:
        if args.command == "run":
            result = _run_job(root, args.report_id, args.job_id, token=args.token)
        else:
            result = status(root, args.report_id, args.job_id)
    except (ExtReviewError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.command == "run":
        return 0 if result.get("state") == "success" else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
