from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r004_all_a_style_box.config import DEFAULT_CONFIG
from src.r004_all_a_style_box.main import (
    _run_workbook_builder,
    _snapshot_file_hashes,
    write_perturbation_replay_contract,
)
from src.r004_all_a_style_box.reporting import (
    _build_entity_audit,
    _configure_date_axis,
    assumption_frame_sha256,
    build_boundary_disclosures,
    build_comparison_payload,
    build_return_series,
    finalize_workbook_payload,
    validate_assumption_registry_for_finalization,
    validate_pit_style_inputs,
    validate_security_event_audit,
    write_detail_tables,
)


def _pit_frame(*, invalid_first_row: bool = False) -> pd.DataFrame:
    signal = pd.Timestamp("2023-03-31")
    rows = []
    labels = (
        ("000001", 100.0, 0.8, 0.2, "Small", "Value", "SV"),
        ("000002", 200.0, 0.2, 0.8, "Small", "Growth", "SG"),
        ("600001", 300.0, 0.8, 0.2, "Big", "Value", "BV"),
        ("600002", 400.0, 0.2, 0.8, "Big", "Growth", "BG"),
    )
    for code, market_value, value_raw, growth_raw, size, style, box in labels:
        current_value = value_raw * market_value
        prior_value = current_value * (2.0 - growth_raw) / (2.0 + growth_raw)
        rows.append(
            {
                "signal_date": signal,
                "stock_code": code,
                "eligible": True,
                "is_eligible": True,
                "financial_end_date": pd.Timestamp("2022-12-31"),
                "period_available_date": signal - pd.Timedelta(days=8),
                "current_info_publ_date": signal - pd.Timedelta(days=8),
                "current_total_operating_revenue": current_value,
                "current_net_profit": current_value,
                "prior_financial_end_date": pd.Timestamp("2021-12-31"),
                "prior_info_publ_date": signal - pd.Timedelta(days=30),
                "prior_total_operating_revenue": prior_value,
                "prior_net_profit": prior_value,
                "prior_fy_financial_end_date": pd.Timestamp("2021-12-31"),
                "prior_fy_info_publ_date": signal - pd.Timedelta(days=30),
                "prior_fy_total_operating_revenue": prior_value,
                "prior_fy_net_profit": prior_value,
                "ttm_revenue": current_value,
                "ttm_revenue_formula": "annual_current",
                "ttm_net_profit": current_value,
                "ttm_net_profit_formula": "annual_current",
                "balance_end_date": pd.Timestamp("2022-12-31"),
                "balance_period_available_date": signal - pd.Timedelta(days=10),
                "balance_info_publ_date": signal - pd.Timedelta(days=10),
                "balance_total_shareholder_equity": current_value,
                "market_value": market_value,
                "negotiable_market_value": market_value * 0.8,
                "book_to_price": value_raw,
                "earnings_to_price": value_raw,
                "sales_to_price": value_raw,
                "dividend_yield": np.nan,
                "revenue_growth_symmetric": growth_raw,
                "net_profit_growth_symmetric": growth_raw,
                "size_group": size,
                "style_group": style,
                "style_box": box,
                "book_to_price_source_date": signal - pd.Timedelta(days=10),
                "earnings_to_price_source_date": signal - pd.Timedelta(days=8),
                "sales_to_price_source_date": signal - pd.Timedelta(days=8),
                "ttm_income_source_date": signal - pd.Timedelta(days=8),
                "dividend_source_date": pd.NaT,
                "dividend_age_trading_days": np.nan,
                "dividend_is_fresh": False,
            }
        )
    frame = pd.DataFrame(rows)
    if invalid_first_row:
        frame.loc[
            0,
            [
                "current_total_operating_revenue",
                "current_net_profit",
                "ttm_revenue",
                "ttm_net_profit",
                "earnings_to_price",
                "sales_to_price",
                "revenue_growth_symmetric",
                "net_profit_growth_symmetric",
            ],
        ] = np.nan
        frame.loc[0, ["style_group", "style_box"]] = pd.NA
    eps = np.finfo(np.float64).eps
    frame["revenue_growth_symmetric"] = 2.0 * (
        frame["current_total_operating_revenue"]
        - frame["prior_total_operating_revenue"]
    ) / (
        frame["current_total_operating_revenue"].abs()
        + frame["prior_total_operating_revenue"].abs()
        + eps
    )
    frame["net_profit_growth_symmetric"] = 2.0 * (
        frame["current_net_profit"] - frame["prior_net_profit"]
    ) / (
        frame["current_net_profit"].abs() + frame["prior_net_profit"].abs() + eps
    )
    value_components = (
        "book_to_price",
        "earnings_to_price",
        "sales_to_price",
        "dividend_yield",
    )
    growth_components = (
        "revenue_growth_symmetric",
        "net_profit_growth_symmetric",
    )
    for component in (*value_components, *growth_components):
        values = frame[component]
        lower = values.quantile(0.01)
        upper = values.quantile(0.99)
        winsorised = values.clip(lower=lower, upper=upper)
        count = winsorised.count()
        rank = winsorised.rank(method="average")
        frame[f"{component}_winsorised"] = winsorised
        frame[f"{component}_rank"] = (
            (rank - 1.0) / (count - 1.0) if count > 1 else rank.where(rank.isna(), 0.5)
        )
    frame["value_core_component_count"] = frame[list(value_components[:3])].notna().sum(axis=1)
    frame["value_component_count"] = frame[list(value_components)].notna().sum(axis=1)
    frame["growth_component_count"] = frame[list(growth_components)].notna().sum(axis=1)
    frame["value_score"] = frame[
        [f"{name}_rank" for name in value_components]
    ].mean(axis=1, skipna=True).where(frame["value_core_component_count"].ge(2))
    frame["growth_score"] = frame[
        [f"{name}_rank" for name in growth_components]
    ].mean(axis=1, skipna=True).where(frame["growth_component_count"].ge(1))
    frame["style_score"] = frame["growth_score"] - frame["value_score"]
    frame["is_style_valid"] = frame["style_score"].notna()
    frame["log_market_value"] = np.log(frame["market_value"])
    frame["size_rank"] = (frame["log_market_value"].rank(method="average") - 1.0) / (
        len(frame) - 1.0
    )
    frame["size_signal"] = -frame["size_rank"]
    return frame


