"""结果一致性预检（v3 批次 C）。

结果外审和写报告之前，机器先核四件事，都是「文书与机器产物对不对得上」的机械检查：

    P1 核心要素有对比条目   覆盖矩阵里优先级为 core、状态不是 skipped / infeasible 的 R 类与 SA 类要素，
                           在 comparison.json 里要有归属于它的条目（显式标 N/A 的条目也算）。
    P2 原始来源指针回查     对比条目带 source_pointer 的，取出 metrics.json 对应位置的值，
                           与复现值在舍入范围内比对。
    P3 空值不得计为通过     复现值为空、非有限或是占位值，却自述通过或被计入通过数的，报出。
    P4 文书与机器结果一致   verify_report.md（report 阶段另加 final_report.md）里写的达标计数、
                           手抄对比表里的复现值，与机器结果一致；此前各版 comparison 的旧数值在
                           文书里的残留列成清单。

「这条指标过没过」一律取 `check_gates.recalc_comparison` 的重算结论，不采信文件自述的 pass。
只查机械性一致，不生成审计意见；只读，不改任何文件。

另外提供文书里的机器生成块：对比总表、达标计数、产物清单由内核从 comparison.json 和结果目录
生成后嵌入文书，正文引用指标编号而不重写数值。生成块里的内容 P4 不查。
"""

from __future__ import annotations

import bisect
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from tools import check_gates as cg
from tools import state as st

__all__ = [
    "Finding",
    "PrecheckResult",
    "run_precheck",
    "comparison_table",
    "comparison_counts",
    "comparison_breakdown",
    "artifacts_table",
    "upsert_block",
    "extract_block",
    "scan_stale_numbers",
]

STAGES = ("result", "report")
LEVEL_CN = {"block": "阻断", "warn": "提示"}

# P1：来源要素写了别的内容、但指标编号或名称以要素编号开头的条目，是否也算该要素的条目。
# True 时算（另出一条提示，要求把来源要素写规范）；False 时这类要素按缺条目报阻断。
# r008 的来源要素写的是图表编号（「EX34（图表34）」），只能靠指标编号（r10_…）对上。
# 定性条目没写来源要素的不受这个开关影响：它的指标编号就是归属（见 `_check_p1`）。
P1_KEY_FALLBACK = True

POINTER_FIELD = "source_pointer"
POINTER_REL_TOL = 1e-6  # P2 的相对误差上限；与「复现值末位小数的半个单位」取宽者

# P4：不一致的计数或手抄值，如果同一行的另一句里或文书后文已有一致的写法（手抄值另认：恰好
# 等于上一版或某一轮迭代快照里的旧值），按旧数残留处理，级别取这里的值；找不到这类解释的才是
# 阻断。改成 "block" 就是严格口径：只有标了历史字样的才放过。
P4_SUPERSEDED_LEVEL = "warn"

# P4：文书写的达标数与重算不一致，但恰好等于 comparison.json 顶层自述的 pass_count / total 时的级别。
# 自述不作数，默认照样阻断；改成 "warn" 则这种情形只提示（r010 就是这种：条目带核验分级，
# 重算时 directional 只核同号、unverifiable 豁免，与自述的严格容差计数对不上）。
P4_SELF_REPORTED_LEVEL = "block"

# 行内、所在章节的标题（二级及以下）出现这些字样的内容，视为已标注的历史记录，P4 不报；
# 表格的表头里某一列出现这些字样时，只是那一列不查
HISTORY_MARKERS = (
    "历史", "上一轮", "上轮", "前一轮", "前轮", "修订前", "修复前", "修正前", "修改前", "更新前",
    "变更前", "调整前", "旧值", "旧版", "旧口径", "旧计数", "旧数", "旧轮", "已废弃", "已作废",
    "superseded", "deprecated",
)

STALE_MIN_SIG_DIGITS = 3  # 旧数值残留扫描只看至少这么多位有效数字、且带小数点的数
# 上一版的旧数：有效数字不到这个位数的，还要求同一行提到了那条指标才报；
# 比上一版更早的各轮快照里的旧数：有效数字不到这个位数的一律不报
STALE_FREE_SIG_DIGITS = 5
STALE_HINT = "逐条改掉或标注为历史记录"


# ---------------------------------------------------------------------------
# 对外的数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """一条预检发现。"""

    check: str  # "P1" | "P2" | "P3" | "P4"
    level: str  # "block"（不过就不派外审）| "warn"
    message: str  # 一句中文：哪条指标 / 哪个要素 / 哪个文件第几行，实际是什么、应该是什么
    where: str = ""  # 文件相对路径[:行号]

    def to_dict(self) -> dict:
        return {"check": self.check, "level": self.level, "message": self.message, "where": self.where}


@dataclass
class PrecheckResult:
    """一次预检的结果。"""

    report_id: str
    stage: str  # "result" | "report"
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        """存在阻断级发现。"""
        return any(f.level == "block" for f in self.findings)

    def _scope_text(self) -> str:
        s = self.stats
        parts = [f"核心要素 {s.get('core_elements', 0)} 个"]
        metrics = f"数值指标 {s.get('metrics_total', 0)} 项（重算达标 {s.get('metrics_pass', 0)}"
        if s.get("metrics_fail"):
            metrics += f"、未达标 {s['metrics_fail']}"
        if s.get("metrics_na"):
            metrics += f"、N/A {s['metrics_na']}"
        parts.append(metrics + "）")
        if s.get("qualitative_total"):
            parts.append(f"定性 {s['qualitative_total']} 项（达标 {s.get('qualitative_pass', 0)}）")
        docs = [Path(p).name for p in s.get("checked_docs", [])]
        if docs:
            parts.append("已核对 " + "、".join(docs))
        skipped = [Path(p).name for p in s.get("skipped_files", [])]
        if skipped:
            parts.append("未核对（文件不在）" + "、".join(skipped))
        return "，".join(parts)

    def render(self) -> str:
        """人读文本：没有任何发现时只一行；有发现时首行给结论，其后逐条列出。"""
        n_block = sum(1 for f in self.findings if f.level == "block")
        n_warn = sum(1 for f in self.findings if f.level != "block")
        scope = self._scope_text()
        if not self.findings:
            return f"一致性预检通过（{self.stage}）：{scope}"
        if n_block:
            head = f"一致性预检未通过（{self.stage}）：{n_block} 条阻断、{n_warn} 条提示；{scope}"
        else:
            head = f"一致性预检通过（{self.stage}），另有 {n_warn} 条提示；{scope}"
        lines = [head]
        for f in self.findings:
            line = f"[{LEVEL_CN.get(f.level, f.level)}] {f.check} {f.message}"
            if f.where:
                line += f"（{f.where}）"
            lines.append(line)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "stage": self.stage,
            "blocked": self.blocked,
            "findings": [f.to_dict() for f in self.findings],
            "stats": self.stats,
        }


@dataclass(frozen=True)
class _Hit:
    """内部用的发现：比 Finding 多带行号，便于排序、去重。"""

    check: str
    level: str
    message: str
    path: str = ""
    line: int = 0

    def finding(self) -> Finding:
        where = self.path
        if self.path and self.line:
            where = f"{self.path}:{self.line}"
        return Finding(self.check, self.level, " ".join(self.message.split()), where)


# ---------------------------------------------------------------------------
# 文书里的机器生成块
# ---------------------------------------------------------------------------

BLOCK_BEGIN_NOTE = "（由内核生成，勿手改；改了会被覆盖）"
_BLOCK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]*$")
_BLOCK_BEGIN_RE = re.compile(r"^\s*<!--\s*flow:generated\s+(?P<name>\S+)\s+BEGIN(?![A-Za-z0-9_]).*-->\s*$")
_BLOCK_END_RE = re.compile(r"^\s*<!--\s*flow:generated\s+(?P<name>\S+)\s+END\s*-->\s*$")
_BLOCK_PLACEHOLDER_RE = re.compile(r"^\s*<!--\s*flow:block\s+(?P<name>\S+?)\s*-->\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _check_block_name(name: str) -> None:
    if not isinstance(name, str) or not _BLOCK_NAME_RE.match(name):
        raise ValueError(f"机器生成块的名字只能用字母、数字和 _ . : -，且以字母或数字开头：{name!r}")


def _block_begin(name: str) -> str:
    return f"<!-- flow:generated {name} BEGIN{BLOCK_BEGIN_NOTE} -->"


def _block_end(name: str) -> str:
    return f"<!-- flow:generated {name} END -->"


def _fence_mask(lines: list[str]) -> list[bool]:
    """逐行标出是否在代码围栏内（围栏的起止行本身也算）。P4 不看围栏里的内容。

    起止规则与 mdslice.scan_lines 相同，只多一条：到文末都没有闭合的围栏不算围栏，免得一处
    漏写的收尾把后面的正文全部挡在检查之外。
    """
    mask = [False] * len(lines)
    i, n = 0, len(lines)
    while i < n:
        m = _FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        marker = m.group(1)
        close = -1
        for j in range(i + 1, n):
            mj = _FENCE_RE.match(lines[j])
            if mj and mj.group(1)[0] == marker[0] and len(mj.group(1)) >= len(marker) and not lines[j].strip().strip(marker[0]):
                close = j
                break
        if close < 0:
            i += 1
            continue
        for k in range(i, close + 1):
            mask[k] = True
        i = close + 1
    return mask


def _block_spans(lines: list[str]) -> tuple[list[tuple[str, int, int]], list[tuple[str, int]]]:
    """找出全部完整的生成块 [(名字, BEGIN 行下标, END 行下标)]，以及缺 END 的 BEGIN [(名字, 行下标)]。

    起止标记按名字配对，一个块的正文里可以带着别的名字的块；同名的 BEGIN 接连出现两次时，
    前一个算缺 END。标记行在不在代码围栏里都认（与 kernelsteps.upsert_block 一致）：标记是
    机器写的，文书里围栏没配平、块的正文里又带围栏时也得认得出来，否则同一个块会越追加越多。
    """
    spans: list[tuple[str, int, int]] = []
    dangling: list[tuple[str, int]] = []
    open_at: dict[str, int] = {}
    for i, text in enumerate(lines):
        mb = _BLOCK_BEGIN_RE.match(text)
        if mb:
            name = mb.group("name")
            if name in open_at:
                dangling.append((name, open_at[name]))
            open_at[name] = i
            continue
        me = _BLOCK_END_RE.match(text)
        if me and me.group("name") in open_at:
            spans.append((me.group("name"), open_at.pop(me.group("name")), i))
    dangling.extend(open_at.items())
    return sorted(spans, key=lambda s: s[1]), sorted(dangling, key=lambda d: d[1])


def upsert_block(text: str, name: str, body: str) -> str:
    """在文书里插入或替换名为 name 的机器生成块，返回新文本（不写文件）。

    块的形状固定为（标记各占一行）::

        <!-- flow:generated <name> BEGIN（由内核生成，勿手改；改了会被覆盖） -->
        …
        <!-- flow:generated <name> END -->

    三种情形按顺序判断：文书里已有同名块，整体替换（有多个同名块就都替换，免得留下一份过期的）；
    没有同名块但有占位行 `<!-- flow:block <name> -->`，把第一处占位行换成块（别的块正文里的
    占位行不算）；两者都没有，追加到文末（与前文隔一个空行）。同样的输入重复调用，结果不变。
    原文是 CRLF 行尾的，写进去的块也用 CRLF。
    """
    _check_block_name(name)
    body_lines = [line.rstrip("\r") for line in body.strip("\r\n").split("\n")] if body.strip() else []
    for line in body_lines:
        mb, me = _BLOCK_BEGIN_RE.match(line), _BLOCK_END_RE.match(line)
        if (mb and mb.group("name") == name) or (me and me.group("name") == name):
            raise ValueError(f"生成块 {name} 的正文里不能再出现它自己的起止标记")
    block_lines = [_block_begin(name), *body_lines, _block_end(name)]

    parts = text.split("\n")
    bare = [p.rstrip("\r") for p in parts]
    newline = "\r\n" if "\r\n" in text else "\n"

    def placed(replaced_last: str) -> list[str]:
        """块的各行配上行尾：中间的行跟文书的行尾风格走，最后一行跟被它换掉的那一行走。"""
        cr = "\r" if newline == "\r\n" else ""
        return [line + cr for line in block_lines[:-1]] + [block_lines[-1] + ("\r" if replaced_last.endswith("\r") else "")]

    spans, _dangling = _block_spans(bare)
    same = [(b, e) for block_name, b, e in spans if block_name == name]
    if same:
        for b, e in reversed(same):
            parts[b : e + 1] = placed(parts[e])
        return "\n".join(parts)

    in_block = set()
    for _block_name, b, e in spans:
        in_block.update(range(b, e + 1))
    for i, line in enumerate(bare):
        if i in in_block:
            continue
        m = _BLOCK_PLACEHOLDER_RE.match(line)
        if m and m.group("name") == name:
            parts[i : i + 1] = placed(parts[i])
            return "\n".join(parts)

    block = newline.join(block_lines)
    if not text.strip():
        return block + newline
    return text.rstrip("\r\n") + newline + newline + block + newline


def extract_block(text: str, name: str) -> Optional[str]:
    """取出名为 name 的机器生成块的正文（不含起止标记）；文书里没有这个块时返回 None。"""
    _check_block_name(name)
    bare = [p.rstrip("\r") for p in text.split("\n")]
    spans, _dangling = _block_spans(bare)
    for block_name, b, e in spans:
        if block_name == name:
            return "\n".join(bare[b + 1 : e])
    return None


# ---------------------------------------------------------------------------
# 小工具：路径、数字、文本规整
# ---------------------------------------------------------------------------


class _Num(float):
    """保留 JSON 字面量写法的浮点数，用来数「复现值写到小数点后第几位」。其余行为同 float。"""

    __slots__ = ("lit",)

    def __new__(cls, text: str) -> "_Num":
        obj = super().__new__(cls, text)
        obj.lit = text
        return obj


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def _results_dir(root: Path, report_id: str) -> Path:
    return root / "output" / report_id / "results"


def _comparison_path(root: Path, report_id: str) -> Path:
    return _results_dir(root, report_id) / "comparison.json"


def _metrics_path(root: Path, report_id: str) -> Path:
    return _results_dir(root, report_id) / "metrics.json"


def _matrix_path(root: Path, report_id: str) -> Path:
    return root / "workspace" / report_id / "spec" / "coverage_matrix.md"


def _doc_paths(root: Path, report_id: str, stage: Optional[str]) -> list[Path]:
    """各阶段要核对的文书：result 只看 verify_report.md，report 另加 final_report.md；None 表示两份都看。"""
    docs = [root / "output" / report_id / "verify_report.md"]
    if stage != "result":
        docs.append(root / "workspace" / report_id / "final_report.md")
    return docs


def _load_json(path: Path) -> tuple[Any, str]:
    """读 JSON，返回 (内容, 读不了的原因)。浮点数保留字面量写法。"""
    if not path.is_file():
        return None, "不存在"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"读不出来（{exc}）"
    try:
        return json.loads(text, parse_float=_Num), ""
    except (ValueError, RecursionError) as exc:
        return None, f"不是合法的 JSON（{exc}）"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value)


