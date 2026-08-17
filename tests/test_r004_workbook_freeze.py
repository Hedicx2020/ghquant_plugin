from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r004_all_a_style_box.main import (
    WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES,
    _compact_workbook_payload_for_node,
    _inspect_xlsx_freeze_panes,
    _run_workbook_builder,
    _validate_workbook_manifest,
)
from src.r004_all_a_style_box.reporting import WORKBOOK_SHEET_PROJECTION_COLUMNS


WORKBOOK_LAYOUT = (
    ("backtest_summary.xlsx", 10),
    ("factor_analysis.xlsx", 10),
    ("style_box_returns.xlsx", 9),
    ("portfolio_holdings.xlsx", 8),
    ("trading_audit.xlsx", 9),
)


def _payload(*, months: int, complete_layout: bool) -> dict[str, object]:
    rows = [
        [f"{2023 + (month + 3) // 12}-{(month + 3) % 12 + 1:02d}", month / 100]
        for month in range(months)
    ]
    workbooks = []
    layout = WORKBOOK_LAYOUT if complete_layout else tuple(
        (filename, 1) for filename, _ in WORKBOOK_LAYOUT
    )
    for filename, sheet_count_without_cover in layout:
        workbooks.append(
            {
                "filename": filename,
                "title": "冻结窗格有界fixture",
                "subtitle": "不含正式回测结果",
                "sheets": [
                    {
                        "name": f"Sheet{index + 1}",
                        "columns": ["date", "net_return"],
                        "rows": rows,
                    }
                    for index in range(sheet_count_without_cover)
                ],
            }
        )
    return {
        "report_id": "r004_all_a_style_box",
        "reproduction_mode": "experimental_fixture",
        "verification_status": "not_formal_verification",
        "workbooks": workbooks,
    }


def _remove_first_pane(source: Path, destination: Path) -> None:
    extract_dir = destination.parent / "tampered_extract"
    with zipfile.ZipFile(source) as archive:
        archive.extractall(extract_dir)
    sheet_path = extract_dir / "xl/worksheets/sheet1.xml"
    xml = sheet_path.read_text(encoding="utf-8")
    start = xml.index("<x:pane ")
    end = xml.index("/>", start) + 2
    sheet_path.write_text(xml[:start] + xml[end:], encoding="utf-8")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extract_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(extract_dir).as_posix())