def test_pit_validator_handles_nullable_extension_dtypes_without_marking_missing_valid() -> None:
    nullable = _pit_frame(invalid_first_row=True)
    for column in nullable.columns:
        if pd.api.types.is_numeric_dtype(nullable[column].dtype):
            nullable[column] = nullable[column].astype("Float64")
    nullable["eligible"] = nullable["eligible"].astype("boolean")
    nullable["dividend_is_fresh"] = nullable["dividend_is_fresh"].astype("boolean")
    nullable["is_style_valid"] = nullable["is_style_valid"].astype("boolean")
    nullable.loc[0, "dividend_is_fresh"] = pd.NA
    nullable.loc[0, "is_style_valid"] = pd.NA
    nullable["style_group"] = nullable["style_group"].astype("string")
    nullable["style_box"] = nullable["style_box"].astype("string")

    checks = validate_pit_style_inputs(nullable)
    assert checks["future_disclosure_count"] == 0
    assert checks["value_core_component_count_max_abs_error"] <= 1e-12
    assert checks["growth_component_count_max_abs_error"] <= 1e-12
    assert checks["is_style_valid_mismatch_count"] == 0
    assert checks["style_box_mismatch_count"] == 0
    assert pd.isna(nullable.loc[0, "style_box"])

    corrupted = nullable.copy()
    corrupted.loc[1, "book_to_price"] += 0.5
    with pytest.raises(AssertionError, match="PIT逐层独立重算不一致"):
        validate_pit_style_inputs(corrupted)


@pytest.mark.parametrize(
    ("column", "increment"),
    (
        ("book_to_price", 0.3),
        ("current_total_operating_revenue", 1.0),
        ("book_to_price_winsorised", 0.2),
        ("book_to_price_rank", 0.2),
        ("value_score", 0.2),
    ),
)
def test_pit_validator_rejects_each_tampered_numeric_layer(
    column: str,
    increment: float,
) -> None:
    corrupted = _pit_frame()
    corrupted.loc[0, column] += increment
    with pytest.raises(AssertionError, match="PIT逐层独立重算不一致"):
        validate_pit_style_inputs(corrupted)


def test_pit_validator_rejects_tampered_style_box_label() -> None:
    corrupted = _pit_frame()
    corrupted.loc[0, "style_box"] = "BG"
    with pytest.raises(AssertionError, match="PIT逐层独立重算不一致"):
        validate_pit_style_inputs(corrupted)


