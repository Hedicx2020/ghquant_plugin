from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.test.strategy import (
    BacktestConfig,
    calculate_calendar_signal,
    calculate_daily_seesaw_signal,
    calculate_reverse_signal,
    combine_strategy_signals,
    performance_metrics,
)


class StrategySignalTest(unittest.TestCase):
    def test_daily_seesaw_signal_is_applied_on_next_trading_day(self) -> None:
        hs300 = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
                "hs300_return": [0.06, -0.04, 0.01],
            }
        )

        signal = calculate_daily_seesaw_signal(
            hs300, lower_threshold=0.03, upper_threshold=0.05
        )

        self.assertEqual(signal.loc[pd.Timestamp("2020-01-03"), "daily_upper"], -1)
        self.assertEqual(signal.loc[pd.Timestamp("2020-01-06"), "daily_lower"], 1)
        self.assertEqual(signal.loc[pd.Timestamp("2020-01-02"), "daily_upper"], 0)

    def test_reverse_signal_uses_t_minus_2_settlement_return_and_thresholds(self) -> None:
        futures = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-02", periods=5, freq="B"),
                "settle_return": [0.001, -0.006, -0.002, 0.0001, 0.003],
            }
        )

        signal = calculate_reverse_signal(futures, min_abs=0.0003, max_abs=0.005)

        self.assertEqual(signal.loc[pd.Timestamp("2020-01-06"), "reverse_signal"], -1)
        self.assertEqual(signal.loc[pd.Timestamp("2020-01-07"), "reverse_signal"], 0)
        self.assertEqual(signal.loc[pd.Timestamp("2020-01-08"), "reverse_signal"], 1)

    def test_final_signal_priority_matches_report_steps(self) -> None:
        idx = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"])
        signals = pd.DataFrame(
            {
                "date": idx,
                "daily_upper": [0, -1, 0, 0],
                "daily_lower": [0, 0, 1, 0],
                "ls_signal": [-1, 1, -1, 1],
                "reverse_signal": [1, 1, -1, 0],
                "reverse_active": [True, True, True, False],
                "calendar_signal": [1, 0, 0, 0],
            }
        ).set_index("date")

        combined = combine_strategy_signals(signals)

        self.assertEqual(combined.loc[pd.Timestamp("2020-01-02"), "position"], 1)
        self.assertEqual(
            combined.loc[pd.Timestamp("2020-01-02"), "signal_source"],
            "daily_upper_calendar",
        )
        self.assertEqual(combined.loc[pd.Timestamp("2020-01-03"), "position"], -1)
        self.assertEqual(
            combined.loc[pd.Timestamp("2020-01-03"), "signal_source"],
            "daily_upper_calendar",
        )
        self.assertEqual(combined.loc[pd.Timestamp("2020-01-06"), "position"], -1)
        self.assertEqual(combined.loc[pd.Timestamp("2020-01-06"), "signal_source"], "reverse")
        self.assertEqual(combined.loc[pd.Timestamp("2020-01-07"), "position"], 1)
        self.assertEqual(combined.loc[pd.Timestamp("2020-01-07"), "signal_source"], "seesaw")

    def test_calendar_signal_is_thursday_only(self) -> None:
        dates = pd.date_range("2020-01-06", periods=5, freq="B")
        signal = calculate_calendar_signal(pd.DataFrame({"date": dates}))

        self.assertEqual(signal.loc[pd.Timestamp("2020-01-09"), "calendar_signal"], 1)
        self.assertEqual(signal["calendar_signal"].sum(), 1)

    def test_performance_metrics_basic_values(self) -> None:
        returns = pd.Series([0.01, -0.02, 0.03], index=pd.date_range("2020-01-01", periods=3))
        metrics = performance_metrics(returns, periods_per_year=252)

        self.assertTrue(np.isclose(metrics["cumulative_return"], (1.01 * 0.98 * 1.03) - 1))
        self.assertEqual(metrics["win_rate"], 2 / 3)
        self.assertGreater(metrics["max_drawdown"], 0)
        self.assertEqual(metrics["n_periods"], 3)
        self.assertIsInstance(BacktestConfig().start_date, str)


if __name__ == "__main__":
    unittest.main()
