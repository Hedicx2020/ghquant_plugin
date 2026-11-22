"""围栏感知的 Markdown 切片器。

内核按「角色 × 步骤」给子 agent 拼任务文件时，要从 spec.md / assumptions.md / plan.md /
coverage_matrix.md 里切出片段。这里的每个片都是原文的一段连续文本（逐字节子串），带起止
偏移和内容哈希，原文始终是权威来源。

与 `check_gates.parse_id_blocks` 的区别：
- 代码围栏里的 `#` 行不算标题；
- 要素块在「下一个同级或更高级标题」处结束，每章最后一块不会把后面的章节吞进来；
- 块内的字段、表格行都有各自的起止位置，可以单独取用。

要素 ID 的识别口径与 `check_gates._ID_HEADING_RE` 相同，单测断言两者切出的 ID 集合一致。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")  # 尾部空白在取用处去掉：写成 (.*?)[ \t]*$ 遇到长空白会平方级回溯
# 与 check_gates._ID_HEADING_RE 同口径：三个井号、一个空格、方括号里的「前缀 + 数字」
_ID_HEADING_RE = re.compile(r"^### \[([A-Z]+)(\d+(?:\.\d+)?)\]\s*(.*)$")
_FIELD_RE = re.compile(r"^-\s*([^\s:：][^:：]*)[:：][ \t]*(.*)$")  # 字段名从非空白起，免得与前面的 \s* 抢同一段空白
_TABLE_SEP_RE = re.compile(r"^\|[\s:-]+(\|[\s:-]+)*\|\s*$")


def read_source(path: Path) -> str:
    """按字节读入并解码，不做换行符转换，保证切出的片是文件内容的逐字节子串。"""
    return path.read_bytes().decode("utf-8")


def slice_hash(text: str) -> str:
    """片级哈希（内容的 sha256 前 16 位）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 行扫描（跟踪代码围栏）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    start: int  # 在全文中的起始偏移
    end: int  # 结束偏移（含行尾换行符）
    text: str  # 去掉行尾换行符的内容
    in_fence: bool  # 是否在代码围栏内（围栏的起止行本身也算）


def scan_lines(text: str) -> list[Line]:
    lines: list[Line] = []
    pos = 0
    fence: Optional[str] = None  # 当前围栏的起始标记，如 "```"
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        in_fence = fence is not None
        m = _FENCE_RE.match(body)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker
                in_fence = True
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not body.strip().strip(marker[0]):
                fence = None  # 收尾围栏：同种符号、不短于起始、其后无内容
        lines.append(Line(pos, pos + len(raw), body, in_fence))
        pos += len(raw)
    return lines


# ---------------------------------------------------------------------------
# 标题与章节
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    start: int  # 标题行起始
    end: int  # 标题行结束（含换行）
    line_no: int  # 行号，从 1 起


@dataclass(frozen=True)
class Section:
    heading: Heading
    start: int  # 标题行起始
    end: int  # 下一个同级或更高级标题的起始，或文末
    text: str

    @property
    def title(self) -> str:
        return self.heading.title

    @property
    def level(self) -> int:
        return self.heading.level


def headings(text: str, lines: Optional[list[Line]] = None) -> list[Heading]:
    out: list[Heading] = []
    for no, line in enumerate(lines if lines is not None else scan_lines(text), 1):
        if line.in_fence:
            continue
        m = _HEADING_RE.match(line.text)
        if m:
            out.append(Heading(len(m.group(1)), m.group(2).rstrip(" \t\r"), line.start, line.end, no))
    return out


def sections(text: str, lines: Optional[list[Line]] = None) -> list[Section]:
    """每个标题一个章节：从标题行起，到下一个同级或更高级标题之前。"""
    heads = headings(text, lines)
    out: list[Section] = []
    for i, head in enumerate(heads):
        end = len(text)
        for later in heads[i + 1:]:
            if later.level <= head.level:
                end = later.start
                break
        out.append(Section(head, head.start, end, text[head.start:end]))
    return out