def _event_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2023-04-03"),
                "holding_month": "2023-04",
                "sample_phase": "formal_oos",
                "portfolio": "ALL_A",
                "stock_code": "000001",
                "price_source_date": pd.Timestamp("2023-04-03"),
                "price_age_trading_days": 0,
                "event_type": "none",
                "event_effective_date": pd.NaT,
                "event_source": "none_required",
                "selected_for_valuation": True,
                "valuation_source_priority": 10,
                "valuation_status": "observable_market_mark",
                "valuation_selection_reason": "same_day_observable_market_preferred",
                "valuation_candidate_count": 1,
                "valuation_candidate_sources": "observable_market_mark|none|none_required",
                "valuation_conflict_resolved": False,
                "has_auditable_valuation_path": True,
                "mark_reconciliation_error": 0.0,
                "unexplained_stale_residual": False,
                "blocking": False,
                "settlement_holding_error": 0.0,
                "settlement_cash_error": 0.0,
                "settlement_return_error": 0.0,
            }
        ]
    )


def _detail_fixture() -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    pit = _pit_frame()
    memberships = pit[["signal_date", "stock_code", "style_box"]].copy()
    memberships["target_weight"] = 1.0
    m2 = SimpleNamespace(
        pit_style_inputs=pit,
        factor_long=pit,
        box_memberships=memberships,
    )
    base = {
        "signal_date": pd.Timestamp("2023-03-31"),
        "holding_month": "2023-04",
        "sample_phase": "formal_oos",
        "portfolio": "ALL_A",
        "stock_code": "000001",
    }
    m3 = SimpleNamespace(
        target_weights=pd.DataFrame([{**base, "target_weight": 1.0}]),
        holdings=pd.DataFrame([{**base, "actual_weight": 1.0}]),
        actual_weights=pd.DataFrame([{**base, "actual_weight": 1.0}]),
        trades=pd.DataFrame([{**base, "side": "BUY", "gross_notional": 1.0}]),
        unfilled_orders=pd.DataFrame(
            columns=[*base.keys(), "side", "unfilled_notional"]
        ),
        turnover=pd.DataFrame([{**base, "one_way_turnover": 0.5}]),
        costs=pd.DataFrame([{**base, "total_cost": 0.001}]),
        coverage=pd.DataFrame([{**base, "cash_weight": 0.0}]),
        security_event_audit=_event_frame(),
    )
    dataset = SimpleNamespace(
        ic_observations=pd.DataFrame(
            [
                {
                    "horizon_months": 1,
                    "holding_month": "2023-04",
                    "factor": "Style",
                    "factor_value": 0.2,
                    "stock_code": "000001",
                }
            ]
        )
    )
    return dataset, m2, m3


def test_pit_event_and_12_table_manifest_roundtrip(tmp_path: Path) -> None:
    pit_checks = validate_pit_style_inputs(_pit_frame())
    event_checks = validate_security_event_audit(_event_frame())
    assert pit_checks["future_disclosure_count"] == 0
    assert pit_checks["style_box_mismatch_count"] == 0
    assert max(
        value for key, value in pit_checks.items() if key.endswith("_max_abs_error")
    ) <= 1e-12
    assert event_checks["unexplained_stale_residual_count"] == 0
    dataset, m2, m3 = _detail_fixture()
    manifest = write_detail_tables(dataset, m2, m3, tmp_path)
    assert len(manifest["tables"]) == 12
    records = {record["table_name"]: record for record in manifest["tables"]}
    assert {"pit_style_inputs", "security_event_audit"}.issubset(records)
    assert all(record["readback_matches_written_frame"] for record in records.values())
    assert all(len(record["sha256"]) == 64 for record in records.values())


