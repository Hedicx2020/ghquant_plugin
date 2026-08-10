"""m1 六因子与中信行业收益构建入口。

本模块只实现本报告特有的中国股票截面定义；月频宏观、基准、国债和
金融湍流仍由 :mod:`data_pipeline` 负责。信号只使用月末已知信息，持仓从
下一交易日开始，并在下一月对应执行日结算收益。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from common.data_loader import filter_st_stocks, get_index_members_on_date

from .config import ChinaFactorTimingConfig


@dataclass
class EquityFactorBase:
    """供 ``data_pipeline.build_m1_dataset`` 消费的股票因子底座。"""

    industry_returns: pd.DataFrame
    factor_returns: pd.DataFrame
    factor_constituents: pd.DataFrame
    data_quality: pd.DataFrame


_STYLE_FACTORS: Final[tuple[str, ...]] = (
    "Value",
    "Growth",
    "Momentum",
    "Low Volatility",
    "Quality",
)

MAX_EXIT_DELAY_TRADING_DAYS: Final[int] = 20


def _date_filters(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[str, str, pd.Timestamp]]:
    return [("date", ">=", start), ("date", "<=", end)]


def _normalise_st_intervals(st: pd.DataFrame) -> pd.DataFrame:
    """标准化ST生效区间；remove_date当日不再视为ST。"""
    result = st[["stock_code", "implement_date", "remove_date"]].copy()
    result["stock_code"] = result["stock_code"].astype(str)
    result["implement_date"] = pd.to_datetime(result["implement_date"], errors="coerce").dt.normalize()
    result["remove_date"] = pd.to_datetime(result["remove_date"], errors="coerce").dt.normalize()
    return result.dropna(subset=["implement_date"])


def _st_active_flags(rows: pd.DataFrame, date_column: str, st: pd.DataFrame) -> pd.Series:
    """逐股票判断日期是否落在任一 ``[implement_date, remove_date)`` 区间。"""
    flags = pd.Series(False, index=rows.index, dtype=bool)
    if rows.empty or st.empty:
        return flags
    intervals = _normalise_st_intervals(st)
    for stock_code, row_index in rows.groupby("stock_code", sort=False).groups.items():
        stock_intervals = intervals.loc[intervals["stock_code"].eq(str(stock_code))]
        if stock_intervals.empty:
            continue
        dates = pd.to_datetime(rows.loc[row_index, date_column]).dt.normalize().to_numpy()
        active = np.zeros(len(row_index), dtype=bool)
        for item in stock_intervals.itertuples(index=False):
            within = dates >= np.datetime64(item.implement_date)
            if pd.notna(item.remove_date):
                within &= dates < np.datetime64(item.remove_date)
            active |= within
        flags.loc[row_index] = active
    return flags


def _apply_trade_restrictions(
    rows: pd.DataFrame,
    date_column: str,
    st: pd.DataFrame,
    *,
    require_close: bool,
) -> pd.DataFrame:
    """统一执行日和退出日的ST、停牌、无量、涨跌停限制。"""
    result = rows.copy()
    result[date_column] = pd.to_datetime(result[date_column]).dt.normalize()
    result["is_st"] = _st_active_flags(result, date_column, st)
    result["no_volume"] = result.get("volume", pd.Series(index=result.index, dtype=float)).fillna(0).le(0)
    result["is_suspended"] = result.get(
        "if_suspend", pd.Series(index=result.index, dtype=float)
    ).fillna(0).eq(1)
    result["is_limit_up"] = result.get(
        "surged_limit", pd.Series(index=result.index, dtype=float)
    ).fillna(0).eq(1)
    result["is_limit_down"] = result.get(
        "decline_limit", pd.Series(index=result.index, dtype=float)
    ).fillna(0).eq(1)
    result["missing_close"] = (
        result.get("close", pd.Series(index=result.index, dtype=float)).isna()
        if require_close
        else False
    )
    blocked_columns = [
        "is_st", "no_volume", "is_suspended", "is_limit_up", "is_limit_down", "missing_close",
    ]
    result["can_trade"] = ~result[blocked_columns].any(axis=1)
    reason_labels = (
        ("is_st", "st"),
        ("no_volume", "no_volume"),
        ("is_suspended", "suspended"),
        ("is_limit_up", "limit_up"),
        ("is_limit_down", "limit_down"),
        ("missing_close", "missing_close"),
    )
    result["restriction_reason"] = [
        "|".join(label for column, label in reason_labels if bool(result.at[index, column])) or "tradable"
        for index in result.index
    ]
    return result


def _build_exit_candidate_calendar(
    config: ChinaFactorTimingConfig,
    intended_dates: pd.Series,
    *,
    max_delay_trading_days: int = MAX_EXIT_DELAY_TRADING_DAYS,
) -> pd.DataFrame:
    """为每个计划退出日冻结当日及之后20个额外交易日。"""
    intended = pd.DatetimeIndex(pd.to_datetime(intended_dates).drop_duplicates().sort_values())
    if intended.empty:
        return pd.DataFrame(
            columns=[
                "intended_return_date", "candidate_return_date",
                "exit_delay_trading_days", "exit_delay_days",
            ]
        )
    calendar_end = intended.max() + pd.Timedelta(days=max(60, 4 * max_delay_trading_days))
    calendar = pd.read_parquet(
        config.path("calendar"),
        columns=["date", "IfTradingDay"],
        filters=_date_filters(intended.min(), calendar_end),
    )
    calendar["date"] = pd.to_datetime(calendar["date"]).dt.normalize()
    trading_days = pd.DatetimeIndex(
        calendar.loc[calendar["IfTradingDay"].eq(1), "date"].drop_duplicates().sort_values()
    )
    parts: list[pd.DataFrame] = []
    for intended_date in intended:
        start = trading_days.searchsorted(intended_date, side="left")
        candidates = trading_days[start : start + max_delay_trading_days + 1]
        if len(candidates) != max_delay_trading_days + 1 or candidates[0] != intended_date:
            raise ValueError(f"交易日历不足以构造{intended_date:%Y-%m-%d}退出搜索窗")
        part = pd.DataFrame(
            {
                "intended_return_date": intended_date,
                "candidate_return_date": candidates,
                "exit_delay_trading_days": np.arange(len(candidates), dtype=int),
            }
        )
        part["exit_delay_days"] = (
            part["candidate_return_date"] - part["intended_return_date"]
        ).dt.days
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def _execution_schedule(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """把每个月末信号映射到下一交易日及下一月的对应执行日。"""
    signals = pd.to_datetime(calendar["signal_date"]).drop_duplicates().sort_values()
    end = signals.max() + pd.offsets.MonthEnd(config.execution_horizon_months)
    trading_days = pd.read_parquet(
        config.path("calendar"),
        columns=["date", "IfTradingDay", "IfMonthEnd"],
        filters=_date_filters(signals.min(), end),
    )
    trading_days["date"] = pd.to_datetime(trading_days["date"]).astype("datetime64[ns]").dt.normalize()
    days = pd.DatetimeIndex(
        trading_days.loc[trading_days["IfTradingDay"] == 1, "date"].drop_duplicates().sort_values()
    )
    month_ends = pd.DatetimeIndex(
        trading_days.loc[
            (trading_days["IfTradingDay"] == 1) & (trading_days["IfMonthEnd"] == 1),
            "date",
        ].drop_duplicates().sort_values()
    )

    def next_trading_day(dates: pd.Series) -> pd.DatetimeIndex:
        positions = days.searchsorted(pd.DatetimeIndex(dates), side="right")
        if (positions >= len(days)).any():
            raise ValueError("交易日历不足以构造下一月T+1收益")
        return days[positions]

    schedule = pd.DataFrame({"signal_date": signals.to_numpy()})
    schedule["execution_date"] = next_trading_day(schedule["signal_date"])
    next_month_positions = month_ends.searchsorted(pd.DatetimeIndex(schedule["signal_date"]), side="right")
    if (next_month_positions >= len(month_ends)).any():
        raise ValueError("交易日历不足以定位下一交易月末")
    schedule["next_signal_date"] = month_ends[next_month_positions]
    schedule["return_date"] = next_trading_day(schedule["next_signal_date"])
    if not (
        (schedule["signal_date"] < schedule["execution_date"])
        & (schedule["execution_date"] < schedule["return_date"])
    ).all():
        raise AssertionError("交易日程必须严格满足 signal_date < execution_date < return_date")
    return schedule


def _read_stock_panel(
    config: ChinaFactorTimingConfig,
    schedule: pd.DataFrame,
    stock_codes: list[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """读取因子历史、信号日估值市值及冻结退出搜索窗内价格。"""
    exit_candidates = _build_exit_candidate_calendar(config, schedule["return_date"])
    end = exit_candidates["candidate_return_date"].max()
    code_filter = [] if stock_codes is None else [("stock_code", "in", stock_codes)]
    price = pd.read_parquet(
        config.path("stock_price_forward"),
        columns=["stock_code", "date", "close"],
        filters=_date_filters(pd.Timestamp(config.factor_history_start), end) + code_filter,
    )
    price["date"] = pd.to_datetime(price["date"]).dt.normalize()
    price = price.sort_values(["stock_code", "date"]).drop_duplicates(["stock_code", "date"], keep="last")

    signal_dates = schedule["signal_date"].tolist()
    trade = pd.read_parquet(
        config.path("stock_trade"),
        columns=["stock_code", "date", "market_value", "volume"],
        filters=[("date", "in", signal_dates + schedule["execution_date"].tolist())] + code_filter,
    )
    trade["date"] = pd.to_datetime(trade["date"]).dt.normalize()
    trade = trade.sort_values(["stock_code", "date"]).drop_duplicates(["stock_code", "date"], keep="last")

    value = pd.read_parquet(
        config.path("stock_value"),
        columns=["stock_code", "date", "pb_lf"],
        filters=_date_filters(pd.Timestamp(config.factor_history_start), schedule["signal_date"].max()) + code_filter,
    )
    value["date"] = pd.to_datetime(value["date"]).dt.normalize()
    value = value.sort_values(["stock_code", "date"]).drop_duplicates(["stock_code", "date"], keep="last")
    return price, trade, value


def _candidate_codes(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
    smoke_stock_limit: int | None,
) -> tuple[pd.DataFrame, list[str] | None]:
    components = pd.read_parquet(
        config.path("index_components"),
        columns=["stock_code", "in_date", "out_date"],
        filters=[("index_code", "==", config.benchmark_index_code)],
    )
    components["in_date"] = pd.to_datetime(components["in_date"]).dt.normalize()
    components["out_date"] = pd.to_datetime(components["out_date"], errors="coerce").dt.normalize()
    components["stock_code"] = components["stock_code"].astype(str)
    if smoke_stock_limit is None:
        return components, None
    active = pd.Index([])
    for signal_date in calendar["signal_date"]:
        active = active.union(get_index_members_on_date(components, signal_date))
    codes = sorted(active.astype(str))[:smoke_stock_limit]
    return components.loc[components["stock_code"].isin(codes)].copy(), codes


def _tradable_on_execution(
    config: ChinaFactorTimingConfig,
    schedule: pd.DataFrame,
    trade: pd.DataFrame,
    stock_codes: list[str] | None,
) -> pd.DataFrame:
    execution = schedule[["signal_date", "execution_date", "return_date"]].merge(
        trade.rename(columns={"date": "execution_date"}), on="execution_date", how="inner"
    )
    code_filter = [] if stock_codes is None else [("stock_code", "in", stock_codes)]
    dates = execution["execution_date"].drop_duplicates().tolist()
    suspend = pd.read_parquet(
        config.path("stock_suspend"),
        columns=["stock_code", "date", "if_suspend"],
        filters=[("date", "in", dates)] + code_filter,
    ).rename(columns={"date": "execution_date"})
    limits = pd.read_parquet(
        config.path("stock_limit"),
        columns=["stock_code", "date", "surged_limit", "decline_limit"],
        filters=[("date", "in", dates)] + code_filter,
    ).rename(columns={"date": "execution_date"})
    st = pd.read_parquet(
        config.path("stock_st"),
        columns=["stock_code", "implement_date", "remove_date"],
        filters=code_filter or None,
    )
    for frame in (suspend, limits):
        frame["execution_date"] = pd.to_datetime(frame["execution_date"]).dt.normalize()
    execution = execution.merge(suspend, on=["stock_code", "execution_date"], how="left")
    execution = execution.merge(limits, on=["stock_code", "execution_date"], how="left")
    execution = _apply_trade_restrictions(
        execution,
        "execution_date",
        st,
        require_close=False,
    )
    execution = execution.rename(
        columns={
            "can_trade": "can_execute",
            "restriction_reason": "execution_restriction_reason",
            "is_st": "execution_is_st",
            "no_volume": "execution_no_volume",
            "is_suspended": "execution_is_suspended",
            "is_limit_up": "execution_is_limit_up",
            "is_limit_down": "execution_is_limit_down",
        }
    )
    return execution[
        [
            "signal_date", "execution_date", "return_date", "stock_code", "can_execute",
            "execution_restriction_reason", "execution_is_st", "execution_no_volume",
            "execution_is_suspended", "execution_is_limit_up", "execution_is_limit_down",
        ]
    ].copy()


def _point_in_time_financials(
    config: ChinaFactorTimingConfig,
    snapshots: pd.DataFrame,
    stock_codes: list[str] | None,
) -> pd.DataFrame:
    """按三张财务表共同披露日向后匹配质量指标，绝不按报告期倒填。"""
    code_filter = [] if stock_codes is None else [("stock_code", "in", stock_codes)]
    upper = pd.Timestamp(config.sample_end)
    statement_specs = {
        "balance": ("stock_balance", ["total_assets", "total_liability", "total_shareholder_equity"]),
        "income": ("stock_income", ["net_profit"]),
        "cashflow": ("stock_cashflow", ["net_operate_cash_flow"]),
    }
    statements: dict[str, pd.DataFrame] = {}
    for name, (file_key, fields) in statement_specs.items():
        frame = pd.read_parquet(
            config.path(file_key),
            columns=["stock_code", "end_date", "info_publ_date", *fields],
            filters=[("info_publ_date", "<=", upper)] + code_filter,
        )
        frame["end_date"] = pd.to_datetime(frame["end_date"]).dt.normalize()
        frame[f"{name}_available_date"] = pd.to_datetime(frame.pop("info_publ_date"), errors="coerce").dt.normalize()
        frame = frame.dropna(subset=[f"{name}_available_date"])
        statements[name] = frame.sort_values(f"{name}_available_date").drop_duplicates(
            ["stock_code", "end_date"], keep="last"
        )

    reports = statements["balance"].merge(statements["income"], on=["stock_code", "end_date"], how="inner")
    reports = reports.merge(statements["cashflow"], on=["stock_code", "end_date"], how="inner")
    available_cols = [f"{name}_available_date" for name in statement_specs]
    reports["financial_available_date"] = reports[available_cols].max(axis=1)
    assets = reports["total_assets"].where(reports["total_assets"].gt(0))
    reports["profitability"] = reports["net_profit"] / assets
    reports["cashflow_profitability"] = reports["net_operate_cash_flow"] / assets
    reports["accrual_quality"] = (reports["net_operate_cash_flow"] - reports["net_profit"]) / assets
    reports["low_leverage"] = -reports["total_liability"] / assets
    reports = reports.sort_values(["stock_code", "financial_available_date", "end_date"])
    reports["earnings_stability"] = -reports.groupby("stock_code", sort=False)["profitability"].transform(
        lambda s: s.expanding(config.quality_stability_min_reports).std()
    )

    left = snapshots[["stock_code", "signal_date"]].sort_values(["signal_date", "stock_code"])
    fields = [*config.quality_weights, "financial_available_date"]
    right = reports[["stock_code", *fields]].sort_values(["financial_available_date", "stock_code"])
    quality = pd.merge_asof(
        left,
        right,
        by="stock_code",
        left_on="signal_date",
        right_on="financial_available_date",
        direction="backward",
    )
    equity_right = statements["balance"][
        ["stock_code", "end_date", "balance_available_date", "total_shareholder_equity"]
    ].rename(columns={"balance_available_date": "equity_available_date"})
    equity_right = (
        equity_right.sort_values(["equity_available_date", "end_date", "stock_code"])
        .drop_duplicates(["stock_code", "equity_available_date"], keep="last")
        .sort_values(["equity_available_date", "stock_code"])
    )
    equity = pd.merge_asof(
        left,
        equity_right.drop(columns="end_date"),
        by="stock_code",
        left_on="signal_date",
        right_on="equity_available_date",
        direction="backward",
    )
    return quality.merge(equity, on=["stock_code", "signal_date"], how="left")


def _build_signal_panel(
    config: ChinaFactorTimingConfig,
    schedule: pd.DataFrame,
    components: pd.DataFrame,
    price: pd.DataFrame,
    trade: pd.DataFrame,
    value: pd.DataFrame,
    stock_codes: list[str] | None,
) -> pd.DataFrame:
    month_history = price[["stock_code", "date", "close"]].copy()
    month_history["month"] = month_history["date"].dt.to_period("M")
    month_history = month_history.sort_values(["stock_code", "date"]).groupby(
        ["stock_code", "month"], as_index=False
    ).tail(1)
    month_history["momentum"] = month_history.groupby("stock_code", sort=False)["close"].transform(
        lambda s: s.shift(config.momentum_skip_months) / s.shift(config.momentum_lookback_months) - 1.0
    )
    month_end = month_history.loc[
        month_history["date"].isin(schedule["signal_date"]),
        ["stock_code", "date", "close", "momentum"],
    ].rename(columns={"date": "signal_date"})
    price["daily_return"] = price.groupby("stock_code", sort=False)["close"].pct_change(fill_method=None)
    price["low_volatility"] = price.groupby("stock_code", sort=False)["daily_return"].transform(
        lambda s: s.rolling(config.low_vol_lookback_days, min_periods=config.low_vol_lookback_days).std()
        * np.sqrt(config.annual_trading_days)
    )
    low_vol = price.loc[price["date"].isin(schedule["signal_date"]), ["stock_code", "date", "low_volatility"]]
    low_vol = low_vol.rename(columns={"date": "signal_date"})

    panel = month_end.merge(low_vol, on=["stock_code", "signal_date"], how="left")
    panel = panel.merge(
        trade.rename(columns={"date": "signal_date"})[["stock_code", "signal_date", "market_value"]],
        on=["stock_code", "signal_date"],
        how="left",
    )
    valuation = value.rename(columns={"date": "valuation_date"}).sort_values(["valuation_date", "stock_code"])
    panel = pd.merge_asof(
        panel.sort_values(["signal_date", "stock_code"]),
        valuation,
        by="stock_code",
        left_on="signal_date",
        right_on="valuation_date",
        direction="backward",
    )
    panel = panel.merge(
        _point_in_time_financials(config, panel, stock_codes),
        on=["stock_code", "signal_date"],
        how="left",
    )
    panel["reported_pb"] = panel["pb_lf"].where(panel["pb_lf"].gt(0))
    valid_equity = panel["total_shareholder_equity"].where(panel["total_shareholder_equity"].gt(0))
    panel["derived_pb"] = panel["market_value"] / valid_equity
    panel["pb_lf"] = panel["reported_pb"].combine_first(panel["derived_pb"])
    panel["pb_source"] = np.select(
        [panel["reported_pb"].notna(), panel["derived_pb"].notna()],
        ["reported", "derived"],
        default=None,
    )

    st = pd.read_parquet(config.path("stock_st"), columns=["stock_code", "implement_date", "remove_date"])
    st["implement_date"] = pd.to_datetime(st["implement_date"]).dt.normalize()
    st["remove_date"] = pd.to_datetime(st["remove_date"], errors="coerce").dt.normalize()
    valid_parts: list[pd.DataFrame] = []
    for signal_date, group in panel.groupby("signal_date", sort=True):
        valid_codes = filter_st_stocks(group["stock_code"], signal_date, st)
        part = group.loc[group["stock_code"].isin(valid_codes)].copy()
        members = get_index_members_on_date(components, signal_date)
        part["in_style_universe"] = part["stock_code"].isin(members)
        part["style_members_total"] = len(members)
        valid_parts.append(part)
    return pd.concat(valid_parts, ignore_index=True)


def _select_factor_constituents(
    config: ChinaFactorTimingConfig,
    panel: pd.DataFrame,
    tradable: pd.DataFrame,
) -> pd.DataFrame:
    schedule_keys = tradable[["signal_date", "execution_date", "return_date"]].drop_duplicates()
    panel = panel.merge(schedule_keys, on="signal_date", how="left")
    execution_evidence = [
        "can_execute", "execution_restriction_reason", "execution_is_st",
        "execution_no_volume", "execution_is_suspended", "execution_is_limit_up",
        "execution_is_limit_down",
    ]
    panel = panel.merge(
        tradable[["signal_date", "stock_code", *execution_evidence]],
        on=["signal_date", "stock_code"],
        how="left",
    )
    panel["can_execute"] = panel["can_execute"].fillna(False).astype(bool)
    panel["execution_restriction_reason"] = panel["execution_restriction_reason"].fillna(
        "missing_trade_or_status"
    )
    for column in execution_evidence[2:]:
        panel[column] = panel[column].fillna(False).astype(bool)
    style_panel = panel.loc[panel["in_style_universe"]].copy()
    pb_coverage = style_panel.groupby("signal_date", as_index=False).agg(
        members=("style_members_total", "max"),
        pb_available=("pb_lf", "count"),
    )
    pb_coverage["pb_coverage"] = pb_coverage["pb_available"] / pb_coverage["members"]
    pb_coverage["pb_eligible"] = (
        pb_coverage["pb_available"].ge(config.pb_min_stocks)
        & pb_coverage["pb_coverage"].ge(config.pb_min_coverage)
    )
    pb_eligible_dates = pd.Index(
        pb_coverage.loc[pb_coverage["pb_eligible"], "signal_date"]
    )
    quality_z: list[pd.Series] = []
    for field, weight in config.quality_weights.items():
        grouped = style_panel.groupby("signal_date", sort=False)[field]
        std = grouped.transform("std").replace(0.0, np.nan)
        quality_z.append(weight * (style_panel[field] - grouped.transform("mean")) / std)
    style_panel["quality"] = pd.concat(quality_z, axis=1).sum(axis=1, min_count=len(quality_z))
    panel = panel.merge(
        style_panel[["signal_date", "stock_code", "quality"]],
        on=["signal_date", "stock_code"],
        how="left",
    )

    definitions = (
        ("Value", "pb_lf", config.value_fraction, True, True),
        ("Growth", "pb_lf", config.growth_fraction, False, True),
        ("Momentum", "momentum", config.momentum_fraction, False, True),
        ("Low Volatility", "low_volatility", config.low_vol_fraction, True, True),
        ("Quality", "quality", config.quality_fraction, False, True),
        ("Small-Cap", "market_value", config.small_cap_fraction, True, False),
    )
    selected: list[pd.DataFrame] = []
    for factor, field, fraction, ascending, style_only in definitions:
        universe = panel["in_style_universe"] if style_only else panel["market_value"].notna()
        candidates = panel.loc[universe & panel[field].notna()].copy()
        if factor in {"Value", "Growth"}:
            candidates = candidates.loc[candidates["signal_date"].isin(pb_eligible_dates)]
        rank = candidates.groupby("signal_date", sort=False)[field].rank(method="first", pct=True, ascending=ascending)
        item = candidates.loc[rank.le(fraction)].copy()
        item["factor"] = factor
        item["factor_signal"] = item[field]
        selected.append(item)
    constituents = pd.concat(selected, ignore_index=True)
    counts = constituents.groupby(["signal_date", "factor"])["stock_code"].transform("count")
    constituents["weight"] = 1.0 / counts
    return constituents[
        [
            "signal_date", "execution_date", "return_date", "factor", "stock_code",
            "weight", "factor_signal", "financial_available_date", "equity_available_date",
            "in_style_universe", "can_execute", "execution_restriction_reason",
            "execution_is_st", "execution_no_volume", "execution_is_suspended",
            "execution_is_limit_up", "execution_is_limit_down", "pb_source",
        ]
    ]


def _resolve_exit_trades(
    entries: pd.DataFrame,
    price: pd.DataFrame,
    config: ChinaFactorTimingConfig,
    *,
    candidate_calendar: pd.DataFrame | None = None,
    exit_trade: pd.DataFrame | None = None,
    exit_suspend: pd.DataFrame | None = None,
    exit_limits: pd.DataFrame | None = None,
    exit_st: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """按预先冻结的交易日窗，寻找每只股票首个真实可退出日。"""
    output_columns = [
        "stock_code", "intended_return_date", "actual_return_date", "exit_delay_days",
        "exit_delay_trading_days", "exit_executed", "restriction_reason", "exit_close",
        "intended_mark_close", "exit_search_horizon_date",
    ]
    positions = entries[["stock_code", "intended_return_date"]].drop_duplicates().copy()
    if positions.empty:
        return pd.DataFrame(columns=output_columns)
    positions["stock_code"] = positions["stock_code"].astype(str)
    positions["intended_return_date"] = pd.to_datetime(
        positions["intended_return_date"]
    ).dt.normalize()
    candidates = (
        candidate_calendar.copy()
        if candidate_calendar is not None
        else _build_exit_candidate_calendar(config, positions["intended_return_date"])
    )
    for column in ("intended_return_date", "candidate_return_date"):
        candidates[column] = pd.to_datetime(candidates[column]).dt.normalize()

    all_codes = positions["stock_code"].drop_duplicates().tolist()
    if exit_st is None:
        st = pd.read_parquet(
            config.path("stock_st"),
            columns=["stock_code", "implement_date", "remove_date"],
            filters=[("stock_code", "in", all_codes)],
        )
    else:
        st = exit_st.copy()

    def normalise_status(frame: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
        result = frame.copy()
        if "date" in result and "candidate_return_date" not in result:
            result = result.rename(columns={"date": "candidate_return_date"})
        result["stock_code"] = result["stock_code"].astype(str)
        result["candidate_return_date"] = pd.to_datetime(
            result["candidate_return_date"]
        ).dt.normalize()
        return result[["stock_code", "candidate_return_date", *fields]].drop_duplicates(
            ["stock_code", "candidate_return_date"], keep="last"
        )

    injected_trade = normalise_status(exit_trade, ["volume"]) if exit_trade is not None else None
    injected_suspend = (
        normalise_status(exit_suspend, ["if_suspend"]) if exit_suspend is not None else None
    )
    injected_limits = (
        normalise_status(exit_limits, ["surged_limit", "decline_limit"])
        if exit_limits is not None
        else None
    )
    price_lookup = price[["stock_code", "date", "close"]].copy().rename(
        columns={"date": "candidate_return_date"}
    )
    price_lookup["stock_code"] = price_lookup["stock_code"].astype(str)
    price_lookup["candidate_return_date"] = pd.to_datetime(
        price_lookup["candidate_return_date"]
    ).dt.normalize()
    price_lookup = price_lookup.drop_duplicates(
        ["stock_code", "candidate_return_date"], keep="last"
    )

    resolved_parts: list[pd.DataFrame] = []
    for intended_date, intended_positions in positions.groupby("intended_return_date", sort=True):
        period_calendar = candidates.loc[candidates["intended_return_date"].eq(intended_date)].copy()
        dates = period_calendar["candidate_return_date"].tolist()
        codes = intended_positions["stock_code"].drop_duplicates().tolist()
        grid = intended_positions.assign(_join_key=1).merge(
            period_calendar.assign(_join_key=1), on="_join_key", how="inner"
        ).drop(columns="_join_key")

        if injected_trade is None:
            trade = pd.read_parquet(
                config.path("stock_trade"),
                columns=["stock_code", "date", "volume"],
                filters=[("date", "in", dates), ("stock_code", "in", codes)],
            )
            trade = normalise_status(trade, ["volume"])
        else:
            trade = injected_trade.loc[
                injected_trade["stock_code"].isin(codes)
                & injected_trade["candidate_return_date"].isin(dates)
            ]
        if injected_suspend is None:
            suspend = pd.read_parquet(
                config.path("stock_suspend"),
                columns=["stock_code", "date", "if_suspend"],
                filters=[("date", "in", dates), ("stock_code", "in", codes)],
            )
            suspend = normalise_status(suspend, ["if_suspend"])
        else:
            suspend = injected_suspend.loc[
                injected_suspend["stock_code"].isin(codes)
                & injected_suspend["candidate_return_date"].isin(dates)
            ]
        if injected_limits is None:
            limits = pd.read_parquet(
                config.path("stock_limit"),
                columns=["stock_code", "date", "surged_limit", "decline_limit"],
                filters=[("date", "in", dates), ("stock_code", "in", codes)],
            )
            limits = normalise_status(limits, ["surged_limit", "decline_limit"])
        else:
            limits = injected_limits.loc[
                injected_limits["stock_code"].isin(codes)
                & injected_limits["candidate_return_date"].isin(dates)
            ]

        status = grid.merge(trade, on=["stock_code", "candidate_return_date"], how="left")
        status = status.merge(suspend, on=["stock_code", "candidate_return_date"], how="left")
        status = status.merge(limits, on=["stock_code", "candidate_return_date"], how="left")
        status = status.merge(
            price_lookup.loc[
                price_lookup["stock_code"].isin(codes)
                & price_lookup["candidate_return_date"].isin(dates)
            ],
            on=["stock_code", "candidate_return_date"],
            how="left",
        )
        status = _apply_trade_restrictions(
            status,
            "candidate_return_date",
            st,
            require_close=True,
        )
        status = status.sort_values(["stock_code", "exit_delay_trading_days"])
        first_rows = status.loc[status["exit_delay_trading_days"].eq(0)].set_index("stock_code")
        tradable = status.loc[status["can_trade"]].drop_duplicates("stock_code", keep="first")
        tradable = tradable.set_index("stock_code")
        period_result = intended_positions.set_index("stock_code")
        period_result["intended_mark_close"] = first_rows["close"]
        period_result["exit_search_horizon_date"] = period_calendar["candidate_return_date"].max()
        period_result["actual_return_date"] = tradable["candidate_return_date"]
        period_result["exit_delay_days"] = tradable["exit_delay_days"]
        period_result["exit_delay_trading_days"] = tradable["exit_delay_trading_days"]
        period_result["exit_close"] = tradable["close"]
        period_result["exit_executed"] = period_result["actual_return_date"].notna()
        initial_reasons = first_rows["restriction_reason"].to_dict()
        exhausted_reasons = (
            status.loc[~status["can_trade"]]
            .groupby("stock_code")["restriction_reason"]
            .agg(lambda values: "|".join(dict.fromkeys(values)))
            .to_dict()
        )
        reasons: list[str] = []
        for stock_code, row in period_result.iterrows():
            initial_reason = initial_reasons.get(stock_code, "missing_status")
            if bool(row["exit_executed"]) and int(row["exit_delay_trading_days"]) == 0:
                reasons.append("tradable")
            elif bool(row["exit_executed"]):
                reasons.append(f"intended_{initial_reason};delayed_to_first_tradable")
            else:
                blocked = exhausted_reasons.get(stock_code, initial_reason)
                reasons.append(f"exit_search_exhausted:{blocked}")
        period_result["restriction_reason"] = reasons
        unresolved = ~period_result["exit_executed"]
        period_result.loc[unresolved, "exit_delay_days"] = (
            period_result.loc[unresolved, "exit_search_horizon_date"]
            - period_result.loc[unresolved, "intended_return_date"]
        ).dt.days
        period_result.loc[unresolved, "exit_delay_trading_days"] = MAX_EXIT_DELAY_TRADING_DAYS
        resolved_parts.append(period_result.reset_index()[output_columns])
    return pd.concat(resolved_parts, ignore_index=True)


def _calculate_factor_returns(
    constituents: pd.DataFrame,
    price: pd.DataFrame,
    config: ChinaFactorTimingConfig | None = None,
    *,
    candidate_calendar: pd.DataFrame | None = None,
    exit_trade: pd.DataFrame | None = None,
    exit_suspend: pd.DataFrame | None = None,
    exit_limits: pd.DataFrame | None = None,
    exit_st: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按原信号权重计收益；受限权重不重选、不重归一，并保留可得日。"""
    cfg = config or ChinaFactorTimingConfig()
    entry_columns = ["signal_date", "execution_date", "return_date", "factor", "stock_code", "weight"]
    entries = constituents[entry_columns].copy()
    entries["stock_code"] = entries["stock_code"].astype(str)
    entries["intended_return_date"] = pd.to_datetime(entries["return_date"]).dt.normalize()
    entries["can_execute"] = (
        constituents["can_execute"].to_numpy() if "can_execute" in constituents else True
    )
    entries["execution_restriction_reason"] = (
        constituents["execution_restriction_reason"].to_numpy()
        if "execution_restriction_reason" in constituents
        else np.where(entries["can_execute"], "tradable", "execution_restricted")
    )
    entry_prices = price[["stock_code", "date", "close"]].copy().rename(
        columns={"date": "execution_date", "close": "entry_close"}
    )
    entry_prices["stock_code"] = entry_prices["stock_code"].astype(str)
    entry_prices["execution_date"] = pd.to_datetime(entry_prices["execution_date"]).dt.normalize()
    holdings = entries.merge(
        entry_prices[["stock_code", "execution_date", "entry_close"]],
        on=["stock_code", "execution_date"],
        how="left",
    )
    holdings["executed"] = holdings["can_execute"] & holdings["entry_close"].notna()
    exit_resolution = _resolve_exit_trades(
        holdings.loc[holdings["executed"]],
        price,
        cfg,
        candidate_calendar=candidate_calendar,
        exit_trade=exit_trade,
        exit_suspend=exit_suspend,
        exit_limits=exit_limits,
        exit_st=exit_st,
    )
    holdings = holdings.merge(
        exit_resolution,
        on=["stock_code", "intended_return_date"],
        how="left",
    )
    holdings["exit_executed"] = holdings["exit_executed"].fillna(False).astype(bool)
    holdings["nav_marked"] = (
        holdings["executed"]
        & ~holdings["exit_executed"]
        & holdings["intended_mark_close"].notna()
    )
    holdings["priced_return"] = holdings["exit_executed"] | holdings["nav_marked"]
    valuation_close = holdings["exit_close"].where(
        holdings["exit_executed"], holdings["intended_mark_close"]
    )
    holdings["stock_return"] = np.where(
        holdings["priced_return"],
        valuation_close / holdings["entry_close"] - 1.0,
        cfg.missing_price_cash_return,
    )
    holdings["return_status"] = np.select(
        [
            ~holdings["can_execute"],
            holdings["can_execute"] & holdings["entry_close"].isna(),
            holdings["exit_executed"] & holdings["actual_return_date"].eq(holdings["intended_return_date"]),
            holdings["exit_executed"],
            holdings["nav_marked"],
        ],
        [
            "not_executed_cash", "missing_entry_cash", "priced",
            "delayed_exit_priced", "exit_search_exhausted_nav_mark",
        ],
        default="exit_search_exhausted_cash",
    )
    holdings["restriction_reason"] = np.select(
        [~holdings["can_execute"], holdings["can_execute"] & holdings["entry_close"].isna()],
        [holdings["execution_restriction_reason"], "missing_entry_close"],
        default=holdings["restriction_reason"].fillna("not_applicable"),
    )
    holdings["label_available_date"] = holdings["actual_return_date"]
    entry_cash = ~holdings["executed"]
    holdings.loc[entry_cash, "label_available_date"] = holdings.loc[
        entry_cash, "intended_return_date"
    ]
    unresolved = holdings["executed"] & ~holdings["exit_executed"]
    holdings.loc[unresolved, "label_available_date"] = holdings.loc[
        unresolved, "exit_search_horizon_date"
    ]
    holdings["weighted_return"] = holdings["weight"] * holdings["stock_return"]
    holdings["executed_weight"] = holdings["weight"].where(holdings["executed"], 0.0)
    holdings["priced_weight"] = holdings["weight"].where(holdings["priced_return"], 0.0)
    holdings["unresolved_weight"] = holdings["weight"].where(unresolved, 0.0)
    holdings["nav_marked_weight"] = holdings["weight"].where(holdings["nav_marked"], 0.0)

    def join_reasons(values: pd.Series) -> str:
        reasons = [str(value) for value in values if pd.notna(value) and value != "tradable"]
        return ";".join(dict.fromkeys(reasons)) or "tradable"

    result = holdings.groupby(
        ["signal_date", "execution_date", "return_date", "factor"], as_index=False
    ).agg(
        factor_return=("weighted_return", "sum"),
        holdings=("stock_code", "nunique"),
        weight_sum=("weight", "sum"),
        executed_weight=("executed_weight", "sum"),
        priced_weight=("priced_weight", "sum"),
        unresolved_weight=("unresolved_weight", "sum"),
        nav_marked_weight=("nav_marked_weight", "sum"),
        intended_return_date=("intended_return_date", "max"),
        actual_return_date=("actual_return_date", "max"),
        exit_delay_days=("exit_delay_days", "max"),
        exit_delay_trading_days=("exit_delay_trading_days", "max"),
        exit_executed=("exit_executed", "all"),
        label_available_date=("label_available_date", "max"),
        restriction_reason=("restriction_reason", join_reasons),
    )
    result["cash_weight"] = result["weight_sum"] - result["priced_weight"]
    audit_columns = [
        "signal_date", "factor", "stock_code", "executed", "priced_return",
        "return_status", "stock_return", "intended_return_date", "actual_return_date",
        "exit_delay_days", "exit_delay_trading_days", "exit_executed", "restriction_reason",
        "label_available_date", "nav_marked", "exit_search_horizon_date",
    ]
    return result, holdings[audit_columns]


