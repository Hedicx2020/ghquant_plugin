"""r004 全链正式入口：m1 → m2 → m3 → formal OOS m4 结果包。"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Mapping, Sequence
import zipfile
from xml.etree import ElementTree

import numpy as np
import pandas as pd

from .config import AllAStyleBoxConfig, DEFAULT_CONFIG
from .data_pipeline import build_m1_dataset, load_frozen_transfer_market_data
from .portfolio import build_m3_dataset, select_formal_oos
from .reporting import (
    DEFAULT_REPORTING_SPEC,
    WORKBOOK_SHEET_PROJECTION_COLUMNS,
    build_comparison_payload,
    build_m4_dataset,
    build_metrics_payload,
    build_workbook_payload,
    finalize_workbook_payload,
    parse_assumption_registry,
    validate_pit_style_inputs,
    validate_security_event_audit,
    write_detail_tables,
    write_png_charts,
)
from .strategy import build_m2_dataset


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "r004_all_a_style_box"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / REPORT_ID / "results"
ASSUMPTIONS_PATH = REPO_ROOT / "workspace" / REPORT_ID / "assumptions.md"
BUILDER_PATH = Path(__file__).with_name("workbook_builder.mjs")
NODE_BINARY = Path(
    "/Users/hedi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)
NODE_PACKAGES = Path(
    "/Users/hedi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
)
SUBPROCESS_WARNING_MARKERS = ("warning", "warn", "missing a required sheetid")
EXPECTED_WORKBOOK_FILENAMES = (
    "backtest_summary.xlsx",
    "factor_analysis.xlsx",
    "style_box_returns.xlsx",
    "portfolio_holdings.xlsx",
    "trading_audit.xlsx",
)
REPEATED_DETAIL_METADATA_COLUMNS = (
    "detail_full_row_count",
    "detail_displayed_row_count",
    "detail_parquet_path",
    "detail_view_rule",
)
WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES = 8 * 1024 * 1024 * 1024
PENDING_WORKBOOK_PAYLOAD_FILENAME = "workbook_payload.pending.json"
VERIFIED_WORKBOOK_PAYLOAD_FILENAME = "workbook_payload.verified.json"
REQUIRED_QA_POLICY_FLAGS = (
    "inspect_key_range_before_export",
    "scan_formula_errors_before_export",
    "render_every_user_sheet_before_export",
    "native_chart_source_same_sheet",
    "ooxml_crc_and_structure_checked",
    "first_row_frozen_in_export",
)

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _inspect_xlsx_freeze_panes(workbook_path: Path) -> list[dict[str, Any]]:
    """独立重读最终OOXML，逐sheet核验真实首行冻结（A2语义）。"""
    with zipfile.ZipFile(workbook_path) as archive:
        workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships_root = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        relation_targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships_root.findall(
                f"{{{_PACKAGE_RELATIONSHIP_NS}}}Relationship"
            )
            if relation.attrib.get("Type", "").endswith("/worksheet")
        }
        records: list[dict[str, Any]] = []
        for sheet in workbook_root.findall(f".//{{{_SPREADSHEET_NS}}}sheet"):
            name = sheet.attrib["name"]
            relationship_id = sheet.attrib[f"{{{_RELATIONSHIP_NS}}}id"]
            target = relation_targets.get(relationship_id)
            if target is None:
                raise RuntimeError(f"{workbook_path.name}/{name}缺少worksheet关系")
            normalized = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            normalized = str(Path(normalized)).replace("\\", "/")
            if not normalized.startswith("xl/worksheets/") or ".." in Path(normalized).parts:
                raise RuntimeError(f"{workbook_path.name}/{name}关系Target异常: {target}")
            worksheet_root = ElementTree.fromstring(archive.read(normalized))
            panes = worksheet_root.findall(
                f"./{{{_SPREADSHEET_NS}}}sheetViews/"
                f"{{{_SPREADSHEET_NS}}}sheetView/{{{_SPREADSHEET_NS}}}pane"
            )
            if len(panes) != 1:
                raise RuntimeError(
                    f"{workbook_path.name}/{name} pane数量必须为1，实际{len(panes)}"
                )
            pane = panes[0]
            y_split = float(pane.attrib.get("ySplit", "0"))
            x_split = float(pane.attrib.get("xSplit", "0"))
            frozen = (
                pane.attrib.get("state") == "frozen"
                and y_split == 1.0
                and x_split == 0.0
                and pane.attrib.get("topLeftCell") == "A2"
            )
            if not frozen:
                raise RuntimeError(
                    f"{workbook_path.name}/{name}首行冻结未真实生效: {pane.attrib}"
                )
            records.append(
                {
                    "sheet": name,
                    "worksheet_entry": normalized,
                    "state": pane.attrib.get("state"),
                    "y_split": y_split,
                    "x_split": x_split,
                    "top_left_cell": pane.attrib.get("topLeftCell"),
                    "active_pane": pane.attrib.get("activePane"),
                    "equivalent_freeze_cell": "A2",
                    "frozen_first_row": frozen,
                }
            )
    return records


def _validate_workbook_manifest(manifest: Mapping[str, Any]) -> None:
    """Python端二次门禁：Node记录与实际inspect/render/OOXML必须闭环。"""
    node_warnings = manifest.get("warnings", [])
    if int(manifest.get("warning_count", -1)) != 0 or node_warnings:
        raise RuntimeError(f"artifact-tool QA含warning: {node_warnings}")
    wrapper = manifest.get("python_wrapper", {})
    wrapper_warnings = wrapper.get("captured_subprocess_warnings", [])
    if int(wrapper.get("captured_subprocess_warning_count", -1)) != 0 or wrapper_warnings:
        raise RuntimeError(f"Python包装器捕获到工作簿warning: {wrapper_warnings}")
    qa_policy = manifest.get("qa_policy", {})
    failed_policy = [flag for flag in REQUIRED_QA_POLICY_FLAGS if qa_policy.get(flag) is not True]
    if failed_policy:
        raise RuntimeError(f"artifact-tool QA策略未由实际记录证明: {failed_policy}")
    verified = manifest.get("verification_state") == "verified"
    if verified and (
        manifest.get("verification_status") != "verified/PASS"
        or manifest.get("verdict") != "PASS"
        or len(str(manifest.get("verification_context_sha256", ""))) != 64
    ):
        raise RuntimeError("verified工作簿manifest未绑定PASS/verifier context SHA")

    workbooks = manifest.get("workbooks", [])
    filenames = [workbook.get("filename") for workbook in workbooks]
    if filenames != list(EXPECTED_WORKBOOK_FILENAMES):
        raise RuntimeError(f"工作簿QA清单不完整或顺序异常: {filenames}")
    isolation = manifest.get("worker_process_isolation", {})
    workers = isolation.get("workers", [])
    worker_filenames = [record.get("filename") for record in workers]
    worker_memory = [record.get("process_memory", {}) for record in workers]
    if (
        isolation.get("enabled") is not True
        or isolation.get("one_workbook_per_worker") is not True
        or int(isolation.get("worker_count", -1)) != len(EXPECTED_WORKBOOK_FILENAMES)
        or worker_filenames != list(EXPECTED_WORKBOOK_FILENAMES)
        or any(int(record.get("payload_serialized_bytes", 0)) <= 0 for record in workers)
        or any(int(memory.get("max_rss_bytes", 0)) <= 0 for memory in worker_memory)
        or int(isolation.get("peak_worker_max_rss_bytes", 0))
        != max(int(memory["max_rss_bytes"]) for memory in worker_memory)
        or int(isolation.get("rss_hard_limit_bytes", -1))
        != WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES
        or int(isolation.get("peak_worker_max_rss_bytes", 0))
        > WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES
        or int(isolation.get("expected_total_sheet_count", -1))
        != sum(int(workbook.get("sheet_count", -1)) for workbook in workbooks)
        or int(isolation.get("total_user_row_count", -1))
        != sum(int(record.get("user_row_count", -1)) for record in workers)
    ):
        raise RuntimeError("工作簿未由5个单工作簿Node进程真实隔离生成")
    for workbook in workbooks:
        filename = str(workbook["filename"])
        workbook_path = Path(str(workbook.get("path", "")))
        if not workbook_path.is_file():
            raise RuntimeError(f"{filename}工作簿文件不存在: {workbook_path}")
        sheets = workbook.get("sheets", [])
        sheet_count = int(workbook.get("sheet_count", -1))
        inspections = workbook.get("inspections", [])
        previews = workbook.get("previews", [])
        if (
            sheet_count <= 0
            or len(sheets) != sheet_count
            or len(set(sheets)) != sheet_count
            or len(inspections) != sheet_count
            or len(previews) != sheet_count
        ):
            raise RuntimeError(f"{filename} sheet/inspect/preview计数未闭环")
        inspection_map = {record.get("sheet"): record for record in inspections}
        preview_map = {record.get("sheet"): record for record in previews}
        if set(inspection_map) != set(sheets) or set(preview_map) != set(sheets):
            raise RuntimeError(f"{filename} inspect/preview未覆盖全部sheet")
        node_freeze_records = workbook.get("freeze_panes", [])
        node_freeze_map = {record.get("sheet"): record for record in node_freeze_records}
        actual_freeze_records = _inspect_xlsx_freeze_panes(workbook_path)
        actual_freeze_map = {record["sheet"]: record for record in actual_freeze_records}
        if (
            len(node_freeze_records) != sheet_count
            or int(workbook.get("frozen_first_row_count", -1)) != sheet_count
            or set(node_freeze_map) != set(sheets)
            or set(actual_freeze_map) != set(sheets)
        ):
            raise RuntimeError(f"{filename}首行冻结记录未覆盖全部sheet")
        freeze_fields = (
            "worksheet_entry",
            "state",
            "y_split",
            "x_split",
            "top_left_cell",
            "active_pane",
            "equivalent_freeze_cell",
            "frozen_first_row",
        )
        for sheet in sheets:
            node_record = node_freeze_map[sheet]
            actual_record = actual_freeze_map[sheet]
            if any(node_record.get(field) != actual_record.get(field) for field in freeze_fields):
                raise RuntimeError(f"{filename}/{sheet}冻结manifest与实际OOXML不一致")
        if any(not str(inspection_map[sheet].get("ndjson", "")).strip() for sheet in sheets):
            raise RuntimeError(f"{filename}存在空inspect记录")
        cover_inspection = str(inspection_map.get("Cover", {}).get("ndjson", ""))
        if verified and ("verified/PASS" not in cover_inspection or "PASS" not in cover_inspection):
            raise RuntimeError(f"{filename} Cover实际inspect未显示verified/PASS")
        for sheet in sheets:
            preview = preview_map[sheet]
            preview_path = Path(str(preview.get("path", "")))
            if (
                int(preview.get("size_bytes", 0)) <= 0
                or not preview_path.is_file()
                or preview_path.stat().st_size <= 0
            ):
                raise RuntimeError(f"{filename}/{sheet}预览为空或不存在")
        formula_scan = workbook.get("formula_scan", {})
        if formula_scan.get("status") != "no_formula_errors" or formula_scan.get(
            "error_tokens"
        ):
            raise RuntimeError(f"{filename}公式错误扫描失败")
        charts = workbook.get("charts", [])
        declared_charts = workbook.get("declared_charts", [])
        declared_chart_count = int(workbook.get("declared_chart_count", -1))
        expected_chart_count = int(workbook.get("expected_chart_count", -1))
        actual_chart_count = int(workbook.get("actual_chart_count", -1))
        ooxml = workbook.get("ooxml_scan", {})
        if (
            declared_chart_count != len(declared_charts)
            or declared_chart_count != expected_chart_count
            or expected_chart_count != actual_chart_count
            or actual_chart_count != len(charts)
            or ooxml.get("crc_status") != "ok"
            or ooxml.get("required_entries_present") is not True
            or int(ooxml.get("worksheet_count", -1)) != sheet_count
            or int(ooxml.get("expected_chart_count", -1)) != declared_chart_count
            or int(ooxml.get("chart_count", -1)) != actual_chart_count
            or ooxml.get("formula_scan_complete") is not True
            or ooxml.get("formula_error_tokens")
        ):
            raise RuntimeError(f"{filename} OOXML或必要chart记录不完整")
        chart_map = {record.get("source_sheet"): record for record in charts}
        for declared in declared_charts:
            actual = chart_map.get(declared.get("source_sheet"))
            if (
                actual is None
                or int(actual.get("source_rows", -1))
                != int(declared.get("source_rows", -1))
                or actual.get("title") != declared.get("title")
            ):
                raise RuntimeError(
                    f"{filename}/{declared.get('source_sheet')} chart声明与实际记录不一致"
                )


def _compact_workbook_payload_for_node(
    workbook: Mapping[str, Any],
) -> tuple[dict[str, Any], int]:
    """移除已在DetailManifest/Sources登记、无须逐行复制的元数据列。"""
    compact = {key: value for key, value in workbook.items() if key != "sheets"}
    compact_sheets: list[dict[str, Any]] = []
    removed_cell_count = 0
    for original_sheet in workbook.get("sheets", []):
        sheet = dict(original_sheet)
        columns = list(sheet.get("columns", []))
        rows = list(sheet.get("rows", []))
        keep_indices = [
            index
            for index, column in enumerate(columns)
            if str(column) not in REPEATED_DETAIL_METADATA_COLUMNS
        ]
        removed_columns = len(columns) - len(keep_indices)
        if removed_columns:
            if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
                raise ValueError(f"{sheet.get('name')}工作表payload行列宽异常")
            sheet["columns"] = [columns[index] for index in keep_indices]
            sheet["rows"] = [
                [row[index] for index in keep_indices] for row in rows
            ]
            removed_cell_count += removed_columns * len(rows)
        projection = WORKBOOK_SHEET_PROJECTION_COLUMNS.get(str(sheet.get("name", "")))
        if projection is not None:
            current_columns = list(sheet.get("columns", columns))
            current_rows = list(sheet.get("rows", rows))
            missing_projection = sorted(set(projection).difference(current_columns))
            if missing_projection:
                raise ValueError(
                    f"{sheet.get('name')}工作簿审计视图缺少冻结列: {missing_projection}"
                )
            projection_indices = [current_columns.index(column) for column in projection]
            if any(
                not isinstance(row, list) or len(row) != len(current_columns)
                for row in current_rows
            ):
                raise ValueError(f"{sheet.get('name')}工作表payload行列宽异常")
            sheet["columns"] = list(projection)
            sheet["rows"] = [
                [row[index] for index in projection_indices] for row in current_rows
            ]
            removed_cell_count += (
                len(current_columns) - len(projection_indices)
            ) * len(current_rows)
        compact_sheets.append(sheet)
    compact["sheets"] = compact_sheets
    return compact, removed_cell_count


def _run_workbook_builder(
    payload: dict[str, Any],
    output_dir: Path,
    *,
    max_payload_bytes: int = DEFAULT_REPORTING_SPEC.workbook_payload_max_bytes,
) -> Path:
    """按工作簿隔离Node进程，生成五工作簿并合并实际QA清单。"""
    if not NODE_BINARY.is_file():
        raise FileNotFoundError(f"Node运行时不存在: {NODE_BINARY}")
    if not NODE_PACKAGES.is_dir():
        raise FileNotFoundError(f"Node packages目录不存在: {NODE_PACKAGES}")
    if not BUILDER_PATH.is_file():
        raise FileNotFoundError(f"工作簿builder不存在: {BUILDER_PATH}")
    workbooks = list(payload.get("workbooks", []))
    filenames = [str(workbook.get("filename", "")) for workbook in workbooks]
    if filenames != list(EXPECTED_WORKBOOK_FILENAMES):
        raise ValueError(f"工作簿payload不完整或顺序异常: {filenames}")
    common_payload = {key: value for key, value in payload.items() if key != "workbooks"}

    def serialize_worker_payload(
        workbook: Mapping[str, Any],
        *,
        compact: bool,
    ) -> tuple[bytes, int]:
        node_workbook, removed_cell_count = (
            _compact_workbook_payload_for_node(workbook)
            if compact
            else (dict(workbook), 0)
        )
        serialized = json.dumps(
            _json_safe({**common_payload, "workbooks": [node_workbook]}),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return serialized, removed_cell_count

    source_worker_payload_sizes = [
        len(serialize_worker_payload(workbook, compact=False)[0])
        for workbook in workbooks
    ]
    compacted_payload_records = [
        serialize_worker_payload(workbook, compact=True) for workbook in workbooks
    ]
    worker_payload_sizes = [len(record[0]) for record in compacted_payload_records]
    removed_metadata_cell_counts = [record[1] for record in compacted_payload_records]
    del compacted_payload_records
    source_aggregate_payload_bytes = sum(source_worker_payload_sizes)
    aggregate_payload_bytes = sum(worker_payload_sizes)
    if aggregate_payload_bytes > max_payload_bytes:
        raise ValueError(
            "工作簿分片摘要payload合计超过硬上限，禁止交给Node或提高内存: "
            f"actual={aggregate_payload_bytes} bytes, limit={max_payload_bytes} bytes；"
            "请检查按月/组合Top-N视图是否误含全量逐行明细"
        )

    with tempfile.TemporaryDirectory(prefix=f"{REPORT_ID}_artifact_") as temp_name:
        temp_dir = Path(temp_name)
        builder_copy = temp_dir / "workbook_builder.mjs"
        shutil.copy2(BUILDER_PATH, builder_copy)
        (temp_dir / "node_modules").symlink_to(NODE_PACKAGES, target_is_directory=True)
        manifest_path = output_dir / "workbook_qa_manifest.json"
        worker_manifests: list[dict[str, Any]] = []
        worker_records: list[dict[str, Any]] = []
        all_process_warnings: list[str] = []
        for index, (workbook, payload_size) in enumerate(
            zip(workbooks, worker_payload_sizes, strict=True), start=1
        ):
            payload_path = temp_dir / f"workbook_{index:02d}.json"
            worker_manifest_path = temp_dir / f"workbook_{index:02d}.manifest.json"
            payload_bytes, removed_cell_count = serialize_worker_payload(
                workbook, compact=True
            )
            if len(payload_bytes) != payload_size:
                raise AssertionError("工作簿分片payload序列化结果不稳定")
            if removed_cell_count != removed_metadata_cell_counts[index - 1]:
                raise AssertionError("工作簿逐行重复元数据压缩结果不稳定")
            payload_path.write_bytes(payload_bytes)
            command = [
                str(NODE_BINARY),
                str(builder_copy),
                "--input",
                str(payload_path),
                "--output",
                str(output_dir),
                "--qa-dir",
                str(output_dir / "workbook_qa"),
                "--manifest",
                str(worker_manifest_path),
            ]
            completed = subprocess.run(command, check=False, text=True, capture_output=True)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"artifact-tool第{index}/5本工作簿生成失败\n"
                    f"command={shlex.join(command)}\n"
                    f"stdout={completed.stdout}\n"
                    f"stderr={completed.stderr}"
                )
            if not worker_manifest_path.is_file():
                raise RuntimeError(f"artifact-tool第{index}/5本未生成QA manifest")
            process_warnings = list(
                dict.fromkeys(
                    line.strip()
                    for stream in (completed.stdout, completed.stderr)
                    for line in stream.splitlines()
                    if any(marker in line.lower() for marker in SUBPROCESS_WARNING_MARKERS)
                )
            )
            all_process_warnings.extend(process_warnings)
            worker_manifest = json.loads(
                worker_manifest_path.read_text(encoding="utf-8")
            )
            worker_books = worker_manifest.get("workbooks", [])
            expected_filename = filenames[index - 1]
            if (
                len(worker_books) != 1
                or worker_books[0].get("filename") != expected_filename
            ):
                raise RuntimeError(
                    f"第{index}/5本worker QA清单与输入不一致: {expected_filename}"
                )
            worker_manifests.append(worker_manifest)
            worker_records.append(
                {
                    "worker_index": index,
                    "filename": expected_filename,
                    "returncode": completed.returncode,
                    "payload_serialized_bytes": payload_size,
                    "source_payload_serialized_bytes": source_worker_payload_sizes[
                        index - 1
                    ],
                    "removed_repeated_metadata_cell_count": removed_cell_count,
                    "user_sheet_count": len(workbook.get("sheets", [])),
                    "user_row_count": sum(
                        len(sheet.get("rows", []))
                        for sheet in workbook.get("sheets", [])
                    ),
                    "process_memory": worker_manifest.get(
                        "worker_process_memory", {}
                    ),
                    "captured_subprocess_warning_count": len(process_warnings),
                    "captured_subprocess_warnings": process_warnings,
                }
            )
            payload_path.unlink()

        first_manifest = worker_manifests[0]
        policy_keys = set(first_manifest.get("qa_policy", {}))
        manifest = {
            "report_id": first_manifest.get("report_id"),
            "verification_status": first_manifest.get("verification_status"),
            "verification_state": first_manifest.get("verification_state"),
            "verdict": first_manifest.get("verdict"),
            "verification_context_sha256": first_manifest.get(
                "verification_context_sha256"
            ),
            "generated_at": max(
                str(worker.get("generated_at", "")) for worker in worker_manifests
            ),
            "artifact_tool_package": first_manifest.get("artifact_tool_package"),
            "artifact_tool_version": first_manifest.get("artifact_tool_version"),
            "minimum_required_version": first_manifest.get(
                "minimum_required_version"
            ),
            "input_payload_size_bytes": aggregate_payload_bytes,
            "qa_policy": {
                key: (
                    all(worker.get("qa_policy", {}).get(key) is True for worker in worker_manifests)
                    if isinstance(first_manifest.get("qa_policy", {}).get(key), bool)
                    else first_manifest.get("qa_policy", {}).get(key)
                )
                for key in policy_keys
            },
            "warning_count": sum(
                int(worker.get("warning_count", 0)) for worker in worker_manifests
            ),
            "warnings": [
                warning
                for worker in worker_manifests
                for warning in worker.get("warnings", [])
            ],
            "worker_process_isolation": {
                "enabled": True,
                "worker_count": len(worker_records),
                "one_workbook_per_worker": True,
                "maximum_worker_payload_serialized_bytes": max(worker_payload_sizes),
                "aggregate_worker_payload_serialized_bytes": aggregate_payload_bytes,
                "source_aggregate_worker_payload_serialized_bytes": (
                    source_aggregate_payload_bytes
                ),
                "removed_repeated_metadata_cell_count": sum(
                    removed_metadata_cell_counts
                ),
                "expected_total_sheet_count": sum(
                    int(record["user_sheet_count"]) + 1 for record in worker_records
                ),
                "total_user_row_count": sum(
                    int(record["user_row_count"]) for record in worker_records
                ),
                "peak_worker_max_rss_bytes": max(
                    int(record["process_memory"].get("max_rss_bytes", 0))
                    for record in worker_records
                ),
                "rss_hard_limit_bytes": WORKBOOK_WORKER_RSS_HARD_LIMIT_BYTES,
                "workers": worker_records,
            },
            "workbooks": [
                worker["workbooks"][0] for worker in worker_manifests
            ],
        }
        manifest["python_wrapper"] = {
            "returncode": 0,
            "payload_serialized_bytes": aggregate_payload_bytes,
            "payload_limit_bytes": max_payload_bytes,
            "worker_count": len(worker_records),
            "captured_subprocess_warning_count": len(all_process_warnings),
            "captured_subprocess_warnings": list(dict.fromkeys(all_process_warnings)),
        }
        _write_json(manifest_path, manifest)
        _validate_workbook_manifest(manifest)
        return manifest_path


def run_formal_pipeline(
    *,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    """运行完整历史形成有状态组合，再按本次config切出正式OOS。"""
    # 在任何正式计算前离线校验全部冻结来源、raw/parsed哈希与429行行情。
    # 返回值不进入选股信息集，仅供600466生命周期退出路径按日取用。
    load_frozen_transfer_market_data(config)
    m1 = build_m1_dataset(config)
    m2 = build_m2_dataset(m1.monthly_panel)
    m3_full = build_m3_dataset(m1, m2, config)
    m3 = select_formal_oos(m3_full, config)
    # 正式结果写盘前的生命周期硬门禁。风险退出公告不能替代估值来源；
    # 任一unpriced/blocking状态都会在这里非零退出，不写完整收益结论。
    validate_security_event_audit(m3.security_event_audit, config=config)
    reporting_specification = DEFAULT_REPORTING_SPEC
    m4 = build_m4_dataset(m1, m2, m3, config, reporting_specification)

    output_dir.mkdir(parents=True, exist_ok=True)
    chart_paths = write_png_charts(m4, output_dir, reporting_specification)
    metrics_path = output_dir / "metrics.json"
    comparison_path = output_dir / "comparison.json"
    _write_json(metrics_path, build_metrics_payload(m4, config))
    _write_json(comparison_path, build_comparison_payload(m4, config))

    assumptions = parse_assumption_registry(ASSUMPTIONS_PATH)
    detail_manifest = write_detail_tables(
        m4, m2, m3, output_dir, reporting_specification
    )
    detail_manifest_path = output_dir / "detail_manifest.json"
    _write_json(detail_manifest_path, detail_manifest)
    workbook_payload = build_workbook_payload(
        m4,
        m2,
        m3,
        assumptions,
        detail_manifest,
        reporting_specification,
        config,
    )
    pending_payload_path = output_dir / PENDING_WORKBOOK_PAYLOAD_FILENAME
    _write_json(pending_payload_path, workbook_payload)
    qa_manifest = _run_workbook_builder(
        workbook_payload,
        output_dir,
        max_payload_bytes=reporting_specification.workbook_payload_max_bytes,
    )
    workbook_paths = {
        filename: output_dir / filename
        for filename in EXPECTED_WORKBOOK_FILENAMES
    }
    missing = [name for name, path in workbook_paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"工作簿合同未完整生成: {missing}")
    return {
        "metrics.json": metrics_path,
        "comparison.json": comparison_path,
        "detail_manifest.json": detail_manifest_path,
        "workbook_qa_manifest.json": qa_manifest,
        PENDING_WORKBOOK_PAYLOAD_FILENAME: pending_payload_path,
        **{
            str(record["file"]): output_dir / str(record["file"])
            for record in detail_manifest["tables"]
        },
        **workbook_paths,
        **chart_paths,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_file_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise FileNotFoundError(f"基线结果目录不存在: {root}")
    return {
        path.relative_to(root).as_posix(): _sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def finalize_workbooks_from_verifier_context(
    *,
    output_dir: Path,
    verification_context_path: Path,
) -> dict[str, Path]:
    """不重跑策略，只凭只读verifier上下文重建五本verified/PASS工作簿。"""
    pending_path = output_dir / PENDING_WORKBOOK_PAYLOAD_FILENAME
    if not pending_path.is_file():
        raise FileNotFoundError(f"缺少待验证工作簿payload: {pending_path}")
    if not verification_context_path.is_file():
        raise FileNotFoundError(f"verification context不存在: {verification_context_path}")
    pending_payload = json.loads(pending_path.read_text(encoding="utf-8"))
    context = json.loads(verification_context_path.read_text(encoding="utf-8"))
    assumptions = parse_assumption_registry(ASSUMPTIONS_PATH)
    verified_payload = finalize_workbook_payload(pending_payload, assumptions, context)
    verified_payload_path = output_dir / VERIFIED_WORKBOOK_PAYLOAD_FILENAME
    _write_json(verified_payload_path, verified_payload)
    qa_manifest = _run_workbook_builder(
        verified_payload,
        output_dir,
        max_payload_bytes=DEFAULT_REPORTING_SPEC.workbook_payload_max_bytes,
    )
    workbooks = {name: output_dir / name for name in EXPECTED_WORKBOOK_FILENAMES}
    missing = [name for name, path in workbooks.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"最终化后五工作簿不完整: {missing}")
    manifest = json.loads(qa_manifest.read_text(encoding="utf-8"))
    if manifest.get("report_id") != REPORT_ID:
        raise RuntimeError("最终化工作簿QA manifest报告ID不一致")
    return {
        VERIFIED_WORKBOOK_PAYLOAD_FILENAME: verified_payload_path,
        "workbook_qa_manifest.json": qa_manifest,
        **workbooks,
    }


def write_perturbation_replay_contract(
    *,
    perturbation_dir: Path,
    baseline_results_dir: Path,
    baseline_hashes_before: Mapping[str, str],
    config_diff: Mapping[str, Any],
    command: str,
    started_at: datetime,
    ended_at: datetime,
    exit_code: int,
) -> Path:
    """把hard扰动落成独立、可读回、可重放且不覆盖正式目录的证据合同。"""
    if exit_code != 0:
        raise ValueError("扰动重放合同只接受exit=0的完整运行")
    baseline_resolved = baseline_results_dir.resolve()
    perturbation_resolved = perturbation_dir.resolve()
    if (
        baseline_resolved == perturbation_resolved
        or baseline_resolved in perturbation_resolved.parents
        or perturbation_resolved in baseline_resolved.parents
    ):
        raise ValueError("扰动目录必须与正式结果目录完全独立，禁止父子嵌套")
    baseline_hashes_after = _snapshot_file_hashes(baseline_resolved)
    if dict(baseline_hashes_before) != baseline_hashes_after:
        raise RuntimeError("扰动运行前后正式结果目录SHA发生变化，拒绝写成功合同")
    required = {
        "metrics.json",
        "comparison.json",
        "detail_manifest.json",
        PENDING_WORKBOOK_PAYLOAD_FILENAME,
        "detail_tables/pit_style_inputs.parquet",
        "detail_tables/security_event_audit.parquet",
    }
    missing = sorted(name for name in required if not (perturbation_resolved / name).is_file())
    if missing:
        raise FileNotFoundError(f"扰动可重放合同缺少产物: {missing}")
    metrics = json.loads((perturbation_resolved / "metrics.json").read_text(encoding="utf-8"))
    comparison = json.loads(
        (perturbation_resolved / "comparison.json").read_text(encoding="utf-8")
    )
    workbook_payload = json.loads(
        (perturbation_resolved / PENDING_WORKBOOK_PAYLOAD_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    detail_manifest = json.loads(
        (perturbation_resolved / "detail_manifest.json").read_text(encoding="utf-8")
    )
    pit_checks = validate_pit_style_inputs(
        pd.read_parquet(perturbation_resolved / "detail_tables/pit_style_inputs.parquet")
    )
    event_checks = validate_security_event_audit(
        pd.read_parquet(perturbation_resolved / "detail_tables/security_event_audit.parquet")
    )
    metric_by_key = {
        str(record.get("key")): record for record in comparison.get("metrics", [])
    }
    r4_cells = int(metric_by_key["R4_china_oos_correlation_cells"]["reproduced_value"])
    r7_sum = float(
        metric_by_key["R7_china_style_box_winner_frequency_sum"]["reproduced_value"]
    )
    required_key_contract = comparison.get("required_key_contract", {})
    if (
        required_key_contract.get("R10_count") != 27
        or required_key_contract.get("SA4_count") != 48
        or len(required_key_contract.get("R10", [])) != 27
        or len(required_key_contract.get("SA4", [])) != 48
    ):
        raise AssertionError("扰动comparison未精确覆盖R10 27项与SA4 48项")
    boundary_sets = [
        payload.get("final_boundary_disclosures")
        for payload in (metrics, comparison, workbook_payload)
    ]
    if not boundary_sets[0] or not all(boundary == boundary_sets[0] for boundary in boundary_sets[1:]):
        raise AssertionError("扰动metrics/comparison/五工作簿边界披露不一致")
    oos = metrics.get("oos", {})
    expected_oos_months = len(
        pd.period_range(oos.get("start"), oos.get("end"), freq="M")
    )
    if int(oos.get("n_months", -1)) != expected_oos_months:
        raise AssertionError("扰动OOS月数未由实际config日期集合动态生成")
    if r4_cells != 49 or abs(r7_sum - 1.0) > 1e-12 or pit_checks["future_disclosure_count"]:
        raise AssertionError(
            f"扰动关键检查失败: R4={r4_cells}, R7={r7_sum}, PIT={pit_checks}"
        )
    if len(detail_manifest.get("tables", [])) < 12:
        raise AssertionError("扰动detail manifest少于12张表")
    config_diff_path = perturbation_resolved / "config_diff.json"
    _write_json(config_diff_path, dict(config_diff))
    artifact_hashes = {
        path.relative_to(perturbation_resolved).as_posix(): _sha256_file(path)
        for path in sorted(perturbation_resolved.rglob("*"))
        if path.is_file() and path.name != "perturbation_replay_contract.json"
    }
    contract = {
        "schema_version": 1,
        "report_id": REPORT_ID,
        "reproduction_mode": "experimental_hard_perturbation",
        "command": command,
        "started_at": started_at.astimezone().isoformat(),
        "ended_at": ended_at.astimezone().isoformat(),
        "exit_code": exit_code,
        "config_diff": dict(config_diff),
        "config_diff_file": "config_diff.json",
        "baseline_results_dir": str(baseline_resolved),
        "baseline_hashes_before": dict(baseline_hashes_before),
        "baseline_hashes_after": baseline_hashes_after,
        "baseline_unchanged": True,
        "metrics_file": "metrics.json",
        "comparison_file": "comparison.json",
        "detail_manifest_file": "detail_manifest.json",
        "key_checks": {
            "R4_cell_count": r4_cells,
            "R7_frequency_sum": r7_sum,
            "R7_frequency_sum_abs_error": abs(r7_sum - 1.0),
            "PIT": pit_checks,
            "security_events": event_checks,
            "comparison_required_keys": {
                "R10_count": required_key_contract["R10_count"],
                "SA4_count": required_key_contract["SA4_count"],
            },
            "boundary_disclosures_identical": True,
            "oos_month_count": expected_oos_months,
        },
        "metrics_report_id": metrics.get("report_id"),
        "detail_table_count": len(detail_manifest["tables"]),
        "artifact_sha256": artifact_hashes,
    }
    contract_path = perturbation_resolved / "perturbation_replay_contract.json"
    _write_json(contract_path, contract)
    return contract_path


def _write_run_log(
    path: Path,
    *,
    command: str,
    started_at: datetime,
    ended_at: datetime,
    exit_code: int,
    artifacts: Mapping[str, Path] | None,
    error: str | None,
    verification_status: str = "pending_verifier",
    title: str = "r004正式运行日志",
    note: str = "本日志仅记录可执行状态，不构成验证通过结论。",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact_lines = [
        f"- `{name}`: `{artifact}`" for name, artifact in sorted((artifacts or {}).items())
    ]
    lines = [
        f"# {title}",
        "",
        f"- command: `{command}`",
        f"- started_at: {started_at.astimezone().isoformat()}",
        f"- ended_at: {ended_at.astimezone().isoformat()}",
        f"- exit={exit_code}",
        "- reproduction_mode: experimental",
        f"- verification_status: {verification_status}",
        f"- note: {note}",
        "",
        "## 产物",
        "",
        *(artifact_lines or ["- 未生成完整产物"]),
    ]
    if error:
        lines.extend(["", "## 错误", "", "```text", error, "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行r004中国全A风格箱完整历史回测并输出正式OOS结果包"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="结果目录；默认output/r004_all_a_style_box/results",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="仅覆盖本地数据根目录，不改变策略、日期或成本参数",
    )
    parser.add_argument(
        "--finalize-workbooks",
        action="store_true",
        help="不重跑策略，只消费--verification-context重建verified/PASS五工作簿",
    )
    parser.add_argument(
        "--verification-context",
        type=Path,
        default=None,
        help="verifier只读最终化上下文JSON",
    )
    parser.add_argument(
        "--perturbation-oos-end",
        type=str,
        default=None,
        help="hard扰动：仅改变OOS截止日并在独立--output-dir完整重跑",
    )
    parser.add_argument(
        "--baseline-results-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="hard扰动前后必须保持SHA不变的正式结果目录",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.finalize_workbooks and args.verification_context is None:
        raise SystemExit("--finalize-workbooks必须提供--verification-context")
    if args.finalize_workbooks and args.perturbation_oos_end is not None:
        raise SystemExit("最终化与hard扰动模式互斥")
    config = (
        replace(DEFAULT_CONFIG, data_root=args.data_root.resolve())
        if args.data_root is not None
        else DEFAULT_CONFIG
    )
    output_dir = args.output_dir.resolve()
    command = shlex.join([sys.executable, "-m", "src.r004_all_a_style_box.main", *(argv or sys.argv[1:])])
    started_at = datetime.now().astimezone()
    artifacts: dict[str, Path] | None = None
    error: str | None = None
    exit_code = 0
    log_path = output_dir / "run_log.md"
    log_status = "pending_verifier"
    log_title = "r004正式运行日志"
    log_note = "本日志仅记录可执行状态，不构成验证通过结论。"
    try:
        if args.finalize_workbooks:
            log_path = output_dir / "workbook_finalization_log.md"
            log_status = "verified/PASS"
            log_title = "r004工作簿最终化日志"
            log_note = "verified/PASS完全来自只读verifier上下文，不由coder自行宣布。"
            artifacts = finalize_workbooks_from_verifier_context(
                output_dir=output_dir,
                verification_context_path=args.verification_context.resolve(),
            )
        elif args.perturbation_oos_end is not None:
            log_title = "r004 hard扰动运行日志"
            log_note = "独立扰动证据，不覆盖正式结果且不构成正式验证结论。"
            baseline_dir = args.baseline_results_dir.resolve()
            if (
                baseline_dir == output_dir
                or baseline_dir in output_dir.parents
                or output_dir in baseline_dir.parents
            ):
                raise ValueError("hard扰动--output-dir必须与正式结果目录完全独立")
            baseline_hashes = _snapshot_file_hashes(baseline_dir)
            perturbed_config = replace(config, oos_end=args.perturbation_oos_end)
            artifacts = run_formal_pipeline(
                config=perturbed_config,
                output_dir=output_dir,
            )
            contract_path = write_perturbation_replay_contract(
                perturbation_dir=output_dir,
                baseline_results_dir=baseline_dir,
                baseline_hashes_before=baseline_hashes,
                config_diff={
                    "oos_end": {
                        "baseline": config.oos_end,
                        "perturbed": args.perturbation_oos_end,
                    }
                },
                command=command,
                started_at=started_at,
                ended_at=datetime.now().astimezone(),
                exit_code=0,
            )
            artifacts["perturbation_replay_contract.json"] = contract_path
        else:
            artifacts = run_formal_pipeline(config=config, output_dir=output_dir)
    except Exception:
        exit_code = 1
        error = traceback.format_exc()
    ended_at = datetime.now().astimezone()
    _write_run_log(
        log_path,
        command=command,
        started_at=started_at,
        ended_at=ended_at,
        exit_code=exit_code,
        artifacts=artifacts,
        error=error,
        verification_status=log_status,
        title=log_title,
        note=log_note,
    )
    if error:
        sys.stderr.write(error)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
