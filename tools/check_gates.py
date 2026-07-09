#!/usr/bin/env python3
"""门禁机器判定（研报复现系统 v2）。

用法：
    uv run python tools/check_gates.py <report_id> --stage <stage> [--assert-done] [--record]

两种模式：
    默认模式      按设计文档 §三 的 G-XX 断言，对 <stage> 当前产物逐条重算，
                  用于该 stage 收尾时判断是否放行进入下一阶段。
    --assert-done 只读 state.json 中记录的 stage 状态，断言其为 done，或
                  （裁剪矩阵允许时，目前仅 iterate）为 skipped——用于下一 stage
                  开始前的前置断言，成本远低于默认模式的全量重算。

输出：逐条 `[PASS|FAIL] G-XX-n 描述`，末行 `VERDICT: PASS|FAIL`；exit code 0/1。
`--record` 把本次判定结果通过 tools/state.py 写入 state.gates[]（唯一写入口）。

不信任任何 agent 自述：comparison.json 的 pass 字段一律按 templates/standards.json
重算；state.json 的 stage 状态只作为 --assert-done 的核验对象，不作为默认模式的
判据来源。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 让 `python tools/check_gates.py` 直接执行时也能 `from tools import state`
# ---------------------------------------------------------------------------

_REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

import yaml  # noqa: E402

from tools import state as st  # noqa: E402

# ---------------------------------------------------------------------------
# 难度裁剪矩阵（设计文档 §三 stage × difficulty 表的机器化子集）
# ---------------------------------------------------------------------------

# --assert-done 允许"已跳过"放行的 stage：全表里唯一条件性跳过的整段 stage 是
# iterate（首轮 verify 即达标则整段迭代不发生）；其余 stage 的"跳过"只发生在
# stage 内部的子机制（如 easy 难度的 auditor 内审），不构成整段 stage 跳过。
SKIPPABLE_STAGES = {"iterate"}

REQUIRED_SPEC_FRONTMATTER_FIELDS = [
    "report_name",
    "title",
    "institution",
    "report_date",
    "authors",
    "market",
    "pdf_pages",
    "exhibit_declared",
    "element_counts",
    "type_hint",
    "tags_hint",
]
# tags_hint 允许为空列表：多数研报没有 ml 等特殊标签，空列表是合法值，
# 只要求键存在，不强制非空（否则绝大多数非 ml 研报会被此项误判 FAIL）。
_OPTIONAL_EMPTY_FRONTMATTER_FIELDS = {"tags_hint"}

ELEMENT_HEADING_RE = re.compile(r"^### \[(D|F|B|R|SA)\d+(?:\.\d+)?\]", re.MULTILINE)

DIFFICULTY_MIN_MILESTONES = {"easy": 1, "medium": 2, "hard": 3}

REQUIRED_REPORT_SECTIONS = ["结论", "指标对比", "假设登记簿", "迭代历史", "审计回应", "残余偏差", "未复现清单", "复跑指引"]


@dataclass
class CheckResult:
    id: str
    desc: str
    passed: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# 通用解析工具：frontmatter / [ID] 块 / markdown 表格
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[Optional[dict], str]:
    """解析文档开头的 YAML frontmatter，返回 (dict 或 None, 去掉 frontmatter 的正文)。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    body = text[m.end():]
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None, body
    if not isinstance(data, dict):
        return None, body
    return data, body


_ID_HEADING_RE = re.compile(r"^### \[([A-Z]+)(\d+(?:\.\d+)?)\]\s*(.*)$", re.MULTILINE)
_ID_FIELD_RE = re.compile(r"^-\s*([^:：]+)[:：]\s*(.*)$")


@dataclass
class IdBlock:
    prefix: str
    number: str
    id: str
    title: str
    fields: dict[str, str]
    body: str


def parse_id_blocks(text: str) -> list[IdBlock]:
    """解析形如 `### [F2] 标题` + `- 字段: 值` 的要素/歧义/假设块（spec.md / ambiguities.md / assumptions.md 通用）。"""
    matches = list(_ID_HEADING_RE.finditer(text))
    blocks: list[IdBlock] = []
    for i, m in enumerate(matches):
        prefix, number, title = m.group(1), m.group(2), m.group(3).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        fields: dict[str, str] = {}
        for line in body.splitlines():
            fm = _ID_FIELD_RE.match(line.strip())
            if fm:
                fields.setdefault(fm.group(1).strip(), fm.group(2).strip())
        blocks.append(IdBlock(prefix=prefix, number=number, id=f"{prefix}{number}", title=title, fields=fields, body=body))
    return blocks


_SEP_RE = re.compile(r"^\|[\s:-]+(\|[\s:-]+)*\|\s*$")


def _split_row_cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|") and inner.endswith("|"):
        inner = inner[1:-1]
    parts = re.split(r"(?<!\\)\|", inner)
    return [p.strip().replace("\\|", "|") for p in parts]


def parse_markdown_table_rows(text: str) -> list[dict[str, str]]:
    """解析文档内全部 markdown 表格，返回按各自表头拼装的行字典列表（多表拼接）。"""
    lines = text.splitlines()
    rows: list[dict[str, str]] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < n and _SEP_RE.match(lines[i + 1].strip()):
            headers = _split_row_cells(line)
            j = i + 2
            while j < n:
                candidate = lines[j].strip()
                if not (candidate.startswith("|") and candidate.endswith("|")):
                    break
                cells = _split_row_cells(candidate)
                row = {headers[k]: (cells[k] if k < len(cells) else "") for k in range(len(headers))}
                rows.append(row)
                j += 1
            i = j
            continue
        i += 1
    return rows


def _row_get(row: dict[str, str], *keywords: str) -> str:
    """按列名取值：优先精确匹配关键词拼接，其次退化为"列名含全部关键词"的模糊匹配。

    审计类模板里列名常带括注（如"处置(accepted/rejected/deferred)"），模糊匹配
    用于在不锁死上游模板措辞的前提下仍能稳定取到目标列。
    """
    exact = " ".join(keywords).strip()
    for k, v in row.items():
        if k.strip() == exact:
            return (v or "").strip()
    for k, v in row.items():
        kl = k.lower()
        if all(kw.lower() in kl for kw in keywords):
            return (v or "").strip()
    return ""


def _row_id(row: dict[str, str], pattern: str) -> str:
    """在行的任意单元格里找匹配 pattern 的 ID（不依赖具体列名，如 DIF-01 / CDX-S-01）。"""
    for v in row.values():
        if v and re.match(pattern, v.strip()):
            return v.strip()
    return ""


# 要素 ID：D/F/B/R/SA 前缀 + 数字，含 F3.1 一类子变体（与 quant-extractor.md 的
# 自查正则、ELEMENT_HEADING_RE 保持一致）。
_MATRIX_ELEMENT_ID_RE = re.compile(r"^(D|F|B|R|SA)\d+(\.\d+)?$")


