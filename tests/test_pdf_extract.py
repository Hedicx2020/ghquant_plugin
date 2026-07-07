"""tools/pdf_extract.py 的测试：对仓库内真实存在的 reports/test.pdf 实跑。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import pdf_extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_PDF = REPO_ROOT / "reports" / "test.pdf"

PAGE_MARK_RE = re.compile(r"^===== PAGE \d+ =====$", re.MULTILINE)


def test_test_pdf_exists() -> None:
    """先决条件：reports/test.pdf 必须真实存在，否则后续断言无意义。"""
    assert TEST_PDF.exists(), f"缺少测试用 PDF：{TEST_PDF}"


def test_run_extract_produces_nonempty_outputs(tmp_path: Path) -> None:
    out_dir = tmp_path / "extract_out"
    result = pdf_extract.run_extract(TEST_PDF, out_dir)

    assert result.n_pages >= 1
    assert result.report_text_path.exists()
    assert result.tables_path.exists()

    report_text = result.report_text_path.read_text(encoding="utf-8")
    assert report_text.strip() != ""

    tables_text = result.tables_path.read_text(encoding="utf-8")
    assert tables_text.strip() != ""

    marks = PAGE_MARK_RE.findall(report_text)
    assert len(marks) >= 1
    # PAGE 标记数应与独立核算的 PDF 页数一致
    assert len(marks) == result.n_pages


def test_page_marks_sequential(tmp_path: Path) -> None:
    out_dir = tmp_path / "extract_seq"
    result = pdf_extract.run_extract(TEST_PDF, out_dir)
    report_text = result.report_text_path.read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^===== PAGE (\d+) =====$", report_text, re.MULTILINE)]
    assert numbers == list(range(1, result.n_pages + 1))


def test_tables_extracted_has_page_table_headings(tmp_path: Path) -> None:
    out_dir = tmp_path / "extract_tbl"
    result = pdf_extract.run_extract(TEST_PDF, out_dir)
    tables_text = result.tables_path.read_text(encoding="utf-8")
    if result.table_count > 0:
        assert re.search(r"^## 第 \d+ 页 · 表 \d+$", tables_text, re.MULTILINE)
    else:
        assert "未检测到表格" in tables_text


def test_engine_field_is_reported(tmp_path: Path) -> None:
    out_dir = tmp_path / "extract_engine"
    result = pdf_extract.run_extract(TEST_PDF, out_dir)
    assert result.engine in {"pdftotext(-layout)", "pypdf(降级)"}


def test_run_extract_falls_back_to_pypdf_when_pdftotext_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 shutil.which 探测不到 pdftotext，走 pypdf 降级分支；PAGE 标记数须与
    pdftotext 路径一致（22）且文本非空——降级不应改变分页数或产出空文本。"""
    monkeypatch.setattr(pdf_extract.shutil, "which", lambda *_a, **_kw: None)

    out_dir = tmp_path / "extract_fallback"
    result = pdf_extract.run_extract(TEST_PDF, out_dir)

    assert result.engine == "pypdf(降级)"
    report_text = result.report_text_path.read_text(encoding="utf-8")
    assert report_text.strip() != ""
    marks = PAGE_MARK_RE.findall(report_text)
    assert len(marks) == 22
    assert len(marks) == result.n_pages


def test_missing_pdf_raises_unparseable(tmp_path: Path) -> None:
    missing = tmp_path / "not_exist.pdf"
    out_dir = tmp_path / "out"
    try:
        pdf_extract.run_extract(missing, out_dir)
        assert False, "应抛出 PdfUnparseableError"
    except pdf_extract.PdfUnparseableError:
        pass


def test_cli_main_exit_code_and_stdout(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "cli_out"
    rc = pdf_extract.main([str(TEST_PDF), str(out_dir)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "总页数" in captured.out
    assert "文本提取引擎" in captured.out
    assert "表格数" in captured.out


def test_cli_main_nonzero_exit_on_bad_pdf(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a real pdf")
    out_dir = tmp_path / "cli_out_bad"
    rc = pdf_extract.main([str(bad_pdf), str(out_dir)])
    assert rc != 0