def _decimals_of(value: Any) -> int:
    """数值写到小数点后第几位（整数为 0；科学计数法按展开后的位数）。"""
    if not isinstance(value, float) or isinstance(value, bool):
        return 0
    literal = getattr(value, "lit", None) or repr(float(value))
    try:
        exponent = Decimal(literal).as_tuple().exponent
    except InvalidOperation:
        return 0
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _norm(text: Any) -> str:
    """全角字母、数字、括号、标点转成半角（NFKC）。"""
    return unicodedata.normalize("NFKC", str(text))


def _squash(text: Any) -> str:
    """规整后去掉全部空白。"""
    return re.sub(r"\s+", "", _norm(text))


def _short(text: Any, limit: int = 40) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _md_cell(text: Any) -> str:
    """把任意值写成一个 markdown 表格单元格：竖线转义、换行改成 <br>，空的写成破折号。"""
    s = str(text).strip().replace("|", "\\|")
    s = re.sub(r"\s*\r?\n\s*", "<br>", s)
    return s or "—"


def _fmt_value(value: Any, unit: str = "") -> str:
    """把研报值 / 复现值写成人读的文本：尽量保留原写法，过长的浮点数压到 6 位有效数字。"""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        literal = getattr(value, "lit", None) or repr(float(value))
        text = literal if len(literal) <= 12 else format(float(value), ".6g")
    else:
        return str(value)
    unit = (unit or "").strip()
    if not unit:
        return text
    return text + unit if unit in ("%", "％") else f"{text} {unit}"


# ---------------------------------------------------------------------------
# 案例装载与重算
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Counts:
    """重算口径的计数。"""

    m_total: int = 0
    m_pass: int = 0
    m_fail: int = 0
    m_na: int = 0  # 重算结论为空：unverifiable 豁免，或标准里没有可用的容差
    m_valued: int = 0  # 复现值不为空的数值条目数
    q_total: int = 0
    q_pass: int = 0
    q_fail: int = 0

    @property
    def metric_denominators(self) -> set[int]:
        """数值口径下可以接受的分母：全部条目、剔除 N/A 后的条目、有复现值的条目。"""
        return {self.m_total, self.m_total - self.m_na, self.m_valued}

    def accepted(self, family: str, polarity: str) -> set[tuple[int, int]]:
        """文书里「a/b」可以接受的取值。family：metrics 数值 / qualitative 定性 / all 合计 / any 任一口径。"""
        m_num = self.m_pass if polarity == "pass" else self.m_fail
        q_num = self.q_pass if polarity == "pass" else self.q_fail
        metrics = {(m_num, d) for d in self.metric_denominators}
        qualitative = {(q_num, self.q_total)}
        combined = {(m_num + q_num, d + self.q_total) for d in self.metric_denominators}
        if family == "metrics":
            return metrics
        if family == "qualitative":
            return qualitative
        if family == "all":
            return combined
        return metrics | qualitative | combined

    def denominators(self, family: str) -> set[int]:
        return {b for _a, b in self.accepted(family, "pass")}

    def grand_totals(self) -> set[int]:
        """全案例的条目总数：数值口径的分母，或再加上定性条目数。"""
        return self.metric_denominators | {d + self.q_total for d in self.metric_denominators}

    def totals(self) -> set[int]:
        """「共 N 项」可以接受的取值：全案例的条目总数，或单是定性条目数。"""
        return self.grand_totals() | ({self.q_total} if self.q_total else set())

    def describe(self) -> str:
        text = f"数值 {self.m_pass}/{self.m_total}"
        if self.m_na:
            text += f"（另 N/A {self.m_na} 项，剔除后分母 {self.m_total - self.m_na}）"
        if self.q_total:
            text += f"、定性 {self.q_pass}/{self.q_total}、合计 {self.m_pass + self.q_pass}/{self.m_total + self.q_total}"
        return text


@dataclass
class _Case:
    """一个案例的机器结果：comparison.json、按 standards.json 的重算结论、案例类型与模式。"""

    root: Path
    report_id: str
    comparison: Optional[dict] = None
    error: str = ""  # comparison.json 用不了的原因
    metrics: list[dict] = field(default_factory=list)
    qualitative: list[dict] = field(default_factory=list)
    recalc: list[Any] = field(default_factory=list)  # 与 metrics 逐条对应的 cg.MetricRecalc
    qual_passed: list[bool] = field(default_factory=list)  # 与 qualitative 逐条对应
    report_type: Optional[str] = None
    experimental: bool = False
    standards: dict = field(default_factory=dict)
    key_lines: dict[str, int] = field(default_factory=dict)  # 指标编号在 comparison.json 里的行号
    notes: list[str] = field(default_factory=list)

    @property
    def comparison_rel(self) -> str:
        return _rel(self.root, _comparison_path(self.root, self.report_id))

    def counts(self) -> _Counts:
        return _counts_of(self.metrics, self.recalc, self.qual_passed)

    def where_of(self, entry: dict) -> tuple[str, int]:
        return self.comparison_rel, self.key_lines.get(str(entry.get("key")), 0)


def _as_dict_list(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _counts_of(metrics: list[dict], recalc: list[Any], qual_passed: list[bool]) -> _Counts:
    passed = [getattr(r, "passed", None) for r in recalc]
    return _Counts(
        m_total=len(metrics),
        m_pass=sum(1 for p in passed if p is True),
        m_fail=sum(1 for p in passed if p is False),
        m_na=sum(1 for p in passed if p is None),
        m_valued=sum(1 for m in metrics if m.get("reproduced_value") is not None),
        q_total=len(qual_passed),
        q_pass=sum(1 for p in qual_passed if p),
        q_fail=sum(1 for p in qual_passed if not p),
    )


def _state_info(root: Path, report_id: str) -> tuple[Optional[str], bool]:
    """案例类型与是否实验模式。只认 state.json（与门禁同口径）；state 读不到时按 strict、类型未知处理。"""
    try:
        state = st.load_state(root, report_id)
    except (OSError, ValueError):
        return None, False
    if not isinstance(state, dict):
        return None, False
    report_type = state.get("type")
    return (report_type if isinstance(report_type, str) else None), state.get("reproduction_mode") == "experimental"


def _recalc(comparison: dict, standards: dict, report_type: Optional[str], experimental: bool) -> tuple[list[dict], list[dict], list[Any], list[bool]]:
    """按 standards.json 重算一份 comparison，返回 (数值条目, 定性条目, 逐条重算结果, 定性逐条是否通过)。"""
    metrics = _as_dict_list(comparison.get("metrics"))
    qualitative = _as_dict_list(comparison.get("qualitative"))
    clean = dict(comparison)
    clean["metrics"], clean["qualitative"] = metrics, qualitative
    result = cg.recalc_comparison(clean, standards, report_type, experimental)
    qual_passed = [bool(item.get("passed")) for item in result.qualitative]
    return metrics, qualitative, list(result.metrics), qual_passed


_KEY_LINE_RE = re.compile(r'"key"\s*:\s*("(?:[^"\\]|\\.)*")')


def _key_lines(path: Path) -> dict[str, int]:
    """指标编号 → 它在 comparison.json 里首次出现的行号（给发现定位用）。"""
    out: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for no, line in enumerate(text.split("\n"), 1):
        for m in _KEY_LINE_RE.finditer(line):
            try:
                key = json.loads(m.group(1))
            except ValueError:
                continue
            out.setdefault(str(key), no)
    return out


def _load_case(root: Path, report_id: str) -> _Case:
    root = Path(root)
    case = _Case(root=root, report_id=report_id)
    case.report_type, case.experimental = _state_info(root, report_id)
    path = _comparison_path(root, report_id)
    data, error = _load_json(path)
    if error:
        case.error = error
        return case
    if not isinstance(data, dict):
        case.error = "顶层不是对象"
        return case
    case.standards = cg.load_standards(root)
    for name in ("metrics", "qualitative"):
        raw = data.get(name)
        if raw is not None and not isinstance(raw, list):
            case.notes.append(f"comparison.json 的 {name} 不是列表，按空处理")
        elif isinstance(raw, list) and any(not isinstance(item, dict) for item in raw):
            case.notes.append(f"comparison.json 的 {name} 里有不是对象的条目，已跳过")
    try:
        metrics, qualitative, recalc, qual_passed = _recalc(data, case.standards, case.report_type, case.experimental)
    except Exception as exc:  # noqa: BLE001 —— 条目字段类型离谱时（如 tolerance_key 写成列表）重算函数会直接抛
        case.error = f"重算不了（{type(exc).__name__}：{_short(exc, 80)}）"
        return case
    case.comparison = data
    case.metrics, case.qualitative, case.recalc, case.qual_passed = metrics, qualitative, recalc, qual_passed
    case.key_lines = _key_lines(path)
    return case


# ---------------------------------------------------------------------------
# 机器生成的表格：对比总表、达标计数、产物清单
# ---------------------------------------------------------------------------

COMPARISON_TABLE_HEADER = "| 指标编号 | 名称 | 来源要素 | 研报值 | 复现值 | 偏差 | 结论 |"
ARTIFACTS_TABLE_HEADER = "| 文件名 | 大小 | 修改时间 |"


def _deviation_text(entry: dict) -> str:
    """相对偏差 = |复现值 - 研报值| / |研报值|；研报值为 0 时给绝对差；有一边不是有限数时不写。"""
    report, reproduced = entry.get("report_value"), entry.get("reproduced_value")
    if not (_is_finite(report) and _is_finite(reproduced)):
        return "—"
    if report == 0:
        return "0.00%" if reproduced == 0 else f"绝对差 {abs(reproduced - report):.6g}"
    return f"{abs(reproduced - report) / abs(report) * 100:.2f}%"


def _verdict_text(passed: Optional[bool], experimental: bool, self_pass: Any) -> str:
    """结论列：取重算结果。文件自述为通过而重算不认的，注明出来。"""
    if experimental:
        text = "产出在位" if passed else "产出缺失"
    elif passed is True:
        text = "达标"
    elif passed is False:
        text = "未达标"
    else:
        text = "N/A"
    if self_pass is True and passed is not True:
        text += "（文件自述为通过，重算不认）"
    return text


def comparison_table(root: Path, report_id: str) -> str:
    """机器生成的对比总表（markdown 表格）。

    列：指标编号 | 名称 | 来源要素 | 研报值 | 复现值 | 偏差 | 结论。数值条目在前，定性条目在后
    （定性条目的研报值、复现值两列放 expect、observed，偏差列写「定性」）。结论一律取
    `check_gates.recalc_comparison` 的重算结果，不采信文件自述的 pass；实验模式下重算只核产出
    是否在位，结论写「产出在位 / 产出缺失」。comparison.json 用不了时返回只有一行说明的表。
    """
    case = _load_case(Path(root), report_id)
    lines = [COMPARISON_TABLE_HEADER, "| --- | --- | --- | --- | --- | --- | --- |"]
    if case.comparison is None:
        lines.append(f"| — | comparison.json {_md_cell(case.error)} | — | — | — | — | — |")
        return "\n".join(lines)
    for entry, recalc in zip(case.metrics, case.recalc):
        unit = entry.get("unit") if isinstance(entry.get("unit"), str) else ""
        cells = [
            entry.get("key", "?"),
            entry.get("name") or "—",
            entry.get("source_element") or "—",
            _fmt_value(entry.get("report_value"), unit),
            _fmt_value(entry.get("reproduced_value"), unit),
            _deviation_text(entry),
            _verdict_text(recalc.passed, case.experimental, entry.get("pass")),
        ]
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    for entry, passed in zip(case.qualitative, case.qual_passed):
        cells = [
            entry.get("key", "?"),
            entry.get("name") or "—",
            entry.get("source_element") or "—",
            _fmt_value(entry.get("expect")),
            _fmt_value(entry.get("observed")),
            "定性",
            _verdict_text(passed, case.experimental, entry.get("pass")),
        ]
        lines.append("| " + " | ".join(_md_cell(c) for c in cells) + " |")
    return "\n".join(lines)


def comparison_counts(root: Path, report_id: str) -> dict:
    """达标计数（重算口径），数值条目与定性条目合在一起数：{"total", "pass", "fail", "na"}。

    na 是重算结论为空的条目（unverifiable 豁免，或标准里没有可用容差）；total = pass + fail + na。
    要分开看数值与定性，用 `comparison_breakdown`。comparison.json 用不了时四项都是 0。
    """
    c = _load_case(Path(root), report_id).counts()
    return {
        "total": c.m_total + c.q_total,
        "pass": c.m_pass + c.q_pass,
        "fail": c.m_fail + c.q_fail,
        "na": c.m_na,
    }


def comparison_breakdown(root: Path, report_id: str) -> dict:
    """达标计数的分项（重算口径）：数值条目、定性条目各自的总数与达标数。"""
    return _stats_counts(_load_case(Path(root), report_id).counts())


def _stats_counts(c: _Counts) -> dict:
    return {
        "metrics_total": c.m_total,
        "metrics_pass": c.m_pass,
        "metrics_fail": c.m_fail,
        "metrics_na": c.m_na,
        "qualitative_total": c.q_total,
        "qualitative_pass": c.q_pass,
        "qualitative_fail": c.q_fail,
        "total": c.m_total + c.q_total,
        "pass": c.m_pass + c.q_pass,
        "fail": c.m_fail + c.q_fail,
        "na": c.m_na,
    }


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _artifact_files(results: Path) -> list[Path]:
    """结果目录下的产物文件（含子目录）：不含 __pycache__、字节码、隐藏文件和 Office 的临时锁文件。"""
    if not results.is_dir():
        return []
    files = []
    for path in results.rglob("*"):
        rel_parts = path.relative_to(results).parts
        if "__pycache__" in rel_parts or path.suffix == ".pyc":
            continue
        if any(part.startswith(".") for part in rel_parts) or path.name.startswith("~$"):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(results).as_posix())