def test_three_return_layers_and_cumulative_cost_reconcile() -> None:
    daily = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2023-04-03"),
                "holding_month": "2023-04",
                "sample_phase": "formal_oos",
                "portfolio": "ALL_A",
                "target_reference_return": np.nan,
                "actual_gross_before_cost_return": 0.10,
                "actual_net_return": 0.085,
                "gross_return": 0.10,
                "net_return": 0.085,
                "gross_cash": 0.10,
                "net_cash": 0.085,
            }
        ]
    )
    monthly = daily.rename(columns={"date": "end_date"}).assign(
        target_reference_return=0.12
    )
    factors = pd.DataFrame(
        [
            {
                "frequency": frequency,
                "date": pd.Timestamp("2023-04-03"),
                "holding_month": "2023-04",
                "sample_phase": "formal_oos",
                "factor": "SMB",
                "target_reference_return": np.nan if frequency == "daily" else 0.01,
                "actual_gross_before_cost_return": 0.0,
                "actual_net_return": 0.0,
            }
            for frequency in ("daily", "monthly")
        ]
    )
    costs = pd.DataFrame(
        [
            {
                "holding_month": "2023-04",
                "sample_phase": "formal_oos",
                "portfolio": "ALL_A",
                "total_cost": 0.01,
            },
            {
                "holding_month": "2023-04",
                "sample_phase": "formal_oos",
                "portfolio": "ALL_A",
                "total_cost": 0.005,
                "event_driven": True,
            },
        ]
    )
    result = build_return_series(
        SimpleNamespace(
            daily_portfolio=daily,
            monthly_portfolio=monthly,
            factor_returns=factors,
            costs=costs,
        )
    )
    all_a = result.loc[result["entity"].astype(str).eq("ALL_A")]
    assert all_a.loc[all_a["frequency"].eq("monthly"), "target_reference_available"].all()
    assert not all_a.loc[all_a["frequency"].eq("daily"), "target_reference_available"].any()
    assert set(
        all_a.loc[all_a["frequency"].eq("monthly"), "target_reference_frequency_contract"]
    ) == {"monthly_available"}
    assert set(
        all_a.loc[all_a["frequency"].eq("daily"), "target_reference_frequency_contract"]
    ) == {"daily_unavailable"}
    semantics = all_a["target_reference_semantics"].drop_duplicates().tolist()
    assert len(semantics) == 1
    assert "月度目标组合参考收益可用" in semantics[0]
    assert "日频目标参考收益不可用" in semantics[0]
    assert all_a["cost_cash_reconciliation_error"].abs().max() <= 1e-12
    assert (all_a["actual_before_cost_nav"] >= all_a["actual_after_cost_net_nav"]).all()


def test_entity_audit_aggregates_rebalance_and_event_rows_on_one_monthly_nav() -> None:
    key = {
        "signal_date": pd.Timestamp("2024-04-30"),
        "holding_month": "2024-05",
        "sample_phase": "formal_oos",
        "portfolio": "ALL_A",
    }
    turnover = pd.DataFrame(
        [
            {
                **key,
                "date": pd.Timestamp("2024-05-08"),
                "buy_notional": 0.25,
                "sell_notional": 0.15,
                "gross_traded_notional": 0.40,
                "two_sided_turnover": 0.20,
                "one_way_turnover": 0.10,
                "event_driven": False,
            },
            {
                **key,
                "date": pd.Timestamp("2024-05-20"),
                "buy_notional": 0.0,
                "sell_notional": 0.10,
                "gross_traded_notional": 0.10,
                "two_sided_turnover": np.nan,
                "one_way_turnover": np.nan,
                "event_driven": True,
            },
        ]
    )
    costs = pd.DataFrame(
        [
            {
                **key,
                "date": pd.Timestamp("2024-05-08"),
                "commission_cost": 0.001,
                "slippage_cost": 0.001,
                "stamp_tax": 0.002,
                "total_cost": 0.004,
                "cost_rate_on_pretrade_nav": 0.002,
                "event_driven": False,
            },
            {
                **key,
                "date": pd.Timestamp("2024-05-20"),
                "commission_cost": 0.0002,
                "slippage_cost": 0.0003,
                "stamp_tax": 0.0005,
                "total_cost": 0.001,
                "cost_rate_on_pretrade_nav": np.nan,
                "event_driven": True,
            },
        ]
    )
    coverage = pd.DataFrame(
        [
            {
                **key,
                "date": pd.Timestamp("2024-05-08"),
                "execution_price_coverage": 0.99,
                "buy_tradable_coverage": 0.98,
                "cash_weight": 0.02,
                "unfilled_order_count": 1,
                "unfilled_notional": 0.03,
            }
        ]
    )
    monthly = pd.DataFrame(
        [
            {
                "holding_month": "2024-05",
                "sample_phase": "formal_oos",
                "portfolio": "ALL_A",
                "start_date": pd.Timestamp("2024-05-08"),
                "start_net_nav": 2.0,
            }
        ]
    )
    audit = _build_entity_audit(
        SimpleNamespace(
            turnover=turnover,
            costs=costs,
            coverage=coverage,
            monthly_portfolio=monthly,
        )
    )
    row = audit.loc[audit["entity"].eq("ALL_A")].iloc[0]
    assert len(audit.loc[audit["entity"].eq("ALL_A")]) == 1
    assert abs(row["gross_traded_notional"] - turnover["gross_traded_notional"].sum()) <= 1e-12
    assert abs(row["two_sided_turnover"] - 0.25) <= 1e-12
    assert abs(row["one_way_turnover"] - 0.125) <= 1e-12
    for column in ("commission_cost", "slippage_cost", "stamp_tax", "total_cost"):
        assert abs(row[column] - costs[column].sum()) <= 1e-12
    assert abs(row["cost_rate_on_pretrade_nav"] - 0.0025) <= 1e-12
    assert row["date"] == pd.Timestamp("2024-05-08")
    assert row["turnover_first_date"] == pd.Timestamp("2024-05-08")
    assert row["turnover_last_date"] == pd.Timestamp("2024-05-20")
    assert row["turnover_record_count"] == 2
    assert row["cost_record_count"] == 2