def test_small_fixture_exports_real_a2_and_manifest_is_actual(tmp_path: Path) -> None:
    output_dir = tmp_path / "small"
    output_dir.mkdir()
    manifest_path = _run_workbook_builder(_payload(months=2, complete_layout=False), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workbook = manifest["workbooks"][0]
    assert manifest["qa_policy"]["first_row_frozen_in_export"] is True
    assert workbook["frozen_first_row_count"] == 2
    assert all(record["top_left_cell"] == "A2" for record in workbook["freeze_panes"])
    assert len(_inspect_xlsx_freeze_panes(output_dir / workbook["filename"])) == 2


def test_node_qa_rejects_missing_exported_pane_fault_injection(tmp_path: Path) -> None:
    output_dir = tmp_path / "node_fault"
    output_dir.mkdir()
    payload = _payload(months=2, complete_layout=False)
    payload["qa_fault_injection"] = {
        "remove_freeze_pane": {"filename": "backtest_summary.xlsx", "sheet": "Cover"}
    }
    with pytest.raises(RuntimeError, match="pane数量必须为1"):
        _run_workbook_builder(payload, output_dir)


def test_large_synthetic_payload_is_worker_bounded_and_exports_51_qa(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "complete"
    output_dir.mkdir()
    months = 1_200
    manifest_path = _run_workbook_builder(
        _payload(months=months, complete_layout=True), output_dir
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["workbooks"]) == 5
    isolation = manifest["worker_process_isolation"]
    assert isolation["enabled"] is True
    assert isolation["worker_count"] == 5
    assert isolation["one_workbook_per_worker"] is True
    assert isolation["expected_total_sheet_count"] == 51
    assert isolation["total_user_row_count"] == sum(
        sheet_count * months for _, sheet_count in WORKBOOK_LAYOUT
    )
    assert 0 < isolation["peak_worker_max_rss_bytes"] <= WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES
    assert all(
        workbook["formula_scan"]["scanned_row_count"] > 0
        and workbook["formula_scan"]["scanned_cell_count"] > 0
        and workbook["ooxml_scan"]["formula_scan_complete"] is True
        for workbook in manifest["workbooks"]
    )
    records = [
        record
        for workbook in manifest["workbooks"]
        for record in _inspect_xlsx_freeze_panes(output_dir / workbook["filename"])
    ]
    assert len(records) == 51
    assert all(record["top_left_cell"] == "A2" for record in records)
    assert all(record["frozen_first_row"] is True for record in records)


def test_node_payload_compaction_keeps_top_n_rows_and_full_detail_references() -> None:
    repeated = [
        "detail_full_row_count",
        "detail_displayed_row_count",
        "detail_parquet_path",
        "detail_view_rule",
    ]
    trades_columns = [
        *WORKBOOK_SHEET_PROJECTION_COLUMNS["TradesTop200"],
        "sample_phase",
        "target_weight",
        *repeated,
    ]
    unfilled_columns = [
        *WORKBOOK_SHEET_PROJECTION_COLUMNS["UnfilledTop200"],
        "sample_phase",
        "view_rank_within_group",
        *repeated,
    ]
    workbook = {
        "filename": "trading_audit.xlsx",
        "title": "fixture",
        "subtitle": "fixture",
        "sheets": [
            {
                "name": "TradesTop200",
                "columns": trades_columns,
                "rows": [[f"trade_{index}" for index in range(len(trades_columns))]],
            },
            {
                "name": "UnfilledTop200",
                "columns": unfilled_columns,
                "rows": [
                    [f"unfilled_{index}" for index in range(len(unfilled_columns))]
                    for _ in range(2)
                ],
            },
            {
                "name": "DetailManifest",
                "columns": ["table_name", "file", "full_row_count", "sha256"],
                "rows": [["trades", "detail_tables/trades.parquet", 39_600, "a" * 64]],
            },
            {
                "name": "Sources",
                "columns": ["source", "row_count", "sha256"],
                "rows": [["detail_tables/trades.parquet", 39_600, "a" * 64]],
            },
        ],
    }
    compact, removed_cell_count = _compact_workbook_payload_for_node(workbook)
    sheets = {sheet["name"]: sheet for sheet in compact["sheets"]}
    assert sheets["TradesTop200"]["columns"] == list(
        WORKBOOK_SHEET_PROJECTION_COLUMNS["TradesTop200"]
    )
    assert sheets["UnfilledTop200"]["columns"] == list(
        WORKBOOK_SHEET_PROJECTION_COLUMNS["UnfilledTop200"]
    )
    assert len(sheets["TradesTop200"]["rows"]) == 1
    assert len(sheets["UnfilledTop200"]["rows"]) == 2
    assert sheets["DetailManifest"] == workbook["sheets"][2]
    assert sheets["Sources"] == workbook["sheets"][3]
    assert removed_cell_count > 0


def test_python_qa_rejects_missing_exported_pane(tmp_path: Path) -> None:
    output_dir = tmp_path / "source"
    output_dir.mkdir()
    manifest_path = _run_workbook_builder(_payload(months=2, complete_layout=False), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original = output_dir / "backtest_summary.xlsx"
    tampered = tmp_path / "tampered.xlsx"
    _remove_first_pane(original, tampered)
    broken = copy.deepcopy(manifest)
    broken["workbooks"][0]["path"] = str(tampered)
    with pytest.raises(RuntimeError, match="pane数量必须为1"):
        _validate_workbook_manifest(broken)


def test_python_qa_rejects_manifest_freeze_false_green(tmp_path: Path) -> None:
    output_dir = tmp_path / "source"
    output_dir.mkdir()
    manifest_path = _run_workbook_builder(_payload(months=2, complete_layout=False), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workbooks"][0]["freeze_panes"][0]["top_left_cell"] = "A999"
    with pytest.raises(RuntimeError, match="冻结manifest与实际OOXML不一致"):
        _validate_workbook_manifest(manifest)