def artifacts_table(root: Path, report_id: str) -> str:
    """`output/<id>/results/` 下的产物清单（markdown 表格）：文件名 | 大小 | 修改时间，末行是合计。

    文件名是相对结果目录的路径，子目录里的文件也列。不含 __pycache__、字节码、隐藏文件和
    Office 的临时锁文件。结果目录不在时返回只有一行说明的表。
    """
    results = _results_dir(Path(root), report_id)
    lines = [ARTIFACTS_TABLE_HEADER, "| --- | --- | --- |"]
    if not results.is_dir():
        lines.append("| （结果目录不存在） | — | — |")
        return "\n".join(lines)
    total_size = 0
    latest = 0.0
    files = _artifact_files(results)
    for path in files:
        try:
            info = path.stat()
        except OSError:
            continue
        total_size += info.st_size
        latest = max(latest, info.st_mtime)
        stamp = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"| {_md_cell(path.relative_to(results).as_posix())} | {_human_size(info.st_size)} | {stamp} |")
    latest_text = datetime.fromtimestamp(latest).strftime("%Y-%m-%d %H:%M:%S") if files else "—"
    lines.append(f"| 合计 {len(files)} 个文件 | {_human_size(total_size)} | {latest_text} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# P1 核心要素有对比条目
# ---------------------------------------------------------------------------

_ELEMENT_AT_RE = re.compile(r"(R|SA)(\d+)(?:\.(\d+))?")
_ELEMENT_SEP_RE = re.compile(r"[/、,+&和与及]|[-~–—至到]")
_RANGE_SEPS = "-~–—至到"
_LEADING_JUNK = "[【(#「『\"'`*<"
_NA_TEXT_RE = re.compile(r"^(?:N/?A(?![A-Za-z])|不适用)", re.IGNORECASE)


def _leading_ids(text: Any) -> set[str]:
    """文本开头写的 R / SA 要素编号（去掉空白、不分大小写）。

    「R1表内格/p10交叉验证」→ {R1}；「SA4对照」→ {SA4}；「r10_top1_hit」→ {R10}（不含 R1）；
    并列与区间也认：「R7/R15表」→ {R7, R15}，「R7-R9」→ {R7, R8, R9}。
    子变体的条目同时算作父要素的条目：「R3.1表」→ {R3, R3.1}。
    """
    s = _squash(text).upper().lstrip(_LEADING_JUNK)
    ids: set[str] = set()
    pos = 0
    previous: Optional[tuple[str, int]] = None
    in_range = False
    while True:
        m = _ELEMENT_AT_RE.match(s, pos)
        if not m:
            break
        prefix, number, sub = m.group(1), int(m.group(2)), m.group(3)
        ids.add(f"{prefix}{number}")
        if sub is not None:
            ids.add(f"{prefix}{number}.{sub}")
        if in_range and previous and previous[0] == prefix and sub is None and 0 < number - previous[1] <= 50:
            ids.update(f"{prefix}{k}" for k in range(previous[1] + 1, number))
        previous = (prefix, number) if sub is None else None
        pos = m.end()
        sep = _ELEMENT_SEP_RE.match(s, pos)
        if not sep:
            break
        in_range = sep.group(0) in _RANGE_SEPS
        pos = sep.end()
    return ids


def _covers(text: Any, element_id: str) -> bool:
    """这段文本是不是以该要素编号开头（R1 不会匹配上 R10）。"""
    eid = element_id.upper()
    if eid in _leading_ids(text):
        return True
    if "." in eid:  # 子变体在指标编号里常写成下划线：R3.1 → r3_1_xxx
        alt = eid.replace(".", "_")
        s = _squash(text).upper().lstrip(_LEADING_JUNK)
        return s.startswith(alt) and not s[len(alt) : len(alt) + 1].isdigit()
    return False


def _is_explicit_na(entry: dict) -> bool:
    """条目是不是显式标了 N/A。

    口径取自 r009、r010 的真实文件，满足任一条即认：
    1. `verification_level` 为 unverifiable。r010 的 R5–R8、R10 等就是这样：report_value、
       reproduced_value、pass 都是 null，note 写明没有复现值的原因（数据缺失或不在范围内）。
    2. 数值条目的 `reproduced_value`，或定性条目的 `expect` / `observed`，是以「N/A」「不适用」
       开头的字符串。r009 的 sa7_outlook_na 是定性条目，expect 为
       「N/A（研报 p41 优化方向展望，spec 显著标注未实测）」。
    3. 条目带 `na: true`，或 `status` 为 na / n/a / not_applicable（留给新案例的结构化写法）。
    """
    if str(entry.get("verification_level") or "").strip().lower() == "unverifiable":
        return True
    if entry.get("na") is True:
        return True
    if str(entry.get("status") or "").strip().lower() in ("na", "n/a", "not_applicable"):
        return True
    for name in ("reproduced_value", "expect", "observed"):
        value = entry.get(name)
        if isinstance(value, str) and _NA_TEXT_RE.match(_norm(value).strip()):
            return True
    return False


def _core_elements(case: _Case) -> tuple[list[dict], str]:
    """要求有对比条目的要素：矩阵里优先级 core、状态不是 skipped / infeasible 的 R 类与 SA 类。

    返回 ([{id, desc, line}], 矩阵用不了的原因)。
    """
    path = _matrix_path(case.root, case.report_id)
    if not path.is_file():
        return [], "不存在"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], f"读不出来（{exc}）"
    line_of: dict[str, int] = {}
    for no, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^\s*\|\s*((?:R|SA)\d+(?:\.\d+)?)\s*\|", line)
        if m:
            line_of.setdefault(m.group(1), no)
    rows = cg.load_matrix_rows(path)
    if not rows:
        return [], "里没有解析出任何要素行"
    out = []
    for row in rows:
        eid = cg._row_get(row, "要素ID").strip()
        if not re.match(r"^(R|SA)\d", eid):
            continue
        # 单元格里的加粗、行内代码记号不算内容：「**core**」「`skipped`」照常认
        priority = re.sub(r"[*`\s]", "", cg._row_get(row, "优先级")).lower()
        status = re.sub(r"[*`\s]", "", cg._row_get(row, "状态")).lower()
        if priority != "core" or status in ("skipped", "infeasible"):
            continue
        out.append({"id": eid, "desc": cg._row_get(row, "描述"), "line": line_of.get(eid, 0)})
    return out, ""


def _check_p1(case: _Case, stats: dict) -> list[_Hit]:
    """P1：核心 R / SA 要素在 comparison.json 里都有对比条目或显式 N/A。

    条目归属哪个要素，看 `metrics[].source_element`（`qualitative[]` 的同名字段同理）：去掉空白后
    以要素编号开头即算（R1 不匹配 R10；并列、区间写法见 `_leading_ids`）。两种条目可以靠指标
    编号指向要素：定性条目没写来源要素的（verifier 合同里定性条目只有 key / expect / observed /
    pass，r009 的 sa5_…、sa6_… 即是），指标编号以要素编号开头即算；显式标 N/A 的条目（认定口径见
    `_is_explicit_na`），指标编号或名称以要素编号开头即算。其余条目的来源要素没对上、但指标编号
    或名称以要素编号开头的，`P1_KEY_FALLBACK` 为 True 时也算有条目，另出一条提示；为 False 时
    按缺条目报阻断。缺条目的要素逐个报出。
    """
    matrix_rel = _rel(case.root, _matrix_path(case.root, case.report_id))
    elements, problem = _core_elements(case)
    stats["core_elements"] = len(elements)
    stats["core_element_ids"] = [e["id"] for e in elements]
    stats["core_missing"] = []
    if problem:
        if problem == "不存在" or problem.startswith("读不出来"):
            return [_Hit("P1", "block", f"覆盖矩阵 coverage_matrix.md {problem}，核不了核心要素有没有对比条目", matrix_rel)]
        return [_Hit("P1", "warn", f"覆盖矩阵 coverage_matrix.md {problem}，核心要素按 0 个处理", matrix_rel)]
    stats["checked_files"].append(matrix_rel)

    entries = []
    for i, entry in enumerate([*case.metrics, *case.qualitative]):
        source = str(entry.get("source_element") or "")
        entries.append(
            {
                "source": source,
                "key": str(entry.get("key") or ""),
                "name": str(entry.get("name") or ""),
                "na": _is_explicit_na(entry),
                # 定性条目没写来源要素：指标编号就是它的归属
                "keyed": i >= len(case.metrics) and not source.strip(),
            }
        )
    stats["explicit_na"] = sum(1 for e in entries if e["na"])

    hits: list[_Hit] = []
    by_fallback: list[str] = []
    for element in elements:
        eid = element["id"]
        by_source = any(_covers(e["source"], eid) or (e["keyed"] and _covers(e["key"], eid)) for e in entries)
        by_key = [e for e in entries if _covers(e["key"], eid) or _covers(e["name"], eid)]
        if by_source or any(e["na"] for e in by_key):
            continue
        if by_key and P1_KEY_FALLBACK:
            by_fallback.append(eid)
            continue
        stats["core_missing"].append(eid)
        desc = f"（{_short(element['desc'], 24)}）" if element["desc"] else ""
        if by_key:
            sample = by_key[0]
            detail = (
                f"在 comparison.json 里没有来源要素以它开头的条目"
                f"（指标 {sample['key']} 的 source_element 是「{_short(sample['source'], 24)}」）："
                f"应把这类条目的 source_element 改成以 {eid} 开头"
            )
        else:
            detail = (
                f"在 comparison.json 里没有对比条目，也没有显式标 N/A 的条目："
                f"应补一条 source_element 以 {eid} 开头的条目，无法复现的显式标 N/A"
            )
        hits.append(_Hit("P1", "block", f"核心要素 {eid}{desc}{detail}", matrix_rel, element["line"]))
    if by_fallback:
        hits.append(
            _Hit(
                "P1",
                "warn",
                f"核心要素 {'、'.join(by_fallback)} 的对比条目没有在 source_element 里写要素编号，"
                "是靠指标编号或名称对上的：新案例的 source_element 应以要素编号开头",
                case.comparison_rel,
            )
        )
    return hits


# ---------------------------------------------------------------------------
# P2 原始来源指针回查
# ---------------------------------------------------------------------------

_POINTER_PREFIX_RE = re.compile(r"^\s*(?:(?:results/)?metrics\.json\s*[#:]\s*/?|\$\.?|#/?)")


def parse_pointer(pointer: str) -> list[Any]:
    """把来源指针拆成路径段。

    写法：用点分隔键，方括号写下标，如 `strategies.core.annual_return`、`table2[3].sharpe`。
    键里带点或方括号的，写成带引号的下标：`perf["A.B"].sharpe`。开头可以带 `metrics.json#`。
    键里的竖线、圆括号、逗号、中文都可以直接写，如 `m4|l1_dynamic|TOP5(动态).sharpe`。
    """
    s = _POINTER_PREFIX_RE.sub("", pointer.strip(), count=1)
    tokens: list[Any] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == ".":
            i += 1
            continue
        if ch == "[":
            j = i + 1
            while j < n and s[j] == " ":
                j += 1
            if j < n and s[j] in "\"'":
                quote = s[j]
                end = s.find(quote, j + 1)
                close = s.find("]", end + 1) if end != -1 else -1
                if end == -1 or close == -1 or s[end + 1 : close].strip():
                    raise ValueError(f"方括号没有配对：{pointer}")
                tokens.append(s[j + 1 : end])
                i = close + 1
                continue
            close = s.find("]", i + 1)
            if close == -1:
                raise ValueError(f"方括号没有配对：{pointer}")
            inner = s[i + 1 : close].strip()
            if not inner:
                raise ValueError(f"方括号里是空的：{pointer}")
            tokens.append(int(inner) if re.fullmatch(r"\d+", inner) else inner)
            i = close + 1
            continue
        j = i
        while j < n and s[j] not in ".[":
            j += 1
        tokens.append(s[i:j].strip())
        i = j
    if not tokens or any(t == "" for t in tokens):
        raise ValueError(f"指针是空的或有空段：{pointer}")
    return tokens


def resolve_pointer(data: Any, pointer: str) -> tuple[bool, Any, str]:
    """按指针从 metrics.json 取值，返回 (取到没有, 值, 取不到的原因)。

    整数段遇到列表按下标取，遇到对象按同名的键取（如年份 `yearly[2015]`）。键本身带点而指针
    没加引号时，会把相邻的段用点拼回去再试一次。
    """
    try:
        tokens = parse_pointer(pointer)
    except ValueError as exc:
        return False, None, str(exc)
    node = data
    i = 0
    walked: list[str] = []
    while i < len(tokens):
        token = tokens[i]
        here = ".".join(walked) or "顶层"
        if isinstance(node, list):
            index = token if isinstance(token, int) else (int(token) if re.fullmatch(r"\d+", str(token)) else None)
            if index is None:
                return False, None, f"{here} 是列表，不能用键 {token!r} 取"
            if index >= len(node):
                return False, None, f"{here} 只有 {len(node)} 项，下标 {index} 越界"
            node = node[index]
            walked.append(str(index))
            i += 1
            continue
        if isinstance(node, dict):
            joined = str(token)
            found = False
            for j in range(i, len(tokens)):
                if j > i:
                    joined = f"{joined}.{tokens[j]}"
                if joined in node:
                    node = node[joined]
                    walked.append(joined)
                    i = j + 1
                    found = True
                    break
            if not found:
                return False, None, f"{here} 下没有键 {str(token)!r}"
            continue
        return False, None, f"{here} 已经是一个值，下面没有 {token!r}"
    if isinstance(node, (dict, list)):
        return False, None, "指到的是一个对象或列表，不是单个值"
    return True, node, ""


def _is_empty_raw(value: Any) -> bool:
    """原始值是空的：null，或不是有限数。"""
    return value is None or (_is_number(value) and not math.isfinite(value))