def load_matrix_rows(path: Path) -> list[dict[str, str]]:
    """解析 coverage_matrix.md 并只保留真正的「要素行」，过滤变更日志等其它表格。

    coverage_matrix.md 除 11 列主表外，文末固定还有一个「变更日志」表格（表头
    「时间/事件/来源/说明」），且不排除未来出现其它文档性表格（如模板里的
    「列说明」）；`parse_markdown_table_rows` 对整份文件逐表拼接返回全部表格的
    数据行，若不过滤会把这些表的行也计入「要素行」，污染依赖行数/遍历的门禁
    （G-EX-4 计数、G-PL-6/G-IM-5/G-VF-7/G-FN-3 遍历要素行判缺失）。

    这里按「要素ID」列值是否匹配 D/F/B/R/SA 前缀+数字（含子变体）过滤——这是
    全部五处门禁读取 coverage_matrix.md 的唯一入口，杜绝各门禁各写各的过滤逻辑。
    """
    if not path.is_file():
        return []
    rows = parse_markdown_table_rows(path.read_text(encoding="utf-8"))
    return [r for r in rows if _MATRIX_ELEMENT_ID_RE.match(_row_get(r, "要素ID"))]


_H2_HEADING_RE = re.compile(r"^##\s+.*$", re.MULTILINE)


def _extract_h2_section(body: str, heading_keyword: str) -> str:
    """按标题关键词定位正文中的 H2 节，返回该节正文（不含标题行本身，至下一个 H2 或文末）。

    用于图表登记清单等按 H2 分节、节内为 markdown 表格（而非 [ID] 标题块）的场景。
    """
    headings = list(_H2_HEADING_RE.finditer(body))
    for i, m in enumerate(headings):
        if heading_keyword in m.group(0):
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            return body[start:end]
    return ""


# 图表登记清单表格的数据行：| FIG12 | ... | / | TBL3 | ... | / | EX25 | ... |
# EX 前缀用于研报以「图表N」统一编号、不区分 TBL/FIG 的情形（替代 TBL/FIG）。
_EXHIBIT_ROW_RE = re.compile(r"^\|\s*(FIG|TBL|EX)(\d+)\s*\|", re.MULTILINE)


def _safe_load_state(root: Path, report_id: str) -> Optional[dict]:
    try:
        return st.load_state(root, report_id)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# G-IN：init
# ---------------------------------------------------------------------------


