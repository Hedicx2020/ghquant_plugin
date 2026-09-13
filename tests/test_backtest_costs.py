"""共享回测引擎的合成算式回归；不读取行情、不运行策略。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.allocation_backtest import portfolio_backtest
from common.backtest import long_short_backtest, quantile_backtest


def _factor_panel() -> pd.DataFrame:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    return pd.DataFrame(
        [
            {"date": date, "stock_code": stock, "factor": score, "forward_return": 0.0}
            for date, scores in zip(dates, ([1, 2, 3, 4], [4, 3, 2, 1], [4, 3, 2, 1]))
            for stock, score in zip("ABCD", scores)
        ]
    )


def test_group_costs_charge_entry_and_both_long_short_legs() -> None:
    round_trip = 0.01
    result = long_short_backtest(_factor_panel(), n_groups=2, transaction_cost=round_trip)
    qbt = result["quantile_result"]
    # 每腿：首次建仓只买一次，次期全部卖出再买入，第三期无换仓。
    expected_turnover = np.array([0.5, 1.0, 0.0])
    for group in ("G1", "G2"):
        np.testing.assert_allclose(qbt["turnover_by_date"][group], expected_turnover)
        np.testing.assert_allclose(qbt["group_costs"][group], expected_turnover * round_trip)
        assert qbt["turnover"][group] == [1.0, 0.0]
    expected_returns = -2 * expected_turnover * round_trip
    np.testing.assert_allclose(result["ls_returns"], expected_returns)
    np.testing.assert_allclose(result["ls_nav"], np.cumprod(1 + expected_returns))


def test_appending_future_data_does_not_change_historical_costs() -> None:
    panel = _factor_panel()
    prefix = quantile_backtest(panel.iloc[:8], n_groups=2, transaction_cost=0.01)
    extended = quantile_backtest(panel, n_groups=2, transaction_cost=0.01)
    for name in ("group_returns_net", "group_nav", "turnover_by_date", "group_costs"):
        pd.testing.assert_frame_equal(prefix[name], extended[name].iloc[:2])


def test_zero_cost_preserves_gross_factor_returns() -> None:
    panel = _factor_panel()
    panel["forward_return"] = panel["factor"] / 100
    result = quantile_backtest(panel, n_groups=2, transaction_cost=0.0)
    pd.testing.assert_frame_equal(result["group_returns_net"], result["group_returns"])
    np.testing.assert_allclose(result["group_returns"]["G1"], 0.015)
    np.testing.assert_allclose(result["group_returns"]["G2"], 0.035)
    np.testing.assert_allclose(result["group_returns"]["long_short"], 0.02)


@pytest.mark.parametrize("rate", [-0.01, np.nan, np.inf])
def test_invalid_transaction_cost_is_rejected(rate: float) -> None:
    with pytest.raises(ValueError, match="transaction_cost"):
        quantile_backtest(_factor_panel(), n_groups=2, transaction_cost=rate)


def test_costs_require_stock_identifiers() -> None:
    with pytest.raises(ValueError, match="stock_code"):
        quantile_backtest(_factor_panel().drop(columns="stock_code"), n_groups=2)


@pytest.mark.parametrize("cost_bps", [0.0, 10.0])
def test_unchanged_half_cash_portfolio_has_no_repeat_turnover(cost_bps: float) -> None:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"A": [0.5, 0.5]}, index=dates[:2])
    returns = pd.DataFrame({"A": [0.0, 0.0, 0.0]}, index=dates)
    result = portfolio_backtest(weights, returns, cost_bps=cost_bps)
    np.testing.assert_allclose(result["turnover"], [0.5, 0.0])
    np.testing.assert_allclose(result["cost"], [0.5 * cost_bps / 1e4, 0.0])
    np.testing.assert_allclose(result["nav"], 1 - 0.5 * cost_bps / 1e4)


def test_cash_is_included_in_drift_after_asset_gain() -> None:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"A": [0.5, 0.5]}, index=dates[:2])
    returns = pd.DataFrame({"A": [0.0, 0.2, 0.0]}, index=dates)
    result = portfolio_backtest(weights, returns)
    # 股票从0.5升至0.6，现金仍0.5；恢复半仓须卖出0.6/1.1 - 0.5。
    np.testing.assert_allclose(result["turnover"], [0.5, 0.6 / 1.1 - 0.5])
    np.testing.assert_allclose(result["gross_return"], [0.5 * 0.2, 0.0])


def test_fully_invested_drift_and_signal_delay_are_preserved() -> None:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"A": [0.5, 0.5], "B": [0.5, 0.5]}, index=dates[:2])
    returns = pd.DataFrame({"A": [0.9, 0.2, 0.0], "B": [-0.9, 0.0, 0.1]}, index=dates)
    result = portfolio_backtest(weights, returns, cost_bps=10)
    # 月末信号只吃下一月收益；满仓分母仍等于两只资产漂移后的财富之和。
    pd.testing.assert_index_equal(result.index, dates[1:].rename("date"))
    drift = np.array([0.5 * 1.2, 0.5]) / (0.5 * 1.2 + 0.5)
    turnover = np.array([1.0, np.abs(np.array([0.5, 0.5]) - drift).sum()])
    gross = np.array([0.5 * 0.2, 0.5 * 0.1])
    np.testing.assert_allclose(result["turnover"], turnover)
    np.testing.assert_allclose(result["port_return"], gross - turnover * 10 / 1e4)
    np.testing.assert_allclose(result["nav"], np.cumprod(1 + gross - turnover * 10 / 1e4))


def test_all_cash_then_entry_only_charges_entry() -> None:
    dates = pd.date_range("2024-01-31", periods=4, freq="ME")
    weights = pd.DataFrame({"A": [0.0, 0.0, 0.5]}, index=dates[:3])
    returns = pd.DataFrame({"A": [0.1, 0.1, 0.1, 0.1]}, index=dates)
    result = portfolio_backtest(weights, returns, cost_bps=10)
    np.testing.assert_allclose(result["turnover"], [0.0, 0.0, 0.5])
    np.testing.assert_allclose(result["port_return"], [0.0, 0.0, 0.5 * 0.1 - 0.5 * 10 / 1e4])


def test_nonpositive_drift_wealth_is_rejected() -> None:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"A": [1.0, 1.0]}, index=dates[:2])
    returns = pd.DataFrame({"A": [0.0, -1.0, 0.0]}, index=dates)
    with pytest.raises(ValueError, match="组合财富"):
        portfolio_backtest(weights, returns)