def _within_rounding(reproduced: Any, raw: Any) -> bool:
    """两个数在舍入范围内一致：相对误差不超过 1e-6，或绝对误差不超过复现值末位小数的半个单位，取宽者。"""
    a, b = float(reproduced), float(raw)
    tol = max(POINTER_REL_TOL * max(abs(a), abs(b)), 0.5 * 10 ** (-_decimals_of(reproduced)))
    return abs(a - b) <= tol * (1 + 1e-9)


def _pointer_agrees(reproduced: Any, raw: Any, unit: str) -> bool:
    if _is_empty_raw(reproduced) and _is_empty_raw(raw):
        return True
    if _is_empty_raw(reproduced) or _is_empty_raw(raw):
        return False
    if _is_number(reproduced) and _is_number(raw):
        if _within_rounding(reproduced, raw):
            return True
        # 条目注明单位是百分号时，容忍「metrics.json 存小数、对比条目存百分数」
        return "%" in _norm(unit) and _within_rounding(reproduced, float(raw) * 100)
    if isinstance(reproduced, bool) or isinstance(raw, bool):
        return reproduced is raw
    return str(reproduced).strip() == str(raw).strip()


def _check_p2(case: _Case, stats: dict, raw_values: dict[int, Any]) -> list[_Hit]:
    """P2：对比条目带了 `source_pointer` 的，取出 metrics.json 对应位置的值与复现值比对。

    舍入范围：相对误差 1e-6，或绝对误差不超过 reproduced_value 末位小数的半个单位，取宽者。
    条目写了 `unit: "%"` 时，另容忍 metrics.json 存小数、对比条目存百分数。指针解析不到也报。
    没带指针的条目不查。metrics.json 用不了时，带指针的条目合成一条阻断。
    取到的原始值记进 raw_values（数值条目的下标 → 值），供 P3 判断「原始值为空」。
    """
    pointed: list[tuple[int, dict, Any, bool]] = []  # (数值条目下标或 -1, 条目, 指针, 是否数值条目)
    for i, entry in enumerate(case.metrics):
        if entry.get(POINTER_FIELD) not in (None, ""):
            pointed.append((i, entry, entry.get(POINTER_FIELD), True))
    for entry in case.qualitative:
        if entry.get(POINTER_FIELD) not in (None, ""):
            pointed.append((-1, entry, entry.get(POINTER_FIELD), False))
    stats["pointers_checked"] = len(pointed)
    if not pointed:
        return []

    metrics_path = _metrics_path(case.root, case.report_id)
    metrics_rel = _rel(case.root, metrics_path)
    data, error = _load_json(metrics_path)
    if error:
        keys = [str(entry.get("key", "?")) for _i, entry, _p, _m in pointed]
        sample = "、".join(keys[:5]) + ("…" if len(keys) > 5 else "")
        return [
            _Hit(
                "P2",
                "block",
                f"{len(keys)} 条对比条目带了来源指针，但 metrics.json {error}，无法回查（{sample}）",
                metrics_rel,
            )
        ]
    stats["checked_files"].append(metrics_rel)

    hits: list[_Hit] = []
    for index, entry, pointer, is_metric in pointed:
        key = entry.get("key", "?")
        path, line = case.where_of(entry)
        if not isinstance(pointer, str):
            hits.append(_Hit("P2", "block", f"指标 {key} 的来源指针不是字符串（{_short(pointer)}）：应写成用点和方括号表示的路径", path, line))
            continue
        ok, raw, reason = resolve_pointer(data, pointer)
        if not ok:
            hits.append(_Hit("P2", "block", f"指标 {key} 的来源指针 {pointer} 在 metrics.json 里取不到值（{reason}）", path, line))
            continue
        if is_metric:
            raw_values[index] = raw
        reproduced = entry.get("reproduced_value") if is_metric else entry.get("observed")
        unit = entry.get("unit") if isinstance(entry.get("unit"), str) else ""
        if _pointer_agrees(reproduced, raw, unit):
            continue
        hits.append(
            _Hit(
                "P2",
                "block",
                f"指标 {key} 的复现值 {_fmt_value(reproduced)} 与来源指针 {pointer} 取到的 {_fmt_value(raw)} 不一致"
                "（超出舍入范围）：复现值应与 metrics.json 里的原始值一致",
                path,
                line,
            )
        )
    return hits


# ---------------------------------------------------------------------------
# P3 空值不得计为通过
# ---------------------------------------------------------------------------

_EMPTY_STRINGS = {
    "", "nan", "inf", "+inf", "-inf", "infinity", "-infinity", "null", "none", "n/a", "na", "-", "--",
    "—", "——", "tbd", "todo", "待补", "待填", "占位", "[verify 后填]",
}
_SENTINEL_VALUES = {0, -1, 999, 9999, 99999, -999, -9999, -99999}
_PLACEHOLDER_STRONG = ("占位", "placeholder", "非真实", "哨兵值", "dummy", "填充值")
_PLACEHOLDER_WEAK = ("不可定义", "无法定义", "未定义", "无定义", "无法计算", "不可计算", "undefined", "not defined")
_PLACEHOLDER_FIELDS = ("note", "reason", "attribution_note", "remark", "comment")
_NEGATIONS = "非不无未免勿"


def _empty_kind(value: Any) -> str:
    """复现值是哪一种空：null / NaN / Inf / 占位字符串；不是空值返回空串。"""
    if value is None:
        return "null"
    if _is_number(value):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        return ""
    if isinstance(value, str) and _norm(value).strip().lower() in _EMPTY_STRINGS:
        return f"占位字符串「{value}」" if value.strip() else "空字符串"
    return ""


def _admitted_placeholder(entry: dict) -> str:
    """复现值是有限数，但条目自己的文字说明承认它不是真实值：返回命中的那段话，否则返回空串。

    这是 r009 结果外审 CDX-R-01 的形态：全程空仓时夏普 0/0 不可定义，对比条目按 0.0 占位、
    note 里注明是占位值，却照样记了 pass。认定口径（两条都要求复现值是 0 或 -1、±999 一类哨兵值）：
    - note / reason / attribution_note 里出现「占位」「placeholder」「非真实」等字样，且前面不带
      否定（「不再占位」「非占位」不算）；
    - 或复现值恰为 0，而这些字段里出现「不可定义」「无法计算」「undefined」等字样。
    """
    value = entry.get("reproduced_value")
    if not _is_finite(value) or value not in _SENTINEL_VALUES:
        return ""
    for name in _PLACEHOLDER_FIELDS:
        text = entry.get(name)
        if not isinstance(text, str):
            continue
        low = text.lower()
        for word in _PLACEHOLDER_STRONG:
            for m in re.finditer(re.escape(word), low):
                if any(ch in _NEGATIONS for ch in low[max(0, m.start() - 2) : m.start()]):
                    continue
                return _short(text[max(0, m.start() - 12) : m.end() + 12], 36)
        if value == 0:
            for word in _PLACEHOLDER_WEAK:
                pos = low.find(word)
                if pos != -1:
                    return _short(text[max(0, pos - 12) : pos + len(word) + 12], 36)
    return ""


def _counted_reason(entry: dict, recalc_passed: Optional[bool], all_counted: bool, pass_count: Any) -> str:
    """这条条目是怎么被计为通过的；没有被计为通过返回空串。"""
    if entry.get("pass") is True:
        return "自述 pass=true"
    if recalc_passed is True:
        return "重算口径计为通过"
    if entry.get("pass") is None and all_counted:
        return f"顶层 pass_count={pass_count} 把全部条目都计入了通过数"
    return ""


def _check_p3(case: _Case, stats: dict, raw_values: dict[int, Any]) -> list[_Hit]:
    """P3：空值、占位值不得计为通过。

    「空」的认定：
    1. `reproduced_value` 是 null、NaN、±Inf，或「NaN」「N/A」「-」「待补」这类占位字符串；
    2. `reproduced_value` 是有限数，但条目自己承认它是占位值（口径见 `_admitted_placeholder`）；
    3. 来源指针取到的原始值是 null 或非有限数，`reproduced_value` 却是有限数；
    4. 定性条目（`qualitative[]`）的 `observed` 是 null 或空白。
    「计为通过」的认定：条目自述 `pass: true`；或重算口径下算通过（实验模式只核产出是否在位，
    NaN、占位值都会被算作在位）；或条目没有 pass 字段而顶层 `pass_count` 不小于条目总数。
    不算在内的：`report_value` 为 null 且带文字 `note` 的数值条目，是没有研报数值可比的对照项，
    通过与否由人和外审看 note 判断，这里不报；pass 不为 true、重算也不算通过的 N/A 条目不报。
    """
    comparison = case.comparison or {}
    pass_count = comparison.get("pass_count")
    all_counted = _is_number(pass_count) and len(case.metrics) > 0 and pass_count >= len(case.metrics)
    hits: list[_Hit] = []
    for i, (entry, recalc) in enumerate(zip(case.metrics, case.recalc)):
        key = entry.get("key", "?")
        value = entry.get("reproduced_value")
        note = entry.get("note")
        if entry.get("report_value") is None and isinstance(note, str) and note.strip():
            continue  # 没有研报数值可比的对照项，不在 P3 范围内
        counted = _counted_reason(entry, recalc.passed, all_counted, pass_count)
        if not counted:
            continue
        kind = _empty_kind(value)
        if kind:
            what = f"复现值是空的（{kind}）"
        else:
            admitted = _admitted_placeholder(entry)
            if admitted:
                what = f"复现值 {_fmt_value(value)} 是占位值（条目自述「{admitted}」）"
            elif i in raw_values and _is_empty_raw(raw_values[i]) and _is_finite(value):
                what = (
                    f"来源指针取到的原始值是空的（{_fmt_value(raw_values[i])}），"
                    f"复现值却写成 {_fmt_value(value)}"
                )
            else:
                continue
        path, line = case.where_of(entry)
        hits.append(
            _Hit(
                "P3",
                "block",
                f"指标 {key} 的{what}，却被计为通过（{counted}）：空值和占位值不得计为通过，"
                "算不出来的应把复现值留空并显式标 N/A",
                path,
                line,
            )
        )
    for entry, passed in zip(case.qualitative, case.qual_passed):
        observed = entry.get("observed")
        if not (observed is None or (isinstance(observed, str) and not observed.strip())):
            continue
        if _is_explicit_na(entry):
            continue
        counted = "自述 pass=true" if entry.get("pass") is True else ("重算口径计为通过" if passed else "")
        if not counted:
            continue
        path, line = case.where_of(entry)
        hits.append(
            _Hit(
                "P3",
                "block",
                f"定性条目 {entry.get('key', '?')} 的实际观察（observed）是空的，却被计为通过（{counted}）："
                "空值不得计为通过",
                path,
                line,
            )
        )
    stats["empty_counted_as_pass"] = len(hits)
    return hits


# ---------------------------------------------------------------------------
# P4 文书解析
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:-]+(\|[\s:-]+)*\|\s*$")


@dataclass
class _Table:
    header: tuple[str, ...]
    header_line: int


@dataclass
class _Line:
    no: int  # 行号，从 1 起
    text: str
    skip: bool  # 在代码围栏或机器生成块里，P4 不看
    headings: tuple[str, ...]  # 所在章节的标题链（二级及以下，含本行自己）
    table: Optional[_Table] = None
    role: str = ""  # 表格里的角色：header / sep / row；不在表格里为空
    cells: tuple[str, ...] = ()


@dataclass
class _Doc:
    rel: str
    lines: list[_Line]
    dangling: list[tuple[str, int]]  # 缺 END 的生成块 [(名字, 行号)]

    @property
    def name(self) -> str:
        return Path(self.rel).name


def _split_cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|") and inner.endswith("|"):
        inner = inner[1:-1]
    return [part.strip().replace("\\|", "|") for part in re.split(r"(?<!\\)\|", inner)]


def _is_table_line(text: str) -> bool:
    s = text.strip()
    return len(s) >= 2 and s.startswith("|") and s.endswith("|")


def _parse_doc(rel: str, text: str) -> _Doc:
    """把文书拆成行：标出代码围栏与机器生成块（这两处 P4 不看）、所在章节的标题链、所在表格。"""
    raw = [part.rstrip("\r") for part in text.split("\n")]
    fence = _fence_mask(raw)
    spans, dangling = _block_spans(raw)
    in_block = [False] * len(raw)
    for _name, b, e in spans:
        for i in range(b, e + 1):
            in_block[i] = True

    lines: list[_Line] = []
    chain: list[tuple[int, str]] = []
    for i, line_text in enumerate(raw):
        skip = fence[i] or in_block[i]
        if not skip:
            m = _HEADING_RE.match(line_text)
            if m:
                level = len(m.group(1))
                while chain and chain[-1][0] >= level:
                    chain.pop()
                chain.append((level, m.group(2)))
        headings = tuple(title for level, title in chain if level >= 2)
        lines.append(_Line(i + 1, line_text, skip, headings))

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        is_header = (
            not line.skip
            and _is_table_line(line.text)
            and i + 1 < n
            and not lines[i + 1].skip
            and _TABLE_SEP_RE.match(lines[i + 1].text.strip())
        )
        if not is_header:
            i += 1
            continue
        table = _Table(tuple(_split_cells(line.text)), line.no)
        line.table, line.role = table, "header"
        lines[i + 1].table, lines[i + 1].role = table, "sep"
        j = i + 2
        while j < n and not lines[j].skip and _is_table_line(lines[j].text):
            lines[j].table, lines[j].role = table, "row"
            lines[j].cells = tuple(_split_cells(lines[j].text))
            j += 1
        i = j
    # 围栏里只写了 BEGIN 的多半是举例，不当成缺 END 的块来提示
    return _Doc(rel, lines, [(name, idx + 1) for name, idx in dangling if not fence[idx]])


def _has_history_marker(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in HISTORY_MARKERS)


def _is_historical(line: _Line) -> bool:
    """这一行是不是已标注的历史记录：行内，或所在章节的标题（二级及以下）里出现历史字样。

    表格另按列看：表头里某一列标了历史字样，只是那一列不查（见 `_history_columns`），
    同一行里别的列照查。
    """
    return _has_history_marker("\n".join([line.text, *line.headings]))