def check_init(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-IN"
    results: list[CheckResult] = []

    state_file = st.state_path(root, report_id)
    if not state_file.is_file():
        results.append(CheckResult(f"{gid}-1", "state schema 合法", False, "state.json 不存在"))
        return results
    try:
        raw_state = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        results.append(CheckResult(f"{gid}-1", "state schema 合法", False, f"JSON 解析失败: {exc}"))
        return results

    schema_errors = st.validate_state(raw_state)
    results.append(CheckResult(f"{gid}-1", "state schema 合法", not schema_errors, "; ".join(schema_errors)))

    ws = root / "workspace" / report_id
    required_dirs = {
        "workspace/{id}/spec": ws / "spec",
        "workspace/{id}/audit": ws / "audit",
        "workspace/{id}/iterations": ws / "iterations",
        "output/{id}/results": root / "output" / report_id / "results",
        "src/{id}": root / "src" / report_id,
    }
    missing_dirs = [name for name, p in required_dirs.items() if not p.is_dir()]
    results.append(CheckResult(f"{gid}-2", "目录树齐全", not missing_dirs, f"缺失: {missing_dirs}" if missing_dirs else ""))

    report_text_path = ws / "spec" / "report_text.md"
    exists = report_text_path.is_file()
    results.append(CheckResult(f"{gid}-3", "report_text.md 存在", exists))

    page_marks = 0
    if exists:
        text = report_text_path.read_text(encoding="utf-8")
        page_marks = len(re.findall(r"^===== PAGE \d+ =====$", text, re.MULTILINE))
    results.append(CheckResult(f"{gid}-4", "report_text.md 中 PAGE 标记数 >= 1", page_marks >= 1, f"实际 {page_marks}"))

    expected_pages = raw_state.get("pdf_pages")
    if expected_pages is None:
        pdf_rel = raw_state.get("pdf_path", "")
        pdf_path = (root / pdf_rel) if pdf_rel else None
        if pdf_path is not None and pdf_path.exists():
            try:
                import pypdf

                expected_pages = len(pypdf.PdfReader(str(pdf_path)).pages)
            except Exception:  # noqa: BLE001
                expected_pages = None
    if expected_pages is None:
        results.append(
            CheckResult(
                f"{gid}-5",
                "PAGE 标记数与 PDF 页数一致",
                False,
                "无法核算 PDF 页数（state.pdf_pages 未设置且原 PDF 不可读）",
            )
        )
    else:
        results.append(
            CheckResult(
                f"{gid}-5",
                "PAGE 标记数与 PDF 页数一致",
                page_marks == expected_pages,
                f"标记数={page_marks} PDF页数={expected_pages}",
            )
        )

    tables_path = ws / "spec" / "tables_extracted.md"
    results.append(CheckResult(f"{gid}-6", "tables_extracted.md 存在", tables_path.is_file()))

    return results


# ---------------------------------------------------------------------------
# G-EX：extract
# ---------------------------------------------------------------------------


def check_extract(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-EX"
    results: list[CheckResult] = []
    spec_dir = root / "workspace" / report_id / "spec"
    spec_path = spec_dir / "spec.md"

    if not spec_path.is_file():
        results.append(CheckResult(f"{gid}-1", "spec.md 存在", False))
        return results
    results.append(CheckResult(f"{gid}-1", "spec.md 存在", True))

    text = spec_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    results.append(CheckResult(f"{gid}-2", "frontmatter 可解析（yaml）", frontmatter is not None))
    if frontmatter is None:
        return results

    missing_keys = [f for f in REQUIRED_SPEC_FRONTMATTER_FIELDS if f not in frontmatter]
    empty_fields = [
        f
        for f in REQUIRED_SPEC_FRONTMATTER_FIELDS
        if f not in missing_keys and f not in _OPTIONAL_EMPTY_FRONTMATTER_FIELDS and not frontmatter.get(f)
    ]
    problems = missing_keys + empty_fields
    results.append(
        CheckResult(f"{gid}-3", "frontmatter 必填字段齐全非空（tags_hint 允许空列表）", not problems, f"缺失/为空: {problems}" if problems else "")
    )

    regex_count = len(ELEMENT_HEADING_RE.findall(body))
    element_counts = frontmatter.get("element_counts") or {}
    fm_sum = sum(v for k, v in element_counts.items() if k in ("D", "F", "B", "R", "SA") and isinstance(v, (int, float)))

    matrix_path = spec_dir / "coverage_matrix.md"
    matrix_rows = load_matrix_rows(matrix_path)
    matrix_count = len(matrix_rows)

    three_way_ok = regex_count == fm_sum == matrix_count
    results.append(
        CheckResult(
            f"{gid}-4",
            "正文正则计数 == frontmatter element_counts 汇总 == coverage_matrix 数据行数",
            three_way_ok,
            f"正则={regex_count} frontmatter={fm_sum} 矩阵={matrix_count}",
        )
    )

    blocks = parse_id_blocks(body)
    dfrbsa_blocks = [b for b in blocks if b.prefix in ("D", "F", "B", "R", "SA")]
    missing_evidence = [b.id for b in dfrbsa_blocks if "页码" not in b.fields or "原文" not in b.fields]
    results.append(
        CheckResult(
            f"{gid}-5",
            "每条要素块含「- 页码:」与「- 原文:」行",
            not missing_evidence,
            f"缺失: {missing_evidence}" if missing_evidence else "",
        )
    )

    r_count = sum(1 for b in dfrbsa_blocks if b.prefix == "R")
    results.append(CheckResult(f"{gid}-6", "R 类要素 >= 1", r_count >= 1, f"实际 {r_count}"))

    ambiguities_path = spec_dir / "ambiguities.md"
    results.append(CheckResult(f"{gid}-7", "ambiguities.md 存在", ambiguities_path.is_file()))

    # 图表登记清单是「图表登记」H2 节内的 markdown 表格（非 ### [ID] 标题块），
    # 数据行形如 `| FIG12 | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |`；
    # EX 前缀用于研报以「图表N」统一编号、替代 TBL/FIG 的情形，计入 FIG 桶。
    # 严格的编号连续性校验属于 spec_audit 阶段审计 agent 的 C1 职责，这里只做
    # 计数一致与「不超过声明上限」两项机器可核的弱校验。
    exhibit_declared = frontmatter.get("exhibit_declared") or {}
    exhibit_section = _extract_h2_section(body, "图表登记")
    exhibit_rows = _EXHIBIT_ROW_RE.findall(exhibit_section)
    fig_ex_numbers = [int(n) for prefix, n in exhibit_rows if prefix in ("FIG", "EX")]
    tbl_numbers = [int(n) for prefix, n in exhibit_rows if prefix == "TBL"]

    fig_registered_decl = element_counts.get("FIG_registered")
    tbl_registered_decl = element_counts.get("TBL_registered")
    fig_max_decl = exhibit_declared.get("fig_max")
    tbl_max_decl = exhibit_declared.get("tbl_max")

    problems: list[str] = []
    if fig_registered_decl is not None and len(fig_ex_numbers) != fig_registered_decl:
        problems.append(f"FIG+EX行数={len(fig_ex_numbers)}!=element_counts.FIG_registered={fig_registered_decl}")
    if tbl_registered_decl is not None and len(tbl_numbers) != tbl_registered_decl:
        problems.append(f"TBL行数={len(tbl_numbers)}!=element_counts.TBL_registered={tbl_registered_decl}")
    if fig_max_decl is not None and max(fig_ex_numbers, default=0) > fig_max_decl:
        problems.append(f"FIG/EX最大编号={max(fig_ex_numbers, default=0)}>exhibit_declared.fig_max={fig_max_decl}")
    if tbl_max_decl is not None and max(tbl_numbers, default=0) > tbl_max_decl:
        problems.append(f"TBL最大编号={max(tbl_numbers, default=0)}>exhibit_declared.tbl_max={tbl_max_decl}")

    results.append(
        CheckResult(
            f"{gid}-8",
            "图表登记清单表格：FIG+EX/TBL 行数与 element_counts 一致，最大编号不超过 exhibit_declared 声明",
            not problems,
            "; ".join(problems),
        )
    )

    return results


# ---------------------------------------------------------------------------
# G-PL：plan
# ---------------------------------------------------------------------------


def _has_cycle(milestones: list[dict]) -> bool:
    graph = {m.get("id"): (m.get("deps") or []) for m in milestones if isinstance(m, dict) and m.get("id")}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in graph}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for dep in graph.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                return True
            if color[dep] == WHITE and visit(dep):
                return True
        color[node] = BLACK
        return False

    return any(color[n] == WHITE and visit(n) for n in list(graph))


def check_plan(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-PL"
    results: list[CheckResult] = []
    plan_path = root / "workspace" / report_id / "plan.md"

    if not plan_path.is_file():
        results.append(CheckResult(f"{gid}-1", "plan.md 存在", False))
        return results
    results.append(CheckResult(f"{gid}-1", "plan.md 存在", True))

    text = plan_path.read_text(encoding="utf-8")
    frontmatter, _body = parse_frontmatter(text)
    results.append(CheckResult(f"{gid}-2", "frontmatter 可解析（yaml）", frontmatter is not None))
    if frontmatter is None:
        return results

    type_ok = frontmatter.get("type") in st.TYPE_VALUES
    difficulty_ok = frontmatter.get("difficulty") in st.DIFFICULTY_VALUES
    feasibility_ok = frontmatter.get("feasibility") in st.FEASIBILITY_VALUES
    results.append(
        CheckResult(
            f"{gid}-3",
            "frontmatter 枚举合法（type/difficulty/feasibility）",
            type_ok and difficulty_ok and feasibility_ok,
            f"type={frontmatter.get('type')} difficulty={frontmatter.get('difficulty')} feasibility={frontmatter.get('feasibility')}",
        )
    )

    milestones = frontmatter.get("milestones") or []
    difficulty = frontmatter.get("difficulty")
    min_required = DIFFICULTY_MIN_MILESTONES.get(difficulty, 1)
    results.append(
        CheckResult(
            f"{gid}-4",
            f"milestone 数 >= 难度下限（{difficulty}: {min_required}）",
            len(milestones) >= min_required,
            f"实际 {len(milestones)}",
        )
    )

    has_cycle = _has_cycle(milestones)
    results.append(CheckResult(f"{gid}-5", "milestone deps 无环", not has_cycle))

    matrix_path = root / "workspace" / report_id / "spec" / "coverage_matrix.md"
    matrix_rows = load_matrix_rows(matrix_path)
    missing_milestone_rows = [
        _row_get(r, "要素ID")
        for r in matrix_rows
        if _row_get(r, "状态") not in ("skipped", "infeasible") and not _row_get(r, "milestone")
    ]
    results.append(
        CheckResult(
            f"{gid}-6",
            "矩阵所有非 skipped/infeasible 行 milestone 列非空",
            not missing_milestone_rows,
            f"缺失: {missing_milestone_rows}" if missing_milestone_rows else "",
        )
    )

    ambiguities_path = root / "workspace" / report_id / "spec" / "ambiguities.md"
    if ambiguities_path.is_file():
        blocks = parse_id_blocks(ambiguities_path.read_text(encoding="utf-8"))
        bad_status = [b.id for b in blocks if b.fields.get("状态") not in ("resolved", "blocked")]
        results.append(
            CheckResult(
                f"{gid}-7",
                "ambiguities.md 每条 status ∈ resolved/blocked",
                not bad_status,
                f"未决议: {bad_status}" if bad_status else "",
            )
        )
        open_blocking = [b.id for b in blocks if b.fields.get("等级") == "blocking" and b.fields.get("状态") == "open"]
        results.append(
            CheckResult(f"{gid}-8", "无 blocking 级 open 歧义", not open_blocking, f"存在: {open_blocking}" if open_blocking else "")
        )
    else:
        results.append(CheckResult(f"{gid}-7", "ambiguities.md 每条 status ∈ resolved/blocked", False, "ambiguities.md 不存在"))
        results.append(CheckResult(f"{gid}-8", "无 blocking 级 open 歧义", False, "ambiguities.md 不存在"))

    results.append(CheckResult(f"{gid}-9", "feasibility != blocked", frontmatter.get("feasibility") != "blocked"))

    return results


# ---------------------------------------------------------------------------
# codex 外审三关（G-SA / G-CA / G-RA）共用解析
# ---------------------------------------------------------------------------


def _parse_codex_output(path: Path) -> tuple[Optional[int], Optional[str]]:
    """解析 codex 审查输出，返回 (issues 数, verdict)。

    约定（供 templates/codex_prompts 与 review_schema.json 对齐）：优先整份 JSON
    或文中 ```json 代码块，形如 {"verdict": ..., "findings": [...]}；否则退化为
    markdown 表格行数 + 文中 `VERDICT: xxx` 行。降级路径只统计首格匹配 `^CDX-`
    的表格行（与 `_parse_audit_responses` 按 CDX- ID 识别行的语义对称），不是文中
    出现的任意表格（如「已检查维度」汇总表）都算一条 issue。
    """
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8")

    for candidate in [text, *(m.group(1) for m in re.finditer(r"```json\s*(.*?)```", text, re.DOTALL))]:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "findings" in data:
            findings = data.get("findings") or []
            return len(findings), data.get("verdict")

    # 裸 JSON：prompt 契约允许「纯 JSON（不 fence）」，实际输出常为混合文本
    # （盲提取标记块等）尾随一个 JSON 对象——整文件 loads 会失败，fenced 扫描
    # 也扫不到。从后往前找行首 "{" 逐个 raw_decode，取最后一个含 findings 的对象。
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"^[ \t]*\{", text, re.MULTILINE))):
        try:
            data, _end = decoder.raw_decode(text, m.end() - 1)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and "findings" in data:
            findings = data.get("findings") or []
            return len(findings), data.get("verdict")

    rows = parse_markdown_table_rows(text)
    cdx_rows = [r for r in rows if re.match(r"^CDX-", next(iter(r.values()), "") or "")]
    verdict_match = re.search(r"VERDICT:\s*(\w+)", text, re.IGNORECASE)
    return len(cdx_rows), (verdict_match.group(1) if verdict_match else None)


