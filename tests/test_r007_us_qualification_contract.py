"""r007 attempt=2 的 AS19/AS26 美股资格与硬失败定向回归。"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from src.r007_cross_market_return_forecasting.config import DEFAULT_CONFIG
from src.r007_cross_market_return_forecasting.data_pipeline import (
    _assert_us_batch_qualification_gate,
    _audit_us_security_qualification,
    _file_sha256,
    _us_batch_qualification_summary,
    audit_security_calendar_coverage,
    audit_us_merged_panel_contract,
    calculate_raw_log_returns,
    standardize_us_quotes,
)


RAW_OHLC = ("open_raw", "high_raw", "low_raw", "close_raw")
ADJUSTED_MAPPING = (
    ("open_raw", "open_adj"),
    ("high_raw", "high_adj"),
    ("low_raw", "low_adj"),
    ("close_raw", "close_adj"),
)


def _refresh_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """按缓存写入公式生成测试真值，生产实现仍会独立重算。"""
    result = frame.copy()
    complete = result[list(RAW_OHLC)].notna().all(axis=1)
    logic = (
        result["open_raw"].gt(0)
        & result["close_raw"].gt(0)
        & result["high_raw"].ge(
            result[["open_raw", "close_raw"]].max(axis=1)
        )
        & result["low_raw"].le(
            result[["open_raw", "close_raw"]].min(axis=1)
        )
        & result["high_raw"].ge(result["low_raw"])
    )
    result["ohlc_logic_valid"] = (~complete) | logic
    factor = result["adj_close"] / result["close_raw"]
    result["adj_factor"] = factor.where(factor.gt(0) & np.isfinite(factor))
    for raw_column, adjusted_column in ADJUSTED_MAPPING:
        adjusted = result[raw_column] * result["adj_factor"]
        result[adjusted_column] = adjusted.where(
            result["ohlc_logic_valid"] & np.isfinite(adjusted)
        )
    result["return_eligible"] = (
        result["ohlc_logic_valid"]
        & result["open_adj"].gt(0)
        & result["close_adj"].gt(0)
    )
    return result


def _security(rows: int = 100, stock_code: str = "TEST") -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "stock_code": stock_code,
            "source_symbol": stock_code,
            "yahoo_symbol": stock_code,
            "date": pd.date_range("2021-01-01", periods=rows, freq="D"),
            "open_raw": 10.0,
            "high_raw": 12.0,
            "low_raw": 9.0,
            "close_raw": 11.0,
            "adj_close": 22.0,
            "volume": 100.0,
            "dividends": 0.0,
            "stock_splits": 0.0,
        }
    )
    return _refresh_derived(frame)


def _request_contract(config: object) -> dict[str, object]:
    return {
        "start": config.sample.start_date,
        "end_exclusive": config.sample.end_exclusive,
        "interval": config.us_yahoo.interval,
        "auto_adjust": config.us_yahoo.auto_adjust,
        "actions": config.us_yahoo.actions,
        "repair": config.us_yahoo.repair,
        "keepna": config.us_yahoo.keepna,
        "threads": config.us_yahoo.threads,
        "timeout_seconds": config.us_yahoo.timeout_seconds,
    }


def _temporary_contract(
    root: Path,
    *,
    individual: pd.DataFrame | None = None,
    manifest_rows: int | None = None,
    manifest_sha: str | None = None,
) -> tuple[pd.DataFrame, object]:
    security = _security() if individual is None else individual
    prices = root / "prices"
    prices.mkdir(parents=True)
    individual_path = prices / "TEST.parquet"
    merged_path = root / "us_panel.parquet"
    security.to_parquet(individual_path, index=False)
    merged = _security()
    merged.to_parquet(merged_path, index=False)
    us_config = replace(
        DEFAULT_CONFIG.us_yahoo,
        cache_dir=root,
        expected_constituents=1,
        minimum_successful_securities=1,
        maximum_failed_securities=0,
    )
    config = replace(
        DEFAULT_CONFIG,
        us_yahoo=us_config,
        sample=replace(DEFAULT_CONFIG.sample, stocks_per_market=1),
    )
    manifest = {
        "request": _request_contract(config),
        "entries": {
            "TEST": {
                "status": "success",
                "file": "prices/TEST.parquet",
                "file_sha256": (
                    manifest_sha
                    if manifest_sha is not None
                    else _file_sha256(individual_path)
                ),
                "rows": len(security) if manifest_rows is None else manifest_rows,
            }
        },
        "merged_panel": {
            "file": "us_panel.parquet",
            "sha256": _file_sha256(merged_path),
            "rows": len(merged),
            "qualified_security_count": 1,
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return merged, config


class USSecurityQualificationTest(unittest.TestCase):
    threshold = DEFAULT_CONFIG.us_yahoo.minimum_ohlcv_non_null_rate

    def audit(self, frame: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
        return _audit_us_security_qualification(
            frame,
            stock_code="TEST",
            minimum_rate=self.threshold,
        )

    def test_01_one_identified_isolated_violation_remains_qualified(self) -> None:
        frame = _security()
        frame.loc[50, "low_raw"] = 10.5
        frame = _refresh_derived(frame)
        row, exceptions = self.audit(frame)
        self.assertTrue(row["qualified"])
        self.assertEqual(row["qualification_status"], "qualified")
        self.assertEqual(row["qualification_reason"], "qualified")
        self.assertEqual(row["ohlc_logic_violation_count_independent"], 1)
        self.assertEqual(row["return_eligible_rows_independent"], 99)
        self.assertEqual(row["flag_mismatch_count"], 0)
        self.assertEqual(len(exceptions), 1)
        self.assertTrue(exceptions.loc[0, "isolation_complete"])

    def test_02_forged_logic_or_eligible_flag_is_hard_failure(self) -> None:
        for column in ("ohlc_logic_valid", "return_eligible"):
            with self.subTest(column=column):
                frame = _security()
                frame.loc[50, "low_raw"] = 10.5
                frame = _refresh_derived(frame)
                frame.loc[50, column] = True
                row, _ = self.audit(frame)
                self.assertFalse(row["hard_contract_pass"])
                self.assertGreater(row["flag_mismatch_count"], 0)
                batch = pd.DataFrame([row] * 501)
                summary = _us_batch_qualification_summary(
                    batch,
                    requested_count=501,
                    manifest_success_count=501,
                    observed_count=501,
                    sets_consistent=True,
                    config=DEFAULT_CONFIG,
                )
                with self.assertRaises(ValueError):
                    _assert_us_batch_qualification_gate(summary)

    def test_03_non_null_adjusted_value_on_violation_is_hard_failure(self) -> None:
        frame = _security()
        frame.loc[50, "low_raw"] = 10.5
        frame = _refresh_derived(frame)
        frame.loc[50, "open_adj"] = 20.0
        row, _ = self.audit(frame)
        self.assertFalse(row["hard_contract_pass"])
        self.assertEqual(row["unisolated_ohlc_violation_count"], 1)
        self.assertGreater(row["adjusted_ohlc_mismatch_count"], 0)

    def test_04_all_true_flags_cannot_hide_raw_logic_violations(self) -> None:
        frame = _security()
        frame.loc[10, "low_raw"] = 10.5
        frame.loc[20, "high_raw"] = 10.5
        frame.loc[30, "open_raw"] = 0.0
        frame.loc[40, ["high_raw", "low_raw"]] = [8.0, 9.0]
        frame["ohlc_logic_valid"] = True
        frame["return_eligible"] = True
        row, _ = self.audit(frame)
        self.assertEqual(row["ohlc_logic_violation_count_independent"], 4)
        self.assertFalse(row["hard_contract_pass"])
        self.assertGreaterEqual(row["flag_mismatch_count"], 4)

    def test_05_return_eligible_rate_inclusive_boundary(self) -> None:
        exact = _security()
        exact.loc[:4, "adj_close"] = np.nan
        exact = _refresh_derived(exact)
        exact_row, _ = self.audit(exact)
        self.assertEqual(exact_row["return_eligible_rate_independent"], 0.95)
        self.assertTrue(exact_row["qualified"])

        below = _security()
        below.loc[:5, "adj_close"] = np.nan
        below = _refresh_derived(below)
        below_row, _ = self.audit(below)
        self.assertEqual(below_row["return_eligible_rate_independent"], 0.94)
        self.assertFalse(below_row["qualified"])

    def test_06_ohlcv_non_null_rate_inclusive_boundary(self) -> None:
        exact = _security()
        exact.loc[:4, "volume"] = np.nan
        exact = _refresh_derived(exact)
        exact_row, _ = self.audit(exact)
        self.assertEqual(exact_row["volume_non_null_ratio"], 0.95)
        self.assertTrue(exact_row["qualified"])

        below = _security()
        below.loc[:5, "volume"] = np.nan
        below = _refresh_derived(below)
        below_row, _ = self.audit(below)
        self.assertEqual(below_row["volume_non_null_ratio"], 0.94)
        self.assertFalse(below_row["qualified"])

    def test_07_batch_500_qualified_one_failed_passes_but_499_two_fail(self) -> None:
        audit = pd.DataFrame(
            {
                "qualified": [True] * 500 + [False],
                "hard_contract_pass": [True] * 501,
            }
        )
        summary = _us_batch_qualification_summary(
            audit,
            requested_count=501,
            manifest_success_count=501,
            observed_count=501,
            sets_consistent=True,
            config=DEFAULT_CONFIG,
        )
        _assert_us_batch_qualification_gate(summary)
        self.assertEqual(summary["qualified_count"], 500)
        self.assertEqual(summary["failed_count"], 1)
        universe = pd.DataFrame(
            {"stock_code": [f"S{i:03d}" for i in range(501)]}
        )
        panel = pd.DataFrame(
            {
                "stock_code": universe["stock_code"].iloc[:500],
                "date": pd.Timestamp("2021-01-04"),
                "pvclcl_raw": 0.0,
                "opcl_raw": 0.0,
                "pvclcl_excess": 0.0,
                "opcl_excess": 0.0,
            }
        )
        coverage = audit_security_calendar_coverage(
            panel,
            universe,
            pd.DataFrame({"date": [pd.Timestamp("2021-01-04")]}),
            market="US",
        )
        self.assertEqual(len(coverage), 500)

        audit.loc[499, "qualified"] = False
        summary = _us_batch_qualification_summary(
            audit,
            requested_count=501,
            manifest_success_count=501,
            observed_count=501,
            sets_consistent=True,
            config=DEFAULT_CONFIG,
        )
        with self.assertRaises(ValueError):
            _assert_us_batch_qualification_gate(summary)
        with self.assertRaises(ValueError):
            audit_security_calendar_coverage(
                panel.iloc[:499],
                universe,
                pd.DataFrame({"date": [pd.Timestamp("2021-01-04")]}),
                market="US",
            )

    def test_08_fixed_candidate_count_and_set_mismatch_are_hard_failures(self) -> None:
        audit = pd.DataFrame(
            {
                "qualified": [True] * 501,
                "hard_contract_pass": [True] * 501,
            }
        )
        for requested, success, observed, sets_consistent in (
            (500, 501, 501, True),
            (502, 501, 501, True),
            (501, 501, 501, False),
        ):
            with self.subTest(
                requested=requested,
                sets_consistent=sets_consistent,
            ):
                summary = _us_batch_qualification_summary(
                    audit,
                    requested_count=requested,
                    manifest_success_count=success,
                    observed_count=observed,
                    sets_consistent=sets_consistent,
                    config=DEFAULT_CONFIG,
                )
                with self.assertRaises(ValueError):
                    _assert_us_batch_qualification_gate(summary)

    def test_09_file_key_row_schema_and_content_integrity_remain_hard(self) -> None:
        cases = ("sha", "schema", "duplicate", "rows", "content")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                individual = _security()
                kwargs: dict[str, object] = {}
                if case == "schema":
                    individual["volume"] = individual["volume"].astype("string")
                elif case == "sha":
                    kwargs["manifest_sha"] = "0" * 64
                elif case == "rows":
                    kwargs["manifest_rows"] = len(individual) + 1
                panel, config = _temporary_contract(
                    root,
                    individual=individual,
                    **kwargs,
                )
                if case == "duplicate":
                    panel = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
                elif case == "content":
                    panel = panel.copy()
                    panel.loc[0, "open_raw"] += 1.0
                with self.assertRaises(ValueError):
                    audit_us_merged_panel_contract(
                        panel,
                        ["TEST"],
                        config=config,
                    )

    def test_10_invalid_day_returns_and_next_day_pvclcl_are_empty(self) -> None:
        frame = _security()
        frame.loc[50, "low_raw"] = 10.5
        frame = _refresh_derived(frame)
        row, _ = self.audit(frame)
        self.assertEqual(row["invalid_row_used_in_opcl_count"], 0)
        self.assertEqual(
            row[
                "invalid_or_missing_previous_close_used_in_pvclcl_count"
            ],
            0,
        )
        standardized = standardize_us_quotes(frame)
        returns = calculate_raw_log_returns(
            standardized,
            entity_column="stock_code",
        ).reset_index(drop=True)
        self.assertTrue(pd.isna(returns.loc[50, "opcl_raw"]))
        self.assertTrue(pd.isna(returns.loc[50, "pvclcl_raw"]))
        self.assertTrue(pd.isna(returns.loc[51, "pvclcl_raw"]))

    def test_11_invalid_adjustment_factor_reduces_eligible_rate(self) -> None:
        frame = _security()
        frame.loc[:5, "adj_close"] = np.inf
        frame = _refresh_derived(frame)
        row, _ = self.audit(frame)
        self.assertEqual(row["return_eligible_rate_independent"], 0.94)
        self.assertEqual(row["adj_factor_mismatch_count"], 0)
        self.assertFalse(row["qualified"])

    def test_12_real_hubb_and_ua_slices_match_planning_facts(self) -> None:
        expected = {
            "HUBB": (2015, 1, 2014),
            "UA": (1456, 1, 1455),
        }
        for stock_code, (
            expected_rows,
            expected_violations,
            expected_eligible,
        ) in expected.items():
            with self.subTest(stock_code=stock_code):
                path = (
                    DEFAULT_CONFIG.us_yahoo.prices_dir
                    / f"{stock_code}.parquet"
                )
                frame = pd.read_parquet(path)
                row, exceptions = _audit_us_security_qualification(
                    frame,
                    stock_code=stock_code,
                    minimum_rate=self.threshold,
                )
                self.assertEqual(row["rows"], expected_rows)
                self.assertEqual(
                    row["ohlc_logic_violation_count_independent"],
                    expected_violations,
                )
                self.assertEqual(
                    row["return_eligible_rows_independent"],
                    expected_eligible,
                )
                self.assertTrue(row["qualified"])
                self.assertEqual(len(exceptions), 1)
                self.assertEqual(
                    pd.Timestamp(exceptions.loc[0, "date"]),
                    pd.Timestamp("2021-05-05"),
                )


if __name__ == "__main__":
    unittest.main()