def _calculate_industry_returns(
    config: ChinaFactorTimingConfig,
    schedule: pd.DataFrame,
    price: pd.DataFrame,
) -> pd.DataFrame:
    industry = pd.read_parquet(
        config.path("stock_industry"),
        columns=["stock_code", "first_industry_name", "standard_code"],
        filters=[("standard_code", "==", config.industry_standard_code)],
    )
    industry = industry.drop_duplicates("stock_code", keep="last")
    monthly = price.copy()
    monthly["month"] = monthly["date"].dt.to_period("M")
    monthly = monthly.sort_values(["stock_code", "date"]).groupby(["stock_code", "month"], as_index=False).tail(1)
    monthly["industry_return"] = monthly.groupby("stock_code", sort=False)["close"].pct_change(fill_method=None)
    monthly["signal_date"] = monthly["date"]
    monthly = monthly.loc[monthly["signal_date"].isin(schedule["signal_date"])]
    monthly = monthly.merge(industry, on="stock_code", how="inner")
    return monthly.groupby(["signal_date", "first_industry_name"], as_index=False)["industry_return"].mean().rename(
        columns={"first_industry_name": "industry"}
    )


def _quality_audit(
    config: ChinaFactorTimingConfig,
    panel: pd.DataFrame,
    constituents: pd.DataFrame,
    factor_returns: pd.DataFrame,
) -> pd.DataFrame:
    summary = pd.DataFrame(
        [
            {"table": "factor_signal_panel", "field": "rows", "rows": len(panel), "missing_rate": float(panel.isna().mean().mean())},
            {"table": "factor_constituents", "field": "rows", "rows": len(constituents), "missing_rate": float(constituents.isna().mean().mean())},
            {"table": "factor_returns", "field": "rows", "rows": len(factor_returns), "missing_rate": float(factor_returns.isna().mean().mean())},
        ]
    )
    style = panel.loc[panel["in_style_universe"]].copy()
    style["reported_count"] = style["pb_source"].eq("reported").astype(int)
    style["derived_count"] = style["pb_source"].eq("derived").astype(int)
    coverage = style.groupby("signal_date", as_index=False).agg(
        members=("style_members_total", "max"),
        pb_available=("pb_lf", "count"),
        reported_pb=("reported_count", "sum"),
        derived_pb=("derived_count", "sum"),
    )
    coverage["pb_coverage"] = coverage["pb_available"] / coverage["members"]
    coverage["pb_eligible"] = (
        coverage["pb_available"].ge(config.pb_min_stocks)
        & coverage["pb_coverage"].ge(config.pb_min_coverage)
    )
    selected = (
        constituents.loc[constituents["factor"].isin(["Value", "Growth"])]
        .groupby(["signal_date", "factor"])["stock_code"]
        .nunique()
        .unstack(fill_value=0)
        .rename(columns={"Value": "value_selected", "Growth": "growth_selected"})
        .reset_index()
    )
    completeness = factor_returns.groupby("signal_date")["factor"].nunique().rename("factor_count").reset_index()
    coverage = coverage.merge(selected, on="signal_date", how="left").merge(
        completeness,
        on="signal_date",
        how="left",
    )
    for column in ("value_selected", "growth_selected", "factor_count"):
        if column not in coverage:
            coverage[column] = 0
        coverage[column] = coverage[column].fillna(0).astype(int)
    coverage["six_factor_complete"] = coverage["factor_count"].eq(len(config.factor_names))
    coverage["table"] = "pb_coverage"
    coverage["field"] = "pb_lf"
    coverage["rows"] = coverage["members"]
    coverage["missing_rate"] = 1.0 - coverage["pb_coverage"]
    return pd.concat([summary, coverage], ignore_index=True, sort=False)