def _parse_audit_responses(path: Path, prefix: str) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows = parse_markdown_table_rows(path.read_text(encoding="utf-8"))
    matched = []
    for r in rows:
        rid = _row_id(r, r"^CDX-[A-Z]-")
        if rid.startswith(prefix):
            matched.append(r)
    return matched


# ---------------------------------------------------------------------------
# G-SA：spec_audit
# ---------------------------------------------------------------------------


def check_spec_audit(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-SA"
    results: list[CheckResult] = []
    state = _safe_load_state(root, report_id) or {}
    difficulty = state.get("difficulty") or "medium"

    spec_dir = root / "workspace" / report_id / "spec"
    audit_dir = root / "workspace" / report_id / "audit"

    spec_codex = spec_dir / "spec_codex.md"
    extract_diff = spec_dir / "extract_diff.md"
    spec_audit_codex = audit_dir / "spec_audit_codex.md"
    responses_path = audit_dir / "audit_responses.md"

    must_exist = {"spec_codex.md": spec_codex, "extract_diff.md": extract_diff, "spec_audit_codex.md": spec_audit_codex}
    missing = [name for name, p in must_exist.items() if not p.is_file()]
    results.append(
        CheckResult(f"{gid}-1", "codex 盲提取/diff/审查产物齐（全难度必跑）", not missing, f"缺失: {missing}" if missing else "")
    )

    extract_audit = audit_dir / "extract_audit.md"
    if difficulty == "easy":
        results.append(CheckResult(f"{gid}-2", "extract_audit.md（内审，easy 允许跳过）", True, "easy 难度跳过"))
    else:
        results.append(CheckResult(f"{gid}-2", "extract_audit.md 存在（medium/hard 必跑）", extract_audit.is_file()))

    if extract_diff.is_file():
        diff_rows = [r for r in parse_markdown_table_rows(extract_diff.read_text(encoding="utf-8")) if _row_id(r, r"^DIF-?\d+")]
        unresolved = [_row_id(r, r"^DIF-?\d+") for r in diff_rows if not _row_get(r, "裁决")]
        results.append(
            CheckResult(f"{gid}-3", "extract_diff.md 所有 DIF 行裁决列非空", not unresolved, f"未裁决: {unresolved}" if unresolved else "")
        )
    else:
        results.append(CheckResult(f"{gid}-3", "extract_diff.md 所有 DIF 行裁决列非空", False, "extract_diff.md 不存在"))

    issues_count, _verdict = _parse_codex_output(spec_audit_codex)
    response_rows = _parse_audit_responses(responses_path, "CDX-S-")
    if issues_count is None:
        results.append(CheckResult(f"{gid}-4", "audit_responses.md 回应行数 == spec 审查 issues 数", False, "spec_audit_codex.md 无法解析"))
    else:
        results.append(
            CheckResult(
                f"{gid}-4",
                "audit_responses.md 回应行数 == spec 审查 issues 数",
                len(response_rows) == issues_count,
                f"回应={len(response_rows)} issues={issues_count}",
            )
        )

    open_critical = [r for r in response_rows if _row_get(r, "severity").lower() == "critical" and _row_get(r, "复核").lower() != "pass"]
    results.append(
        CheckResult(f"{gid}-5", "无 open 状态的 critical", not open_critical, f"未清零: {[_row_id(r, r'^CDX-') for r in open_critical]}" if open_critical else "")
    )

    unanswered_major = [r for r in response_rows if _row_get(r, "severity").lower() == "major" and not _row_get(r, "处置")]
    results.append(
        CheckResult(f"{gid}-6", "major 全部有回应", not unanswered_major, f"未回应: {[_row_id(r, r'^CDX-') for r in unanswered_major]}" if unanswered_major else "")
    )

    return results


# ---------------------------------------------------------------------------
# G-CA：code_audit
# ---------------------------------------------------------------------------

# 空壳判定必须单独成行、格式 `判定: not_found`（quant-auditor.md mode=code 硬约束 7）；
# 行锚定结构化匹配，不再对全文做 `not[_ ]found` 子串 grep——否定句式（如「无 not_found
# 判定」「未见 not_found」）不会因为文中出现该字面量就被误判为空壳。
_NOT_FOUND_VERDICT_RE = re.compile(r"^.*判定[:：]\s*not_?found", re.MULTILINE | re.IGNORECASE)


def check_code_audit(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-CA"
    results: list[CheckResult] = []
    state = _safe_load_state(root, report_id) or {}
    difficulty = state.get("difficulty") or "medium"
    tags = set(state.get("tags") or [])

    audit_dir = root / "workspace" / report_id / "audit"
    code_audit_codex = audit_dir / "code_audit_codex.md"
    responses_path = audit_dir / "audit_responses.md"

    must_exist = {"code_audit_codex.md": code_audit_codex, "audit_responses.md": responses_path}
    missing = [name for name, p in must_exist.items() if not p.is_file()]
    results.append(
        CheckResult(f"{gid}-1", "code_audit_codex.md / audit_responses.md 存在（codex 全难度必跑）", not missing, f"缺失: {missing}" if missing else "")
    )

    impl_audit_files = sorted(audit_dir.glob("impl_audit_m*.md"))
    requires_impl_audit = (difficulty != "easy") or ("ml" in tags)
    if requires_impl_audit:
        results.append(CheckResult(f"{gid}-2", "impl_audit_m{X}.md 存在（按难度/ml 标签要求）", len(impl_audit_files) > 0))
    else:
        results.append(CheckResult(f"{gid}-2", "impl_audit_m{X}.md（easy 且非 ml，可并入 verify）", True, "该难度下非本 stage 必需"))

    not_found_hits = [p.name for p in impl_audit_files if _NOT_FOUND_VERDICT_RE.search(p.read_text(encoding="utf-8"))]
    results.append(
        CheckResult(
            f"{gid}-3",
            "impl_audit 文件中无结构化空壳判定「判定: not_found」（行锚定，非全文子串匹配）",
            not not_found_hits,
            f"命中: {not_found_hits}" if not_found_hits else "",
        )
    )

    issues_count, _verdict = _parse_codex_output(code_audit_codex)
    response_rows = _parse_audit_responses(responses_path, "CDX-C-")
    if issues_count is None:
        results.append(CheckResult(f"{gid}-4", "audit_responses.md 回应行数 == code 审查 issues 数", False, "code_audit_codex.md 无法解析"))
    else:
        results.append(
            CheckResult(
                f"{gid}-4",
                "audit_responses.md 回应行数 == code 审查 issues 数",
                len(response_rows) == issues_count,
                f"回应={len(response_rows)} issues={issues_count}",
            )
        )

    open_critical = [r for r in response_rows if _row_get(r, "severity").lower() == "critical" and _row_get(r, "复核").lower() != "pass"]
    results.append(CheckResult(f"{gid}-5", "无 open critical（未来函数/硬编码/方向反）", not open_critical))

    unanswered_major = [r for r in response_rows if _row_get(r, "severity").lower() == "major" and not _row_get(r, "处置")]
    results.append(CheckResult(f"{gid}-6", "无 open major 未回应", not unanswered_major))

    return results


# ---------------------------------------------------------------------------
# G-RA：result_audit
# ---------------------------------------------------------------------------


def check_result_audit(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-RA"
    results: list[CheckResult] = []
    state = _safe_load_state(root, report_id) or {}
    difficulty = state.get("difficulty") or "medium"
    report_type = state.get("type")
    standards = load_standards(root)

    audit_dir = root / "workspace" / report_id / "audit"
    result_audit_codex = audit_dir / "result_audit_codex.md"
    responses_path = audit_dir / "audit_responses.md"

    must_exist = {"result_audit_codex.md": result_audit_codex, "audit_responses.md": responses_path}
    missing = [name for name, p in must_exist.items() if not p.is_file()]
    results.append(
        CheckResult(f"{gid}-1", "result_audit_codex.md / audit_responses.md 存在（codex 全难度必跑）", not missing, f"缺失: {missing}" if missing else "")
    )

    response_rows = _parse_audit_responses(responses_path, "CDX-R-")
    open_critical = [r for r in response_rows if _row_get(r, "severity").lower() == "critical" and _row_get(r, "复核").lower() != "pass"]
    results.append(CheckResult(f"{gid}-2", "无 open critical（数字不符/漏对比项/归因造假）", not open_critical))

    comparison_path = root / "output" / report_id / "results" / "comparison.json"
    attribution_issue: list[str] = []
    if comparison_path.is_file():
        try:
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            for m in comparison.get("metrics", []):
                # 不信任文件自述的 pass 字段（K8：声称已通过实际未改）：与 G-VF-3 同一套
                # standards.json 容差重算圈定"超差"集合，只有重算结果不为 True 才要求
                # 归因，防止 comparison.json 谎称 pass=true 却无 attribution_status 蒙混过关。
                spec = _tolerance_spec_for_metric(standards, report_type, m)
                r = recalc_metric(m, spec)
                if r.passed is not True and m.get("attribution_status") not in ("accepted", "assumption_linked"):
                    attribution_issue.append(m.get("key", "?"))
        except json.JSONDecodeError:
            attribution_issue.append("<comparison.json 解析失败>")
    results.append(
        CheckResult(
            f"{gid}-3",
            "超差指标（按 standards.json 重算圈定，不信任文件自述 pass）归因状态 ∈ {accepted, assumption_linked}",
            not attribution_issue,
            f"未归因: {attribution_issue}" if attribution_issue else "",
        )
    )

    evidence_manifest = root / "workspace" / report_id / "audit" / "evidence_manifest.md"
    if difficulty == "hard":
        has_record = evidence_manifest.is_file() and "扰动测试" in evidence_manifest.read_text(encoding="utf-8")
        results.append(CheckResult(f"{gid}-4", "扰动测试有记录（hard 必做一次）", has_record))
    else:
        results.append(CheckResult(f"{gid}-4", "扰动测试有记录（仅触发时要求，本难度未强制）", True, "非 hard 难度，仅 K2 触发时要求"))

    # 三审查点（G-SA/G-CA/G-RA）回应协议统一：audit_responses.md 中该审查点的回应
    # 行数必须与 codex 输出 verdict json（或降级的 markdown 表格）的 issues 数一致，
    # 防止 codex 提了 N 条意见、回应表只写了 M < N 条却蒙混过关。
    issues_count, _verdict = _parse_codex_output(result_audit_codex)
    if issues_count is None:
        results.append(CheckResult(f"{gid}-5", "audit_responses.md 回应行数 == result 审查 issues 数", False, "result_audit_codex.md 无法解析"))
    else:
        results.append(
            CheckResult(
                f"{gid}-5",
                "audit_responses.md 回应行数 == result 审查 issues 数",
                len(response_rows) == issues_count,
                f"回应={len(response_rows)} issues={issues_count}",
            )
        )

    return results


# ---------------------------------------------------------------------------
# G-IM：implement
# ---------------------------------------------------------------------------


def check_implement(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-IM"
    results: list[CheckResult] = []
    src = root / "src" / report_id

    results.append(CheckResult(f"{gid}-1", "src/{id}/strategy.py 存在", (src / "strategy.py").is_file()))
    results.append(CheckResult(f"{gid}-2", "src/{id}/main.py 存在", (src / "main.py").is_file()))

    if src.is_dir():
        proc = subprocess.run([sys.executable, "-m", "compileall", "-q", str(src)], capture_output=True)
        compile_ok = proc.returncode == 0
        detail = "" if compile_ok else (proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace"))[:300]
    else:
        compile_ok = False
        detail = "src 目录不存在"
    results.append(CheckResult(f"{gid}-3", "python -m compileall src/{id} 通过", compile_ok, detail))

    state = _safe_load_state(root, report_id) or {}
    milestones = state.get("milestones") or []
    not_done = [m.get("id") for m in milestones if m.get("implement") != "done"]
    results.append(
        CheckResult(f"{gid}-4", "state.milestones 全部 implement=done", not not_done, f"未完成: {not_done}" if not_done else "")
    )

    matrix_path = root / "workspace" / report_id / "spec" / "coverage_matrix.md"
    matrix_rows = load_matrix_rows(matrix_path)
    missing_impl_loc = [
        _row_get(r, "要素ID") for r in matrix_rows if _row_get(r, "状态") not in ("skipped", "infeasible") and not _row_get(r, "实现位置")
    ]
    results.append(
        CheckResult(
            f"{gid}-5",
            "矩阵「实现位置」列对非 excluded（skipped/infeasible）行非空",
            not missing_impl_loc,
            f"缺失: {missing_impl_loc}" if missing_impl_loc else "",
        )
    )

    return results


# ---------------------------------------------------------------------------
# G-VF：verify（含 standards.json 容差重算，核心逻辑）
# ---------------------------------------------------------------------------


def _apply_user_tolerance(standards: dict, root: Path) -> dict:
    """用户全局偏差容忍（.reproduce.json 的 default_max_rel_dev）覆盖相对偏差上限。

    语义：用户在 setup 配置的「能接受的与原报告的偏差」是对所有**相对偏差判定**
    的统一要求——替换 standards 中每个含 max_rel_dev 键的容差 spec 的该键；
    abs_eps / require_same_sign / order_of_magnitude_only / direction_only /
    定性判定等其他语义不受影响。null / 缺失 / 非法值 / 无配置文件 → 原样返回
    （默认走 standards.json 分类型精细容差）。
    """
    cfg = root / ".reproduce.json"
    if not cfg.is_file():
        return standards
    try:
        value = json.loads(cfg.read_text(encoding="utf-8")).get("default_max_rel_dev")
    except (json.JSONDecodeError, OSError):
        return standards
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not (0 < value <= 1):
        return standards
    out = json.loads(json.dumps(standards))  # 深拷贝，不污染缓存/复用方

    def _walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("max_rel_dev"), (int, float)):
                node["max_rel_dev"] = value
            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(out)
    return out


def load_standards(root: Path) -> dict:
    path = root / "templates" / "standards.json"
    if not path.is_file():
        return {}
    try:
        standards = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return _apply_user_tolerance(standards, root)


def _tolerance_spec_for_metric(standards: dict, report_type: Optional[str], metric: dict) -> dict:
    type_std = standards.get(report_type) or {}
    if report_type == "ml" and metric.get("layer"):
        layers = type_std.get("layers") or {}
        return layers.get(metric["layer"]) or {}
    metrics_std = type_std.get("metrics") or {}
    key = metric.get("tolerance_key") or metric.get("key")
    if key in metrics_std:
        return metrics_std[key]
    return metrics_std.get("default") or {}


@dataclass
class MetricRecalc:
    key: str
    rel_dev: Optional[float]
    passed: Optional[bool]
    reason: str


def recalc_metric(metric: dict, spec: dict) -> MetricRecalc:
    """按 standards.json 的容差语义重算单条 metric 的 rel_dev 与 pass。

    容差语义（brief 逐字）：
        max_rel_dev              相对偏差上限
        require_same_sign        同号要求，违反直接判负（不论幅度）
        abs_eps                  近零改绝对偏差：|report_value| < abs_eps 时改判绝对偏差 <= abs_eps
        order_of_magnitude_only  数量级一致（比值落在 [0.1, 10] 视为同量级）
        direction_only           （ml model 层）仅方向性判定，不算数值偏差
        未收录 -> default        由调用方 _tolerance_spec_for_metric 兜底

    优先级（require_same_sign 与 abs_eps 同时出现时）：近零判定优先于同号否决——
    |report_value| < abs_eps 时符号是噪声，直接改用绝对偏差判定，不再执行同号否决；
    只有 |report_value| >= abs_eps（不满足近零条件，含未设置 abs_eps 的情形）才落回
    同号否决逻辑。
    """
    key = metric.get("key", "?")
    try:
        report_value = float(metric.get("report_value"))
        reproduced_value = float(metric.get("reproduced_value"))
    except (TypeError, ValueError):
        return MetricRecalc(key, None, False, "report_value/reproduced_value 缺失或非数值")

    require_same_sign = bool(spec.get("require_same_sign"))
    abs_eps = spec.get("abs_eps")
    max_rel_dev = spec.get("max_rel_dev")
    oom_only = bool(spec.get("order_of_magnitude_only"))
    direction_only = bool(spec.get("direction_only"))

    sign_ok = (report_value == 0 and reproduced_value == 0) or (report_value * reproduced_value >= 0)

    if direction_only:
        return MetricRecalc(key, None, sign_ok, "direction_only：仅校验同号/方向")

    near_zero = abs_eps is not None and abs(report_value) < abs_eps
    if near_zero:
        abs_dev = abs(reproduced_value - report_value)
        return MetricRecalc(
            key,
            abs_dev,
            abs_dev <= abs_eps,
            f"研报值近零（|{report_value}|<{abs_eps}），改用绝对偏差判定，不执行同号否决",
        )

    if require_same_sign and not sign_ok:
        rel_dev = abs(reproduced_value - report_value) / abs(report_value) if report_value != 0 else None
        return MetricRecalc(key, rel_dev, False, "同号要求违反（符号不一致），不论幅度直接判负")

    if oom_only:
        if report_value == 0:
            passed = reproduced_value == 0
        else:
            ratio = abs(reproduced_value / report_value)
            passed = 0.1 <= ratio <= 10
        rel_dev = abs(reproduced_value - report_value) / abs(report_value) if report_value != 0 else None
        return MetricRecalc(key, rel_dev, passed, "数量级一致性判定（比值落在 [0.1,10]）")

    if report_value == 0:
        return MetricRecalc(key, None, reproduced_value == 0, "研报值为 0 且未声明 abs_eps，要求复现值同为 0")

    rel_dev = abs(reproduced_value - report_value) / abs(report_value)
    if max_rel_dev is None:
        return MetricRecalc(key, rel_dev, None, "standards.json 未提供 max_rel_dev，无法判定")
    passed = rel_dev <= max_rel_dev
    return MetricRecalc(key, rel_dev, passed, f"相对偏差判定 max_rel_dev={max_rel_dev}")


def _check_freshness(src: Path, output_results: Path) -> tuple[bool, str]:
    if not src.is_dir() or not output_results.is_dir():
        return False, "src 或 output/{id}/results 目录不存在"
    # 两侧都排除 __pycache__/*.pyc：它们是派生物，不是源码也不是产物。
    # src 侧计入会使「先重放 G-IM（compileall）再查 G-VF」的合法顺序被误判为产物过期；
    # out 侧计入会让 results 内脚本（如 build_final_artifacts.py）的旧字节码缓存把
    # 「产物最早时间」拉早，同样造成误判。
    def _real_files(d: Path) -> list[Path]:
        return [
            p for p in d.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        ]

    src_files = _real_files(src)
    out_files = _real_files(output_results)
    if not src_files or not out_files:
        return False, "src 或 results 下没有文件可比较"
    latest_src_mtime = max(p.stat().st_mtime for p in src_files)
    earliest_out_mtime = min(p.stat().st_mtime for p in out_files)
    ok = earliest_out_mtime > latest_src_mtime
    return ok, f"src最新mtime={latest_src_mtime:.0f} results最早mtime={earliest_out_mtime:.0f}"


def check_verify(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-VF"
    results: list[CheckResult] = []
    state = _safe_load_state(root, report_id) or {}
    report_type = state.get("type")
    output_results = root / "output" / report_id / "results"

    run_log = output_results / "run_log.md"
    run_log_ok = run_log.is_file() and "exit=0" in run_log.read_text(encoding="utf-8")
    results.append(CheckResult(f"{gid}-1", "run_log.md 存在且含 exit=0 字样", run_log_ok))

    comparison_path = output_results / "comparison.json"
    comparison: Optional[dict] = None
    if comparison_path.is_file():
        try:
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            comparison = None
    results.append(CheckResult(f"{gid}-2", "comparison.json 存在且可解析", comparison is not None))

    standards = load_standards(root)
    if comparison is not None:
        fails: list[str] = []
        metrics = comparison.get("metrics", [])
        for m in metrics:
            spec = _tolerance_spec_for_metric(standards, report_type, m)
            r = recalc_metric(m, spec)
            if r.passed is not True:
                fails.append(f"{r.key}[{r.reason}]")
        qualitative = comparison.get("qualitative", [])
        for q in qualitative:
            if q.get("expect") != q.get("observed"):
                fails.append(f"{q.get('key', '?')}[定性指标 expect!=observed]")
        recalced_ok = not fails
        detail = f"未通过: {fails}" if fails else f"{len(metrics)} 项数值指标 + {len(qualitative)} 项定性指标均通过重算"
    else:
        recalced_ok = False
        detail = "comparison.json 不可用，无法重算"
    results.append(
        CheckResult(f"{gid}-3", "按 standards.json 重算每条 metric 的 rel_dev 与 pass（不信任文件内 pass 字段）", recalced_ok, detail)
    )

    type_std = standards.get(report_type) or {}
    required_charts = type_std.get("required_charts") or []
    chart_problems = []
    for name in required_charts:
        p = output_results / name
        if not p.is_file():
            chart_problems.append(f"{name}:缺失")
        elif p.stat().st_size <= 15 * 1024:
            chart_problems.append(f"{name}:<=15KB")
    chart_detail = f"{chart_problems}" if chart_problems else (f"共 {len(required_charts)} 张，全部存在且 >15KB" if required_charts else "该类型未在 standards.json 声明必需图表")
    results.append(CheckResult(f"{gid}-4", "standards.json 要求的图表全存在且 >15KB", not chart_problems, chart_detail))

    required_excels = type_std.get("required_excels") or []
    excel_problems = []
    for name in required_excels:
        p = output_results / name
        if not p.is_file():
            excel_problems.append(f"{name}:缺失")
        elif p.stat().st_size == 0:
            excel_problems.append(f"{name}:0字节")
    results.append(CheckResult(f"{gid}-5", "standards.json 要求的 Excel 全存在且非零字节", not excel_problems, f"{excel_problems}" if excel_problems else ""))

    src = root / "src" / report_id
    freshness_ok, freshness_detail = _check_freshness(src, output_results)
    results.append(CheckResult(f"{gid}-6", "产物 mtime 晚于 src/ 最新 mtime（E2 新鲜度）", freshness_ok, freshness_detail))

    matrix_path = root / "workspace" / report_id / "spec" / "coverage_matrix.md"
    matrix_rows = load_matrix_rows(matrix_path)
    # 与 G-IM-5 一致：skipped/infeasible 行本就不需要「验证结果」（核对/实现均已豁免），
    # 否则 core 行一旦被标 skipped/infeasible 会因验证结果列必然空白而永久卡在本门禁。
    missing_verify = [
        _row_get(r, "要素ID")
        for r in matrix_rows
        if _row_get(r, "状态") not in ("skipped", "infeasible")
        and _row_get(r, "优先级") in ("core", "support")
        and not _row_get(r, "验证结果")
    ]
    results.append(
        CheckResult(
            f"{gid}-7",
            "矩阵验证结果列对非 skipped/infeasible 的 core/support 行无空",
            not missing_verify,
            f"缺失: {missing_verify}" if missing_verify else "",
        )
    )

    return results


# ---------------------------------------------------------------------------
# G-IT：iterate
# ---------------------------------------------------------------------------

# stop_partial/blocked 轮：diagnoser 判定不再需要 coder 出手（stop_partial 是「归因
# 接受残差」、blocked 是「缺外部输入」），该轮天然不会产出 changes.md——若仍要求
# changes.md，这类轮次会被 G-IT-1 永久判 FAIL，构成死锁。按「结论: stop_partial」
# 一类行豁免 changes.md（diagnosis.md 与 comparison.json 仍必须齐）。
# 枚举值必须紧跟冒号（允许尾随附注）：防止「结论: continue（已排除 stop_partial 假设）」
# 这类同行提及被否决枚举值的写法被误判豁免。
_ITER_EXEMPT_CONCLUSION_RE = re.compile(r"结论[:：]\s*[*_`]*(stop_partial|blocked)\b")


def check_iterate(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-IT"
    results: list[CheckResult] = []
    state = _safe_load_state(root, report_id) or {}
    iteration = state.get("iteration") or {}
    current = iteration.get("current") or 0
    max_iter = iteration.get("max")

    iterations_dir = root / "workspace" / report_id / "iterations"
    missing_sets = []
    missing_excluded_hint = []
    for n in range(1, current + 1):
        iter_dir = iterations_dir / f"iter_{n:02d}"
        diagnosis_path = iter_dir / "diagnosis.md"
        diagnosis_text = diagnosis_path.read_text(encoding="utf-8") if diagnosis_path.is_file() else ""
        exempt_changes = bool(_ITER_EXEMPT_CONCLUSION_RE.search(diagnosis_text))
        required = ["diagnosis.md", "comparison.json"] if exempt_changes else ["diagnosis.md", "changes.md", "comparison.json"]
        missing = [f for f in required if not (iter_dir / f).is_file()]
        if missing:
            missing_sets.append(f"iter_{n:02d}缺{missing}")
        if n >= 2:
            if not (diagnosis_path.is_file() and "已排除假设" in diagnosis_text):
                missing_excluded_hint.append(f"iter_{n:02d}")

    results.append(
        CheckResult(
            f"{gid}-1",
            "每轮 iter_NN/ 三件套齐（diagnosis.md/changes.md/comparison.json；结论 stop_partial/blocked 豁免 changes.md）",
            not missing_sets,
            "; ".join(missing_sets),
        )
    )

    max_ok = max_iter is None or current <= max_iter
    results.append(CheckResult(f"{gid}-2", "iteration.current <= max_iter", max_ok, f"current={current} max={max_iter}"))

    results.append(
        CheckResult(
            f"{gid}-3",
            "N>=2 时 diagnosis.md 含「已排除假设」字样",
            not missing_excluded_hint,
            f"缺失: {missing_excluded_hint}" if missing_excluded_hint else "",
        )
    )

    return results


# ---------------------------------------------------------------------------
# G-FN：report
# ---------------------------------------------------------------------------


def check_report(root: Path, report_id: str) -> list[CheckResult]:
    gid = "G-FN"
    results: list[CheckResult] = []
    report_path = root / "workspace" / report_id / "final_report.md"

    if not report_path.is_file():
        results.append(CheckResult(f"{gid}-1", "final_report.md 存在", False))
        return results
    results.append(CheckResult(f"{gid}-1", "final_report.md 存在", True))

    text = report_path.read_text(encoding="utf-8")
    h2_lines = re.findall(r"^##\s+(.*)$", text, re.MULTILINE)
    missing_sections = [s for s in REQUIRED_REPORT_SECTIONS if not any(s in line for line in h2_lines)]
    results.append(
        CheckResult(
            f"{gid}-2",
            "必需 H2 章节齐（结论/指标对比/假设登记簿/迭代历史/审计回应/残余偏差/未复现清单/复跑指引）",
            not missing_sections,
            f"缺失: {missing_sections}" if missing_sections else "",
        )
    )

    matrix_path = root / "workspace" / report_id / "spec" / "coverage_matrix.md"
    matrix_rows = load_matrix_rows(matrix_path)
    pending_rows = [_row_get(r, "要素ID") for r in matrix_rows if _row_get(r, "状态") in ("pending", "in_progress")]
    results.append(CheckResult(f"{gid}-3", "coverage_matrix 无 pending/in_progress 行", not pending_rows, f"仍未终态: {pending_rows}" if pending_rows else ""))

    assumptions_path = root / "workspace" / report_id / "assumptions.md"
    if assumptions_path.is_file():
        has_placeholder = "[verify 后填]" in assumptions_path.read_text(encoding="utf-8")
        results.append(CheckResult(f"{gid}-4", "假设登记簿无未决议条目（无遗留占位符）", not has_placeholder))
    else:
        results.append(CheckResult(f"{gid}-4", "假设登记簿无未决议条目（无遗留占位符）", False, "assumptions.md 不存在"))

    responses_path = root / "workspace" / report_id / "audit" / "audit_responses.md"
    if responses_path.is_file():
        rows = parse_markdown_table_rows(responses_path.read_text(encoding="utf-8"))
        rejected_ids = [_row_id(r, r"^CDX-[A-Z]-") for r in rows if _row_get(r, "处置") == "rejected"]
        rejected_ids = [rid for rid in rejected_ids if rid]
        missing_in_report = [rid for rid in rejected_ids if rid not in text]
        results.append(CheckResult(f"{gid}-5", "所有 rejected 意见出现在报告", not missing_in_report, f"缺失: {missing_in_report}" if missing_in_report else ""))
    else:
        results.append(CheckResult(f"{gid}-5", "所有 rejected 意见出现在报告", True, "audit_responses.md 不存在，视为无 rejected 项"))

    state = _safe_load_state(root, report_id) or {}
    coverage_stats = state.get("coverage_stats") or {}
    total = coverage_stats.get("total")
    coverage_stats_ok = isinstance(total, (int, float)) and not isinstance(total, bool) and total > 0
    results.append(
        CheckResult(
            f"{gid}-6",
            "state.json coverage_stats 已写入且 total 字段 > 0（可信度评级依赖它）",
            coverage_stats_ok,
            f"coverage_stats={coverage_stats}",
        )
    )

    return results


# ---------------------------------------------------------------------------
# 调度 / --assert-done / CLI
# ---------------------------------------------------------------------------

STAGE_CHECK_FUNCS = {
    "init": check_init,
    "extract": check_extract,
    "plan": check_plan,
    "spec_audit": check_spec_audit,
    "implement": check_implement,
    "code_audit": check_code_audit,
    "verify": check_verify,
    "iterate": check_iterate,
    "result_audit": check_result_audit,
    "report": check_report,
}


def run_gate(root: Path, report_id: str, stage: str) -> list[CheckResult]:
    if stage == "review":
        return [CheckResult("REVIEW", "review 为人工审核阶段，无机器门禁", True)]
    func = STAGE_CHECK_FUNCS.get(stage)
    if func is None:
        raise ValueError(f"未知 stage: {stage}，应属于 {st.STAGE_ORDER}")
    return func(root, report_id)


def check_assert_done(root: Path, report_id: str, stage: str) -> CheckResult:
    desc = f"{stage} 状态为 done 或（裁剪矩阵允许时）skipped"
    state = _safe_load_state(root, report_id)
    if state is None:
        return CheckResult("ASSERT-DONE", desc, False, "state.json 不存在或不可解析")
    entry = (state.get("stages") or {}).get(stage)
    if entry is None:
        return CheckResult("ASSERT-DONE", desc, False, f"state.stages 中无 {stage}")
    status = entry.get("status")
    if status == "done":
        return CheckResult("ASSERT-DONE", desc, True, "done")
    if status == "skipped" and stage in SKIPPABLE_STAGES:
        return CheckResult("ASSERT-DONE", desc, True, f"skipped（{stage} 属于裁剪矩阵允许跳过的 stage）")
    if status == "skipped":
        return CheckResult("ASSERT-DONE", desc, False, f"{stage} 属于必跑 stage，不允许 skipped")
    return CheckResult("ASSERT-DONE", desc, False, f"实际状态={status}")


def format_check(c: CheckResult) -> str:
    tag = "PASS" if c.passed else "FAIL"
    line = f"[{tag}] {c.id} {c.desc}"
    if c.detail:
        line += f"（{c.detail}）"
    return line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="门禁机器判定（研报复现系统 v2）")
    parser.add_argument("report_id")
    parser.add_argument("--stage", required=True, choices=st.STAGE_ORDER)
    parser.add_argument("--assert-done", action="store_true", dest="assert_done")
    parser.add_argument("--record", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = st.default_root()

    if args.assert_done:
        check = check_assert_done(root, args.report_id, args.stage)
        print(format_check(check))
        verdict = "PASS" if check.passed else "FAIL"
        print(f"VERDICT: {verdict}")
        if args.record:
            st.record_gate(root, args.report_id, args.stage, verdict, [{"id": check.id, "desc": check.desc, "result": verdict}])
        return 0 if check.passed else 1

    try:
        checks = run_gate(root, args.report_id, args.stage)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    for c in checks:
        print(format_check(c))
    verdict = "PASS" if all(c.passed for c in checks) else "FAIL"
    print(f"VERDICT: {verdict}")

    if args.record:
        checks_payload = [{"id": c.id, "desc": c.desc, "result": "PASS" if c.passed else "FAIL"} for c in checks]
        st.record_gate(root, args.report_id, args.stage, verdict, checks_payload)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