def find_sections(text: str, predicate: Callable[[Heading], bool]) -> list[Section]:
    return [s for s in sections(text) if predicate(s.heading)]


# ---------------------------------------------------------------------------
# 要素块（### [F2] 标题 + 字段行）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSlice:
    name: str
    value: str  # 字段首行冒号之后的内容
    start: int
    end: int  # 到下一个字段之前（去掉尾部空行）
    text: str


@dataclass(frozen=True)
class Block:
    id: str
    prefix: str
    number: str
    title: str
    start: int  # 标题行起始
    heading_end: int  # 标题行结束（含换行）
    end: int
    text: str
    fields: tuple[FieldSlice, ...]

    @property
    def heading_line(self) -> str:
        return self.text[: self.heading_end - self.start]

    def field(self, name: str) -> Optional[FieldSlice]:
        """按字段名精确取第一条。"""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def fields_where(self, predicate: Callable[[str], bool]) -> list[FieldSlice]:
        return [f for f in self.fields if predicate(f.name)]


def parse_blocks(text: str) -> list[Block]:
    """切出全部要素块。块在下一个三级及以上标题处结束（围栏内的标题不算）。"""
    lines = scan_lines(text)
    heads = headings(text, lines)
    blocks: list[Block] = []
    for i, head in enumerate(heads):
        if head.level != 3:
            continue
        m = _ID_HEADING_RE.match(text[head.start:head.end].rstrip("\r\n"))
        if not m:
            continue
        end = len(text)
        for later in heads[i + 1:]:
            if later.level <= 3:
                end = later.start
                break
        prefix, number, title = m.group(1), m.group(2), m.group(3).strip()
        body_lines = [ln for ln in lines if head.end <= ln.start < end]
        blocks.append(
            Block(
                id=f"{prefix}{number}",
                prefix=prefix,
                number=number,
                title=title,
                start=head.start,
                heading_end=head.end,
                end=end,
                text=text[head.start:end],
                fields=tuple(_parse_fields(text, body_lines, end)),
            )
        )
    return blocks


def _parse_fields(text: str, body_lines: list[Line], block_end: int) -> list[FieldSlice]:
    starts: list[tuple[Line, str, str]] = []
    for line in body_lines:
        if line.in_fence:
            continue
        m = _FIELD_RE.match(line.text)  # 只认顶格的字段行，缩进的子弹属于上一个字段
        if m:
            starts.append((line, m.group(1).strip(), m.group(2).strip()))
    fields: list[FieldSlice] = []
    for i, (line, name, value) in enumerate(starts):
        hard_end = starts[i + 1][0].start if i + 1 < len(starts) else block_end
        end = line.end
        for ln in body_lines:  # 去掉尾部空行：结束在本字段范围内最后一个非空行
            if line.start <= ln.start < hard_end and ln.text.strip():
                end = ln.end
        fields.append(FieldSlice(name, value, line.start, end, text[line.start:end]))
    return fields


def block_ids(text: str) -> list[str]:
    return [b.id for b in parse_blocks(text)]


# ---------------------------------------------------------------------------
# 表格行（保留每行在原文中的位置）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableRow:
    cells: dict[str, str]
    start: int
    end: int
    text: str
    header_start: int  # 所属表格的表头行起始
    header_end: int  # 分隔行结束（表头行 + 分隔行是连续的两行）


def _split_cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|") and inner.endswith("|"):
        inner = inner[1:-1]
    return [p.strip().replace("\\|", "|") for p in re.split(r"(?<!\\)\|", inner)]


def parse_table_rows(text: str) -> list[TableRow]:
    """解析全文的 markdown 表格行（拆格规则与 check_gates.parse_markdown_table_rows 相同）。"""
    lines = scan_lines(text)
    rows: list[TableRow] = []
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].text.strip()
        if (
            not lines[i].in_fence
            and stripped.startswith("|")
            and stripped.endswith("|")
            and i + 1 < n
            and _TABLE_SEP_RE.match(lines[i + 1].text.strip())
        ):
            header = _split_cells(stripped)
            header_start, header_end = lines[i].start, lines[i + 1].end
            j = i + 2
            while j < n:
                candidate = lines[j].text.strip()
                if not (candidate.startswith("|") and candidate.endswith("|")):
                    break
                cells = _split_cells(candidate)
                row = {header[k]: (cells[k] if k < len(cells) else "") for k in range(len(header))}
                rows.append(TableRow(row, lines[j].start, lines[j].end, text[lines[j].start:lines[j].end], header_start, header_end))
                j += 1
            i = j
            continue
        i += 1
    return rows


