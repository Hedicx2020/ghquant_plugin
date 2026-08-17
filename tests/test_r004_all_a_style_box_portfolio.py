"""r004 iter_01 正式 OOS 现金初始化与生命周期阻断。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r004_all_a_style_box.data_pipeline import build_m1_dataset
from src.r004_all_a_style_box.config import DEFAULT_CONFIG
from src.r004_all_a_style_box.portfolio import (
    _execute_delisting_risk_exit,
    _execute_zero_target_residual_exit,
    _find_unexplained_zero_target_codes,
    _initial_state,
    _is_unexplained_missing_price_residual,
    _normalise_valuation_audit,
    build_m3_dataset,
)
from src.r004_all_a_style_box.reporting import build_return_series
from src.r004_all_a_style_box.strategy import build_m2_dataset


def test_risk_exit_waits_through_limit_down_until_first_daily_can_sell() -> None:
    state = _initial_state(DEFAULT_CONFIG)
    state.shares.loc["000001"] = 100.0
    state.current_target_weights.loc["000001"] = 0.0
    state.zero_target_rebalances.loc["000001"] = 1
    state.last_prices.loc["000001"] = 10.0
    state.last_price_dates.loc["000001"] = pd.Timestamp("2024-05-05")
    state.active_holding_month = "2024-05"
    state.active_sample_phase = "formal_oos"
    state.active_signal_date = pd.Timestamp("2024-04-30")
    events = pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "event_type": "delisting_risk_warning_exit",
                "announcement_date": pd.Timestamp("2024-05-05"),
                "event_effective_date": pd.Timestamp("2024-05-06"),
                "action": "risk_exit_on_next_trade",
                "event_source": "official_test_event",
            }
        ]
    ).set_index(pd.Index([0]))
    limit_down = pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "daily_can_sell": False,
                "daily_vwap_valid": True,
                "daily_vwap": 9.0,
                "active_suspension": False,
                "daily_no_volume": False,
                "daily_limit_down": True,
                "volume": 1_000_000.0,
            }
        ]
    )
    trades, audit, cost = _execute_delisting_risk_exit(
        state,
        portfolio="ALL_A",
        date=pd.Timestamp("2024-05-06"),
        daily_status=limit_down,
        events=events,
        config=DEFAULT_CONFIG,
    )
    assert trades.empty
    assert cost == 0.0
    assert state.shares.loc["000001"] == 100.0
    assert len(audit) == 1
    assert audit[0]["rule_label"] == "risk_exit_waiting_daily_can_sell"
    assert np.isnan(audit[0]["executed_vwap"])

    sellable = limit_down.assign(daily_can_sell=True, daily_limit_down=False, daily_vwap=8.5)
    trades, audit, cost = _execute_delisting_risk_exit(
        state,
        portfolio="ALL_A",
        date=pd.Timestamp("2024-05-07"),
        daily_status=sellable,
        events=events,
        config=DEFAULT_CONFIG,
    )
    assert len(trades) == 1
    assert "000001" not in state.shares.index
    assert trades.iloc[0]["vwap"] == 8.5
    assert trades.iloc[0]["date"] == pd.Timestamp("2024-05-07")
    assert cost == trades.iloc[0]["total_cost"]
    assert audit[0]["executed_vwap"] == 8.5
    assert audit[0]["executed_market_volume"] == 1_000_000.0


def test_zero_target_residual_gate_scans_all_holdings_and_honours_exemptions() -> None:
    state = _initial_state(DEFAULT_CONFIG)
    state.shares.loc["000001"] = 100.0
    state.current_target_weights.loc["000001"] = 0.0
    state.zero_target_rebalances.loc["000001"] = 2
    status = pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "close": 10.0,
                "daily_can_sell": True,
                "active_suspension": False,
            }
        ]
    ).set_index("stock_code")
    assert _find_unexplained_zero_target_codes(
        state,
        status,
        lifecycle_exempt_codes=set(),
        config=DEFAULT_CONFIG,
    ) == ["000001"]
    suspended = status.assign(active_suspension=True)
    assert not _find_unexplained_zero_target_codes(
        state,
        suspended,
        lifecycle_exempt_codes=set(),
        config=DEFAULT_CONFIG,
    )
    assert not _find_unexplained_zero_target_codes(
        state,
        status,
        lifecycle_exempt_codes={"000001"},
        config=DEFAULT_CONFIG,
    )
    assert _is_unexplained_missing_price_residual(
        active_suspension=False,
        has_auditable_valuation_path=False,
        price_age_trading_days=21,
        config=DEFAULT_CONFIG,
    )
    assert _is_unexplained_missing_price_residual(
        active_suspension=True,
        has_auditable_valuation_path=False,
        price_age_trading_days=21,
        config=DEFAULT_CONFIG,
    )
    assert not _is_unexplained_missing_price_residual(
        active_suspension=False,
        has_auditable_valuation_path=True,
        price_age_trading_days=21,
        config=DEFAULT_CONFIG,
    )
    state.active_holding_month = "2024-05"
    state.active_sample_phase = "formal_oos"
    state.active_signal_date = pd.Timestamp("2024-04-30")
    executable = status.assign(
        daily_vwap=9.5,
        daily_vwap_valid=True,
        daily_no_volume=False,
        volume=1_000_000.0,
    )
    trades, audit, cost = _execute_zero_target_residual_exit(
        state,
        portfolio="ALL_A",
        date=pd.Timestamp("2024-05-08"),
        status_index=executable,
        codes=["000001"],
        config=DEFAULT_CONFIG,
    )
    assert len(trades) == 1
    assert "000001" not in state.shares.index
    assert trades.iloc[0]["vwap"] == 9.5
    assert trades.iloc[0]["total_cost"] == cost
    assert audit[0]["rule_label"] == "zero_target_two_rebalances_exit_first_sellable_day"
    assert audit[0]["executed_market_volume"] == 1_000_000.0


def test_two_month_formal_oos_bridges_execution_boundaries_from_cash() -> None:
    m1 = build_m1_dataset(smoke_months=2, smoke_stock_limit=100)
    m2 = build_m2_dataset(m1.monthly_panel)
    m3 = build_m3_dataset(m1, m2)

    first = m3.coverage.sort_values(["date", "portfolio"]).groupby("portfolio").first()
    assert first["pretrade_stock_count"].eq(0).all()
    assert np.allclose(first["pretrade_cash_weight"], 1.0)
    assert m3.security_event_audit["event_type"].eq(
        "formal_oos_cash_initialization"
    ).sum() == 6
    assert np.allclose(
        m3.monthly_portfolio["actual_gross_before_cost_return"],
        m3.monthly_portfolio["gross_return"],
    )
    assert np.allclose(
        m3.monthly_portfolio["actual_net_return"],
        m3.monthly_portfolio["net_return"],
    )
    assert "target_reference_return" in m3.factor_returns
    monthly = m3.monthly_portfolio
    ledger_points = {
        "ledger_start_pretrade_vwap_net_nav",
        "ledger_posttrade_close_net_nav",
        "ledger_month_last_close_net_nav",
        "ledger_next_pretrade_vwap_net_nav",
        "ledger_start_pretrade_vwap_gross_nav",
        "ledger_posttrade_close_gross_nav",
        "ledger_month_last_close_gross_nav",
        "ledger_next_pretrade_vwap_gross_nav",
    }
    assert ledger_points.issubset(monthly.columns)
    assert monthly["ledger_net_reconciliation_error"].abs().max() <= 1e-12
    assert monthly["ledger_gross_reconciliation_error"].abs().max() <= 1e-12
    daily_compound = m3.daily_portfolio.groupby(
        ["holding_month", "portfolio"], sort=False
    ).agg(
        gross=("gross_return", lambda values: (1.0 + values).prod() - 1.0),
        net=("net_return", lambda values: (1.0 + values).prod() - 1.0),
    )
    joined = monthly.set_index(["holding_month", "portfolio"]).join(daily_compound)
    assert np.allclose(joined["gross_return"], joined["gross"], atol=1e-12, rtol=1e-12)
    assert np.allclose(joined["net_return"], joined["net"], atol=1e-12, rtol=1e-12)
    component_counts = m3.daily_portfolio.groupby(
        ["holding_month", "portfolio", "ledger_component"], sort=False
    ).size().unstack(fill_value=0)
    assert component_counts["first_bridge"].eq(1).all()
    assert component_counts["tail_bridge"].eq(1).all()


def test_33_month_oos_still_blocks_other_unclosed_delisting_assets() -> None:
    m1 = build_m1_dataset(smoke_months=33)
    m2 = build_m2_dataset(m1.monthly_panel)
    with pytest.raises(RuntimeError, match=r"risk_exit永久豁免: \['000540'\]"):
        build_m3_dataset(m1, m2)


def test_valuation_state_normalises_duplicate_behavior_and_unpriced_candidate() -> None:
    base = {
        "date": pd.Timestamp("2025-11-03"),
        "processing_date": pd.Timestamp("2025-11-03"),
        "holding_month": "2025-11",
        "sample_phase": "formal_oos",
        "portfolio": "ALL_A",
        "stock_code": "600466",
        "shares": 100.0,
        "target_weight": 0.0,
        "price_source_date": pd.Timestamp("2023-06-05"),
        "price_age_trading_days": 600,
        "consecutive_missing_price_days": 600,
        "active_suspension": False,
        "delisting_board_flag": True,
        "event_type": "announced_security_lifecycle_risk_exit",
        "announcement_date": pd.Timestamp("2023-04-28"),
        "event_effective_date": pd.Timestamp("2023-05-04"),
        "settlement_code": pd.NA,
        "settlement_ratio": 0.0,
        "settlement_cash": 0.0,
        "mark_used_in_nav": 0.4,
        "executed_vwap": np.nan,
        "executed_market_volume": np.nan,
        "settlement_holding_error": 0.0,
        "settlement_cash_error": 0.0,
        "settlement_return_error": 0.0,
    }
    candidates = [
        {
            **base,
            "event_source": "official_risk_exit;waiting_for_daily_can_sell",
            "rule_label": "risk_exit_waiting_daily_can_sell",
            "unexplained_stale_residual": False,
            "blocking": False,
        },
        {
            **base,
            "event_source": "daily_price+suspension_observation",
            "rule_label": "risk_exit_behavior_not_valuation_source",
            "unexplained_stale_residual": True,
            "blocking": True,
        },
    ]
    audit = _normalise_valuation_audit(candidates, config=DEFAULT_CONFIG)
    assert len(audit) == 1
    row = audit.iloc[0]
    assert row["selected_for_valuation"]
    assert row["valuation_status"] == "unpriced_asset"
    assert not row["has_auditable_valuation_path"]
    assert row["valuation_candidate_count"] == 2
    assert row["valuation_conflict_resolved"]
    assert "risk_exit_waiting_daily_can_sell" in row["behavior_actions"]