def build_equity_factor_base(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
    *,
    smoke_stock_limit: int | None = None,
) -> EquityFactorBase:
    """构造中信行业收益及六个A股因子的PIT、T+1月收益底座。"""
    schedule = _execution_schedule(config, calendar)
    components, stock_codes = _candidate_codes(config, calendar, smoke_stock_limit)
    price, trade, value = _read_stock_panel(config, schedule, stock_codes)
    tradable = _tradable_on_execution(config, schedule, trade, stock_codes)
    panel = _build_signal_panel(config, schedule, components, price, trade, value, stock_codes)
    constituents = _select_factor_constituents(config, panel, tradable)
    factor_returns, return_audit = _calculate_factor_returns(constituents, price, config)
    constituents = constituents.merge(
        return_audit,
        on=["signal_date", "factor", "stock_code"],
        how="left",
    )
    industry_returns = _calculate_industry_returns(config, schedule, price)
    return EquityFactorBase(
        industry_returns=industry_returns,
        factor_returns=factor_returns,
        factor_constituents=constituents,
        data_quality=_quality_audit(config, panel, constituents, factor_returns),
    )


def build_m1_inputs(
    config: ChinaFactorTimingConfig | None = None,
    *,
    smoke_months: int | None = None,
    smoke_stock_limit: int | None = None,
) -> object:
    """薄入口：交由数据管线组合完整m1数据集，避免复制编排逻辑。"""
    from .data_pipeline import build_m1_dataset

    return build_m1_dataset(
        config,
        smoke_months=smoke_months,
        smoke_stock_limit=smoke_stock_limit,
    )


__all__ = ["EquityFactorBase", "build_equity_factor_base", "build_m1_inputs"]