def _history_columns(line: _Line) -> set[int]:
    """表格行里哪些列是标了历史字样的列（「上一轮复现」「修订前」这种表头）。"""
    if line.table is None:
        return set()
    return {i for i, name in enumerate(line.table.header) if _has_history_marker(name)}


# ---------------------------------------------------------------------------
# P4 之一：达标计数
# ---------------------------------------------------------------------------

_CLAUSE_SPLIT_RE = re.compile(r"[。;!?]")
_STRONG_ANCHOR_RE = re.compile(
    r"overall_pass|pass_count|overall|总体|整体|总计|合计|共计|全部指标|全部条目|全量|comparison|对比总表|指标对比",
    re.IGNORECASE,
)
_CATEGORY_RE = re.compile(
    r"(?P<q>定性指标|定性项|定性类|定性|qualitative)|(?P<m>数值指标|数值项|数值型|数值类|数值|metrics?)",
    re.IGNORECASE,
)
_GLOBAL_NEAR_RE = re.compile(
    r"overall_pass|pass_count|overall|总体|整体|总计|合计|共计|全部指标|全部条目", re.IGNORECASE
)
_GLOBAL_NEAR_SPAN = 24  # 全局字样离数字多近才算「紧挨着」（字符数）
_VERDICT_WORD_RE = re.compile(
    r"(?P<fail>未达标|不达标|未通过|不通过|超差|失败|fail)|(?P<pass>达标|通过|合格|pass)", re.IGNORECASE
)
# 紧挨在数字前面出现这些，说明讲的是某个要素、某一簇或门禁检查项的小计，不是全案例的达标数
_SUBSET_BEFORE_RE = re.compile(
    r"(?<![A-Za-z])(?:R|SA|F|B|D|EX|FIG|TBL|AS|IM|M)\d+|簇|分年|子样本|抽查|抽样|抽检|采样|锚点"
    r"|门禁|G-[A-Z]{2}|检查项|断言|审查|外审|意见|测试|用例|里程碑|milestone|阶段|页码|日期",
    re.IGNORECASE,
)
# 紧跟在「a/b」后面的量词：a/b 年、a/b 个行业……是比例，不是达标数
_SUBSET_AFTER_RE = re.compile(r"^\s*(?:年|个?月|日|周|格|行|列|只|轮|次|个?行业|样本|策略|页|段|组|层)")
_RATIO_RE = re.compile(r"(?<![A-Za-z0-9_.\-/])(\d{1,5})\s*/\s*(\d{1,5})(?![A-Za-z0-9_/]|\.\d)")
_UNIT = r"(?:项|条|个)"
_PAIR_RES = (
    # 达标 104 项，共 158 项
    re.compile(
        rf"(?P<verb>达标|通过|pass(?:ed)?)\s*(?:的)?\s*(?P<a>\d{{1,5}})\s*{_UNIT}\s*[,、]?\s*"
        rf"(?:共计|总计|合计|总共|共)\s*(?P<b>\d{{1,5}})\s*{_UNIT}",
        re.IGNORECASE,
    ),
    # 共 158 项，（其中）104 项达标
    re.compile(
        rf"(?:共计|总计|合计|总共|共)\s*(?P<b>\d{{1,5}})\s*{_UNIT}\s*[,、]?\s*(?:其中)?\s*"
        rf"(?P<a>\d{{1,5}})\s*{_UNIT}\s*(?P<verb>达标|通过|pass(?:ed)?)",
        re.IGNORECASE,
    ),
    # 共 158 项，（其中）达标 104 项
    re.compile(
        rf"(?:共计|总计|合计|总共|共)\s*(?P<b>\d{{1,5}})\s*{_UNIT}\s*[,、]?\s*(?:其中)?\s*"
        rf"(?P<verb>达标|通过|pass(?:ed)?)\s*(?P<a>\d{{1,5}})\s*{_UNIT}",
        re.IGNORECASE,
    ),
    # 158 项（指标）中 104 项达标
    re.compile(
        rf"(?P<b>\d{{1,5}})\s*{_UNIT}\s*(?:数值指标|定性指标|指标)?\s*中\s*(?:有)?\s*"
        rf"(?P<a>\d{{1,5}})\s*{_UNIT}\s*(?P<verb>达标|通过|pass(?:ed)?)",
        re.IGNORECASE,
    ),
)
# 74 项 metrics + 12 项 qualitative
_PARTS_RE = re.compile(
    rf"(?P<m>\d{{1,5}})\s*{_UNIT}?\s*(?:数值\s*)?(?:metrics|数值指标|数值项|数值型指标|数值)\s*"
    rf"(?:\+|加|和|与|及|、|,)\s*(?P<q>\d{{1,5}})\s*{_UNIT}?\s*(?:定性\s*)?(?:qualitative|定性指标|定性项|定性)",
    re.IGNORECASE,
)
# 数值 120 + unverifiable 7 + 定性 3
_PARTS_REV_RE = re.compile(
    rf"(?:数值指标|数值项|数值|metrics)\s*(?P<m>\d{{1,5}})\s*{_UNIT}?\s*\+\s*(?:[^+。;,]{{0,24}}\+\s*)?"
    rf"(?:定性指标|定性项|定性|qualitative)\s*(?P<q>\d{{1,5}})",
    re.IGNORECASE,
)
# 分项加和、「共 N 项」紧跟在这些字样后面（「新增 2 项 metrics + …」「改动的共 3 项」），说的是
# 增减了多少条，不是条目总数；「修订后共 86 项」这种隔着别的字的不算
_DELTA_BEFORE_RE = re.compile(
    r"(?:新增|增加|增补|补充|补齐|补记|补了|删除|删去|减少|去掉|移出|并入|修改|修订|改动)\s*(?:了|的)?\s*$"
)
# 「共 N 项」所在的句子要点名对比表：comparison、对比总表，或单独出现的 metrics / qualitative
# （metrics.json、metrics_total 这类文件名、字段名不算）
_TOTAL_CONTEXT_RE = re.compile(
    r"comparison|(?<![A-Za-z0-9_.])(?:metrics|qualitative)(?!\.json)(?![A-Za-z0-9_])"
    r"|对比总表|指标对比|对比表|验证条目|对照条目",
    re.IGNORECASE,
)
# 「共 N 项」紧挨在对比表的名字后面（中间至多隔 4 个字符）：无条件与条目总数比对
_TOTAL_ADJACENT_RE = re.compile(r"(?:comparison(?:\.json)?|对比总表|指标对比表?|对比表)[^,、。;:]{0,4}$", re.IGNORECASE)
_NEAR_TOTAL_RATIO = 0.2  # 与条目总数相差不到这个比例（至少容 1 条）的数，才当作是在讲条目总数
_TOTAL_RE = re.compile(
    r"(?:共计|总计|合计|总共|共|总)\s*(?P<n>\d{1,5})\s*项\s*"
    r"(?:验证条目|对比条目|对照条目|指标条目|条目|指标|对比项|对照项|验证项)?(?=\s*(?:[,、。;:)(\]】]|$))"
)


@dataclass(frozen=True)
class _Mention:
    """文书里一处讲达标数或条目数的写法。"""

    line: int
    family: str  # metrics / qualitative / any（a/b 与「达标 N 项，共 M 项」）；parts（分项加和）；total（共 N 项）
    polarity: str  # pass / fail
    nums: tuple[int, ...]
    raw: str
    # 写法本身够不够明确（不够明确的，数字还得对得上或贴近已知的条目数才判，见 `_mention_verdict`）：
    # a/b 紧挨着 overall_pass、合计这类全局字样；分项加和点了 metrics、qualitative 两个数组的名字；
    # 「共 N 项」紧挨在 comparison、对比总表后面；「达标 N 项，共 M 项」恒为真
    strong: bool
    clause: int = 0  # 在这一行的第几句里（按句号、分号切）


def _family_near(clause: str, start: int, end: int) -> str:
    """这处计数说的是哪个口径。

    看数字前 18 个字符里离它最近的字样：是「数值 / 定性」就按那个口径，是 overall_pass、合计
    这类全局字样就不限口径；前面都没有时再看数字后面紧跟的「数值 / 定性」，仍没有则不限口径。
    """
    before = clause[max(0, start - 18) : start]
    category = None
    for m in _CATEGORY_RE.finditer(before):
        category = m
    global_word = None
    for m in _GLOBAL_NEAR_RE.finditer(before):
        global_word = m
    if category is not None and (global_word is None or category.start() > global_word.start()):
        return "qualitative" if category.group("q") else "metrics"
    if global_word is not None:
        return "any"
    after = _CATEGORY_RE.search(clause[end : end + 8])
    if after is None:
        return "any"
    return "qualitative" if after.group("q") else "metrics"


def _count_mentions(text: str, line_no: int = 0) -> list[_Mention]:
    """从一行文字里找出明确在讲指标达标数的写法。宁可漏认，不乱认。

    认四种写法，都先按句号、分号切成句子，在句子内部判断：
    1. `a/b`（a ≤ b）：数字前 18 个字符或后 12 个字符内要有「达标 / 通过 / pass / FAIL / 未通过」
       一类字样，并且句子里要有全局字样（overall_pass、pass_count、总体、合计、comparison 等）
       或口径字样（数值指标、定性项、metrics、qualitative）。数字前 24 个字符内紧挨着
       overall_pass、pass_count、总体、合计这类字样的，无条件与重算比对；其余的，分母还得等于
       当前（或上一版）这个口径的条目总数才认，否则当作某个要素的小计放过。
    2. 「达标 N 项，共 M 项」及其倒装（「共 M 项，其中 N 项达标」「M 项中 N 项通过」）。
    3. 分项加和：「74 项 metrics + 12 项 qualitative」「数值 120 + … + 定性 3」。只在看得出是在
       讲条目总数时才判（见 `_mention_verdict`），「数值 54 条 + 定性 14 条未达标」这类别的分项
       放过。紧跟在「新增 / 删除 / 修改」等字样后面的是增减量，不认。
    4. 「共 N 项」：句子里要点名 comparison、对比总表、验证条目，或单独出现 metrics / qualitative
       （metrics.json 这类文件名不算），且「项」后面不再跟别的名词。紧挨在 comparison、对比总表
       后面的无条件比对；其余的，N 要等于上一版的条目总数或贴近当前的条目总数才判，否则当作
       某一部分的小计放过。紧跟在「新增 / 删除」等字样后面、或前面 12 个字符内有「其中」的不认。
    不认的：表格单元格里的计数、代码围栏和机器生成块里的内容；紧挨着要素编号（R3、SA1）、
    「簇」「分年」「抽查」「门禁」「检查项」「页码」「日期」等字样的小计；后面跟着
    「年 / 月 / 日 / 页 / 格 / 个行业」等量词的比例；a > b 的写法；「2026/11/20」这种连写的日期。
    """
    plain = _norm(text).replace("*", "").replace("`", "")
    mentions: list[_Mention] = []
    for index, clause in enumerate(_CLAUSE_SPLIT_RE.split(plain)):
        if not clause.strip():
            continue
        strong = bool(_STRONG_ANCHOR_RE.search(clause))
        has_category = bool(_CATEGORY_RE.search(clause))

        for regex in (_PARTS_RE, _PARTS_REV_RE):
            for m in regex.finditer(clause):
                before = clause[max(0, m.start() - 18) : m.start()]
                if _SUBSET_BEFORE_RE.search(before) or _DELTA_BEFORE_RE.search(before):
                    continue
                nums = (int(m.group("m")), int(m.group("q")))
                raw = m.group(0).strip()
                # 点了 comparison.json 两个数组的名字（N metrics + M qualitative）
                named = bool(re.search(r"metrics", raw, re.IGNORECASE) and re.search(r"qualitative", raw, re.IGNORECASE))
                mentions.append(_Mention(line_no, "parts", "pass", nums, raw, named, index))

        for regex in _PAIR_RES:
            for m in regex.finditer(clause):
                before = clause[max(0, m.start() - 18) : m.start()]
                if _SUBSET_BEFORE_RE.search(before):
                    continue
                verb = m.group("verb")
                if verb != "达标" and not (strong or has_category or "指标" in clause):
                    continue
                negated = clause[max(0, m.start("verb") - 1) : m.start("verb")] in ("未", "不")
                a, b = int(m.group("a")), int(m.group("b"))
                if a > b:
                    continue
                family = _family_near(clause, m.start(), m.end())
                mentions.append(_Mention(line_no, family, "fail" if negated else "pass", (a, b), m.group(0).strip(), True, index))

        if strong or has_category:
            for m in _RATIO_RE.finditer(clause):
                a, b = int(m.group(1)), int(m.group(2))
                if a > b or b == 0:
                    continue
                before = clause[max(0, m.start() - 18) : m.start()]
                after = clause[m.end() : m.end() + 12]
                if _SUBSET_BEFORE_RE.search(before) or _SUBSET_AFTER_RE.match(after):
                    continue
                verdict = None
                for found in _VERDICT_WORD_RE.finditer(before):
                    verdict = found
                if verdict is None:
                    verdict = _VERDICT_WORD_RE.search(after)
                if verdict is None:
                    continue
                polarity = "fail" if verdict.group("fail") else "pass"
                family = _family_near(clause, m.start(), m.end())
                near_global = bool(_GLOBAL_NEAR_RE.search(clause[max(0, m.start() - _GLOBAL_NEAR_SPAN) : m.start()]))
                mentions.append(_Mention(line_no, family, polarity, (a, b), m.group(0).replace(" ", ""), near_global, index))

        if _TOTAL_CONTEXT_RE.search(clause):
            for m in _TOTAL_RE.finditer(clause):
                head = clause[max(0, m.start() - 40) : m.start()]  # 够放下「comparison.json」再加几个字
                before = head[-18:]
                if _SUBSET_BEFORE_RE.search(before) or _DELTA_BEFORE_RE.search(before) or "其中" in before[-12:]:
                    continue
                adjacent = bool(_TOTAL_ADJACENT_RE.search(head))
                mentions.append(_Mention(line_no, "total", "pass", (int(m.group("n")),), m.group(0).strip(), adjacent, index))
    return mentions


def _near_total(n: int, total: int) -> bool:
    """n 是不是贴近条目总数 total：相差不到 `_NEAR_TOTAL_RATIO`，至少容 1 条。"""
    return total > 0 and abs(n - total) <= max(1.0, _NEAR_TOTAL_RATIO * total)


