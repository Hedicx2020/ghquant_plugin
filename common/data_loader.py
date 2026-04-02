"""
Common data loading utilities.

Provides functions to load market data, construct stock universes,
and filter ST / suspended stocks from local parquet files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

# Default local data directory
LOCAL_DATA_DIR = Path.home() / "local_data"


# ---------------------------------------------------------------------------
# Core loaders
# ---------------------------------------------------------------------------

def load_stock_price(
    data_dir: Path = LOCAL_DATA_DIR,
    columns: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load daily stock price data.

    Args:
        data_dir: Root directory of parquet files.
        columns: Subset of columns to load; None for all.

    Returns:
        DataFrame with columns [stock_code, date, prev_close, close, open,
        high, low, ...].
    """
    path = data_dir / "ashare_stock_price.parquet"
    df = pd.read_parquet(path, columns=columns)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_stock_trade(
    data_dir: Path = LOCAL_DATA_DIR,
    columns: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load daily stock trade data (returns, turnover, market cap, etc.).

    Args:
        data_dir: Root directory.
        columns: Subset of columns.

    Returns:
        DataFrame with columns [stock_code, date, change_pct, range_pct,
        market_value, negotiable_market_value, turnover_rate, ...].
    """
    path = data_dir / "ashare_stock_trade.parquet"
    df = pd.read_parquet(path, columns=columns)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_suspend(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
    """Load daily suspend status.

    Returns:
        DataFrame with [stock_code, date, ifsuspend].
    """
    path = data_dir / "ashare_suspend.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "date", "ifsuspend"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_st_data(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
    """Load ST status records.

    Returns:
        DataFrame with [stock_code, implement_date, remove_date].
    """
    path = data_dir / "ashare_stock_st.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "implement_date", "remove_date"])
    df["implement_date"] = pd.to_datetime(df["implement_date"])
    df["remove_date"] = pd.to_datetime(df["remove_date"])
    return df


def load_industry(
    data_dir: Path = LOCAL_DATA_DIR,
    standard_code: int = 37,
) -> pd.DataFrame:
    """Load industry classification (default: CITICS level-1, code=37).

    Args:
        data_dir: Root directory.
        standard_code: 37 for CITICS (中信一级), 38 for Shenwan (申万一级).

    Returns:
        DataFrame with [stock_code, first_industry_name].
    """
    path = data_dir / "ashare_stock_industry.parquet"
    df = pd.read_parquet(path)
    df = df.loc[df["standard_code"] == standard_code, ["stock_code", "first_industry_name"]]
    return df.drop_duplicates(subset=["stock_code"]).reset_index(drop=True)


def load_trade_calendar(
    data_dir: Path = LOCAL_DATA_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load trade calendar.

    Args:
        data_dir: Root directory.
        start_date: Start date filter (inclusive).
        end_date: End date filter (inclusive).

    Returns:
        DataFrame with [date, IfTradingDay, IfMonthEnd, ...].
    """
    path = data_dir / "ashare_tradeday.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    # Filter to trading days in SecuMarket 83 (Shanghai) or 90 (both)
    df = df[df["IfTradingDay"] == 1]
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    return df.sort_values("date").reset_index(drop=True)


def load_index_components(
    index_code: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DataFrame:
    """Load index component history.

    Args:
        index_code: e.g. '000300' for CSI 300.
        data_dir: Root directory.

    Returns:
        DataFrame with [stock_code, in_date, out_date].
    """
    path = data_dir / "ashare_index_components.parquet"
    df = pd.read_parquet(path)
    df = df[df["index_code"] == index_code][["stock_code", "in_date", "out_date"]].copy()
    df["in_date"] = pd.to_datetime(df["in_date"])
    df["out_date"] = pd.to_datetime(df["out_date"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Stock universe helpers
# ---------------------------------------------------------------------------

def get_month_end_trading_days(
    start_date: str,
    end_date: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DatetimeIndex:
    """Get month-end trading days within [start_date, end_date].

    Args:
        start_date: Start date.
        end_date: End date.
        data_dir: Root directory.

    Returns:
        DatetimeIndex of month-end trading days.
    """
    cal = load_trade_calendar(data_dir, start_date, end_date)
    month_ends = cal[cal["IfMonthEnd"] == 1]["date"]
    return pd.DatetimeIndex(month_ends.values)


def filter_st_stocks(
    stock_codes: pd.Series,
    date: pd.Timestamp,
    st_data: pd.DataFrame,
) -> pd.Index:
    """Return stock codes that are NOT in ST status on the given date.

    Args:
        stock_codes: Series or Index of stock codes.
        date: Reference date.
        st_data: ST records from load_st_data().

    Returns:
        Index of non-ST stock codes.
    """
    st_on_date = st_data[
        (st_data["implement_date"] <= date)
        & ((st_data["remove_date"] > date) | st_data["remove_date"].isna())
    ]["stock_code"].unique()
    codes = pd.Index(stock_codes)
    return codes.difference(pd.Index(st_on_date))


def filter_suspended(
    panel: pd.DataFrame,
    suspend_data: pd.DataFrame,
    stock_col: str = "stock_code",
    date_col: str = "date",
) -> pd.DataFrame:
    """Remove rows where the stock is suspended on that date.

    Args:
        panel: Panel DataFrame.
        suspend_data: Suspend status data.
        stock_col: Stock code column.
        date_col: Date column.

    Returns:
        Filtered DataFrame.
    """
    merged = panel.merge(
        suspend_data[[stock_col, date_col, "ifsuspend"]],
        on=[stock_col, date_col],
        how="left",
    )
    return merged[merged["ifsuspend"] != 1].drop(columns=["ifsuspend"])


def get_stock_universe(
    date: pd.Timestamp,
    panel: pd.DataFrame,
    st_data: pd.DataFrame,
    index_code: Optional[str] = None,
    index_components: Optional[pd.DataFrame] = None,
    stock_col: str = "stock_code",
    date_col: str = "date",
) -> pd.Index:
    """Get investable stock universe on a given date.

    Filters: non-ST, non-suspended (caller should have already removed
    suspended rows from panel).  Optionally restricts to index members.

    Args:
        date: Reference date.
        panel: Panel data (already filtered for the date).
        st_data: ST records.
        index_code: Optional index code for restricting to members.
        index_components: Pre-loaded index component data.
        stock_col: Stock code column.
        date_col: Date column.

    Returns:
        Index of valid stock codes.
    """
    day_data = panel[panel[date_col] == date]
    codes = day_data[stock_col].unique()

    # Filter ST
    codes = filter_st_stocks(pd.Series(codes), date, st_data)

    # Filter to index members if requested
    if index_code and index_components is not None:
        members = index_components[
            (index_components["in_date"] <= date)
            & ((index_components["out_date"] > date) | index_components["out_date"].isna())
        ]["stock_code"].unique()
        codes = codes.intersection(pd.Index(members))

    return codes


def load_market_data(
    start_date: str,
    end_date: str,
    data_dir: Path = LOCAL_DATA_DIR,
    price_cols: Optional[Sequence[str]] = None,
    trade_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load and merge price + trade data for the given period.

    Args:
        start_date: Start date (inclusive).
        end_date: End date (inclusive).
        data_dir: Root directory.
        price_cols: Price columns to keep.
        trade_cols: Trade columns to keep.

    Returns:
        Merged DataFrame with both price and trade fields.
    """
    # Default columns
    if price_cols is None:
        price_cols = ["stock_code", "date", "prev_close", "close", "open", "high", "low"]
    if trade_cols is None:
        trade_cols = [
            "stock_code", "date", "change_pct", "range_pct",
            "market_value", "negotiable_market_value", "turnover_rate",
        ]

    price = load_stock_price(data_dir, columns=list(price_cols))
    trade = load_stock_trade(data_dir, columns=list(trade_cols))

    # Date filter -- include extra lookback buffer (400 days before start)
    buffer_start = pd.Timestamp(start_date) - pd.DateOffset(days=400)
    price = price[(price["date"] >= buffer_start) & (price["date"] <= pd.Timestamp(end_date))]
    trade = trade[(trade["date"] >= buffer_start) & (trade["date"] <= pd.Timestamp(end_date))]

    merged = price.merge(trade, on=["stock_code", "date"], how="inner")
    return merged.sort_values(["stock_code", "date"]).reset_index(drop=True)