def _pending_payload(assumptions: pd.DataFrame, checks: pd.DataFrame) -> dict[str, object]:
    workbook_layout = (
        ("backtest_summary.xlsx", 10),
        ("factor_analysis.xlsx", 10),
        ("style_box_returns.xlsx", 9),
        ("portfolio_holdings.xlsx", 8),
        ("trading_audit.xlsx", 9),
    )
    sheets = [
        {"name": "Assumptions", "columns": list(assumptions.columns), "rows": assumptions.values.tolist()},
        {"name": "Checks", "columns": list(checks.columns), "rows": checks.values.tolist()},
        {"name": "Sources", "columns": ["source"], "rows": [["pending"]]},
    ]
    return {
        "report_id": "r004_all_a_style_box",
        "reproduction_mode": "experimental",
        "verification_status": "pending_verifier",
        "verification_state": "pending_verifier",
        "verdict": None,
        "verification_context": None,
        "final_boundary_disclosures": [
            {"disclosure_id": disclosure_id, "text": text}
            for disclosure_id, text in build_boundary_disclosures(
                DEFAULT_CONFIG, pd.Timestamp("2026-01-05")
            )
        ],
        "workbooks": [
            {
                "filename": filename,
                "title": filename,
                "subtitle": "pending_verifier；本工作簿不构成验证通过结论",
                "sheets": [
                    *json.loads(json.dumps(sheets)),
                    *[
                        {
                            "name": f"Extra{index}",
                            "columns": ["value"],
                            "rows": [[index]],
                        }
                        for index in range(1, sheet_count_without_cover - len(sheets) + 1)
                    ],
                ],
            }
            for filename, sheet_count_without_cover in workbook_layout
        ],
    }


def _complete_assumptions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "assumption_id": f"AS{index}",
                "title": f"假设{index}",
                "来源": "spec/plan冻结口径",
                "假设内容": f"第{index}条完整假设内容",
                "行业惯例依据": "中国股票量化回测时点与交易惯例",
                "影响面": "method",
                "影响 milestone": "m1,m2,m3,m4",
                "影响指标": "正式OOS指标与审计证据",
                "预期影响": "影响方向由正式证据逐项解释",
                "验证后回看": f"verifier已对AS{index}逐项回看并绑定证据",
                "状态": "assumed",
                "高亮等级": "major-auto",
            }
            for index in range(1, 25)
        ]
    )


def _verification_context(assumptions: pd.DataFrame) -> dict[str, object]:
    return {
        "schema_version": 1,
        "verification_status": "verified",
        "verdict": "PASS",
        "assumptions_sha256": assumption_frame_sha256(assumptions),
        "check_results": {f"check_{index}": "PASS" for index in range(1, 8)},
        "boundary_disclosures_acknowledged": [
            "experimental_china_transplant",
            "oos_months",
            "beijing_exchange_included",
            "security_lifecycle_boundary",
            "trading_constraints_and_costs",
            "terminal_accounting_date",
            "not_investment_advice",
        ],
        "verified_at": "2026-07-18T12:00:00+08:00",
        "verify_report": "output/r004_all_a_style_box/verify_report.md",
        "evidence_manifest": "workspace/r004_all_a_style_box/audit/evidence_manifest.md",
    }