def _mention_verdict(mention: _Mention, counts: _Counts, previous: Optional[_Counts]) -> Optional[bool]:
    """这处写法与重算一致（True）、不一致（False），还是不该当作全案例计数（None）。"""
    if mention.family == "total":
        n = mention.nums[0]
        if n in counts.totals():
            return True
        if mention.strong:
            return False
        # 没有紧挨着 comparison、对比总表的：等于上一版的条目总数，或贴近当前、上一版的条目总数，
        # 才当作是在讲条目总数；差得远的当作某一部分的小计放过
        for known in (counts, previous):
            if known is None:
                continue
            if known is not counts and n in known.totals():
                return False
            if any(_near_total(n, total) for total in known.grand_totals()):
                return False
        return None
    if mention.family == "parts":
        n_m, n_q = mention.nums
        if n_m in counts.metric_denominators and n_q == counts.q_total:
            return True
        # 「数值 54 条 + 定性 14 条」也可能是在拆达标或未达标的条目
        if (n_m, n_q) in ((counts.m_pass, counts.q_pass), (counts.m_fail, counts.q_fail)):
            return True
        # 其余情形只在看得出是在讲条目总数时才判：数值那一半等于当前或上一版的条目数；或者数值
        # 那一半贴近条目数，同时定性那一半对得上、或写法点了 metrics、qualitative 两个数组的名字。
        # 否则当作别的分项（改了几条、某一类有几条）放过。
        for known in (counts, previous):
            if known is None:
                continue
            if n_m in known.metric_denominators:
                return False
            if _near_total(n_m, known.m_total) and (mention.strong or n_q == known.q_total):
                return False
        return None
    pair = (mention.nums[0], mention.nums[1])
    if pair in counts.accepted(mention.family, mention.polarity):
        return True
    if mention.strong:
        return False
    # 没有紧挨着全局字样的：分母是当前或上一版这个口径的条目数，才当作全案例的达标数
    for known in (counts, previous):
        if known is not None and pair[1] in known.denominators(mention.family):
            return False
    return None


def _compatible(a: _Mention, b: _Mention) -> bool:
    """两处写法是不是在讲同一个口径（用来判断「同一行 / 后文已有一致的写法」）。

    分项加和、「共 N 项」各自只和同类比；`a/b` 这类要达标与否的方向相同，并且口径相同
    （都点明了数值或都点明了定性），有一方没点明口径时分母相同才算。
    """
    if a.family in ("parts", "total") or b.family in ("parts", "total"):
        return a.family == b.family
    if a.polarity != b.polarity:
        return False
    if "any" not in (a.family, b.family):
        return a.family == b.family
    return a.nums[1] == b.nums[1]


def _count_hits(case: _Case, doc: _Doc, previous: Optional[_Counts]) -> list[_Hit]:
    """P4 之一：文书里写的达标数、条目数与重算一致。

    哪些句子算在讲达标数见 `_count_mentions`。分母可以是全部数值条目、剔除 N/A 后的条目或有
    复现值的条目；没点明口径的，数值、定性、合计任一口径对上都算一致。不一致时：
    - 同一句里同口径另有一处是对的（「fv6 100/158 → fv7 104/158」这种写变化过程的句子），不报；
    - 行内或所在章节标题里标了历史字样的，不报；
    - 同一行的另一句里、或文书后文同口径已有一处是对的，按旧计数残留报提示（`P4_SUPERSEDED_LEVEL`）；
    - 恰好等于 comparison.json 顶层自述的 pass_count / total 的，级别取 `P4_SELF_REPORTED_LEVEL`
      （默认阻断：自述不作数）；
    - 否则报阻断。
    """
    counts = case.counts()
    comparison = case.comparison or {}
    self_pair = (comparison.get("pass_count"), comparison.get("total"))
    judged: list[tuple[_Mention, bool, _Line]] = []
    for line in doc.lines:
        if line.skip or line.role or _is_historical(line):
            continue
        for mention in _count_mentions(line.text, line.no):
            verdict = _mention_verdict(mention, counts, previous)
            if verdict is not None:
                judged.append((mention, verdict, line))

    def self_reported(mention: _Mention) -> bool:
        return mention.family not in ("parts", "total") and (mention.nums[0], mention.nums[1]) == self_pair

    good = [m for m, ok, _line in judged if ok]
    by_line: dict[int, list[tuple[_Mention, str, int]]] = {}  # 行号 -> [(写法, 级别, 一致写法所在的行号或 0)]
    for mention, ok, _line in judged:
        if ok:
            continue
        peers = [g for g in good if _compatible(mention, g)]
        if any(g.line == mention.line and g.clause == mention.clause for g in peers):
            continue  # 同一句里另有一处是对的：是在写变化过程
        elsewhere = [g.line for g in peers if g.line >= mention.line]  # 同一行的另一句，或后文
        if elsewhere:
            level = P4_SUPERSEDED_LEVEL
        elif self_reported(mention):
            level = P4_SELF_REPORTED_LEVEL
        else:
            level = "block"
        by_line.setdefault(mention.line, []).append((mention, level, min(elsewhere) if elsewhere else 0))

    hits: list[_Hit] = []
    for line_no in sorted(by_line):
        items = by_line[line_no]
        level = "block" if any(lv == "block" for _m, lv, _later in items) else "warn"
        raws = "、".join(dict.fromkeys(f"「{m.raw}」" for m, _lv, _later in items))
        message = f"{doc.name} 第 {line_no} 行写的计数{raws}与重算不一致（重算：{counts.describe()}）"
        notes = []
        if any(self_reported(m) for m, _lv, _later in items):
            notes.append("与 comparison.json 自述的 pass_count/total 相同，但自述不作数")
        if previous is not None and any(_mention_verdict(m, previous, None) is True for m, _lv, _later in items):
            notes.append("等于上一版 comparison 的计数")
        consistent_at = [where for _m, _lv, where in items if where]
        if level != "block" and consistent_at:
            position = "同一行的另一句里" if min(consistent_at) == line_no else f"后文第 {min(consistent_at)} 行"
            notes.append(f"{position}已有一致的写法，疑似旧计数残留或历史轮次记录，{STALE_HINT}")
        if notes:
            message += "；" + "；".join(notes)
        hits.append(_Hit("P4", level, message, doc.rel, line_no))
    return hits


# ---------------------------------------------------------------------------
# P4 之二：手抄对比表里的复现值
# ---------------------------------------------------------------------------

_MINUS_SIGN = chr(0x2212)  # Unicode 减号，文书里常用来写负数
_SIGN = "(?P<sign>[+\\-" + _MINUS_SIGN + "]?)"
_CELL_NUMBER_RE = re.compile(
    r"^(?P<paren>\()?\s*" + _SIGN + r"\s*(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?\s*(?P<pct>%)?\s*"
    r"(?(paren)\))(?:\s*\(.*\))?$"
)


@dataclass(frozen=True)
class _Number:
    """文书里写的一个数。"""

    value: float
    decimals: int  # 写到小数点后第几位
    percent: bool
    text: str


def _clean_cell(cell: str) -> str:
    """去掉单元格外面包着的加粗、斜体、行内代码、删除线记号。"""
    s = cell.strip()
    while True:
        before = s
        for mark in ("**", "__", "~~", "`", "*"):
            if len(s) >= 2 * len(mark) + 1 and s.startswith(mark) and s.endswith(mark):
                s = s[len(mark) : -len(mark)].strip()
        if s == before:
            return s


def _parse_cell_number(cell: str) -> Optional[_Number]:
    """单元格整体是一个数时解析出来（容忍百分号、千分位、正负号的各种写法、后面带括注）。

    「5.09%」「-19.69」「+3.58%」「1,234.5」「(5.28%)」「13.63%（向研报收敛）」都认，负号写成
    Unicode 减号（U+2212）或全角的也认；
    「10.41% vs 10.56%」「90/93 = 96.8%」「NaN（全程空仓）」这类不是单个数的不认。
    """
    s = _norm(_clean_cell(cell)).strip()
    m = _CELL_NUMBER_RE.match(s)
    if not m:
        return None
    digits = m.group("int").replace(",", "") + (m.group("frac") or "")
    value = float(digits)
    if m.group("sign") in ("-", _MINUS_SIGN) or m.group("paren"):
        value = -value
    return _Number(value, len(m.group("frac") or ".") - 1, bool(m.group("pct")), cell.strip())


def _cell_agrees(number: _Number, value: Any) -> bool:
    """文书里手抄的数与机器结果是否一致（宽松口径，用于阻断级的判断）。

    只比绝对值（回撤写成正数还是负数、带不带正号都不算差异）；小数与百分数互换都接受
    （0.1041 ↔ 10.41% ↔ 10.41）；保留位数不同也接受：文书的数是机器值按文书的位数四舍五入
    或直接截断的结果都算一致（5.0860% 写成 5.09%、5.08% 都行，5.10%、5.28% 不行）。
    机器值本来就能用文书的位数写全时，这条规则等于要求两者相等。
    """
    if not _is_finite(value):
        return False
    written = abs(number.value)
    unit = 10 ** (-number.decimals)
    for candidate in (abs(float(value)), abs(float(value)) * 100, abs(float(value)) / 100):
        slack = 1e-9 * max(1.0, candidate)
        # 四舍五入：机器值比文书小不超过半个末位单位；截断：机器值比文书大、但不到一个末位单位
        if -0.5 * unit - slack <= candidate - written < unit - slack:
            return True
    return False


def _label(text: Any) -> str:
    return _squash(text).lower().strip(":")


@dataclass
class _MetricIndex:
    by_key: dict[str, int]
    by_label: dict[str, int]


def _metric_index(case: _Case) -> _MetricIndex:
    """文书表格的行怎么对上 comparison 的数值条目：单元格等于指标编号，或等于指标名称
    （也认「要素编号 + 名称」，如「R1 信息比」）。名称对应多条指标的不用来对。"""
    by_key: dict[str, int] = {}
    labels: dict[str, set[int]] = {}
    for i, entry in enumerate(case.metrics):
        key = entry.get("key")
        if isinstance(key, str) and key.strip():
            by_key.setdefault(key.strip(), i)
        name = entry.get("name")
        if not isinstance(name, str) or len(_label(name)) < 3:
            continue
        labels.setdefault(_label(name), set()).add(i)
        ids = _leading_ids(entry.get("source_element") or "") | _leading_ids(entry.get("key") or "")
        for eid in ids:
            labels.setdefault(_label(eid + name), set()).add(i)
    by_label = {label: next(iter(idx)) for label, idx in labels.items() if len(idx) == 1}
    return _MetricIndex(by_key, by_label)


def _match_row(cells: Iterable[str], index: _MetricIndex) -> tuple[Optional[int], str]:
    """这一行对上了哪条指标：返回 (条目下标, 靠什么对上的)。对不上或对上不止一条时返回 (None, "")。"""
    cleaned = [_clean_cell(c) for c in cells]
    keys = {index.by_key[c] for c in cleaned if c in index.by_key}
    if len(keys) == 1:
        return keys.pop(), "指标编号"
    if keys:
        return None, ""
    names = {index.by_label[_label(c)] for c in cleaned if _label(c) in index.by_label}
    if len(names) == 1:
        return names.pop(), "名称"
    return None, ""


def _reproduced_columns(header: tuple[str, ...]) -> list[int]:
    """表头里哪些列是复现值：列名含「复现」或 reproduced，且不是「复现 vs 研报」「复现偏差」这种复合列。"""
    out = []
    for i, name in enumerate(header):
        n = _squash(name).lower()
        if "复现" not in n and "reproduc" not in n:
            continue
        if any(word in n for word in ("研报", "原文", "vs", "→", "->", "偏差", "差值", "差异", "/")):
            continue
        out.append(i)
    return out


# 「复现 vs 研报」复合列：表头这样写的列，单元格形如「5.09% vs 7.47%（偏差 31.91%）」
_PAIR_HEADER_RE = re.compile(r"(复现|研报|原文)\S{0,6}?vs\.?\S{0,6}?(复现|研报|原文)")
_PAIR_NUMBER = "[+\\-" + _MINUS_SIGN + "]?\\s*(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?\\s*%?"
_PAIR_CELL_RE = re.compile(
    "^(?P<a>" + _PAIR_NUMBER + ")\\s*vs\\.?\\s*(?P<b>" + _PAIR_NUMBER + ")(?![A-Za-z0-9_.])", re.IGNORECASE
)
_PAIR_MIN_SIG_DIGITS = 3  # 研报值至少写到这么多位有效数字，才拿它去认是哪条指标


def _pair_columns(header: tuple[str, ...]) -> dict[int, bool]:
    """表头里哪些列是「复现 vs 研报」复合列：{列号: 复现值是否写在前面}。"""
    out: dict[int, bool] = {}
    for i, name in enumerate(header):
        m = _PAIR_HEADER_RE.search(_squash(name).lower())
        if m and "复现" in m.groups() and m.group(1) != m.group(2):
            out[i] = m.group(1) == "复现"
    return out


def _element_members(case: _Case) -> dict[str, list[int]]:
    """要素编号 → 归属于它的数值条目下标（来源要素或指标编号以该要素编号开头）。"""
    out: dict[str, list[int]] = {}
    for i, entry in enumerate(case.metrics):
        for eid in _leading_ids(entry.get("source_element") or "") | _leading_ids(entry.get("key") or ""):
            out.setdefault(eid, []).append(i)
    return out


@dataclass
class _PairCell:
    """要素宽表里一个「复现 vs 研报」单元格。"""

    line: _Line
    title: str  # 列名
    cell: str  # 单元格原文
    written: _Number  # 手抄的复现值
    report: _Number  # 手抄的研报值
    candidates: list[int]  # 该要素名下研报值对得上的数值条目
    ok: bool


