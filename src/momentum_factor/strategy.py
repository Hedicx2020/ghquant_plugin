"""
Core factor calculation for momentum factor strategy.

Implements four categories of momentum factors:
1. Raw momentum (Momentum_1M/3M/6M/12M/24M, Momentum_1M_Max)
2. Trend momentum (MA_20/60/120/240)
3. Purified momentum (Momentum_1M_Neu) -- strip liquidity via cross-sectional regression
4. Residual momentum (Momentum_1M_Resid) -- Fama-French 3-factor residual
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from common.data_loader import (
    LOCAL_DATA_DIR,
    load_stock_price,
    load_stock_trade,
    load_st_data,
    load_suspend,
    load_industry,
    load_trade_calendar,
    get_month_end_trading_days,
    filter_st_stocks,
)


# =====================================================================
# Data preparation
# =====================================================================

def load_stock_info(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
    """Load stock basic information (IPO date).

    Args:
        data_dir: Data directory.

    Returns:
        DataFrame with [stock_code, list_date].
    """
    path = data_dir / "ashare_stock.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "list_date"])
    df["list_date"] = pd.to_datetime(df["list_date"])
    return df


def load_valuation(
    data_dir: Path = LOCAL_DATA_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load stock valuation data (PB for HML factor).

    Args:
        data_dir: Data directory.
        start_date: Optional start date filter.
        end_date: Optional end date filter.

    Returns:
        DataFrame with [stock_code, date, pb_lf].
    """
    path = data_dir / "ashare_stock_value.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "date", "pb_lf"])
    df["date"] = pd.to_datetime(df["date"])
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    return df