@pytest.mark.parametrize("failure_mode", ("missing_id", "duplicate_id", "missing_field", "placeholder"))
def test_finalizer_rejects_incomplete_assumption_registry(failure_mode: str) -> None:
    assumptions = _complete_assumptions()
    if failure_mode == "missing_id":
        assumptions = assumptions.loc[assumptions["assumption_id"].ne("AS24")].copy()
    elif failure_mode == "duplicate_id":
        assumptions.loc[23, "assumption_id"] = "AS23"
    elif failure_mode == "missing_field":
        assumptions.loc[0, "行业惯例依据"] = ""
    else:
        assumptions.loc[0, "验证后回看"] = "[verify 后填]"
    checks = pd.DataFrame(
        [{"check_id": f"check_{index}", "verifier_result": None} for index in range(1, 8)]
    )
    context = _verification_context(assumptions)
    with pytest.raises(ValueError):
        finalize_workbook_payload(_pending_payload(assumptions, checks), assumptions, context)


def test_verifier_context_finalizes_excel_without_pending(tmp_path: Path) -> None:
    assumptions = _complete_assumptions()
    validated = validate_assumption_registry_for_finalization(assumptions)
    assert validated["assumption_id"].tolist() == [f"AS{index}" for index in range(1, 25)]
    checks = pd.DataFrame(
        [
            {"check_id": f"check_{index}", "verifier_result": None}
            for index in range(1, 8)
        ]
    )
    context = _verification_context(assumptions)
    payload = finalize_workbook_payload(_pending_payload(assumptions, checks), assumptions, context)
    assert payload["verification_status"] == "verified/PASS"
    assert all("pending_verifier" not in workbook["subtitle"] for workbook in payload["workbooks"])
    manifest_path = _run_workbook_builder(payload, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["workbooks"]) == 5
    assert sum(workbook["sheet_count"] for workbook in manifest["workbooks"]) == 51
    for filename in (workbook["filename"] for workbook in payload["workbooks"]):
        book = openpyxl.load_workbook(tmp_path / filename, read_only=False)
        cover = dict(book["Cover"].iter_rows(min_col=1, max_col=2, values_only=True))
        assert cover["验证状态"] == "verified/PASS"
        assert cover["验证结论"] == "PASS"
        assert all(sheet.freeze_panes == "A2" for sheet in book.worksheets)
        book.close()


def test_comparison_required_keys_cover_exact_r10_and_sa4_core_values() -> None:
    entities = ("BV", "BG", "SV", "SG", "SMB", "HML", "GML", "ALL_A", "STYLE_1N")
    performance = pd.DataFrame(
        [
            {
                "frequency": "monthly",
                "entity": entity,
                "annualized_net_return": 0.01 + index * 0.001,
                "annualized_net_volatility": 0.10 + index * 0.001,
                "net_sharpe_zero_cash": 0.10 + index * 0.01,
            }
            for index, entity in enumerate(entities)
        ]
    )
    benchmarks = pd.DataFrame(
        [
            {
                "entity": entity,
                "benchmark": benchmark,
                "annualized_excess_return": 0.01,
                "annualized_tracking_error": 0.02,
                "information_ratio": 0.5,
            }
            for benchmark in ("ALL_A", "STYLE_1N")
            for entity in entities
            if entity != benchmark
        ]
    )
    dataset = SimpleNamespace(
        performance_summary=performance,
        benchmark_comparison=benchmarks,
        correlation_matrix=pd.DataFrame(index=range(49)),
        winner_frequency=pd.DataFrame(
            [{"winner_frequency": 1.0, "n_months": 33}]
        ),
        return_series=pd.DataFrame(
            [
                {
                    "frequency": "monthly",
                    "date": pd.Timestamp("2026-01-05"),
                }
            ]
        ),
    )
    payload = build_comparison_payload(dataset, DEFAULT_CONFIG)
    core = [
        metric
        for metric in payload["metrics"]
        if metric["element_id"] in {"R10", "SA4"}
    ]
    assert len([metric for metric in core if metric["element_id"] == "R10"]) == 27
    assert len([metric for metric in core if metric["element_id"] == "SA4"]) == 48
    assert len({metric["key"] for metric in core}) == 75
    assert payload["required_key_contract"]["R10_count"] == 27
    assert payload["required_key_contract"]["SA4_count"] == 48