def _pair_cells(case: _Case, doc: _Doc) -> list[_PairCell]:
    """找出要素宽表里的「复现 vs 研报」单元格，并认出各自对应的指标。

    这种表一行一个要素（首格以要素编号开头），列名写明「…（复现 vs 研报）」，单元格以
    「5.09% vs 7.47%」开头。行里没有指标编号，靠研报值去认：该要素名下研报值等于单元格里
    研报值的数值条目就是候选（研报值至少写到 3 位有效数字才认），候选里有一条的复现值与手抄的
    一致就算一致。认不出候选的单元格不查。
    """
    members = _element_members(case)
    out: list[_PairCell] = []
    for line in doc.lines:
        if line.skip or line.role != "row" or line.table is None or not line.cells:
            continue
        marked = _history_columns(line)
        columns = {c: first for c, first in _pair_columns(line.table.header).items() if c not in marked}
        if not columns:
            continue
        own = sorted({i for eid in _leading_ids(_clean_cell(line.cells[0])) for i in members.get(eid, [])})
        if not own:
            continue
        for c, reproduced_first in columns.items():
            if c >= len(line.cells):
                continue
            m = _PAIR_CELL_RE.match(_norm(line.cells[c]).replace("*", "").replace("`", "").strip())
            if not m:
                continue
            first, second = _parse_cell_number(m.group("a")), _parse_cell_number(m.group("b"))
            if first is None or second is None:
                continue
            written, report = (first, second) if reproduced_first else (second, first)
            if _significant_digits(report.text) < _PAIR_MIN_SIG_DIGITS:
                continue
            candidates = [i for i in own if _cell_agrees(report, case.metrics[i].get("report_value"))]
            if not candidates:
                continue
            ok = any(_cell_agrees(written, case.metrics[i].get("reproduced_value")) for i in candidates)
            out.append(_PairCell(line, line.table.header[c].strip(), line.cells[c].strip(), written, report, candidates, ok))
    return out


def _stale_reason(
    numbers: list[_Number],
    keys: list[str],
    prev_values: dict[str, Any],
    history: dict[str, list[tuple[int, Any]]],
    later: list[int],
) -> str:
    """不一致的手抄值是不是旧值残留：是就返回说明文字，找不到这类解释返回空串。"""
    for key in keys:
        old = prev_values.get(key)
        if old is not None and any(_cell_agrees(n, old) for n in numbers):
            return f"这是上一版 comparison 的旧值（{_fmt_value(old)}）"
    rounds = sorted({no for key in keys for no, past in history.get(key, []) if any(_cell_agrees(n, past) for n in numbers)})
    if rounds:
        return f"这是第 {'、'.join(str(no) for no in rounds)} 轮迭代快照里的旧值"
    if later:
        return f"后文第 {min(later)} 行同一指标已是新值，疑似旧值残留或历史记录"
    return ""


def _table_value_hits(
    case: _Case, doc: _Doc, prev_values: dict[str, Any], history: Optional[dict[str, list[tuple[int, Any]]]] = None
) -> tuple[list[_Hit], set[tuple[int, str]]]:
    """P4 之二：手抄对比表里的复现值与 comparison.json 一致。

    只看能对上的两种表：
    - 一行一条指标：行里有单元格等于某条指标的编号或名称，表头里有复现值列，且那一格整体是
      一个数。一行有多个复现值列（「fv6 复现 | fv7 复现」）时，有一列对上就算一致。
    - 一行一个要素的宽表：列名写明「复现 vs 研报」，单元格以「5.09% vs 7.47%」开头，靠研报值
      认出是哪条指标（见 `_pair_cells`；r008 结果外审 CDX-R-01 就是这种表）。
    比对口径见 `_cell_agrees`。表头标了历史字样的列（「上一轮复现」）不查。不一致时：行内或
    所在章节标题标了历史字样的不报；等于上一版 comparison 或某一轮迭代快照里这条指标的值，
    或文书后文同一指标另有一处是对的，按旧数值残留报提示；否则报阻断。
    返回 (发现, 已经报过的 (行号, 单元格原文)，旧数值扫描据此不再重复报)。
    """
    history = history or {}
    index = _metric_index(case)
    rows: list[tuple[_Line, int, str, list[_Number], bool]] = []
    for line in doc.lines:
        if line.skip or line.role != "row" or line.table is None:
            continue
        columns = [c for c in _reproduced_columns(line.table.header) if c not in _history_columns(line)]
        if not columns:
            continue
        matched, how = _match_row(line.cells, index)
        if matched is None:
            continue
        numbers = [n for n in (_parse_cell_number(line.cells[c]) for c in columns if c < len(line.cells)) if n]
        if not numbers:
            continue
        value = case.metrics[matched].get("reproduced_value")
        if isinstance(value, (str, bool)):
            continue
        rows.append((line, matched, how, numbers, any(_cell_agrees(n, value) for n in numbers)))

    pairs = _pair_cells(case, doc)
    agreeing_lines: dict[int, list[int]] = {}  # 条目下标 -> 文书里写对了它的行号
    for line, matched, _how, _numbers, ok in rows:
        if ok:
            agreeing_lines.setdefault(matched, []).append(line.no)
    for pair in pairs:
        for i in pair.candidates:
            if _cell_agrees(pair.written, case.metrics[i].get("reproduced_value")):
                agreeing_lines.setdefault(i, []).append(pair.line.no)

    hits: list[_Hit] = []
    reported: set[tuple[int, str]] = set()
    for line, matched, how, numbers, ok in rows:
        if ok or _is_historical(line):
            continue
        entry = case.metrics[matched]
        key = entry.get("key", "?")
        value = entry.get("reproduced_value")
        written = "、".join(n.text for n in numbers)
        target = f"comparison.json 里是 {_fmt_value(value)}" if value is not None else "comparison.json 里复现值是空的"
        message = f"{doc.name} 第 {line.no} 行手抄的指标 {key}（按{how}对上）复现值 {written} 与机器结果不一致：{target}"
        later = [no for no in agreeing_lines.get(matched, []) if no > line.no]
        reason = _stale_reason(numbers, [str(key)], prev_values, history, later)
        if reason:
            level = P4_SUPERSEDED_LEVEL
            message += f"；{reason}，{STALE_HINT}"
        else:
            level = "block"
        hits.append(_Hit("P4", level, message, doc.rel, line.no))
        reported.update((line.no, n.text) for n in numbers)

    # 要素宽表里的「复现 vs 研报」单元格：一行汇成一条
    wrong: dict[int, list[tuple[str, str]]] = {}  # 行号 -> [(这一格的说明, 旧值解释或空串)]
    for pair in pairs:
        if pair.ok or _is_historical(pair.line):
            continue
        keys = [str(case.metrics[i].get("key", "?")) for i in pair.candidates]
        later = [no for i in pair.candidates for no in agreeing_lines.get(i, []) if no > pair.line.no]
        reason = _stale_reason([pair.written], keys, prev_values, history, later)
        value = case.metrics[pair.candidates[0]].get("reproduced_value")
        target = _fmt_value(value) if value is not None else "空的"
        which = keys[0] + (f" 等 {len(keys)} 条" if len(keys) > 1 else "")
        detail = (
            f"「{pair.title}」一栏写的复现值是 {pair.written.text}（研报值 {pair.report.text}），"
            f"按研报值对上的指标 {which} 在 comparison.json 里是 {target}"
        )
        wrong.setdefault(pair.line.no, []).append((detail + (f"（{reason}）" if reason else ""), reason))
        reported.add((pair.line.no, pair.cell))
    for line_no in sorted(wrong):
        items = wrong[line_no]
        explained = all(reason for _detail, reason in items)
        shown = "；".join(detail for detail, _reason in items[:3]) + (f"；另有 {len(items) - 3} 处" if len(items) > 3 else "")
        message = f"{doc.name} 第 {line_no} 行手抄的复现值与机器结果不一致：{shown}"
        if explained:
            message += f"。{STALE_HINT}"
        hits.append(_Hit("P4", P4_SUPERSEDED_LEVEL if explained else "block", message, doc.rel, line_no))
    return hits, reported


# ---------------------------------------------------------------------------
# P4 之三：旧数值残留
# ---------------------------------------------------------------------------

_SCAN_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_./:])" + _SIGN + r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)\s*(?P<pct>%)?"
    r"(?![A-Za-z0-9_/:]|\.\d)"
)
_THOUSANDS_TAIL_RE = re.compile(r"\d,$")


@dataclass(frozen=True)
class _Stored:
    """机器结果里的一个数，连同它的存法。"""

    value: float
    kind: str  # 复现值 / 研报值 / 偏差
    percent: bool = False  # 条目注明单位是百分号：值本身就是百分数


@dataclass(frozen=True)
class _OldValue:
    """一个旧数：哪条指标的、现在变成了多少、这条指标属于哪些要素、出自哪一版。"""

    key: str
    stored: _Stored
    new: Optional[_Stored]
    ids: tuple[str, ...]
    origin: str = "上一版"  # 上一版 / 第 N 轮快照
    precise_only: bool = False  # 更早轮次的旧数：只认有效数字够多的写法


def _target(stored: _Stored, percent_written: bool) -> float:
    """机器值按文书的写法应该是多少（只取绝对值）。

    偏差按比例存，文书带百分号时乘 100；复现值、研报值默认按小数存，文书带百分号时乘 100，
    条目注明单位是百分号的原样比。
    """
    value = abs(stored.value)
    if percent_written and not (stored.percent and stored.kind != "偏差"):
        value *= 100
    return value


def _written_as(number: _Number, stored: _Stored) -> bool:
    """文书里的这个数，是不是机器值按文书的位数四舍五入后的写法（严格口径，用于旧数值扫描）。"""
    target = _target(stored, number.percent)
    half = 0.5 * 10 ** (-number.decimals) * (1 + 1e-9)
    return abs(abs(number.value) - target) <= half + 1e-12 * max(1.0, target)


class _TargetIndex:
    """一批机器值，查「文书里的这个数可能是其中哪几个的写法」（两种写法各排好序，二分查找）。"""

    def __init__(self, stored: Iterable[_Stored]) -> None:
        items = list(stored)
        self._plain = sorted((_target(s, False), i) for i, s in enumerate(items))
        self._percent = sorted((_target(s, True), i) for i, s in enumerate(items))

    def lookup(self, number: _Number) -> list[int]:
        """可能对上的那几个值的下标（按原来的顺序）；是否真对上由调用方再用 `_written_as` 确认。"""
        targets = self._percent if number.percent else self._plain
        written = abs(number.value)
        tol = 0.5 * 10 ** (-number.decimals) * (1 + 1e-9) + 1e-9 * max(1.0, written)
        out = []
        at = bisect.bisect_left(targets, (written - tol, -1))
        while at < len(targets) and targets[at][0] <= written + tol:
            out.append(targets[at][1])
            at += 1
        return sorted(out)


def _rel_dev(entry: dict) -> Optional[float]:
    report, reproduced = entry.get("report_value"), entry.get("reproduced_value")
    if not (_is_finite(report) and _is_finite(reproduced)) or report == 0:
        return None
    return abs(reproduced - report) / abs(report)


def _stored_percent(entry: dict) -> bool:
    unit = entry.get("unit")
    return isinstance(unit, str) and "%" in _norm(unit)


def _old_values(current: list[dict], previous: list[dict], origin: str = "上一版", precise_only: bool = False) -> list[_OldValue]:
    """某一版 comparison 里与当前不同的数：旧复现值、旧偏差。"""
    now_by_key = {str(e.get("key")): e for e in current}
    olds: list[_OldValue] = []
    for entry in previous:
        key = str(entry.get("key"))
        now = now_by_key.get(key)
        percent = _stored_percent(entry)
        ids = tuple(sorted(_leading_ids(entry.get("source_element") or "") | _leading_ids(key)))
        old_value = entry.get("reproduced_value")
        new_value = now.get("reproduced_value") if now else None
        if _is_finite(old_value) and not (_is_finite(new_value) and float(new_value) == float(old_value)):
            new = _Stored(float(new_value), "复现值", _stored_percent(now)) if now and _is_finite(new_value) else None
            olds.append(_OldValue(key, _Stored(float(old_value), "复现值", percent), new, ids, origin, precise_only))
        old_dev = _rel_dev(entry)
        new_dev = _rel_dev(now) if now else None
        if old_dev is not None and not (new_dev is not None and math.isclose(new_dev, old_dev, rel_tol=1e-12, abs_tol=1e-15)):
            new = _Stored(new_dev, "偏差") if new_dev is not None else None
            olds.append(_OldValue(key, _Stored(old_dev, "偏差"), new, ids, origin, precise_only))
    return olds


def _current_values(current: list[dict]) -> list[_Stored]:
    """当前版本的全部数：复现值、研报值、偏差（文件里写的和自己算的都算）。"""
    currents: list[_Stored] = []
    for entry in current:
        percent = _stored_percent(entry)
        for name, kind in (("reproduced_value", "复现值"), ("report_value", "研报值")):
            if _is_finite(entry.get(name)):
                currents.append(_Stored(float(entry[name]), kind, percent))
        if _is_finite(entry.get("rel_dev")):
            currents.append(_Stored(float(entry["rel_dev"]), "偏差"))
        dev = _rel_dev(entry)
        if dev is not None:
            currents.append(_Stored(dev, "偏差"))
    return currents


def _significant_digits(digits: str) -> int:
    return len(re.sub(r"[^0-9]", "", digits).lstrip("0"))


def _text_numbers(entries: Iterable[dict]) -> list[_Number]:
    """当前 comparison 的文字字段（expect、observed、note 等）里写到的数：文书引用它们不算旧数。"""
    out: list[_Number] = []
    for entry in entries:
        for value in entry.values():
            if isinstance(value, str):
                out.extend(_scan_numbers(value))
    return out


def _same_written(number: _Number, quoted: _Number) -> bool:
    """文书里的数是不是 comparison 文字字段里那个数的写法：都带或都不带百分号，文书的位数不多于
    后者，且后者按文书的位数四舍五入后相等（文字字段里的 100.6% 不能替文书里的 100.58% 开脱）。"""
    if number.percent != quoted.percent or number.decimals > quoted.decimals:
        return False
    return abs(round(abs(quoted.value), number.decimals) - abs(number.value)) <= 1e-9


def _has_clue(line_upper: str, old: _OldValue) -> bool:
    """这一行有没有提到这条指标：出现了指标编号，或它所属的要素编号（R5 不会被 R50 当成线索）。"""
    if old.key and old.key.upper() in line_upper:
        return True
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(eid)}(?![0-9])", line_upper) for eid in old.ids)