def row_get(cells: dict[str, str], *keywords: str) -> str:
    """按列名取值：先精确匹配，再退化为「列名含全部关键词」（同 check_gates._row_get）。"""
    exact = " ".join(keywords).strip()
    for key, value in cells.items():
        if key.strip() == exact:
            return (value or "").strip()
    for key, value in cells.items():
        low = key.lower()
        if all(kw.lower() in low for kw in keywords):
            return (value or "").strip()
    return ""


# ---------------------------------------------------------------------------
# frontmatter 位置
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def frontmatter_span(text: str) -> Optional[tuple[int, int]]:
    """frontmatter 整段（含首尾 --- 行）在全文中的起止；没有则返回 None。"""
    m = _FRONTMATTER_RE.match(text)
    return (m.start(), m.end()) if m else None


# ---------------------------------------------------------------------------
# 要素引用解析
# ---------------------------------------------------------------------------

ELEMENT_PREFIXES = ("SA", "D", "F", "B", "R")
_RANGE_SEP = r"[-–—~～至到]"


def extract_refs(text: str, prefixes: Iterable[str] = ELEMENT_PREFIXES) -> list[str]:
    """从文字里取出要素编号，保持首次出现的顺序。

    支持 `D1-D3`、`R2~R7`、`SA5–SA7` 这类同前缀区间（展开为逐个编号，跨度不超过 50）。
    前后紧挨字母或数字的不算，避免把变量名里的片段当成编号。
    """
    alternation = "|".join(sorted({re.escape(p) for p in prefixes}, key=len, reverse=True))
    if not alternation:
        return []
    token = rf"(?<![A-Za-z0-9_])({alternation})(\d+(?:\.\d+)?)(?![A-Za-z0-9_])"
    range_re = re.compile(rf"(?<![A-Za-z0-9_])({alternation})(\d+)\s*{_RANGE_SEP}\s*({alternation})(\d+)(?![A-Za-z0-9_.])")
    found: list[tuple[int, str]] = []
    covered: list[tuple[int, int]] = []
    for m in range_re.finditer(text):
        left, lo, right, hi = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        if left == right and lo <= hi and hi - lo <= 50:
            found.extend((m.start(), f"{left}{n}") for n in range(lo, hi + 1))
            covered.append((m.start(), m.end()))
    for m in re.finditer(token, text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        found.append((m.start(), f"{m.group(1)}{m.group(2)}"))
    out: list[str] = []
    for _pos, ref in sorted(found, key=lambda item: item[0]):
        if ref not in out:
            out.append(ref)
    return out


def extract_milestones(text: str) -> list[str]:
    """取出 mN 编号（支持 m2-m4 区间），保持首次出现的顺序。"""
    out: list[str] = []
    covered: list[tuple[int, int]] = []
    hits: list[tuple[int, str]] = []
    for m in re.finditer(rf"(?<![A-Za-z0-9_])m(\d+)\s*{_RANGE_SEP}\s*m?(\d+)(?![A-Za-z0-9_])", text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi and hi - lo <= 30:
            hits.extend((m.start(), f"m{n}") for n in range(lo, hi + 1))
            covered.append((m.start(), m.end()))
    for m in re.finditer(r"(?<![A-Za-z0-9_])m(\d+)(?![A-Za-z0-9_])", text):
        if any(a <= m.start() < b for a, b in covered):
            continue
        hits.append((m.start(), f"m{m.group(1)}"))
    for _pos, ms in sorted(hits, key=lambda item: item[0]):
        if ms not in out:
            out.append(ms)
    return out
