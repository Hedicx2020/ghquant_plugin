"""r004 iter_03：600466→400165 有限转板退出链定向测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import socket

import numpy as np
import pandas as pd
import pytest

from src.r004_all_a_style_box.config import DEFAULT_CONFIG
from src.r004_all_a_style_box.data_pipeline import load_frozen_transfer_market_data
from src.r004_all_a_style_box.portfolio import (
    _execute_security_transfer_exit,
    _initial_state,
    _is_pending_security_transfer,
    _is_unexplained_missing_price_residual,
    _normalise_valuation_audit,
    _transfer_window_age_trading_days,
)
from src.r004_all_a_style_box.reporting import validate_security_event_audit


def _positions(dates: pd.DatetimeIndex) -> dict[pd.Timestamp, int]:
    return {pd.Timestamp(value).normalize(): index for index, value in enumerate(dates)}


def _transfer_state(shares: float = 100.0):
    state = _initial_state(DEFAULT_CONFIG)
    state.shares.loc[DEFAULT_CONFIG.security_transfer_old_code] = shares
    state.current_target_weights.loc[DEFAULT_CONFIG.security_transfer_old_code] = 0.0
    state.zero_target_rebalances.loc[DEFAULT_CONFIG.security_transfer_old_code] = 0
    state.last_prices.loc[DEFAULT_CONFIG.security_transfer_old_code] = (
        DEFAULT_CONFIG.security_transfer_old_mark
    )
    state.last_price_dates.loc[DEFAULT_CONFIG.security_transfer_old_code] = pd.Timestamp(
        DEFAULT_CONFIG.security_transfer_old_mark_date
    )
    state.active_holding_month = "2023-07"
    state.active_sample_phase = "formal_oos"
    state.active_signal_date = pd.Timestamp("2023-06-30")
    return state


def test_frozen_transfer_market_replays_offline_with_exact_first_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def network_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("正式运行不得联网")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    market = load_frozen_transfer_market_data()
    first = market.iloc[0]
    assert len(market) == DEFAULT_CONFIG.security_transfer_market_row_count == 429
    assert first["stock_code"] == "400165"
    assert first["date"] == pd.Timestamp("2023-07-26")
    assert np.allclose(first[["open", "high", "low", "close"]], 0.38)
    assert first["volumn"] == 5_753_700.0
    assert first["volume_shares"] == first["volumn"]
    assert first["volume_unit"] == "shares"
    assert np.isnan(first["amount"])
    assert not first["amount_available"]
    assert first["amount_status"] == "unavailable"
    assert first["daily_vwap"] == 0.38
    assert first["vwap_proof_method"] == (
        "positive_volume_and_identical_ohlc_single_price"
    )
    assert first["external_source_sha256"] == dict(
        DEFAULT_CONFIG.security_transfer_frozen_sha256
    )[DEFAULT_CONFIG.security_transfer_market_raw_filename]


def test_frozen_transfer_market_blocks_any_hash_tamper(tmp_path: Path) -> None:
    copied = tmp_path / "frozen"
    shutil.copytree(DEFAULT_CONFIG.security_transfer_data_root, copied)
    raw = copied / DEFAULT_CONFIG.security_transfer_market_raw_filename
    raw.write_bytes(raw.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256不符"):
        load_frozen_transfer_market_data(data_root=copied)


def test_transfer_wait_is_code_scoped_and_ordinary_twenty_day_gate_is_unchanged() -> None:
    dates = pd.bdate_range("2023-06-06", "2023-07-26")
    positions = _positions(dates)
    pending, age = _is_pending_security_transfer(
        "600466", pd.Timestamp("2023-06-07"), positions, DEFAULT_CONFIG
    )
    assert pending and age == 2
    assert _is_pending_security_transfer(
        "400165", pd.Timestamp("2023-06-07"), positions, DEFAULT_CONFIG
    ) == (False, 0)
    assert not _is_pending_security_transfer(
        "600466", pd.Timestamp("2023-07-26"), positions, DEFAULT_CONFIG
    )[0]
    assert _is_unexplained_missing_price_residual(
        active_suspension=True,
        has_auditable_valuation_path=False,
        price_age_trading_days=21,
        config=DEFAULT_CONFIG,
    )


def test_transfer_exit_is_one_to_one_capacity_bounded_and_cost_reconciled() -> None:
    state = _transfer_state()
    market = load_frozen_transfer_market_data()
    first_day = market.loc[market["date"].eq(pd.Timestamp("2023-07-26"))]
    dates = pd.bdate_range("2023-06-06", "2023-07-26")
    net_cash_before = state.net_cash
    gross_cash_before = state.gross_cash
    trades, audit_records, cost = _execute_security_transfer_exit(
        state,
        portfolio="ALL_A",
        date=pd.Timestamp("2023-07-26"),
        daily_status=first_day,
        trading_day_position=_positions(dates),
        config=DEFAULT_CONFIG,
    )
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["stock_code"] == "400165"
    assert trade["shares"] == 100.0
    assert trade["vwap"] == 0.38
    assert np.isclose(trade["gross_notional"], 38.0)
    expected_cost = 38.0 * (
        DEFAULT_CONFIG.commission_rate
        + DEFAULT_CONFIG.slippage_rate
        + DEFAULT_CONFIG.stamp_tax_before_2023_08_28
    )
    assert np.isclose(cost, expected_cost)
    assert np.isclose(state.net_cash - net_cash_before, 38.0 - expected_cost)
    assert np.isclose(state.gross_cash - gross_cash_before, 38.0)
    assert "600466" not in state.shares
    assert "400165" not in state.shares

    audit = _normalise_valuation_audit(audit_records, config=DEFAULT_CONFIG)
    checks = validate_security_event_audit(audit, config=DEFAULT_CONFIG)
    row = audit.iloc[0]
    assert checks["transfer_exit_count"] == 1
    assert checks["invalid_transfer_exit_count"] == 0
    assert row["mapped_shares"] == row["old_shares_before"]
    assert row["exit_shares"] <= row["volumn"]
    assert np.isnan(row["amount"])
    assert not row["amount_available"]
    assert row["vwap_proof_method"] == (
        "positive_volume_and_identical_ohlc_single_price"
    )


def test_transfer_exit_blocks_missing_market_capacity_and_over_45_days() -> None:
    dates = pd.bdate_range("2023-06-06", "2023-07-26")
    positions = _positions(dates)
    with pytest.raises(RuntimeError, match="缺冻结行情"):
        _execute_security_transfer_exit(
            _transfer_state(),
            portfolio="ALL_A",
            date=pd.Timestamp("2023-07-26"),
            daily_status=pd.DataFrame(),
            trading_day_position=positions,
            config=DEFAULT_CONFIG,
        )

    market = load_frozen_transfer_market_data()
    first_day = market.loc[market["date"].eq(pd.Timestamp("2023-07-26"))]
    with pytest.raises(RuntimeError, match="超过400165首日真实成交量"):
        _execute_security_transfer_exit(
            _transfer_state(6_000_000.0),
            portfolio="ALL_A",
            date=pd.Timestamp("2023-07-26"),
            daily_status=first_day,
            trading_day_position=positions,
            config=DEFAULT_CONFIG,
        )

    later_config = replace(
        DEFAULT_CONFIG,
        security_transfer_mapping_public_date=pd.Timestamp("2023-09-01").date(),
        security_transfer_effective_date=pd.Timestamp("2023-09-01").date(),
    )
    later_dates = pd.bdate_range("2023-06-06", periods=46)
    later_positions = _positions(later_dates)
    assert _transfer_window_age_trading_days(
        later_dates[-1], later_positions, later_config
    ) == 46
    with pytest.raises(RuntimeError, match="超过官方45交易日"):
        _execute_security_transfer_exit(
            _transfer_state(),
            portfolio="ALL_A",
            date=later_dates[-1],
            daily_status=pd.DataFrame(),
            trading_day_position=later_positions,
            config=later_config,
        )


def test_transfer_audit_rejects_pre_public_successor_disclosure() -> None:
    state = _transfer_state()
    market = load_frozen_transfer_market_data()
    dates = pd.bdate_range("2023-06-06", "2023-07-26")
    _, audit_records, _ = _execute_security_transfer_exit(
        state,
        portfolio="ALL_A",
        date=pd.Timestamp("2023-07-26"),
        daily_status=market.iloc[[0]],
        trading_day_position=_positions(dates),
        config=DEFAULT_CONFIG,
    )
    audit = _normalise_valuation_audit(audit_records, config=DEFAULT_CONFIG)
    audit.loc[0, "date"] = pd.Timestamp("2023-07-25")
    with pytest.raises(AssertionError, match="pre_mapping_successor"):
        validate_security_event_audit(audit, config=DEFAULT_CONFIG)
