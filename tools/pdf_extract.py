#!/usr/bin/env python3
"""PDF -> 文本/表格提取工具（研报复现系统 v2 · init 阶段）。

用法：
    uv run python tools/pdf_extract.py <pdf_path> <out_dir>

产出：
    <out_dir>/report_text.md       逐页文本，每页前插 "===== PAGE n =====" 标记行
    <out_dir>/tables_extracted.md  pdfplumber 逐页抽表，每表带「第 n 页 · 表 k」标题

文本提取优先用 poppler 的 `pdftotext -layout`（保留版式，便于 codex/grep 按列读表）；
探测不到 pdftotext 可执行文件时降级为 pypdf 逐页提取。

PDF 不可解析（无法打开 / 页数为 0）时非零退出。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PAGE_MARKER_TEMPLATE = "===== PAGE {n} ====="


@dataclass
class ExtractResult:
    """一次提取的汇总信息，供 stdout 报告与测试断言使用。"""

    n_pages: int
    engine: str
    table_count: int
    report_text_path: Path
    tables_path: Path


class PdfUnparseableError(RuntimeError):
    """PDF 完全无法解析（打不开 / 页数为 0）。"""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def count_pdf_pages(pdf_path: Path) -> int:
    """用 pypdf 独立核算 PDF 物理页数（作为分页数的权威参考）。"""
    import pypdf

    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - 需要把底层各类异常统一为不可解析
        raise PdfUnparseableError(f"pypdf 无法打开 PDF：{pdf_path}（{exc}）") from exc
    n = len(reader.pages)
    if n <= 0:
        raise PdfUnparseableError(f"PDF 页数为 0：{pdf_path}")
    return n


def _pad_or_trim(pages: list[str], n_pages: int) -> list[str]:
    """把提取出的分页列表对齐到权威页数 n_pages（缺页补空串，多页截断）。"""
    if len(pages) < n_pages:
        pages = pages + [""] * (n_pages - len(pages))
    elif len(pages) > n_pages:
        pages = pages[:n_pages]
    return pages


def extract_text_pdftotext(pdf_path: Path, n_pages: int) -> list[str] | None:
    """优先引擎：poppler `pdftotext -layout`。探测不到可执行文件返回 None（触发降级）。"""
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", errors="replace")
    # pdftotext 用 \x0c（form feed）分页，末尾常有一个空的尾随分片
    parts = text.split("\x0c")
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    if not parts:
        return None
    return _pad_or_trim(parts, n_pages)


def extract_text_pypdf(pdf_path: Path, n_pages: int) -> list[str]:
    """降级引擎：pypdf 逐页 extract_text()。"""
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - 单页解析失败不影响整体，留空
            text = ""
        pages.append(text)
    return _pad_or_trim(pages, n_pages)


def write_report_text(out_path: Path, pages: list[str]) -> None:
    lines: list[str] = []
    for i, page_text in enumerate(pages, start=1):
        lines.append(PAGE_MARKER_TEMPLATE.format(n=i))
        lines.append("")
        lines.append(page_text.rstrip("\n"))
        lines.append("")
    out_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def _escape_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", " ").replace("|", "\\|").strip()
    return text


def _table_to_markdown(table: list[list[object]]) -> str | None:
    """把 pdfplumber 的表格（行×列的原始 cell 值）转成 markdown 表格文本。"""
    rows = [row for row in table if row is not None]
    if not rows:
        return None
    width = max(len(row) for row in rows)
    if width == 0:
        return None
    header = [_escape_cell(c) for c in rows[0]] + [""] * (width - len(rows[0]))
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        cells = [_escape_cell(c) for c in row] + [""] * (width - len(row))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def extract_tables(pdf_path: Path, n_pages: int) -> tuple[str, int]:
    """pdfplumber 逐页抽表，返回 (markdown 全文, 表格总数)。无表页跳过。"""
    import pdfplumber

    sections: list[str] = [
        "# 表格提取（pdfplumber）",
        "",
        f"文档共 {n_pages} 页。",
        "",
    ]
    table_count = 0
    pages_with_tables = 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:  # noqa: BLE001 - 单页抽表失败不影响其余页
                tables = []
            if not tables:
                continue
            page_has_valid_table = False
            for k, table in enumerate(tables, start=1):
                md = _table_to_markdown(table)
                if md is None:
                    continue
                page_has_valid_table = True
                table_count += 1
                sections.append(f"## 第 {page_idx} 页 · 表 {k}")
                sections.append("")
                sections.append(md)
                sections.append("")
            if page_has_valid_table:
                pages_with_tables += 1
    if table_count == 0:
        sections.append("（未检测到表格）")
        sections.append("")
    else:
        sections.insert(3, f"其中 {pages_with_tables} 页含表格，共 {table_count} 个表格。")
        sections.insert(4, "")
    return "\n".join(sections).rstrip("\n") + "\n", table_count


def run_extract(pdf_path: Path, out_dir: Path) -> ExtractResult:
    if not pdf_path.exists():
        raise PdfUnparseableError(f"PDF 文件不存在：{pdf_path}")

    n_pages = count_pdf_pages(pdf_path)  # 打不开 / 0 页在此处抛出 PdfUnparseableError

    out_dir.mkdir(parents=True, exist_ok=True)

    pages = extract_text_pdftotext(pdf_path, n_pages)
    if pages is not None:
        engine = "pdftotext(-layout)"
    else:
        pages = extract_text_pypdf(pdf_path, n_pages)
        engine = "pypdf(降级)"

    report_text_path = out_dir / "report_text.md"
    write_report_text(report_text_path, pages)

    tables_md, table_count = extract_tables(pdf_path, n_pages)
    tables_path = out_dir / "tables_extracted.md"
    tables_path.write_text(tables_md, encoding="utf-8")

    return ExtractResult(
        n_pages=n_pages,
        engine=engine,
        table_count=table_count,
        report_text_path=report_text_path,
        tables_path=tables_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PDF -> report_text.md / tables_extracted.md（研报复现系统 v2）"
    )
    parser.add_argument("pdf_path", type=str, help="源 PDF 路径")
    parser.add_argument("out_dir", type=str, help="输出目录（不存在则自动创建）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pdf_path = Path(args.pdf_path).resolve()
    out_dir = Path(args.out_dir).resolve()

    try:
        result = run_extract(pdf_path, out_dir)
    except PdfUnparseableError as exc:
        print(f"PDF 不可解析: {exc}", file=sys.stderr)
        return 1

    print(f"PDF: {pdf_path}")
    print(f"总页数: {result.n_pages}")
    print(f"文本提取引擎: {result.engine}")
    print(f"表格数: {result.table_count}")
    print(f"输出: {result.report_text_path}, {result.tables_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
