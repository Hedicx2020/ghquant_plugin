"""Strategy logic for the stock-bond seesaw and alternate-day reversal report.

The implementation follows the 2023-08-22 CMS report as far as the PDF
specifies it.  The prior report's exact "modified reversal" formula is not
included in this PDF, so the reversal signal is intentionally isolated in one
function and can be replaced when the original formula is available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for the report reproduction."""

    data_dir: Path = Path.home() / "local_data"
    output_dir: Path = Path(__file__).resolve().parents[2] / "output" / "test" / "results"
    start_date: str = "2015-03-24"
    end_date: str = "2023-08-02"
    hs300_code: str = "000300"
    long_window: int = 120
    short_window: int = 20
    daily_lower_threshold: float = 0.03
    daily_upper_threshold: float = 0.05
    reverse_min_abs: float = 0.0003
    reverse_max_abs: float = 0.005
    periods_per_year: int = 252

    def to_jsonable(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        data = asdict(self)
        data["data_dir"] = str(self.data_dir)
        data["output_dir"] = str(self.output_dir)
        return data


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required data file is missing: {path}")


def _to_date_index(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    return result.sort_values("date").drop_duplicates("date", keep="last").set_index("date")


def signed_signal(values: pd.Series | np.ndarray) -> pd.Series:
    """Return -1, 0, +1 as integer signal values."""

    series = pd.Series(values)
    return np.sign(series.fillna(0.0)).astype(int)


def load_treasury_futures_main(
    data_dir: Path,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Load 10-year CGB futures main-contract daily data.

    Args:
        data_dir: Local data directory.
        start_date: Backtest start date.
        end_date: Backtest end date.

    Returns:
        Date-indexed DataFrame with close/settle returns in decimal form.
    """

    path = data_dir / "financial_future_price.parquet"
    _require_file(path)
    columns = [
        "date",
        "contract_code",
        "contract_name",
        "close",
        "settle",
        "pct_of_close_price",
        "pct_of_sett_price",
        "main_contract",
    ]
    raw = pd.read_parquet(path, columns=columns)
    code = raw["contract_code"].astype(str)
    mask = code.str.match(r"^T\d{4}$") & raw["main_contract"].eq(1)
    frame = _to_date_index(raw.loc[mask, columns[:-1]])

    frame["close_return"] = frame["pct_of_close_price"] / 100.0
    frame["settle_return"] = frame["pct_of_sett_price"] / 100.0
    frame["close_return"] = frame["close_return"].fillna(frame["close"].pct_change())
    frame["settle_return"] = frame["settle_return"].fillna(frame["settle"].pct_change())

    start = pd.Timestamp(start_date) - pd.Timedelta(days=10)
    end = pd.Timestamp(end_date)
    return frame.loc[(frame.index >= start) & (frame.index <= end)].copy()


def load_hs300(data_dir: Path, hs300_code: str = "000300") -> pd.DataFrame:
    """Load CSI 300 daily data with enough history for expanding quantiles."""

    path = data_dir / "ashare_csiindex_trade.parquet"
    _require_file(path)
    columns = ["index_code", "index_name", "date", "prev_close", "close", "change_pct"]
    raw = pd.read_parquet(path, columns=columns)
    frame = raw.loc[raw["index_code"].astype(str).eq(hs300_code), columns].copy()
    frame = _to_date_index(frame)
    frame["hs300_return"] = frame["change_pct"] / 100.0
    frame["hs300_return"] = frame["hs300_return"].fillna(frame["close"].pct_change())
    return frame


def _interval_signal(close: pd.Series, window: int) -> pd.DataFrame:
    interval_return = close.pct_change(window)
    lower = interval_return.expanding(min_periods=max(30, window)).quantile(1 / 3)
    upper = interval_return.expanding(min_periods=max(30, window)).quantile(2 / 3)
    signal = pd.Series(0, index=close.index, dtype=int)
    signal = signal.mask(interval_return > upper, -1)
    signal = signal.mask(interval_return < lower, 1)
    return pd.DataFrame(
        {
            f"chg_{window}": interval_return,
            f"lower_{window}": lower,
            f"upper_{window}": upper,
            f"signal_{window}": signal.fillna(0).astype(int),
        },
        index=close.index,
    )


def calculate_interval_seesaw_signal(
    hs300: pd.DataFrame,
    long_window: int = 120,
    short_window: int = 20,
) -> pd.DataFrame:
    """Calculate long/short horizon stock-bond seesaw signals."""

    source = hs300.copy()
    if "date" in source.columns:
        source = _to_date_index(source)
    long_part = _interval_signal(source["close"], long_window)
    short_part = _interval_signal(source["close"], short_window)
    combined = long_part.join(short_part, how="outer")
    combined["long_signal"] = combined[f"signal_{long_window}"].fillna(0).astype(int)
    combined["short_signal"] = combined[f"signal_{short_window}"].fillna(0).astype(int)
    combined["ls_signal"] = np.sign(combined["long_signal"] + combined["short_signal"]).astype(int)
    return combined


def calculate_daily_seesaw_signal(
    hs300: pd.DataFrame,
    lower_threshold: float = 0.03,
    upper_threshold: float = 0.05,
) -> pd.DataFrame:
    """Calculate daily seesaw signals and apply them on the next trading day."""

    source = hs300.copy()
    if "date" in source.columns:
        source = _to_date_index(source)
    returns = source["hs300_return"].copy()

    raw_lower = pd.Series(0, index=returns.index, dtype=int)
    raw_lower = raw_lower.mask(returns > lower_threshold, -1)
    raw_lower = raw_lower.mask(returns < -lower_threshold, 1)

    raw_upper = pd.Series(0, index=returns.index, dtype=int)
    raw_upper = raw_upper.mask(returns > upper_threshold, -1)
    raw_upper = raw_upper.mask(returns < -upper_threshold, 1)

    return pd.DataFrame(
        {
            "daily_lower": raw_lower.shift(1).fillna(0).astype(int),
            "daily_upper": raw_upper.shift(1).fillna(0).astype(int),
            "hs300_return_lag1": returns.shift(1),
        },
        index=returns.index,
    )


def calculate_reverse_signal(
    futures: pd.DataFrame,
    min_abs: float = 0.0003,
    max_abs: float = 0.005,
) -> pd.DataFrame:
    """Calculate the T-2 settlement-price alternate-day reversal signal."""

    source = futures.copy()
    if "date" in source.columns:
        source = _to_date_index(source)
    lagged = source["settle_return"].shift(2)
    active = lagged.abs().between(min_abs, max_abs, inclusive="both")
    signal = pd.Series(0, index=source.index, dtype=int)
    signal = signal.mask(active & (lagged > 0), -1)
    signal = signal.mask(active & (lagged < 0), 1)
    return pd.DataFrame(
        {
            "reverse_chg_t_minus_2": lagged,
            "reverse_active": active.fillna(False),
            "reverse_signal": signal.fillna(0).astype(int),
        },
        index=source.index,
    )


def calculate_calendar_signal(frame: pd.DataFrame) -> pd.DataFrame:
    """Thursday calendar signal from the report."""

    source = frame.copy()
    if "date" in source.columns:
        source = _to_date_index(source)
    signal = pd.Series((source.index.weekday == 3).astype(int), index=source.index)
    return pd.DataFrame({"calendar_signal": signal.astype(int)}, index=source.index)


def combine_strategy_signals(signals: pd.DataFrame) -> pd.DataFrame:
    """Combine signals according to the three report priority steps."""

    frame = signals.copy().fillna(
        {
            "daily_upper": 0,
            "daily_lower": 0,
            "ls_signal": 0,
            "reverse_signal": 0,
            "calendar_signal": 0,
            "reverse_active": False,
        }
    )
    int_cols = ["daily_upper", "daily_lower", "ls_signal", "reverse_signal", "calendar_signal"]
    frame[int_cols] = frame[int_cols].astype(int)
    frame["reverse_active"] = frame["reverse_active"].astype(bool)

    frame["daily_upper_calendar"] = np.sign(
        frame["daily_upper"] + frame["calendar_signal"]
    ).astype(int)
    frame["seesaw_signal"] = np.sign(frame["daily_lower"] + frame["ls_signal"]).astype(int)

    frame["position"] = 0
    frame["signal_source"] = "flat"

    first = frame["daily_upper_calendar"].ne(0)
    frame.loc[first, "position"] = frame.loc[first, "daily_upper_calendar"]
    frame.loc[first, "signal_source"] = "daily_upper_calendar"

    second = (
        ~first
        & frame["daily_upper"].eq(0)
        & frame["reverse_active"]
        & frame["reverse_signal"].ne(0)
    )
    frame.loc[second, "position"] = frame.loc[second, "reverse_signal"]
    frame.loc[second, "signal_source"] = "reverse"

    third = ~first & ~second & frame["seesaw_signal"].ne(0)
    frame.loc[third, "position"] = frame.loc[third, "seesaw_signal"]
    frame.loc[third, "signal_source"] = "seesaw"

    frame["position"] = frame["position"].astype(int)
    frame["long_only_position"] = frame["position"].clip(lower=0)
    return frame


def calculate_strategy_returns(
    futures: pd.DataFrame,
    combined_signals: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate target-day close-to-close returns for each signal."""

    future = futures.copy()
    if "date" in future.columns:
        future = _to_date_index(future)
    future = future[["contract_code", "close", "settle", "close_return", "settle_return"]].copy()
    future["future_return"] = future["close_return"]

    result = combined_signals.join(future, how="inner")
    result["strategy_return"] = result["position"] * result["future_return"]
    result["long_only_return"] = result["long_only_position"] * result["future_return"]
    result["benchmark_return"] = result["future_return"]
    return result.dropna(subset=["future_return"]).copy()


def performance_metrics(
    returns: pd.Series,
    periods_per_year: int = 252,
    active_mask: pd.Series | None = None,
) -> dict[str, float]:
    """Calculate common daily strategy performance metrics."""

    clean = returns.dropna().astype(float)
    if clean.empty:
        return {
            "cumulative_return": 0.0,
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "n_periods": 0,
        }

    nav = (1.0 + clean).cumprod()
    cumulative_return = float(nav.iloc[-1] - 1.0)
    annual_return = float(nav.iloc[-1] ** (periods_per_year / len(clean)) - 1.0)
    annual_volatility = float(clean.std(ddof=1) * np.sqrt(periods_per_year))
    sharpe = float(annual_return / annual_volatility) if annual_volatility > 0 else 0.0
    drawdown = nav / nav.cummax() - 1.0
    max_drawdown = float(-drawdown.min())
    calmar = float(annual_return / max_drawdown) if max_drawdown > 0 else 0.0

    if active_mask is not None:
        aligned_mask = active_mask.reindex(clean.index).fillna(False).astype(bool)
        win_base = clean[aligned_mask]
    else:
        win_base = clean
    if win_base.empty:
        win_rate = 0.0
        profit_loss_ratio = 0.0
    else:
        win_rate = float((win_base > 0).mean())
        avg_gain = win_base[win_base > 0].mean()
        avg_loss = win_base[win_base < 0].mean()
        profit_loss_ratio = float(avg_gain / abs(avg_loss)) if pd.notna(avg_loss) and avg_loss < 0 else 0.0

    return {
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "n_periods": int(len(clean)),
    }


def summarize_backtest(backtest: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """Summarize multi-side, long-only and benchmark performance."""

    variants = [
        ("周内+复合跷跷板+隔日反转(多空)", "strategy_return", backtest["position"].ne(0)),
        ("周内+复合跷跷板+隔日反转(仅做多)", "long_only_return", backtest["long_only_position"].gt(0)),
        ("T", "benchmark_return", pd.Series(True, index=backtest.index)),
    ]
    records: list[dict[str, float | str]] = []
    n_years = len(backtest) / config.periods_per_year
    for name, column, active in variants:
        metrics = performance_metrics(backtest[column], config.periods_per_year, active)
        record: dict[str, float | str] = {"策略": name, **metrics}
        if column == "strategy_return":
            changes = backtest["position"].diff().fillna(0).ne(0).sum()
            record["annual_timing_count"] = float(changes / n_years) if n_years > 0 else 0.0
        else:
            record["annual_timing_count"] = float(active.sum() / n_years) if n_years > 0 else 0.0
        if column == "strategy_return":
            long_mask = backtest["position"].gt(0)
            short_mask = backtest["position"].lt(0)
            up_mask = backtest["benchmark_return"].gt(0)
            down_mask = backtest["benchmark_return"].lt(0)
            record["long_win_rate"] = float((backtest.loc[long_mask, column] > 0).mean()) if long_mask.any() else 0.0
            record["short_win_rate"] = float((backtest.loc[short_mask, column] > 0).mean()) if short_mask.any() else 0.0
            record["up_market_win_rate"] = float((backtest.loc[up_mask, column] > 0).mean()) if up_mask.any() else 0.0
            record["down_market_win_rate"] = float((backtest.loc[down_mask, column] > 0).mean()) if down_mask.any() else 0.0
        records.append(record)
    return pd.DataFrame(records).set_index("策略")


def calculate_signal_correlation(backtest: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Rolling correlation between final signal and next futures return."""

    corr = backtest["position"].rolling(window).corr(backtest["future_return"])
    return pd.DataFrame(
        {
            "date": corr.index,
            "rolling_signal_return_corr": corr.values,
            "position": backtest["position"].values,
            "future_return": backtest["future_return"].values,
            "strategy_return": backtest["strategy_return"].values,
        }
    )


def group_performance(backtest: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """Performance by signal source."""

    records = []
    for source in ["daily_upper_calendar", "reverse", "seesaw", "flat"]:
        mask = backtest["signal_source"].eq(source)
        source_returns = backtest["strategy_return"].where(mask, 0.0)
        metrics = performance_metrics(source_returns, config.periods_per_year, mask)
        records.append({"signal_source": source, "active_days": int(mask.sum()), **metrics})
    return pd.DataFrame(records).set_index("signal_source")


def annual_performance(backtest: pd.DataFrame) -> pd.DataFrame:
    """Calendar-year return table for strategy and benchmark."""

    data = backtest[["strategy_return", "long_only_return", "benchmark_return"]].copy()
    grouped = data.groupby(data.index.year)
    return grouped.apply(lambda g: (1.0 + g).prod() - 1.0, include_groups=False)


def build_backtest(config: BacktestConfig) -> dict[str, Any]:
    """Run the complete signal and return calculation pipeline."""

    futures = load_treasury_futures_main(config.data_dir, config.start_date, config.end_date)
    hs300 = load_hs300(config.data_dir, config.hs300_code)

    interval = calculate_interval_seesaw_signal(
        hs300, long_window=config.long_window, short_window=config.short_window
    )
    daily = calculate_daily_seesaw_signal(
        hs300,
        lower_threshold=config.daily_lower_threshold,
        upper_threshold=config.daily_upper_threshold,
    )
    reverse = calculate_reverse_signal(
        futures, min_abs=config.reverse_min_abs, max_abs=config.reverse_max_abs
    )
    calendar = calculate_calendar_signal(futures.reset_index()[["date"]])

    signal_frame = (
        futures[[]]
        .join(interval[["ls_signal", "long_signal", "short_signal"]].shift(1), how="left")
        .join(daily[["daily_lower", "daily_upper", "hs300_return_lag1"]], how="left")
        .join(reverse, how="left")
        .join(calendar, how="left")
        .fillna(
            {
                "ls_signal": 0,
                "long_signal": 0,
                "short_signal": 0,
                "daily_lower": 0,
                "daily_upper": 0,
                "reverse_signal": 0,
                "calendar_signal": 0,
                "reverse_active": False,
            }
        )
    )
    combined = combine_strategy_signals(signal_frame)
    backtest = calculate_strategy_returns(futures, combined)
    backtest = backtest.loc[
        (backtest.index >= pd.Timestamp(config.start_date))
        & (backtest.index <= pd.Timestamp(config.end_date))
    ].copy()

    summary = summarize_backtest(backtest, config)
    ic_series = calculate_signal_correlation(backtest)
    group_perf = group_performance(backtest, config)
    annual = annual_performance(backtest)

    return {
        "config": config,
        "futures": futures,
        "hs300": hs300,
        "signals": combined,
        "backtest": backtest,
        "summary": summary,
        "ic_series": ic_series,
        "group_performance": group_perf,
        "annual_performance": annual,
    }
