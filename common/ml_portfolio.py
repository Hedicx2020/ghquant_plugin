"""机器学习截面因子的分组、多路径与可成交组合回测。

本模块接收长表形式的样本外预测、逐日估值/可成交面板和全市场交易日历，
输出可逐笔复算的分组、持仓、交易、净值与指标表。模型预测只在信号日参与
截面排序；T+1 的可成交状态只在执行函数中读取，不会回流到 T 日因子。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy import stats

from common.backtest import calculate_rank_ic
from common.utils import (
    calculate_annualized_return,
    calculate_max_drawdown,
    calculate_sharpe,
)


@dataclass(frozen=True)
class MLPortfolioSettings:
    """分组和组合回测的全部显式参数。"""

    model_col: str
    stock_col: str
    signal_date_col: str
    prediction_col: str
    forward_return_col: str
    market_date_col: str
    market_price_col: str
    market_tradable_col: str
    n_groups: int
    expected_model_count: int
    path_offsets: tuple[int, ...]
    rebalance_interval: int
    entry_offset: int
    exit_offset: int
    sell_fee_rate: float
    initial_capital: float
    periods_per_year: int
    risk_free_rate_per_day: float
    factor_correlation_method: str
    min_cross_section_size: int
    share_epsilon: float

    def validate(self) -> None:
        """拒绝会改变报告口径或导致不可复算的配置。"""
        if self.n_groups <= 1:
            raise ValueError("n_groups 必须大于1")
        if self.expected_model_count <= 0:
            raise ValueError("expected_model_count 必须为正整数")
        if self.rebalance_interval <= 0:
            raise ValueError("rebalance_interval 必须为正整数")
        if tuple(sorted(set(self.path_offsets))) != self.path_offsets:
            raise ValueError("path_offsets 必须严格递增且不得重复")
        if self.path_offsets != tuple(range(self.rebalance_interval)):
            raise ValueError("多路径必须覆盖调仓周期内每个起始偏移且各一次")
        if not 0 < self.entry_offset < self.exit_offset:
            raise ValueError("必须满足 0 < entry_offset < exit_offset")
        if self.exit_offset - self.entry_offset != self.rebalance_interval:
            raise ValueError("持有期必须与调仓周期一致")
        if not 0.0 <= self.sell_fee_rate < 1.0:
            raise ValueError("sell_fee_rate 必须位于 [0,1)")
        if self.initial_capital <= 0.0 or self.periods_per_year <= 0:
            raise ValueError("initial_capital 与 periods_per_year 必须为正")
        if self.factor_correlation_method not in {"pearson", "spearman"}:
            raise ValueError("因子相关性仅支持 pearson/spearman")
        if self.min_cross_section_size < self.n_groups:
            raise ValueError("min_cross_section_size 不得小于 n_groups")
        if self.share_epsilon <= 0.0:
            raise ValueError("share_epsilon 必须为正")


@dataclass
class MLPortfolioResult:
    """m4 的结构化交付；所有表都保留模型和路径键。"""

    factor_panel: pd.DataFrame
    factor_correlation: pd.DataFrame
    factor_correlation_by_date: pd.DataFrame
    rank_ic: pd.DataFrame
    rank_ic_path_series: pd.DataFrame
    rank_ic_path_summary: pd.DataFrame
    rank_ic_path_aggregate: pd.DataFrame
    group_assignments: pd.DataFrame
    path_holdings: pd.DataFrame
    path_trades: pd.DataFrame
    path_nav: pd.DataFrame
    portfolio_returns: pd.DataFrame
    path_metrics: pd.DataFrame
    annual_metrics: pd.DataFrame
    path_metric_aggregate: pd.DataFrame
    path_daily_aggregate: pd.DataFrame
    monotonicity: pd.DataFrame


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], context: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _normalise_dates(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    result = frame.copy()
    result[column] = pd.to_datetime(result[column], errors="raise").dt.normalize()
    return result


def prepare_factor_panel(
    predictions: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> pd.DataFrame:
    """建立仅由有效键和预测决定的候选因子面板。

    ``forward_return`` 只供事后RankIC/散点诊断；其缺失不得删除T日候选、
    改变十分档或影响组合交易。
    """
    settings.validate()
    required = (
        settings.model_col,
        settings.stock_col,
        settings.signal_date_col,
        settings.prediction_col,
    )
    _require_columns(predictions, required, "样本外预测面板")
    selected_columns = list(required)
    if settings.forward_return_col in predictions.columns:
        selected_columns.append(settings.forward_return_col)
    panel = _normalise_dates(
        predictions.loc[:, selected_columns], settings.signal_date_col
    )
    if settings.forward_return_col not in panel.columns:
        panel[settings.forward_return_col] = np.nan
    key_columns = [settings.model_col, settings.stock_col, settings.signal_date_col]
    if panel.loc[:, key_columns].isna().any().any():
        raise ValueError("样本外预测面板的 model/stock/date 键不得缺失")
    panel[settings.model_col] = panel[settings.model_col].astype(str)
    panel[settings.stock_col] = panel[settings.stock_col].astype(str)
    keys = key_columns
    if panel.duplicated(keys).any():
        duplicate_count = int(panel.duplicated(keys, keep=False).sum())
        raise ValueError(f"样本外预测面板存在 {duplicate_count} 行重复键")
    panel[settings.prediction_col] = pd.to_numeric(
        panel[settings.prediction_col], errors="coerce"
    )
    panel[settings.forward_return_col] = pd.to_numeric(
        panel[settings.forward_return_col], errors="coerce"
    )
    panel[settings.prediction_col] = panel[settings.prediction_col].replace(
        [np.inf, -np.inf], np.nan
    )
    panel[settings.forward_return_col] = panel[settings.forward_return_col].replace(
        [np.inf, -np.inf], np.nan
    )
    panel = panel.dropna(subset=[settings.prediction_col])
    model_count = panel[settings.model_col].nunique()
    if model_count != settings.expected_model_count:
        raise ValueError(
            f"有效预测模型数量不符: actual={model_count}, expected={settings.expected_model_count}"
        )
    cross_section_size = panel.groupby(
        [settings.model_col, settings.signal_date_col], observed=True
    )[settings.stock_col].transform("size")
    panel = panel.loc[cross_section_size >= settings.min_cross_section_size].copy()
    if panel.empty:
        raise ValueError("没有达到最小截面数量的有效预测")
    return panel.sort_values(keys).reset_index(drop=True)


def assign_descending_quantile_groups(
    factor_panel: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> pd.DataFrame:
    """按预测值降序等数量分组，``group=1`` 始终为最高预测组。

    同值时仅以股票代码升序作确定性裁决；组号只依赖 T 日预测和 T 日证券键。
    """
    required = (
        settings.model_col,
        settings.stock_col,
        settings.signal_date_col,
        settings.prediction_col,
    )
    _require_columns(factor_panel, required, "因子面板")
    ordered = factor_panel.sort_values(
        [
            settings.model_col,
            settings.signal_date_col,
            settings.prediction_col,
            settings.stock_col,
        ],
        ascending=[True, True, False, True],
        kind="mergesort",
    ).copy()
    cross_section = ordered.groupby(
        [settings.model_col, settings.signal_date_col], observed=True
    )
    rank_zero_based = cross_section.cumcount()
    count = cross_section[settings.stock_col].transform("size")
    ordered["group"] = (
        np.floor(rank_zero_based * settings.n_groups / count).astype("int64") + 1
    )
    return ordered.sort_values(
        [settings.model_col, settings.signal_date_col, "group", settings.stock_col]
    ).reset_index(drop=True)


def calculate_prediction_diagnostics(
    factor_panel: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """诊断时才成对删除缺失标签；预测相关性完全不读取标签。"""

    def _daily_rank_ic(group: pd.DataFrame) -> pd.Series:
        paired = group.loc[
            :, [settings.prediction_col, settings.forward_return_col]
        ].dropna()
        candidate_count = int(len(group))
        valid_label_count = int(len(paired))
        label_missing_count = candidate_count - valid_label_count
        return pd.Series(
            {
                "rank_ic": calculate_rank_ic(
                    paired[settings.prediction_col], paired[settings.forward_return_col]
                ),
                "candidate_count": candidate_count,
                "valid_label_count": valid_label_count,
                "label_missing_count": label_missing_count,
                "valid_label_rate": (
                    valid_label_count / candidate_count if candidate_count else np.nan
                ),
                "label_missing_rate": (
                    label_missing_count / candidate_count if candidate_count else np.nan
                ),
            }
        )

    rank_ic = (
        factor_panel.groupby(
            [settings.model_col, settings.signal_date_col], observed=True
        )
        .apply(_daily_rank_ic, include_groups=False)
        .reset_index()
    )
    wide = factor_panel.pivot(
        index=[settings.signal_date_col, settings.stock_col],
        columns=settings.model_col,
        values=settings.prediction_col,
    )
    overall = wide.corr(method=settings.factor_correlation_method)
    overall.index.name = "model_left"
    factor_correlation = overall.reset_index().melt(
        id_vars="model_left", var_name="model_right", value_name="correlation"
    )
    daily_records: list[pd.DataFrame] = []
    for signal_date, daily in wide.groupby(level=settings.signal_date_col, sort=True):
        corr = daily.droplevel(settings.signal_date_col).corr(
            method=settings.factor_correlation_method
        )
        corr.index.name = "model_left"
        long = corr.reset_index().melt(
            id_vars="model_left", var_name="model_right", value_name="correlation"
        )
        long.insert(0, settings.signal_date_col, signal_date)
        daily_records.append(long)
    factor_correlation_by_date = pd.concat(daily_records, ignore_index=True)
    return rank_ic, factor_correlation, factor_correlation_by_date


def build_rank_ic_path_aggregates(
    rank_ic: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """按调仓事件的相同offset分配RankIC，再做严格路径等权汇总。

    逐日RankIC先依据模型有效信号区间内的交易日位置映射到
    ``path_offset = position % rebalance_interval``；随后每条路径独立计算
    时序均值，最终对全部20条路径的均值做算术平均。最终值绝不直接对
    日期行求均值，因此各路径信号数量不同时仍保持路径等权。
    """
    settings.validate()
    _require_columns(
        rank_ic,
        (settings.model_col, settings.signal_date_col, "rank_ic"),
        "逐日RankIC",
    )
    calendar = _prepare_calendar(trade_calendar, settings.market_date_col)
    daily_source = _normalise_dates(rank_ic, settings.signal_date_col)
    if daily_source.duplicated([settings.model_col, settings.signal_date_col]).any():
        raise ValueError("逐日RankIC存在重复 model/signal_date 键")

    path_frames: list[pd.DataFrame] = []
    for model, model_daily in daily_source.groupby(settings.model_col, sort=True):
        signal_dates = pd.DatetimeIndex(
            model_daily[settings.signal_date_col].unique()
        ).sort_values()
        eligible_calendar = calendar[
            (calendar >= signal_dates.min()) & (calendar <= signal_dates.max())
        ]
        path_map = pd.DataFrame(
            {
                settings.signal_date_col: eligible_calendar,
                "path_offset": np.arange(len(eligible_calendar))
                % settings.rebalance_interval,
            }
        )
        assigned = model_daily.merge(
            path_map,
            on=settings.signal_date_col,
            how="left",
            validate="one_to_one",
        )
        if assigned["path_offset"].isna().any():
            raise ValueError(f"{model} RankIC含不在交易日历内的信号日")
        assigned["path_offset"] = assigned["path_offset"].astype("int64")
        path_frames.append(assigned)
    path_series = pd.concat(path_frames, ignore_index=True).sort_values(
        [settings.model_col, "path_offset", settings.signal_date_col]
    ).reset_index(drop=True)
    if path_series.duplicated(
        [settings.model_col, "path_offset", settings.signal_date_col]
    ).any():
        raise AssertionError("RankIC路径分配后出现重复信号日")

    summary_aggregations: dict[str, tuple[str, str]] = {
        "rank_ic_time_mean": ("rank_ic", "mean"),
        "signal_count": ("rank_ic", "size"),
        "valid_rank_ic_count": ("rank_ic", "count"),
        "signal_start": (settings.signal_date_col, "min"),
        "signal_end": (settings.signal_date_col, "max"),
    }
    label_count_columns = {
        "candidate_count",
        "valid_label_count",
        "label_missing_count",
    }
    has_label_counts = label_count_columns.issubset(path_series.columns)
    if has_label_counts:
        summary_aggregations.update(
            {
                "candidate_count": ("candidate_count", "sum"),
                "valid_label_count": ("valid_label_count", "sum"),
                "label_missing_count": ("label_missing_count", "sum"),
            }
        )
    path_summary = (
        path_series.groupby(
            [settings.model_col, "path_offset"], observed=True, as_index=False
        )
        .agg(**summary_aggregations)
        .sort_values([settings.model_col, "path_offset"])
        .reset_index(drop=True)
    )
    if has_label_counts:
        path_summary["valid_label_rate"] = (
            path_summary["valid_label_count"] / path_summary["candidate_count"]
        )
        path_summary["label_missing_rate"] = (
            path_summary["label_missing_count"] / path_summary["candidate_count"]
        )
    expected = pd.MultiIndex.from_product(
        [
            sorted(path_series[settings.model_col].astype(str).unique()),
            settings.path_offsets,
        ],
        names=[settings.model_col, "path_offset"],
    )
    actual = pd.MultiIndex.from_frame(
        path_summary.loc[:, [settings.model_col, "path_offset"]]
    )
    missing_paths = expected.difference(actual)
    unexpected_paths = actual.difference(expected)
    if len(missing_paths) or len(unexpected_paths):
        raise ValueError(
            "RankIC路径覆盖不完整或含意外offset: "
            f"missing={list(missing_paths)}, unexpected={list(unexpected_paths)}"
        )

    aggregate_records: list[dict[str, Any]] = []
    for model, model_paths in path_summary.groupby(settings.model_col, sort=True):
        ordered = model_paths.set_index("path_offset").reindex(settings.path_offsets)
        path_means = ordered["rank_ic_time_mean"].to_numpy(dtype=float)
        equal_path_mean = float(np.mean(path_means))
        record = {
            settings.model_col: model,
            "rank_ic_mean": equal_path_mean,
            "rank_ic_equal_path_mean": equal_path_mean,
            "path_count": int(len(ordered)),
            "valid_path_count": int(np.isfinite(path_means).sum()),
            "signal_count": int(ordered["signal_count"].sum()),
            "min_signal_count_per_path": int(ordered["signal_count"].min()),
            "max_signal_count_per_path": int(ordered["signal_count"].max()),
        }
        if has_label_counts:
            candidate_count = int(ordered["candidate_count"].sum())
            valid_label_count = int(ordered["valid_label_count"].sum())
            label_missing_count = int(ordered["label_missing_count"].sum())
            record.update(
                {
                    "candidate_count": candidate_count,
                    "valid_label_count": valid_label_count,
                    "label_missing_count": label_missing_count,
                    "valid_label_rate": valid_label_count / candidate_count,
                    "label_missing_rate": label_missing_count / candidate_count,
                }
            )
        aggregate_records.append(record)
    path_aggregate = pd.DataFrame(aggregate_records)
    if not path_aggregate["path_count"].eq(len(settings.path_offsets)).all():
        raise AssertionError("RankIC聚合未使用全部offset路径")
    return path_series, path_summary, path_aggregate


def _prepare_market_panel(
    market_panel: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> dict[pd.Timestamp, pd.DataFrame]:
    required = (
        settings.stock_col,
        settings.market_date_col,
        settings.market_price_col,
        settings.market_tradable_col,
    )
    _require_columns(market_panel, required, "逐日估值/可成交面板")
    market = _normalise_dates(market_panel.loc[:, required], settings.market_date_col)
    market[settings.stock_col] = market[settings.stock_col].astype(str)
    keys = [settings.stock_col, settings.market_date_col]
    if market.duplicated(keys).any():
        raise ValueError("逐日估值/可成交面板存在重复 stock/date 键")
    market[settings.market_price_col] = pd.to_numeric(
        market[settings.market_price_col], errors="coerce"
    ).where(lambda value: value > 0)
    market[settings.market_tradable_col] = (
        market[settings.market_tradable_col].fillna(False).astype(bool)
    )
    return {
        pd.Timestamp(date): group.set_index(settings.stock_col, drop=False)
        for date, group in market.groupby(settings.market_date_col, sort=True)
    }


def _prepare_calendar(trade_calendar: pd.DataFrame, date_col: str) -> pd.DatetimeIndex:
    _require_columns(trade_calendar, (date_col,), "交易日历")
    dates = pd.DatetimeIndex(
        pd.to_datetime(trade_calendar[date_col], errors="raise").dt.normalize().unique()
    ).sort_values()
    if dates.empty:
        raise ValueError("交易日历不得为空")
    return dates


def _build_path_events(
    assignments: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    *,
    model: str,
    path_offset: int,
    group_number: int,
    settings: MLPortfolioSettings,
) -> list[dict[str, Any]]:
    model_rows = assignments.loc[assignments[settings.model_col] == model]
    signal_dates = pd.DatetimeIndex(model_rows[settings.signal_date_col].unique()).sort_values()
    if signal_dates.empty:
        return []
    eligible_calendar = calendar[
        (calendar >= signal_dates.min()) & (calendar <= signal_dates.max())
    ]
    scheduled_signals = eligible_calendar[path_offset :: settings.rebalance_interval]
    calendar_positions = pd.Series(np.arange(len(calendar)), index=calendar)
    events: list[dict[str, Any]] = []
    for signal_date in scheduled_signals:
        position = int(calendar_positions.loc[signal_date])
        if position + settings.entry_offset >= len(calendar):
            continue
        targets = model_rows.loc[
            (model_rows[settings.signal_date_col] == signal_date)
            & (model_rows["group"] == group_number),
            settings.stock_col,
        ].astype(str).tolist()
        events.append(
            {
                "signal_date": pd.Timestamp(signal_date),
                "execution_date": pd.Timestamp(calendar[position + settings.entry_offset]),
                "target_stocks": tuple(targets),
                "event_type": "rebalance",
            }
        )
    nonempty = [event for event in events if event["target_stocks"]]
    if not nonempty:
        return []
    first_nonempty = events.index(nonempty[0])
    events = events[first_nonempty:]
    last_signal = events[-1]["signal_date"]
    last_position = int(calendar_positions.loc[last_signal])
    final_position = last_position + settings.exit_offset
    if final_position >= len(calendar):
        raise ValueError(f"路径 {path_offset} 的最后卖出端点超出交易日历")
    events.append(
        {
            "signal_date": last_signal,
            "execution_date": pd.Timestamp(calendar[final_position]),
            "target_stocks": tuple(),
            "event_type": "final_exit",
        }
    )
    return events


def _market_snapshot(
    market_by_date: dict[pd.Timestamp, pd.DataFrame],
    date: pd.Timestamp,
) -> pd.DataFrame:
    return market_by_date.get(date, pd.DataFrame())


def _read_market_value(
    snapshot: pd.DataFrame,
    stock: str,
    settings: MLPortfolioSettings,
) -> tuple[float, bool]:
    if snapshot.empty or stock not in snapshot.index:
        return float("nan"), False
    row = snapshot.loc[stock]
    if isinstance(row, pd.DataFrame):
        raise ValueError(f"市场面板 {stock} 在同一交易日存在重复行")
    price = float(row[settings.market_price_col])
    tradable = bool(row[settings.market_tradable_col]) and np.isfinite(price) and price > 0
    return price, tradable


def _simulate_group_path(
    *,
    model: str,
    path_offset: int,
    group_number: int,
    events: list[dict[str, Any]],
    calendar: pd.DatetimeIndex,
    market_by_date: dict[pd.Timestamp, pd.DataFrame],
    settings: MLPortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """逐日估值并在预定执行日先卖后买；不可成交订单保留原状态。"""
    if not events:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    start_date = events[0]["execution_date"]
    end_date = events[-1]["execution_date"]
    valuation_dates = calendar[(calendar >= start_date) & (calendar <= end_date)]
    events_by_date = {event["execution_date"]: event for event in events}
    positions: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    cash = settings.initial_capital
    previous_equity = settings.initial_capital
    nav_records: list[dict[str, Any]] = []
    trade_records: list[dict[str, Any]] = []
    holding_records: list[dict[str, Any]] = []

    for date in valuation_dates:
        date = pd.Timestamp(date)
        daily_fee_paid = 0.0
        snapshot = _market_snapshot(market_by_date, date)
        for stock in list(positions):
            price, _ = _read_market_value(snapshot, stock, settings)
            if np.isfinite(price):
                last_prices[stock] = price

        event = events_by_date.get(date)
        if event is not None:
            target_stocks = tuple(dict.fromkeys(event["target_stocks"]))
            current_value = sum(
                shares * last_prices.get(stock, float("nan"))
                for stock, shares in positions.items()
                if np.isfinite(last_prices.get(stock, float("nan")))
            )
            equity_before = cash + current_value
            target_value = equity_before / len(target_stocks) if target_stocks else 0.0
            desired_shares: dict[str, float] = {}
            all_stocks = sorted(set(positions) | set(target_stocks))
            for stock in all_stocks:
                price, _ = _read_market_value(snapshot, stock, settings)
                desired_shares[stock] = (
                    target_value / price
                    if stock in target_stocks and np.isfinite(price) and price > 0
                    else 0.0
                )

            # 先处理卖单，保证卖出费用仅由实际卖出名义金额产生。
            for stock in all_stocks:
                held = positions.get(stock, 0.0)
                requested = min(desired_shares[stock] - held, 0.0)
                if requested >= -settings.share_epsilon:
                    continue
                price, tradable = _read_market_value(snapshot, stock, settings)
                if not tradable:
                    trade_records.append(
                        {
                            "model": model,
                            "path_offset": path_offset,
                            "group": group_number,
                            "signal_date": event["signal_date"],
                            "execution_date": date,
                            "event_type": event["event_type"],
                            "stock_code": stock,
                            "action": "sell",
                            "requested_shares": requested,
                            "executed_shares": 0.0,
                            "price": price,
                            "notional": 0.0,
                            "fee": 0.0,
                            "status": "blocked",
                            "reason": "untradable_or_missing_price",
                        }
                    )
                    continue
                executed = max(requested, -held)
                notional = -executed * price
                fee = notional * settings.sell_fee_rate
                daily_fee_paid += fee
                cash += notional - fee
                remaining = held + executed
                if remaining <= settings.share_epsilon:
                    positions.pop(stock, None)
                else:
                    positions[stock] = remaining
                trade_records.append(
                    {
                        "model": model,
                        "path_offset": path_offset,
                        "group": group_number,
                        "signal_date": event["signal_date"],
                        "execution_date": date,
                        "event_type": event["event_type"],
                        "stock_code": stock,
                        "action": "sell",
                        "requested_shares": requested,
                        "executed_shares": executed,
                        "price": price,
                        "notional": notional,
                        "fee": fee,
                        "status": "filled",
                        "reason": "",
                    }
                )

            buy_requests: list[tuple[str, float, float, bool]] = []
            for stock in all_stocks:
                held = positions.get(stock, 0.0)
                requested = max(desired_shares[stock] - held, 0.0)
                if requested <= settings.share_epsilon:
                    continue
                price, tradable = _read_market_value(snapshot, stock, settings)
                buy_requests.append((stock, requested, price, tradable))
            requested_cash = sum(
                requested * price
                for _, requested, price, tradable in buy_requests
                if tradable
            )
            cash_before_buys = cash
            buy_scale = (
                min(1.0, cash_before_buys / requested_cash)
                if requested_cash > 0.0
                else 0.0
            )
            for stock, requested, price, tradable in buy_requests:
                if not tradable:
                    trade_records.append(
                        {
                            "model": model,
                            "path_offset": path_offset,
                            "group": group_number,
                            "signal_date": event["signal_date"],
                            "execution_date": date,
                            "event_type": event["event_type"],
                            "stock_code": stock,
                            "action": "buy",
                            "requested_shares": requested,
                            "executed_shares": 0.0,
                            "price": price,
                            "notional": 0.0,
                            "fee": 0.0,
                            "cash_before_buys": cash_before_buys,
                            "requested_cash": requested_cash,
                            "buy_scale": buy_scale,
                            "status": "blocked",
                            "reason": "untradable_or_missing_price",
                        }
                    )
                    continue
                executed = requested * buy_scale
                notional = executed * price
                cash -= notional
                positions[stock] = positions.get(stock, 0.0) + executed
                status = "filled" if np.isclose(buy_scale, 1.0) else "partial"
                trade_records.append(
                    {
                        "model": model,
                        "path_offset": path_offset,
                        "group": group_number,
                        "signal_date": event["signal_date"],
                        "execution_date": date,
                        "event_type": event["event_type"],
                        "stock_code": stock,
                        "action": "buy",
                        "requested_shares": requested,
                        "executed_shares": executed,
                        "price": price,
                        "notional": notional,
                        "fee": 0.0,
                        "cash_before_buys": cash_before_buys,
                        "requested_cash": requested_cash,
                        "buy_scale": buy_scale,
                        "status": status,
                        "reason": "" if status == "filled" else "cash_constraint",
                    }
                )

            event_position_value = 0.0
            holding_start = len(holding_records)
            for stock, shares in sorted(positions.items()):
                price = last_prices.get(stock, float("nan"))
                current_price, current_tradable = _read_market_value(snapshot, stock, settings)
                if np.isfinite(current_price):
                    price = current_price
                    last_prices[stock] = current_price
                market_value = shares * price if np.isfinite(price) else float("nan")
                if np.isfinite(market_value):
                    event_position_value += market_value
                holding_records.append(
                    {
                        "model": model,
                        "path_offset": path_offset,
                        "group": group_number,
                        "signal_date": event["signal_date"],
                        "execution_date": date,
                        "event_type": event["event_type"],
                        "asset_type": "security",
                        "stock_code": stock,
                        "shares": shares,
                        "valuation_price": price,
                        "market_value": market_value,
                        "tradable": current_tradable,
                    }
                )
            event_equity = cash + event_position_value
            if event_equity <= 0.0 or not np.isfinite(event_equity):
                raise FloatingPointError("组合权益在执行后非正或非有限")
            holding_records.append(
                {
                    "model": model,
                    "path_offset": path_offset,
                    "group": group_number,
                    "signal_date": event["signal_date"],
                    "execution_date": date,
                    "event_type": event["event_type"],
                    "asset_type": "cash",
                    "stock_code": "__CASH__",
                    "shares": cash,
                    "valuation_price": 1.0,
                    "market_value": cash,
                    "tradable": True,
                }
            )
            for record in holding_records[holding_start:]:
                record["weight"] = record["market_value"] / event_equity
                record["cash"] = cash
                record["equity"] = event_equity

        position_value = sum(
            shares * last_prices.get(stock, float("nan"))
            for stock, shares in positions.items()
            if np.isfinite(last_prices.get(stock, float("nan")))
        )
        equity = cash + position_value
        if equity <= 0.0 or not np.isfinite(equity):
            raise FloatingPointError("组合逐日权益非正或非有限")
        daily_return = equity / previous_equity - 1.0
        fee_return = daily_fee_paid / previous_equity
        nav_records.append(
            {
                "model": model,
                "path_offset": path_offset,
                "group": group_number,
                "date": date,
                "cash": cash,
                "position_value": position_value,
                "equity": equity,
                "nav": equity / settings.initial_capital,
                "daily_return": daily_return,
                "fee_paid": daily_fee_paid,
                "fee_return": fee_return,
                "gross_daily_return": daily_return + fee_return,
            }
        )
        previous_equity = equity

    return (
        pd.DataFrame(holding_records),
        pd.DataFrame(trade_records),
        pd.DataFrame(nav_records),
    )


def _performance_record(
    returns: pd.Series,
    *,
    model: str,
    path_offset: int,
    portfolio: str,
    period: str,
    settings: MLPortfolioSettings,
) -> dict[str, Any]:
    clean = returns.dropna().astype(float)
    nav = (1.0 + clean).cumprod()
    return {
        "model": model,
        "path_offset": path_offset,
        "portfolio": portfolio,
        "period": period,
        "annualized_return": calculate_annualized_return(
            clean, periods_per_year=settings.periods_per_year
        ),
        "sharpe": calculate_sharpe(
            clean,
            rf=settings.risk_free_rate_per_day,
            periods_per_year=settings.periods_per_year,
        ),
        "max_drawdown": calculate_max_drawdown(nav),
        "cumulative_return": float(nav.iloc[-1] - 1.0) if not nav.empty else 0.0,
        "n_days": int(len(clean)),
    }


def _build_portfolio_returns(
    path_nav: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> pd.DataFrame:
    top = path_nav.loc[path_nav["group"] == 1, [
        "model", "path_offset", "date", "daily_return", "gross_daily_return", "fee_return",
    ]].rename(
        columns={
            "daily_return": "top_return",
            "gross_daily_return": "top_gross_return",
            "fee_return": "top_fee_return",
        }
    )
    bottom = path_nav.loc[path_nav["group"] == settings.n_groups, [
        "model", "path_offset", "date", "daily_return", "gross_daily_return", "fee_return",
    ]].rename(
        columns={
            "daily_return": "bottom_return",
            "gross_daily_return": "bottom_gross_return",
            "fee_return": "bottom_fee_return",
        }
    )
    paired = top.merge(bottom, on=["model", "path_offset", "date"], validate="one_to_one")
    long = paired.loc[:, ["model", "path_offset", "date", "top_return"]].rename(
        columns={"top_return": "daily_return"}
    )
    long["portfolio"] = "top_long"
    spread = paired.loc[:, ["model", "path_offset", "date"]].copy()
    spread["daily_return"] = (
        paired["top_gross_return"]
        - paired["bottom_gross_return"]
        - paired["top_fee_return"]
        - paired["bottom_fee_return"]
    )
    spread["portfolio"] = "top_bottom"
    result = pd.concat([long, spread], ignore_index=True)
    result = result.sort_values(["model", "path_offset", "portfolio", "date"])
    result["nav"] = (
        result.groupby(["model", "path_offset", "portfolio"], observed=True)["daily_return"]
        .transform(lambda values: (1.0 + values).cumprod())
    )
    return result.reset_index(drop=True)


def _build_metrics(
    path_nav: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metric_records: list[dict[str, Any]] = []
    annual_records: list[dict[str, Any]] = []
    for (model, path_offset, group), frame in path_nav.groupby(
        ["model", "path_offset", "group"], observed=True, sort=True
    ):
        portfolio = f"group_{int(group)}"
        metric_records.append(
            _performance_record(
                frame["daily_return"],
                model=str(model),
                path_offset=int(path_offset),
                portfolio=portfolio,
                period="all",
                settings=settings,
            )
        )
        for year, annual in frame.groupby(frame["date"].dt.year, sort=True):
            annual_records.append(
                _performance_record(
                    annual["daily_return"],
                    model=str(model),
                    path_offset=int(path_offset),
                    portfolio=portfolio,
                    period=str(int(year)),
                    settings=settings,
                )
            )
    for (model, path_offset, portfolio), frame in portfolio_returns.groupby(
        ["model", "path_offset", "portfolio"], observed=True, sort=True
    ):
        metric_records.append(
            _performance_record(
                frame["daily_return"],
                model=str(model),
                path_offset=int(path_offset),
                portfolio=str(portfolio),
                period="all",
                settings=settings,
            )
        )
        for year, annual in frame.groupby(frame["date"].dt.year, sort=True):
            annual_records.append(
                _performance_record(
                    annual["daily_return"],
                    model=str(model),
                    path_offset=int(path_offset),
                    portfolio=str(portfolio),
                    period=str(int(year)),
                    settings=settings,
                )
            )
    path_metrics = pd.DataFrame(metric_records)
    annual_metrics = pd.DataFrame(annual_records)
    aggregate = (
        pd.concat([path_metrics, annual_metrics], ignore_index=True)
        .groupby(["model", "portfolio", "period"], observed=True, as_index=False)
        .agg(
            path_count=("path_offset", "nunique"),
            annualized_return=("annualized_return", "mean"),
            sharpe=("sharpe", "mean"),
            max_drawdown=("max_drawdown", "mean"),
            cumulative_return=("cumulative_return", "mean"),
            n_days_mean=("n_days", "mean"),
        )
    )
    return path_metrics, annual_metrics, aggregate


def _build_daily_path_aggregate(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    """对当日已启动路径的净值做直接算术平均，不从平均收益重建曲线。"""
    aggregate = (
        portfolio_returns.groupby(["model", "portfolio", "date"], observed=True, as_index=False)
        .agg(
            nav=("nav", "mean"),
            mean_active_path_daily_return=("daily_return", "mean"),
            active_path_count=("path_offset", "nunique"),
        )
        .sort_values(["model", "portfolio", "date"])
    )
    previous_nav = aggregate.groupby(
        ["model", "portfolio"], observed=True
    )["nav"].shift(1)
    aggregate["daily_return"] = np.where(
        previous_nav.notna(),
        aggregate["nav"] / previous_nav - 1.0,
        aggregate["nav"] - 1.0,
    )
    return aggregate.loc[
        :,
        [
            "model",
            "portfolio",
            "date",
            "daily_return",
            "nav",
            "mean_active_path_daily_return",
            "active_path_count",
        ],
    ].reset_index(drop=True)


def _calculate_monotonicity(
    path_metric_aggregate: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> pd.DataFrame:
    full = path_metric_aggregate.loc[
        path_metric_aggregate["period"].eq("all")
        & path_metric_aggregate["portfolio"].str.startswith("group_")
    ].copy()
    full["group"] = full["portfolio"].str.removeprefix("group_").astype(int)
    records: list[dict[str, Any]] = []
    for model, frame in full.groupby("model", sort=True):
        ordered = frame.sort_values("group")
        rho, _ = stats.spearmanr(ordered["group"], ordered["annualized_return"])
        adjacent = ordered["annualized_return"].to_numpy()
        adjacent_success = float(np.mean(adjacent[:-1] >= adjacent[1:]))
        records.append(
            {
                "model": model,
                "spearman_group_vs_return": float(rho),
                "directional_monotonicity": float(-rho),
                "adjacent_descending_ratio": adjacent_success,
                "top_minus_bottom_annualized_return": float(adjacent[0] - adjacent[-1]),
                "n_groups": settings.n_groups,
            }
        )
    return pd.DataFrame(records)


def run_multi_path_factor_backtest(
    predictions: pd.DataFrame,
    market_panel: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    settings: MLPortfolioSettings,
) -> MLPortfolioResult:
    """执行五模型、十分档、20偏移路径的逐日可成交回测。"""
    factor_panel = prepare_factor_panel(predictions, settings)
    assignments = assign_descending_quantile_groups(factor_panel, settings)
    rank_ic, correlation, correlation_by_date = calculate_prediction_diagnostics(
        factor_panel, settings
    )
    market_by_date = _prepare_market_panel(market_panel, settings)
    calendar = _prepare_calendar(trade_calendar, settings.market_date_col)
    rank_ic_path_series, rank_ic_path_summary, rank_ic_path_aggregate = (
        build_rank_ic_path_aggregates(rank_ic, trade_calendar, settings)
    )
    models = sorted(factor_panel[settings.model_col].astype(str).unique())
    holding_frames: list[pd.DataFrame] = []
    trade_frames: list[pd.DataFrame] = []
    nav_frames: list[pd.DataFrame] = []
    for model in models:
        for path_offset in settings.path_offsets:
            for group_number in range(1, settings.n_groups + 1):
                events = _build_path_events(
                    assignments,
                    calendar,
                    model=model,
                    path_offset=path_offset,
                    group_number=group_number,
                    settings=settings,
                )
                holdings, trades, nav = _simulate_group_path(
                    model=model,
                    path_offset=path_offset,
                    group_number=group_number,
                    events=events,
                    calendar=calendar,
                    market_by_date=market_by_date,
                    settings=settings,
                )
                if not holdings.empty:
                    holding_frames.append(holdings)
                if not trades.empty:
                    trade_frames.append(trades)
                if not nav.empty:
                    nav_frames.append(nav)
    if not nav_frames:
        raise ValueError("全部模型和路径均未生成可估值净值")
    path_holdings = pd.concat(holding_frames, ignore_index=True) if holding_frames else pd.DataFrame()
    path_trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    path_nav = pd.concat(nav_frames, ignore_index=True)
    portfolio_returns = _build_portfolio_returns(path_nav, settings)
    path_metrics, annual_metrics, metric_aggregate = _build_metrics(
        path_nav, portfolio_returns, settings
    )
    daily_aggregate = _build_daily_path_aggregate(portfolio_returns)
    monotonicity = _calculate_monotonicity(metric_aggregate, settings)
    return MLPortfolioResult(
        factor_panel=factor_panel,
        factor_correlation=correlation,
        factor_correlation_by_date=correlation_by_date,
        rank_ic=rank_ic,
        rank_ic_path_series=rank_ic_path_series,
        rank_ic_path_summary=rank_ic_path_summary,
        rank_ic_path_aggregate=rank_ic_path_aggregate,
        group_assignments=assignments,
        path_holdings=path_holdings,
        path_trades=path_trades,
        path_nav=path_nav,
        portfolio_returns=portfolio_returns,
        path_metrics=path_metrics,
        annual_metrics=annual_metrics,
        path_metric_aggregate=metric_aggregate,
        path_daily_aggregate=daily_aggregate,
        monotonicity=monotonicity,
    )