def test_boundary_disclosure_uses_runtime_config_and_terminal_date() -> None:
    perturbed = replace(DEFAULT_CONFIG, oos_end="2025-11-30")
    disclosures = dict(
        build_boundary_disclosures(perturbed, pd.Timestamp("2025-12-01"))
    )
    assert "2023-04至2025-11共32个持有月" in disclosures["oos_months"]
    assert "2025-12-01" in disclosures["terminal_accounting_date"]


def test_security_event_validator_rejects_duplicate_valuation_keys() -> None:
    duplicate = pd.concat([_event_frame(), _event_frame()], ignore_index=True)
    with pytest.raises(AssertionError, match="duplicate=2"):
        validate_security_event_audit(duplicate)


def test_perturbation_contract_is_independent_and_replayable(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    perturbation = tmp_path / "perturbation"
    baseline.mkdir()
    perturbation.mkdir()
    (baseline / "formal.txt").write_text("unchanged", encoding="utf-8")
    before = _snapshot_file_hashes(baseline)
    perturbation_config = replace(DEFAULT_CONFIG, oos_end="2025-11-30")
    boundaries = [
        {"disclosure_id": disclosure_id, "text": text}
        for disclosure_id, text in build_boundary_disclosures(
            perturbation_config, pd.Timestamp("2025-12-01")
        )
    ]
    (perturbation / "metrics.json").write_text(
        json.dumps(
            {
                "report_id": "r004_all_a_style_box",
                "oos": {
                    "start": "2023-04-01",
                    "end": "2025-11-30",
                    "n_months": 32,
                },
                "final_boundary_disclosures": boundaries,
            }
        ),
        encoding="utf-8",
    )
    r10_keys = [f"R10_required_{index}" for index in range(27)]
    sa4_keys = [f"SA4_required_{index}" for index in range(48)]
    (perturbation / "comparison.json").write_text(
        json.dumps(
            {
                "final_boundary_disclosures": boundaries,
                "required_key_contract": {
                    "R10": r10_keys,
                    "SA4": sa4_keys,
                    "R10_count": 27,
                    "SA4_count": 48,
                },
                "metrics": [
                    {"key": "R4_china_oos_correlation_cells", "reproduced_value": 49},
                    {"key": "R7_china_style_box_winner_frequency_sum", "reproduced_value": 1.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    (perturbation / "workbook_payload.pending.json").write_text(
        json.dumps({"final_boundary_disclosures": boundaries}), encoding="utf-8"
    )
    (perturbation / "detail_tables").mkdir()
    _pit_frame().to_parquet(perturbation / "detail_tables/pit_style_inputs.parquet", index=False)
    _event_frame().to_parquet(
        perturbation / "detail_tables/security_event_audit.parquet", index=False
    )
    (perturbation / "detail_manifest.json").write_text(
        json.dumps({"tables": [{"table_name": f"t{index}"} for index in range(12)]}),
        encoding="utf-8",
    )
    contract = write_perturbation_replay_contract(
        perturbation_dir=perturbation,
        baseline_results_dir=baseline,
        baseline_hashes_before=before,
        config_diff={"oos_end": {"baseline": "2025-12-31", "perturbed": "2025-11-30"}},
        command="python -m src.r004_all_a_style_box.main --perturbation-oos-end 2025-11-30",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        exit_code=0,
    )
    payload = json.loads(contract.read_text(encoding="utf-8"))
    assert payload["baseline_unchanged"] is True
    assert payload["key_checks"]["R4_cell_count"] == 49
    assert payload["key_checks"]["PIT"]["future_disclosure_count"] == 0
    assert payload["key_checks"]["oos_month_count"] == 32
    assert (perturbation / "config_diff.json").is_file()


def test_group_cumulative_date_axis_has_at_most_12_rotated_labels() -> None:
    fig, axis = plt.subplots()
    dates = pd.date_range("2023-04-30", periods=33, freq="ME")
    axis.plot(dates, np.arange(len(dates)))
    _configure_date_axis(axis, dates)
    labels = axis.get_xticklabels()
    assert 1 <= len(labels) <= 12
    assert all(label.get_rotation() == 35 for label in labels)
    assert all(label.get_ha() == "right" for label in labels)
    plt.close(fig)