def prepare_daily_panel(
    start_date: str,
    end_date: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DataFrame:
    """Load and merge daily price + trade data with sufficient lookback.

    Returns:
        Merged daily panel with [stock_code, date, close, prev_close,
        change_pct, market_value, negotiable_market_value, ...].
    """
    # Lookback ~40 months before start to support 24M momentum + 36M regression
    buffer_start = str(
        (pd.Timestamp(start_date) - pd.DateOffset(months=40)).date()
    )

    price = load_stock_price(
        data_dir,
        columns=["stock_code", "date", "close", "prev_close"],
    )
    trade = load_stock_trade(
        data_dir,
        columns=[
            "stock_code", "date", "change_pct",
            "market_value", "negotiable_market_value",
        ],
    )

    # Date range filter
    mask_date = lambda df: df[
        (df["date"] >= pd.Timestamp(buffer_start))
        & (df["date"] <= pd.Timestamp(end_date))
    ]
    price = mask_date(price)
    trade = mask_date(trade)

    merged = price.merge(trade, on=["stock_code", "date"], how="inner")
    return merged.sort_values(["stock_code", "date"]).reset_index(drop=True)


def build_monthly_panel(
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Extract month-end snapshots and compute monthly returns.

    Args:
        daily_panel: Daily panel data.
        month_end_dates: Month-end trading dates.

    Returns:
        Monthly panel with [stock_code, date, close, monthly_return,
        market_value, negotiable_market_value].
    """
    # Keep only month-end dates
    monthly = daily_panel[daily_panel["date"].isin(month_end_dates)].copy()
    monthly = monthly.sort_values(["stock_code", "date"]).reset_index(drop=True)

    # Monthly return: close / prev_month_close - 1
    monthly["prev_close_m"] = (
        monthly.groupby("stock_code")["close"].shift(1)
    )
    monthly["monthly_return"] = monthly["close"] / monthly["prev_close_m"] - 1

    return monthly


def apply_universe_filter(
    monthly_panel: pd.DataFrame,
    st_data: pd.DataFrame,
    suspend_data: pd.DataFrame,
    stock_info: pd.DataFrame,
    min_list_days: int = 252,
) -> pd.DataFrame:
    """Filter stock universe: remove ST, suspended, and newly listed stocks.

    Args:
        monthly_panel: Monthly panel data.
        st_data: ST status records.
        suspend_data: Suspension records.
        stock_info: Stock IPO info.
        min_list_days: Minimum calendar days since IPO.

    Returns:
        Filtered monthly panel.
    """
    # Merge IPO date
    panel = monthly_panel.merge(
        stock_info[["stock_code", "list_date"]], on="stock_code", how="left"
    )

    # Filter: listed at least min_list_days ago
    panel = panel[
        (panel["date"] - panel["list_date"]).dt.days >= min_list_days
    ].copy()

    # Filter ST stocks per date
    st_flags = []
    for dt in panel["date"].unique():
        codes_dt = panel.loc[panel["date"] == dt, "stock_code"]
        valid = filter_st_stocks(codes_dt, pd.Timestamp(dt), st_data)
        st_flags.append(
            pd.DataFrame({"stock_code": valid.values, "date": dt, "_valid": True})
        )
    valid_df = pd.concat(st_flags, ignore_index=True)
    panel = panel.merge(valid_df, on=["stock_code", "date"], how="inner").drop(
        columns=["_valid"]
    )

    # Filter suspended stocks on month-end dates
    suspend_me = suspend_data[suspend_data["date"].isin(panel["date"].unique())]
    suspended_mask = suspend_me[suspend_me["ifsuspend"] == 1][
        ["stock_code", "date"]
    ].assign(_suspended=True)
    panel = panel.merge(suspended_mask, on=["stock_code", "date"], how="left")
    panel = panel[panel["_suspended"].isna()].drop(columns=["_suspended"])

    return panel.drop(columns=["list_date"], errors="ignore").reset_index(drop=True)


# =====================================================================
# Factor 1: Raw momentum factors
# =====================================================================

def calculate_momentum_factors(
    monthly_panel: pd.DataFrame,
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
    momentum_months: list[int] | None = None,
) -> pd.DataFrame:
    """Calculate raw momentum factors (Momentum_NM and Momentum_1M_Max).

    Args:
        monthly_panel: Monthly panel with [stock_code, date, close, monthly_return].
        daily_panel: Daily panel for Momentum_1M_Max calculation.
        month_end_dates: Month-end trading dates.
        momentum_months: List of look-back months [1, 3, 6, 12, 24].

    Returns:
        DataFrame with [stock_code, date, Momentum_1M, ..., Momentum_1M_Max].
    """
    if momentum_months is None:
        momentum_months = [1, 3, 6, 12, 24]

    result = monthly_panel[["stock_code", "date"]].copy()

    # Momentum_NM: close(t) / close(t-N) - 1 using monthly close
    close_pivot = monthly_panel.pivot_table(
        index="date", columns="stock_code", values="close"
    )

    for n in momentum_months:
        mom = close_pivot / close_pivot.shift(n) - 1
        mom_long = mom.stack().rename(f"Momentum_{n}M").reset_index()
        result = result.merge(mom_long, on=["stock_code", "date"], how="left")

    # Momentum_1M_Max: max daily return in the past ~20 trading days
    # For each month-end, find the max daily return in the past month
    daily_sub = daily_panel[["stock_code", "date", "change_pct"]].copy()
    daily_sub["change_pct"] = daily_sub["change_pct"] / 100.0  # Pct to decimal

    # Map daily dates to month-end dates
    me_series = pd.Series(month_end_dates, name="month_end").sort_values()

    # For each month-end, get the daily data in the preceding month
    max_ret_records: list[pd.DataFrame] = []
    for i, me_date in enumerate(sorted(month_end_dates)):
        # Previous month-end (or start of data)
        prev_me = sorted(month_end_dates)[i - 1] if i > 0 else me_date - pd.DateOffset(months=1)
        daily_window = daily_sub[
            (daily_sub["date"] > prev_me) & (daily_sub["date"] <= me_date)
        ]
        if daily_window.empty:
            continue
        max_ret = (
            daily_window.groupby("stock_code")["change_pct"]
            .max()
            .rename("Momentum_1M_Max")
            .reset_index()
            .assign(date=me_date)
        )
        max_ret_records.append(max_ret)

    if max_ret_records:
        max_ret_df = pd.concat(max_ret_records, ignore_index=True)
        result = result.merge(max_ret_df, on=["stock_code", "date"], how="left")
    else:
        result["Momentum_1M_Max"] = np.nan

    return result


# =====================================================================
# Factor 2: Trend momentum factors (MA-based)
# =====================================================================

def calculate_trend_momentum_factors(
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Calculate trend momentum factors MA_L = MA(close, L) / close.

    Args:
        daily_panel: Daily panel with [stock_code, date, close].
        month_end_dates: Month-end trading dates.
        windows: MA windows in trading days [20, 60, 120, 240].

    Returns:
        DataFrame with [stock_code, date, MA_20, MA_60, MA_120, MA_240].
    """
    if windows is None:
        windows = [20, 60, 120, 240]

    # Pivot close prices
    close_pivot = daily_panel.pivot_table(
        index="date", columns="stock_code", values="close"
    )

    # Keep only month-end rows at the end
    results: list[pd.DataFrame] = []
    for w in windows:
        ma = close_pivot.rolling(window=w, min_periods=w).mean()
        # Standardize: MA / current_price
        ma_bar = ma / close_pivot
        # Filter to month-end dates
        ma_me = ma_bar.loc[ma_bar.index.isin(month_end_dates)]
        ma_long = ma_me.stack().rename(f"MA_{w}").reset_index()
        ma_long.columns = ["date", "stock_code", f"MA_{w}"]
        results.append(ma_long)

    # Merge all MA factors
    merged = results[0]
    for df in results[1:]:
        merged = merged.merge(df, on=["stock_code", "date"], how="outer")

    return merged


# =====================================================================
# Factor 3: Purified momentum (strip liquidity)
# =====================================================================

def calculate_purified_momentum(
    monthly_panel: pd.DataFrame,
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Calculate purified momentum by stripping FC_MC and VSTD_1M via cross-sectional OLS.

    Momentum_1M_Neu = residual of regressing Momentum_1M on FC_MC + VSTD_1M.

    Args:
        monthly_panel: Monthly panel with monthly_return, market_value, negotiable_market_value.
        daily_panel: Daily panel for VSTD_1M calculation.
        month_end_dates: Month-end trading dates.

    Returns:
        DataFrame with [stock_code, date, Momentum_1M_Neu].
    """
    # --- 1. FC_MC = negotiable_market_value / market_value ---
    mp = monthly_panel[["stock_code", "date", "market_value", "negotiable_market_value"]].copy()
    mp["FC_MC"] = mp["negotiable_market_value"] / mp["market_value"]

    # --- 2. VSTD_1M: std of daily returns in past ~20 trading days ---
    daily_sub = daily_panel[["stock_code", "date", "change_pct"]].copy()
    daily_sub["daily_ret"] = daily_sub["change_pct"] / 100.0

    vstd_records: list[pd.DataFrame] = []
    sorted_me = sorted(month_end_dates)
    for i, me_date in enumerate(sorted_me):
        prev_me = sorted_me[i - 1] if i > 0 else me_date - pd.DateOffset(months=1)
        window = daily_sub[
            (daily_sub["date"] > prev_me) & (daily_sub["date"] <= me_date)
        ]
        if window.empty:
            continue
        vstd = (
            window.groupby("stock_code")["daily_ret"]
            .std()
            .rename("VSTD_1M")
            .reset_index()
            .assign(date=me_date)
        )
        vstd_records.append(vstd)

    vstd_df = pd.concat(vstd_records, ignore_index=True)

    # --- 3. Momentum_1M ---
    close_pivot = monthly_panel.pivot_table(
        index="date", columns="stock_code", values="close"
    )
    mom_1m = (close_pivot / close_pivot.shift(1) - 1).stack().rename("Momentum_1M").reset_index()
    mom_1m.columns = ["date", "stock_code", "Momentum_1M"]

    # --- 4. Merge and run cross-sectional OLS ---
    reg_data = (
        mom_1m
        .merge(mp[["stock_code", "date", "FC_MC"]], on=["stock_code", "date"], how="inner")
        .merge(vstd_df, on=["stock_code", "date"], how="inner")
    )

    def _cross_sectional_ols(grp: pd.DataFrame) -> pd.Series:
        """Run OLS: Momentum_1M ~ FC_MC + VSTD_1M, return residuals."""
        sub = grp[["Momentum_1M", "FC_MC", "VSTD_1M"]].dropna()
        if len(sub) < 10:
            return pd.Series(np.nan, index=grp.index, name="Momentum_1M_Neu")
        y = sub["Momentum_1M"].values
        X = np.column_stack([np.ones(len(sub)), sub["FC_MC"].values, sub["VSTD_1M"].values])
        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            residuals = y - X @ beta
        except np.linalg.LinAlgError:
            return pd.Series(np.nan, index=grp.index, name="Momentum_1M_Neu")
        result = pd.Series(np.nan, index=grp.index, name="Momentum_1M_Neu")
        result.loc[sub.index] = residuals
        return result

    reg_data["Momentum_1M_Neu"] = (
        reg_data.groupby("date", group_keys=False).apply(_cross_sectional_ols)
    )

    return reg_data[["stock_code", "date", "Momentum_1M_Neu"]]


# =====================================================================
# Factor 4: Residual momentum (FF3 neutralization)
# =====================================================================

def construct_fama_french_factors(
    monthly_panel: pd.DataFrame,
    valuation: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Construct Fama-French 3 factors (MKT, SMB, HML) monthly series.

    Args:
        monthly_panel: Monthly panel with monthly_return, negotiable_market_value.
        valuation: Valuation data with pb_lf.
        month_end_dates: Month-end trading dates.

    Returns:
        DataFrame with [date, MKT, SMB, HML].
    """
    mp = monthly_panel[
        ["stock_code", "date", "monthly_return", "negotiable_market_value"]
    ].dropna(subset=["monthly_return", "negotiable_market_value"]).copy()

    # Merge BP = 1 / PB
    val_me = valuation[valuation["date"].isin(month_end_dates)].copy()
    val_me["BP"] = 1.0 / val_me["pb_lf"].replace(0, np.nan)
    val_me = val_me[["stock_code", "date", "BP"]].dropna()

    mp = mp.merge(val_me, on=["stock_code", "date"], how="left")

    ff_records: list[dict] = []

    for dt, grp in mp.groupby("date"):
        sub = grp.dropna(subset=["monthly_return", "negotiable_market_value"])
        if len(sub) < 50:
            continue

        # --- MKT: cap-weighted market return ---
        weights = sub["negotiable_market_value"] / sub["negotiable_market_value"].sum()
        mkt = (sub["monthly_return"] * weights).sum()

        # --- SMB: small minus big ---
        cap_median = sub["negotiable_market_value"].median()
        small = sub[sub["negotiable_market_value"] <= cap_median]
        big = sub[sub["negotiable_market_value"] > cap_median]

        def _cap_weighted_return(df: pd.DataFrame) -> float:
            w = df["negotiable_market_value"] / df["negotiable_market_value"].sum()
            return float((df["monthly_return"] * w).sum())

        smb = _cap_weighted_return(small) - _cap_weighted_return(big) if len(small) > 10 and len(big) > 10 else np.nan

        # --- HML: high BP minus low BP ---
        bp_sub = sub.dropna(subset=["BP"])
        if len(bp_sub) > 20:
            bp_median = bp_sub["BP"].median()
            high_bp = bp_sub[bp_sub["BP"] >= bp_median]
            low_bp = bp_sub[bp_sub["BP"] < bp_median]
            hml = _cap_weighted_return(high_bp) - _cap_weighted_return(low_bp) if len(high_bp) > 10 and len(low_bp) > 10 else np.nan
        else:
            hml = np.nan

        ff_records.append({"date": dt, "MKT": mkt, "SMB": smb, "HML": hml})

    return pd.DataFrame(ff_records).sort_values("date").reset_index(drop=True)


def calculate_residual_momentum(
    monthly_panel: pd.DataFrame,
    ff_factors: pd.DataFrame,
    lookback: int = 36,
) -> pd.DataFrame:
    """Calculate residual momentum via rolling FF3 regression.

    For each stock at each month-end, regress the past `lookback` months of
    monthly returns on MKT, SMB, HML, and take the current-period residual.

    Args:
        monthly_panel: Monthly panel with [stock_code, date, monthly_return].
        ff_factors: Fama-French factors with [date, MKT, SMB, HML].
        lookback: Number of months for rolling regression window.

    Returns:
        DataFrame with [stock_code, date, Momentum_1M_Resid].
    """
    # Merge returns with FF factors
    mp = monthly_panel[["stock_code", "date", "monthly_return"]].merge(
        ff_factors, on="date", how="inner"
    )
    mp = mp.sort_values(["stock_code", "date"]).reset_index(drop=True)

    # Pivot to wide format for vectorized processing
    ret_pivot = mp.pivot_table(index="date", columns="stock_code", values="monthly_return")
    ff = ff_factors.set_index("date")[["MKT", "SMB", "HML"]].reindex(ret_pivot.index)

    dates = ret_pivot.index.tolist()
    residual_records: list[pd.DataFrame] = []

    for i in range(lookback, len(dates)):
        dt = dates[i]
        # Window: [i-lookback, i] inclusive (lookback+1 points, but regression uses lookback points before current)
        # Actually we want t-35 to t (36 months including current)
        window_dates = dates[i - lookback + 1: i + 1]  # 36 months
        if len(window_dates) < lookback:
            continue

        ret_window = ret_pivot.loc[window_dates]
        ff_window = ff.loc[window_dates].dropna()

        common_dates = ret_window.index.intersection(ff_window.index)
        if len(common_dates) < lookback // 2:
            continue

        ret_w = ret_window.loc[common_dates]
        X = np.column_stack([
            np.ones(len(common_dates)),
            ff_window.loc[common_dates].values,
        ])

        # Vectorized OLS for all stocks at once
        # For each stock with sufficient data, compute residual at current period
        valid_cols = ret_w.columns[ret_w.notna().sum() >= lookback // 2]
        Y = ret_w[valid_cols].values  # T x N

        # Mask NaN rows per stock
        residuals = {}
        for j, stock in enumerate(valid_cols):
            y_j = Y[:, j]
            valid_mask = ~np.isnan(y_j)
            if valid_mask.sum() < 12:
                continue
            X_valid = X[valid_mask]
            y_valid = y_j[valid_mask]
            try:
                beta = np.linalg.lstsq(X_valid, y_valid, rcond=None)[0]
                # Current period residual (last row)
                last_idx = len(common_dates) - 1
                if valid_mask[last_idx]:
                    resid = y_j[last_idx] - X[last_idx] @ beta
                    residuals[stock] = resid
            except np.linalg.LinAlgError:
                continue

        if residuals:
            rec = pd.DataFrame(
                {"stock_code": list(residuals.keys()), "Momentum_1M_Resid": list(residuals.values())}
            ).assign(date=dt)
            residual_records.append(rec)

    if residual_records:
        return pd.concat(residual_records, ignore_index=True)
    return pd.DataFrame(columns=["stock_code", "date", "Momentum_1M_Resid"])