def _scan_numbers(text: str) -> list[_Number]:
    """一行里带小数点、且有效数字够多的数（日期、时间、页码、版本号、带字母单位的量都不取）。"""
    out = []
    normalized = _norm(text)
    for m in _SCAN_NUMBER_RE.finditer(normalized):
        digits = m.group("int") + m.group("frac")
        if _significant_digits(digits) < STALE_MIN_SIG_DIGITS:
            continue
        if not m.group("sign") and len(m.group("int")) == 3 and _THOUSANDS_TAIL_RE.search(normalized[: m.start()][-2:]):
            continue  # 「1,234.5」没能整体认出时的后半截，不当成一个数
        value = float(digits.replace(",", ""))
        if m.group("sign") in ("-", _MINUS_SIGN):
            value = -value
        out.append(_Number(value, len(m.group("frac")) - 1, bool(m.group("pct")), m.group(0).strip()))
    return out


def _stale_hits(
    case: _Case,
    doc: _Doc,
    previous_metrics: list[dict],
    already: Optional[set[tuple[int, str]]] = None,
    older: Optional[list[tuple[int, list[dict]]]] = None,
) -> list[_Hit]:
    """P4 之三：旧版 comparison 的数值在文书里的残留（提示级，按行汇总）。

    报的是这样的数：按它自己的位数四舍五入后，等于某条指标在上一版里的复现值或相对偏差
    （该指标两版之间确实变了），同时不等于当前版本里任何一条指标的复现值、研报值、偏差，
    也不是当前 comparison 的文字字段里写到的数。只看带小数点、至少 3 位有效数字的数；
    有效数字不到 5 位的容易与别的数撞上，还要求同一行提到了这条指标（指标编号或所属的要素
    编号），5 位及以上的不要求。小数与百分数的换算按存法定（见 `_target`）。
    older 是比上一版更早的各轮快照 [(轮次, 数值条目)]：它们的旧数只认 5 位及以上有效数字的
    写法（r008 结果外审 CDX-R-02 的「最大相对偏差 100.58%」就是隔了几轮的旧值）。
    不报的：同一行里也写了这条指标的新值（写变化过程的句子）；行内或所在章节标题标了历史
    字样的行，表头标了历史字样的列；代码围栏与机器生成块里的内容。
    """
    olds = _old_values(case.metrics, previous_metrics)
    seen = {(old.key, old.stored.kind, round(old.stored.value, 12)) for old in olds}
    for number_of_round, metrics in older or []:
        for old in _old_values(case.metrics, metrics, f"第 {number_of_round} 轮快照", True):
            signature = (old.key, old.stored.kind, round(old.stored.value, 12))
            if signature not in seen:
                seen.add(signature)
                olds.append(old)
    if not olds:
        return []
    old_index = _TargetIndex(old.stored for old in olds)
    currents = _current_values(case.metrics)
    current_index = _TargetIndex(currents)
    quoted = _text_numbers([*case.metrics, *case.qualitative])
    already = already or set()
    hits: list[_Hit] = []
    for line in doc.lines:
        if line.skip or line.role in ("header", "sep") or _is_historical(line):
            continue
        text = line.text
        marked = _history_columns(line) if line.role == "row" else set()
        if marked:  # 表头标了历史字样的列不看
            text = " | ".join(cell for i, cell in enumerate(line.cells) if i not in marked)
        numbers = _scan_numbers(text)
        if not numbers:
            continue
        reported_cells = [_norm(cell) for no, cell in already if no == line.no]
        line_upper = ""
        found: dict[str, str] = {}
        for number in numbers:
            if number.text in found or any(number.text in cell for cell in reported_cells):
                continue
            if any(_written_as(number, currents[i]) for i in current_index.lookup(number)):
                continue
            if any(_same_written(number, other) for other in quoted):
                continue
            needs_clue = _significant_digits(number.text) < STALE_FREE_SIG_DIGITS
            for old in (olds[i] for i in old_index.lookup(number)):
                if (old.precise_only and needs_clue) or not _written_as(number, old.stored):
                    continue
                if needs_clue:
                    line_upper = line_upper or _norm(line.text).upper()
                    if not _has_clue(line_upper, old):
                        continue
                if old.new is not None and any(_written_as(other, old.new) for other in numbers):
                    break  # 同一行里也有新值：是在写变化过程
                now = _fmt_value(round(old.new.value, 6)) if old.new is not None else "空"
                found[number.text] = (
                    f"{number.text}（指标 {old.key} {old.origin}的{old.stored.kind} "
                    f"{_fmt_value(round(old.stored.value, 6))}，现为 {now}）"
                )
                break
        if not found:
            continue
        items = list(found.values())
        shown = "；".join(items[:3]) + (f"；另有 {len(items) - 3} 处" if len(items) > 3 else "")
        hits.append(_Hit("P4", "warn", f"{doc.name} 第 {line.no} 行出现旧数值：{shown}。{STALE_HINT}", doc.rel, line.no))
    return hits


# ---------------------------------------------------------------------------
# P4 汇总、上一版 comparison 的来源
# ---------------------------------------------------------------------------

_ITER_DIR_RE = re.compile(r"^iter_(\d+)$")


def _fingerprint(comparison: dict) -> str:
    """一份 comparison 里的数值内容（不含备注、归因这类文字）。两版指纹相同就没有旧数值可言。"""
    metrics = [
        (str(e.get("key")), repr(e.get("report_value")), repr(e.get("reproduced_value")))
        for e in _as_dict_list(comparison.get("metrics"))
    ]
    qualitative = [
        (str(e.get("key")), repr(e.get("expect")), repr(e.get("observed")))
        for e in _as_dict_list(comparison.get("qualitative"))
    ]
    return json.dumps([metrics, qualitative], ensure_ascii=False)


def _snapshots(case: _Case) -> list[tuple[int, str, dict]]:
    """各轮迭代留下的 comparison 快照（iterations/iter_NN/comparison.json），按轮次从新到旧。

    返回 [(轮次, 相对路径, 内容)]；读不了的跳过。
    """
    iterations = case.root / "workspace" / case.report_id / "iterations"
    if not iterations.is_dir():
        return []
    numbered = []
    for path in iterations.iterdir():
        m = _ITER_DIR_RE.match(path.name)
        if m and path.is_dir():
            numbered.append((int(m.group(1)), path / "comparison.json"))
    out = []
    for number, path in sorted(numbered, reverse=True):
        data, error = _load_json(path)
        if not error and isinstance(data, dict):
            out.append((number, _rel(case.root, path), data))
    return out


def _resolve_previous(
    case: _Case, previous: Optional[dict], snapshots: list[tuple[int, str, dict]]
) -> tuple[Optional[dict], str, list[tuple[int, list[dict]]]]:
    """上一版 comparison，以及比它更早的各轮快照。

    调用方给了 previous 就用给的（不再看磁盘上的快照）；没给时取迭代快照里最近一个数值内容与
    当前不同的作上一版，比它更早、同样与当前不同的快照另外返回（旧数值扫描对它们只认有效数字
    够多的写法）。返回 (上一版, 来源说明, [(轮次, 数值条目)])；没有上一版时返回 (None, "", [])。
    """
    if previous is not None:
        return (previous, "调用方传入", []) if isinstance(previous, dict) else (None, "", [])
    if case.comparison is None:
        return None, "", []
    current = _fingerprint(case.comparison)
    different = [item for item in snapshots if _fingerprint(item[2]) != current]
    if not different:
        return None, "", []
    _number, rel, data = different[0]
    older = [(number, _as_dict_list(snapshot.get("metrics"))) for number, _rel_path, snapshot in different[1:]]
    return data, rel, older


def _history_values(snapshots: list[tuple[int, str, dict]]) -> dict[str, list[tuple[int, Any]]]:
    """每条指标在各轮快照里的复现值：{指标编号: [(轮次, 值)]}。只用来认出「这是某一轮的旧值」。"""
    out: dict[str, list[tuple[int, Any]]] = {}
    for number, _rel_path, data in snapshots:
        for entry in _as_dict_list(data.get("metrics")):
            value = entry.get("reproduced_value")
            if _is_finite(value):
                out.setdefault(str(entry.get("key")), []).append((number, value))
    return out


def _read_docs(case: _Case, stage: Optional[str], stats: Optional[dict] = None) -> list[_Doc]:
    docs = []
    for path in _doc_paths(case.root, case.report_id, stage):
        rel = _rel(case.root, path)
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else None
        except (OSError, UnicodeDecodeError):
            text = None
        if text is None:
            if stats is not None:
                stats["skipped_files"].append(rel)
            continue
        if stats is not None:
            stats["checked_files"].append(rel)
            stats["checked_docs"].append(rel)
        docs.append(_parse_doc(rel, text))
    return docs


def _check_p4(case: _Case, stage: str, stats: dict, previous: Optional[dict] = None) -> list[_Hit]:
    """P4：文书与机器结果一致。result 阶段查 verify_report.md，report 阶段另查 final_report.md。

    三个子项见 `_count_hits`（达标计数）、`_table_value_hits`（手抄对比表的复现值）、
    `_stale_hits`（旧数值残留）。机器生成块和代码围栏里的内容不查。文书不存在时跳过，
    记在 stats 的 skipped_files 里。
    """
    docs = _read_docs(case, stage, stats)
    snapshots = _snapshots(case)
    prev, source, older = _resolve_previous(case, previous, snapshots)
    stats["previous"] = source or None
    stats["older_snapshots"] = [number for number, _metrics in older]
    prev_metrics: list[dict] = []
    prev_counts: Optional[_Counts] = None
    if prev is not None:
        prev_metrics = _as_dict_list(prev.get("metrics"))
        try:
            _pm, _pq, prev_recalc, prev_qual = _recalc(prev, case.standards, case.report_type, case.experimental)
            prev_counts = _counts_of(prev_metrics, prev_recalc, prev_qual)
        except Exception:  # noqa: BLE001 —— 上一版重算不了时只是少一个「等于上一版计数」的线索
            prev_counts = None
    prev_values = {str(e.get("key")): e.get("reproduced_value") for e in prev_metrics if _is_finite(e.get("reproduced_value"))}
    history = _history_values(snapshots)

    hits: list[_Hit] = []
    for doc in docs:
        for name, line_no in doc.dangling:
            hits.append(
                _Hit("P4", "warn", f"{doc.name} 第 {line_no} 行的机器生成块 {name} 缺少 END 标记，块里的内容会被当成正文核对", doc.rel, line_no)
            )
        hits += _count_hits(case, doc, prev_counts)
        value_hits, reported = _table_value_hits(case, doc, prev_values, history)
        hits += value_hits
        if prev is not None:
            hits += _stale_hits(case, doc, prev_metrics, reported, older)
    return hits


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

_CHECK_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _sorted_findings(hits: list[_Hit]) -> list[Finding]:
    """去重并排序：阻断在前、提示在后，各自按检查项、文件、行号排。"""
    ordered = sorted(hits, key=lambda h: (0 if h.level == "block" else 1, _CHECK_ORDER.get(h.check, 9), h.path, h.line))
    out: list[Finding] = []
    seen: set[Finding] = set()
    for hit in ordered:
        finding = hit.finding()
        if finding not in seen:
            seen.add(finding)
            out.append(finding)
    return out


def run_precheck(root: Path, report_id: str, stage: str = "result") -> PrecheckResult:
    """跑一次结果一致性预检。只读，不改任何文件。

    stage 为 "result"（结果外审之前）时 P4 只查 verify_report.md；为 "report"（写完报告之后）
    时另查 final_report.md。P1–P3 两个阶段都查。comparison.json 不存在或不可解析时只给一条
    阻断并直接返回。stats 里有重算口径的计数、核心要素数、核对过和跳过的文件。
    """
    if stage not in STAGES:
        raise ValueError(f"stage 只能是 {' / '.join(STAGES)}，收到的是 {stage!r}")
    root = Path(root)
    case = _load_case(root, report_id)
    stats: dict = {
        **_stats_counts(case.counts()),
        "core_elements": 0,
        "core_element_ids": [],
        "core_missing": [],
        "explicit_na": 0,
        "pointers_checked": 0,
        "empty_counted_as_pass": 0,
        "checked_files": [],
        "checked_docs": [],
        "skipped_files": [],
        "previous": None,
        "older_snapshots": [],
        "report_type": case.report_type,
        "experimental": case.experimental,
        "notes": list(case.notes),
    }
    hits: list[_Hit] = []
    if case.comparison is None:
        hits.append(_Hit("P1", "block", f"comparison.json {case.error}，四项检查都无法进行", case.comparison_rel))
    else:
        stats["checked_files"].append(case.comparison_rel)
        raw_values: dict[int, Any] = {}
        hits += _check_p1(case, stats)
        hits += _check_p2(case, stats, raw_values)
        hits += _check_p3(case, stats, raw_values)
        hits += _check_p4(case, stage, stats)
    findings = _sorted_findings(hits)
    stats["block"] = sum(1 for f in findings if f.level == "block")
    stats["warn"] = sum(1 for f in findings if f.level != "block")
    return PrecheckResult(report_id=report_id, stage=stage, findings=findings, stats=stats)


def scan_stale_numbers(
    root: Path, report_id: str, previous: Optional[dict] = None, stage: Optional[str] = None
) -> list[Finding]:
    """对比表变动之后，扫描文书里残留的旧数值，返回提示级的清单（每行一条）。

    previous 是上一版 comparison 的内容；没给时取 `workspace/<id>/iterations/iter_NN/comparison.json`
    里最近一个数值内容与当前不同的，找不到就返回空清单。哪些数算残留见 `_stale_hits`：等于
    某条指标的旧复现值或旧偏差、又不等于当前任何一个值的数；同一行里含「历史」「上一轮」
    「修订前」「旧值」等字样的不报。没给 previous 时，比上一版更早的快照也看，但只认 5 位及以上
    有效数字的写法。stage 不给时两份文书（verify_report.md、final_report.md）都扫，给 "result"
    只扫前一份。
    """
    if stage is not None and stage not in STAGES:
        raise ValueError(f"stage 只能是 {' / '.join(STAGES)}，收到的是 {stage!r}")
    case = _load_case(Path(root), report_id)
    if case.comparison is None:
        return []
    prev, _source, older = _resolve_previous(case, previous, [] if previous is not None else _snapshots(case))
    if prev is None:
        return []
    prev_metrics = _as_dict_list(prev.get("metrics"))
    hits: list[_Hit] = []
    for doc in _read_docs(case, stage):
        hits += _stale_hits(case, doc, prev_metrics, None, older)
    return _sorted_findings(hits)
