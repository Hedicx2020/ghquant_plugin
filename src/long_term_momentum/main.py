"""
Main execution script for Long-Term Momentum 2.0 factor strategy.

Orchestrates the full pipeline:
1. Load and preprocess data
2. Compute factor values on each month-end rebalance date
3. Calculate forward returns for the next holding period
4. Run IC analysis and quantile backtesting
5. Generate charts and Excel output

Usage:
    cd /Users/hedi/report_reproduce
    python -m src.long_term_momentum.main
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.backtest import performance_analysis
from common.data_loader import (
    get_month_end_trading_days,
    load_industry,
    load_market_data,
    load_st_data,
    load_suspend,
    load_trade_calendar,
)
from common.utils import standardize_factor
from src.long_term_momentum.config import (
    DATA_DIR,
    END_DATE,
    INDUSTRY_STANDARD_CODE,
    LOOKBACK_DAYS,
    LOW_AMPLITUDE_RATIO,
    N_GROUPS,
    OUTPUT_DIR,
    REVERSE_DAYS,
    START_DATE,
    TRANSACTION_COST,
)
from src.long_term_momentum.strategy import (
    calculate_long_momentum_1,
    calculate_long_momentum_2,
    prepare_panel,
)


def main() -> None:
    """Run the full Long-Term Momentum 2.0 factor backtest."""
    t0 = time.time()
    print("=" * 60)
    print("Long-Term Momentum 2.0 Factor Backtest")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load raw data
    # ------------------------------------------------------------------
    print("\n[1/6] Loading raw data ...")
    price_df = load_market_data(
        start_date=START_DATE,
        end_date=END_DATE,
        data_dir=DATA_DIR,
    )
    suspend_df = load_suspend(data_dir=DATA_DIR)
    st_data = load_st_data(data_dir=DATA_DIR)
    industry_df = load_industry(data_dir=DATA_DIR, standard_code=INDUSTRY_STANDARD_CODE)

    # Separate price and trade components from the merged market data
    price_cols = ["stock_code", "date", "prev_close", "close", "open", "high", "low"]
    trade_cols = [
        "stock_code", "date", "change_pct", "market_value",
        "negotiable_market_value", "turnover_rate",
    ]
    price_only = price_df[price_cols].copy()
    trade_only = price_df[trade_cols].copy()

    print(f"  Price data: {price_only.shape[0]:,} rows, "
          f"{price_only['stock_code'].nunique():,} stocks")

    # ------------------------------------------------------------------
    # 2. Prepare panel (merge, clean, flag limit/suspend)
    # ------------------------------------------------------------------
    print("\n[2/6] Preparing panel (merge, flag limit/suspend) ...")
    panel = prepare_panel(price_only, trade_only, suspend_df, st_data, industry_df)

    # Filter to date range (keep extra lookback for factor calculation)
    buffer_start = pd.Timestamp(START_DATE) - pd.DateOffset(days=400)
    panel = panel[
        (panel["date"] >= buffer_start) & (panel["date"] <= pd.Timestamp(END_DATE))
    ].reset_index(drop=True)

    print(f"  Panel: {panel.shape[0]:,} rows")

    # ------------------------------------------------------------------
    # 3. Get rebalance dates
    # ------------------------------------------------------------------
    print("\n[3/6] Computing rebalance dates ...")
    rebalance_dates = get_month_end_trading_days(START_DATE, END_DATE, DATA_DIR)
    print(f"  {len(rebalance_dates)} month-end rebalance dates "
          f"({rebalance_dates[0].date()} ~ {rebalance_dates[-1].date()})")

    # ------------------------------------------------------------------
    # 4. Calculate factors
    # ------------------------------------------------------------------
    # --- 4a. Long-Term Momentum 1.0 ---
    print("\n[4/6] Calculating factor values ...")
    print("  Computing Long-Term Momentum 1.0 ...")
    factor_1 = calculate_long_momentum_1(
        panel, rebalance_dates,
        lookback=LOOKBACK_DAYS,
        low_ratio=LOW_AMPLITUDE_RATIO,
    )
    print(f"    LM 1.0: {factor_1.shape[0]:,} stock-date observations")

    # --- 4b. Long-Term Momentum 2.0 ---
    print("  Computing Long-Term Momentum 2.0 ...")
    factor_2 = calculate_long_momentum_2(
        panel, rebalance_dates,
        lookback=LOOKBACK_DAYS,
        low_ratio=LOW_AMPLITUDE_RATIO,
        reverse_days=REVERSE_DAYS,
    )
    print(f"    LM 2.0: {factor_2.shape[0]:,} stock-date observations")

    # ------------------------------------------------------------------
    # 5. Compute forward returns
    # ------------------------------------------------------------------
    print("\n[5/6] Computing forward returns ...")

    # For monthly rebalancing, forward return = return from month-end T
    # to next month-end T+1.  Use change_pct (日涨跌幅) which already
    # accounts for dividends and splits (后复权效果).
    # Compound daily returns: prod(1 + r_i) - 1
    rb_list = sorted(rebalance_dates)
    daily_ret = panel[["stock_code", "date", "change_pct"]].copy()
    daily_ret["daily_factor"] = 1 + daily_ret["change_pct"] / 100

    fwd_ret_records = []
    for i in range(len(rb_list) - 1):
        t_date = rb_list[i]
        t1_date = rb_list[i + 1]
        # Select trading days in (t_date, t1_date]
        mask = (daily_ret["date"] > t_date) & (daily_ret["date"] <= t1_date)
        period = daily_ret.loc[mask]
        # Compound daily returns per stock
        fwd = (
            period.groupby("stock_code")["daily_factor"]
            .prod()
            .subtract(1)
            .rename("forward_return")
            .reset_index()
        )
        fwd["date"] = t_date
        fwd_ret_records.append(fwd)

    fwd_ret_df = pd.concat(fwd_ret_records, ignore_index=True)
    print(f"  Forward returns: {fwd_ret_df.shape[0]:,} observations")

    # ------------------------------------------------------------------
    # 5b. Merge factor with forward returns and panel info
    # ------------------------------------------------------------------
    # For factor 2.0
    factor_panel_2 = (
        factor_2[["stock_code", "date", "long_mom_2"]]
        .merge(fwd_ret_df, on=["stock_code", "date"], how="inner")
        .dropna(subset=["long_mom_2", "forward_return"])
    )

    # Add market cap and industry for neutralization
    panel_info = (
        panel[["stock_code", "date", "market_value", "industry"]]
        .drop_duplicates(subset=["stock_code", "date"])
    )
    factor_panel_2 = factor_panel_2.merge(
        panel_info, on=["stock_code", "date"], how="left"
    )

    print(f"  Factor 2.0 panel: {factor_panel_2.shape[0]:,} stock-date pairs "
          f"across {factor_panel_2['date'].nunique()} months")

    # --- Filter ST stocks on rebalance dates ---
    st_codes_per_date: dict[pd.Timestamp, set] = {}
    for _, row in st_data.iterrows():
        for rdate in rb_list:
            if row["implement_date"] <= rdate and (pd.isna(row["remove_date"]) or row["remove_date"] > rdate):
                st_codes_per_date.setdefault(rdate, set()).add(row["stock_code"])

    def _not_st(row: pd.Series) -> bool:
        codes = st_codes_per_date.get(row["date"], set())
        return row["stock_code"] not in codes

    mask = factor_panel_2.apply(_not_st, axis=1)
    factor_panel_2 = factor_panel_2[mask].reset_index(drop=True)
    print(f"  After ST filter: {factor_panel_2.shape[0]:,} observations")

    # Note: Not filtering rebalance-date suspended stocks, as the report's
    # methodology appears to retain them (matching LS return/G5 return metrics).

    # ------------------------------------------------------------------
    # 5c. IC calculation on RAW factor (before neutralization)
    # ------------------------------------------------------------------
    # Research report calculates RankIC on the raw factor (after reverse
    # neutralization but before market cap / industry neutralization).
    from common.backtest import calculate_ic_series, ic_summary
    raw_ic_df = calculate_ic_series(
        factor_panel_2, "long_mom_2", "forward_return", "date", method="rank"
    )
    raw_ic_stats = ic_summary(raw_ic_df["ic"])
    print(f"  Raw factor RankIC: {raw_ic_stats['ic_mean']:.4f} "
          f"({raw_ic_stats['ic_mean']*100:.2f}%), "
          f"ICIR: {raw_ic_stats['icir']:.2f}, "
          f"WinRate: {raw_ic_stats['win_rate']:.2%}")

    # ------------------------------------------------------------------
    # 5d. Factor preprocessing (winsorize + neutralize + standardize)
    #     for portfolio construction / backtest
    # ------------------------------------------------------------------
    print("  Standardizing factor (winsorize + mktcap/industry neutral + z-score) ...")
    factor_panel_2 = standardize_factor(
        factor_panel_2,
        factor_col="long_mom_2",
        date_col="date",
        market_cap_col="market_value",
        industry_col="industry",
        winsorize_method="mad",
    )
    # Use factor_std for backtest grouping
    factor_panel_2["factor"] = factor_panel_2["factor_std"]

    # ------------------------------------------------------------------
    # 6. Run backtest and generate output
    # ------------------------------------------------------------------
    print("\n[6/6] Running backtest and generating output ...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = performance_analysis(
        factor_panel=factor_panel_2,
        factor_col="factor",
        return_col="forward_return",
        date_col="date",
        n_groups=N_GROUPS,
        transaction_cost=TRANSACTION_COST,
        output_dir=OUTPUT_DIR,
        report_name="long_term_momentum_2",
    )

    # Use raw IC stats as the primary IC metric (matching report methodology)
    ic_stats = raw_ic_stats
    ls_perf = results["ls_result"]["ls_performance"]
    top_perf = results["ls_result"]["top_performance"]

    print("\n" + "=" * 60)
    print("BACKTEST RESULTS: Long-Term Momentum 2.0")
    print("=" * 60)
    print(f"  RankIC:           {ic_stats['ic_mean']:.4f} ({ic_stats['ic_mean']*100:.2f}%)")
    print(f"  RankICIR:         {ic_stats['icir']:.2f}")
    print(f"  RankIC Win Rate:  {ic_stats['win_rate']:.2%}")
    print(f"  T-stat:           {ic_stats['t_stat']:.2f}")
    print()
    print(f"  Top Group (G{N_GROUPS}):")
    print(f"    Ann. Return:    {top_perf['ann_return']:.2%}")
    print(f"    Ann. Volatility:{top_perf['ann_volatility']:.2%}")
    print(f"    Sharpe:         {top_perf['sharpe']:.2f}")
    print(f"    Max Drawdown:   {top_perf['max_drawdown']:.2%}")
    print()
    print(f"  Long-Short:")
    print(f"    Ann. Return:    {ls_perf['ann_return']:.2%}")
    print(f"    Ann. Volatility:{ls_perf['ann_volatility']:.2%}")
    print(f"    IR (ann.):      {ls_perf['sharpe']:.2f}")
    print(f"    Max Drawdown:   {ls_perf['max_drawdown']:.2%}")
    print(f"    Win Rate:       {ls_perf['win_rate']:.2%}")

    # --- Also run LM 1.0 for comparison ---
    print("\n" + "-" * 40)
    print("Bonus: Long-Term Momentum 1.0 comparison")
    print("-" * 40)

    factor_panel_1 = (
        factor_1[["stock_code", "date", "long_mom_1"]]
        .merge(fwd_ret_df, on=["stock_code", "date"], how="inner")
        .dropna(subset=["long_mom_1", "forward_return"])
    )
    factor_panel_1 = factor_panel_1.merge(
        panel_info, on=["stock_code", "date"], how="left"
    )
    # Filter ST
    mask1 = factor_panel_1.apply(_not_st, axis=1)
    factor_panel_1 = factor_panel_1[mask1].reset_index(drop=True)

    factor_panel_1 = standardize_factor(
        factor_panel_1,
        factor_col="long_mom_1",
        date_col="date",
        market_cap_col="market_value",
        industry_col="industry",
        winsorize_method="mad",
    )
    factor_panel_1["factor"] = factor_panel_1["factor_std"]

    lm1_output_dir = OUTPUT_DIR / "lm1_comparison"
    lm1_output_dir.mkdir(parents=True, exist_ok=True)
    results_1 = performance_analysis(
        factor_panel=factor_panel_1,
        factor_col="factor",
        return_col="forward_return",
        date_col="date",
        n_groups=N_GROUPS,
        transaction_cost=TRANSACTION_COST,
        output_dir=lm1_output_dir,
        report_name="long_term_momentum_1",
    )

    ic1 = results_1["ic_stats"]
    print(f"  LM1.0 RankIC:     {ic1['ic_mean']:.4f} ({ic1['ic_mean']*100:.2f}%)")
    print(f"  LM1.0 RankICIR:   {ic1['icir']:.2f}")
    print(f"  LM1.0 Win Rate:   {ic1['win_rate']:.2%}")

    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s")
    print(f"Output saved to: {OUTPUT_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
