"""
Core factor calculation for Long-Term Momentum 1.0 and 2.0.

This module implements the factor construction logic described in the
KaiYuan Securities report. It does NOT handle backtesting or output --
those are delegated to the common modules.

Key functions:
- identify_limit_days: flag limit-up / limit-down trading days
- calculate_market_return: cross-sectional mean of daily stock returns
- calculate_long_momentum_1: baseline factor (振幅 = high/low - 1)
- calculate_long_momentum_2: improved factor (alpha return + reversal neutral)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.long_term_momentum.config import (
    GEM_REFORM_DATE,
    LIMIT_RATIO_GEM,
    LIMIT_RATIO_MAIN,
    LIMIT_RATIO_ST,
    LIMIT_RATIO_STAR,
    LIMIT_TOLERANCE,
    LOOKBACK_DAYS,
    LOW_AMPLITUDE_RATIO,
    REVERSE_DAYS,
)


# ---------------------------------------------------------------------------
# Limit-up / limit-down identification
# ---------------------------------------------------------------------------

def _get_limit_ratio(stock_code: str, date: pd.Timestamp, is_st: bool) -> float:
    """Determine the applicable limit ratio for a stock on a given date.

    Args:
        stock_code: 6-digit stock code.
        date: Trading date.
        is_st: Whether the stock is ST.

    Returns:
        Limit ratio (e.g. 0.10 for 10%).
    """
    if is_st:
        return LIMIT_RATIO_ST
    if stock_code.startswith("688"):
        return LIMIT_RATIO_STAR
    if stock_code.startswith("3"):
        return LIMIT_RATIO_GEM if date >= pd.Timestamp(GEM_REFORM_DATE) else LIMIT_RATIO_MAIN
    return LIMIT_RATIO_MAIN


def identify_limit_days(
    panel: pd.DataFrame,
    st_data: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """Vectorised identification of limit-up/limit-down days.

    Uses close / prev_close - 1 to check whether the actual return
    reaches the board limit (within tolerance).

    Args:
        panel: DataFrame with [stock_code, date, close, prev_close].
        st_data: ST records (implement_date, remove_date, stock_code).

    Returns:
        Boolean Series aligned with panel index, True = limit day.
    """
    actual_ret = panel["close"] / panel["prev_close"] - 1

    # Determine limit ratio per row
    # Build a vectorised limit ratio column
    code = panel["stock_code"]
    date = panel["date"]

    # Default: main board 10%
    limit_ratio = pd.Series(LIMIT_RATIO_MAIN, index=panel.index)

    # STAR market (688xxx): 20%
    is_star = code.str.startswith("688")
    limit_ratio = limit_ratio.where(~is_star, LIMIT_RATIO_STAR)

    # ChiNext (3xxxxx): 20% after reform, else 10%
    is_gem = code.str.startswith("3")
    gem_after_reform = is_gem & (date >= pd.Timestamp(GEM_REFORM_DATE))
    limit_ratio = limit_ratio.where(~gem_after_reform, LIMIT_RATIO_GEM)

    # ST stocks: 5% -- mark via st_data
    if st_data is not None and not st_data.empty:
        # Build a set of (stock_code, date) pairs that are in ST
        # For efficiency, join on stock_code and filter by date range
        st_expanded = st_data.copy()
        st_codes = st_expanded["stock_code"].unique()
        is_st_mask = pd.Series(False, index=panel.index)
        for _, row in st_expanded.iterrows():
            mask = (
                (code == row["stock_code"])
                & (date >= row["implement_date"])
                & ((date < row["remove_date"]) | pd.isna(row["remove_date"]))
            )
            is_st_mask = is_st_mask | mask
        limit_ratio = limit_ratio.where(~is_st_mask, LIMIT_RATIO_ST)

    # Check limit: |actual_ret| >= limit_ratio - tolerance
    is_limit = actual_ret.abs() >= (limit_ratio - LIMIT_TOLERANCE)

    return is_limit


def identify_limit_days_fast(panel: pd.DataFrame) -> pd.Series:
    """Fast limit-day identification using close/prev_close with tolerance.

    Uses the recommended approach: |close/prev_close - 1| >= limit_ratio - 0.1%.
    Handles different limit ratios for main board (10%), GEM/STAR (20%),
    and ST stocks (5%).

    Args:
        panel: DataFrame with [stock_code, date, close, prev_close, is_st].

    Returns:
        Boolean Series, True = limit day.
    """
    # Use close/prev_close for precise calculation
    actual_ret = (panel["close"] / panel["prev_close"] - 1).abs()

    # Default threshold: 10% - 0.1% = 9.9% (main board)
    threshold = pd.Series(LIMIT_RATIO_MAIN - LIMIT_TOLERANCE, index=panel.index)

    # STAR market (688xxx): 20% - 0.1% = 19.9%
    is_star = panel["stock_code"].str.startswith("688")
    threshold = threshold.where(~is_star, LIMIT_RATIO_STAR - LIMIT_TOLERANCE)

    # ChiNext after reform (3xxxxx): 20% - 0.1% = 19.9%
    is_gem_reform = (
        panel["stock_code"].str.startswith("3")
        & (panel["date"] >= pd.Timestamp(GEM_REFORM_DATE))
    )
    threshold = threshold.where(~is_gem_reform, LIMIT_RATIO_GEM - LIMIT_TOLERANCE)

    # ST stocks: 5% - 0.1% = 4.9%
    if "is_st" in panel.columns:
        is_st = panel["is_st"].astype(bool)
        threshold = threshold.where(~is_st, LIMIT_RATIO_ST - LIMIT_TOLERANCE)

    return actual_ret >= threshold


# ---------------------------------------------------------------------------
# Market return
# ---------------------------------------------------------------------------

def calculate_market_return(
    panel: pd.DataFrame,
    return_col: str = "daily_return",
    date_col: str = "date",
) -> pd.Series:
    """Cross-sectional mean of daily stock returns per trading day.

    Args:
        panel: Panel data with [date, daily_return].
        return_col: Column with decimal daily returns.
        date_col: Date column.

    Returns:
        Series indexed by date with the market mean return.
    """
    return panel.groupby(date_col)[return_col].mean()


# ---------------------------------------------------------------------------
# Long-Term Momentum 1.0
# ---------------------------------------------------------------------------

def calculate_long_momentum_1(
    panel: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
    lookback: int = LOOKBACK_DAYS,
    low_ratio: float = LOW_AMPLITUDE_RATIO,
) -> pd.DataFrame:
    """Calculate Long-Term Momentum 1.0 factor.

    For each stock on each rebalance date, looks back *lookback* trading
    days, computes amplitude = high/low - 1, selects the lowest
    *low_ratio* fraction by amplitude, and sums their daily returns.

    Args:
        panel: Panel data with [stock_code, date, high, low, daily_return].
            Must be sorted by [stock_code, date].
        rebalance_dates: Dates on which to compute factor values.
        lookback: Number of trading days to look back.
        low_ratio: Fraction of lowest-amplitude days to keep.

    Returns:
        DataFrame with [stock_code, date, long_mom_1].
    """
    # Pivot to wide format for vectorised rolling
    # columns: stock_code, index: date
    ret_wide = panel.pivot_table(index="date", columns="stock_code", values="daily_return")
    high_wide = panel.pivot_table(index="date", columns="stock_code", values="high")
    low_wide = panel.pivot_table(index="date", columns="stock_code", values="low")

    # amplitude = high / low - 1
    amp_wide = high_wide / low_wide - 1

    all_dates = ret_wide.index.sort_values()
    results = []

    for rdate in rebalance_dates:
        if rdate not in all_dates:
            continue
        loc = all_dates.get_loc(rdate)
        start = max(loc - lookback + 1, 0)
        window_dates = all_dates[start: loc + 1]

        ret_window = ret_wide.loc[window_dates]
        amp_window = amp_wide.loc[window_dates]

        # For each stock, keep lowest low_ratio% amplitude days, sum returns
        n_days = amp_window.notna().sum()  # per stock
        n_keep = (n_days * low_ratio).astype(int).clip(lower=1)

        # Rank amplitude within each stock's window (ascending)
        amp_rank = amp_window.rank(axis=0, method="first", na_option="bottom")

        # Mask: keep rows where rank <= n_keep (per stock)
        keep_mask = amp_rank.le(n_keep, axis=1)

        factor_values = (ret_window * keep_mask).sum()
        factor_df = factor_values.reset_index()
        factor_df.columns = ["stock_code", "long_mom_1"]
        factor_df["date"] = rdate
        results.append(factor_df)

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


# ---------------------------------------------------------------------------
# Long-Term Momentum 2.0
# ---------------------------------------------------------------------------

def calculate_long_momentum_2(
    panel: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
    lookback: int = LOOKBACK_DAYS,
    low_ratio: float = LOW_AMPLITUDE_RATIO,
    reverse_days: int = REVERSE_DAYS,
) -> pd.DataFrame:
    """Calculate Long-Term Momentum 2.0 factor.

    Improvements over 1.0:
    1. Amplitude = (high - low) / prev_close
    2. Exclude suspended and limit-up/down days
    3. Use alpha return (daily_return - market_return) instead of raw return
    4. Neutralize against 20-day reversal factor

    Args:
        panel: Panel data with columns [stock_code, date, high, low,
            prev_close, daily_return, is_suspend, is_limit]. Must be
            sorted by [stock_code, date].
        rebalance_dates: Dates on which to compute factor values.
        lookback: Rolling window length.
        low_ratio: Fraction of low-amplitude days to keep.
        reverse_days: Lookback for the reversal neutralization factor.

    Returns:
        DataFrame with [stock_code, date, long_mom_2, alpha_ret_low, reverse_20d].
    """
    # --- Step 1: Compute improved amplitude ---
    panel = panel.copy()
    panel["amplitude"] = (panel["high"] - panel["low"]) / panel["prev_close"]

    # --- Step 2: Flag invalid days (suspend + limit) ---
    invalid = panel["is_suspend"] | panel["is_limit"]

    # --- Step 3: Market return per day ---
    # Use only valid (non-suspend, non-limit) observations
    valid_panel = panel[~invalid]
    market_ret = calculate_market_return(valid_panel, "daily_return", "date")
    panel["market_return"] = panel["date"].map(market_ret)

    # --- Step 4: Alpha return ---
    panel["alpha_return"] = panel["daily_return"] - panel["market_return"]

    # Set invalid-day amplitude and alpha return to NaN so they are excluded
    panel.loc[invalid, "amplitude"] = np.nan
    panel.loc[invalid, "alpha_return"] = np.nan

    # --- Step 5: Pivot to wide ---
    alpha_wide = panel.pivot_table(index="date", columns="stock_code", values="alpha_return")
    amp_wide = panel.pivot_table(index="date", columns="stock_code", values="amplitude")
    close_wide = panel.pivot_table(index="date", columns="stock_code", values="close")

    all_dates = alpha_wide.index.sort_values()
    all_stocks = alpha_wide.columns

    results = []

    for rdate in rebalance_dates:
        if rdate not in all_dates:
            continue
        loc = all_dates.get_loc(rdate)
        start = max(loc - lookback + 1, 0)
        window_dates = all_dates[start: loc + 1]

        alpha_window = alpha_wide.loc[window_dates]
        amp_window = amp_wide.loc[window_dates]

        # Count valid (non-NaN) days per stock
        n_valid = amp_window.notna().sum()
        n_keep = (n_valid * low_ratio).astype(int).clip(lower=1)

        # Rank amplitude ascending (NaN at bottom = excluded)
        amp_rank = amp_window.rank(axis=0, method="first", na_option="bottom")

        # Keep mask: rank <= n_keep means low-amplitude day
        keep_mask = amp_rank.le(n_keep, axis=1) & amp_window.notna()

        # AlphaRet_low = sum of alpha returns on low-amplitude days
        alpha_ret_low = (alpha_window * keep_mask).sum()

        # --- Step 6: 20-day reversal factor ---
        # Reverse20d = close(T) / close(T-20) - 1
        if loc >= reverse_days:
            rev_date = all_dates[loc - reverse_days]
            close_t = close_wide.loc[rdate]
            close_t20 = close_wide.loc[rev_date]
            reverse_20d = close_t / close_t20 - 1
        else:
            reverse_20d = pd.Series(np.nan, index=all_stocks)

        # --- Step 7: Cross-sectional OLS neutralization ---
        df_cs = pd.DataFrame({
            "alpha_ret_low": alpha_ret_low,
            "reverse_20d": reverse_20d,
        }).dropna()

        if df_cs.shape[0] > 10:
            X = np.column_stack([np.ones(len(df_cs)), df_cs["reverse_20d"].values])
            y = df_cs["alpha_ret_low"].values
            try:
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
                residual = y - X @ beta
                long_mom_2 = pd.Series(residual, index=df_cs.index)
            except np.linalg.LinAlgError:
                long_mom_2 = df_cs["alpha_ret_low"]
        else:
            long_mom_2 = alpha_ret_low

        # Assemble output
        out = pd.DataFrame({
            "stock_code": all_stocks,
            "date": rdate,
            "alpha_ret_low": alpha_ret_low.reindex(all_stocks),
            "reverse_20d": reverse_20d.reindex(all_stocks),
            "long_mom_2": long_mom_2.reindex(all_stocks),
        })
        results.append(out)

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


# ---------------------------------------------------------------------------
# Convenience: prepare panel from raw data
# ---------------------------------------------------------------------------

def prepare_panel(
    price_df: pd.DataFrame,
    trade_df: pd.DataFrame,
    suspend_df: pd.DataFrame,
    st_data: pd.DataFrame,
    industry_df: pd.DataFrame,
) -> pd.DataFrame:
    """Merge and clean raw data into a unified panel.

    Args:
        price_df: Stock price data.
        trade_df: Stock trade data.
        suspend_df: Suspend status.
        st_data: ST records (for limit-day identification).
        industry_df: Industry classification.

    Returns:
        Cleaned panel DataFrame with all necessary columns.
    """
    # Merge price + trade
    panel = price_df.merge(
        trade_df[["stock_code", "date", "change_pct", "market_value",
                   "negotiable_market_value", "turnover_rate"]],
        on=["stock_code", "date"],
        how="inner",
    )

    # Daily return in decimal
    panel["daily_return"] = panel["change_pct"] / 100.0

    # Merge suspend
    panel = panel.merge(
        suspend_df[["stock_code", "date", "ifsuspend"]],
        on=["stock_code", "date"],
        how="left",
    )
    panel["is_suspend"] = panel["ifsuspend"].fillna(0).astype(bool)
    panel.drop(columns=["ifsuspend"], inplace=True)

    # Mark ST status for limit-day identification (vectorized)
    st_records = st_data[["stock_code", "implement_date", "remove_date"]].copy()
    st_records["remove_date"] = st_records["remove_date"].fillna(pd.Timestamp("2099-12-31"))
    # Cross-join on stock_code, then filter by date range
    panel_st = panel[["stock_code", "date"]].merge(st_records, on="stock_code", how="inner")
    st_mask = (panel_st["date"] >= panel_st["implement_date"]) & (panel_st["date"] < panel_st["remove_date"])
    st_keys = panel_st.loc[st_mask, ["stock_code", "date"]].drop_duplicates()
    st_keys["is_st"] = True
    panel = panel.merge(st_keys, on=["stock_code", "date"], how="left")
    panel["is_st"] = panel["is_st"].fillna(False)

    # Identify limit days (fast method, now with ST support)
    panel["is_limit"] = identify_limit_days_fast(panel)

    # Merge industry
    panel = panel.merge(industry_df, on="stock_code", how="left")
    panel.rename(columns={"first_industry_name": "industry"}, inplace=True)

    # Sort
    panel.sort_values(["stock_code", "date"], inplace=True)
    panel.reset_index(drop=True, inplace=True)

    return panel
