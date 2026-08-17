"""m3：组合、成本与中国交易约束回测。

本模块只消费 m1 的执行状态与 m2 的风格箱信号，不生成正式结果文件。交易
发生在信号日 T 之后的 ``execution_date``，成交价严格使用 m1 已完成单位核验
的前复权 ``execution_vwap``；日频估值使用同一前复权 ``close``，缺失时只沿用
此前已观察价格，绝不向后填充未来价格。

组合是有状态的：卖不出的旧仓继续持有，买不进的目标额度留在现金；成交按
“先卖后买”执行，可买订单在扣除交易费用后的可用现金内同比缩放。四箱、同池
全 A 与四箱 1/N 均使用同一执行器，SMB/HML/GML 再由四箱已实现收益逐期合成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from common.data_loader import load_trade_calendar

from .config import AllAStyleBoxConfig, DEFAULT_CONFIG
from .data_pipeline import (
    M1Dataset,
    _adjusted_vwap_panel,
    load_frozen_transfer_market_data,
)
from .strategy import M2Dataset


STYLE_BOXES: Final[tuple[str, ...]] = ("BV", "BG", "SV", "SG")
LONG_PORTFOLIOS: Final[tuple[str, ...]] = (*STYLE_BOXES, "ALL_A", "STYLE_1N")
FACTOR_NAMES: Final[tuple[str, ...]] = ("SMB", "HML", "GML")
CASH_CODE: Final[str] = "CASH"


@dataclass(frozen=True)
class M3Dataset:
    """F19/B7/B11/SA3：m3 的纯数据合同，不含 Excel/PNG。"""

    target_weights: pd.DataFrame
    daily_portfolio: pd.DataFrame
    monthly_portfolio: pd.DataFrame
    actual_weights: pd.DataFrame
    trades: pd.DataFrame
    turnover: pd.DataFrame
    costs: pd.DataFrame
    unfilled_orders: pd.DataFrame
    coverage: pd.DataFrame
    factor_returns: pd.DataFrame
    holdings: pd.DataFrame
    security_event_audit: pd.DataFrame
    source_catalog: pd.DataFrame


@dataclass
class _PortfolioState:
    shares: pd.Series
    net_cash: float
    gross_cash: float
    last_prices: pd.Series
    last_price_dates: pd.Series
    current_target_weights: pd.Series
    zero_target_rebalances: pd.Series
    previous_daily_net_nav: float
    previous_daily_gross_nav: float
    active_holding_month: str | None = None
    active_sample_phase: str | None = None
    active_signal_date: pd.Timestamp | None = None


@dataclass(frozen=True)
class _ExecutionResult:
    state: _PortfolioState
    trades: pd.DataFrame
    unfilled: pd.DataFrame
    actual_weights: pd.DataFrame
    holdings: pd.DataFrame
    turnover: dict[str, object]
    costs: dict[str, object]
    coverage: dict[str, object]
    pretrade_net_nav: float
    pretrade_gross_nav: float


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], source: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{source} 缺少 m3 必需字段: {missing}")


def _normalise_dates(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result:
            result[column] = pd.to_datetime(result[column], errors="coerce").dt.normalize()
    return result


def _finite_numeric(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    return numeric.where(np.isfinite(numeric))


def _stamp_tax_rate(date: pd.Timestamp, config: AllAStyleBoxConfig) -> float:
    change_date = pd.Timestamp(config.stamp_tax_change_date)
    if date < change_date:
        return config.stamp_tax_before_2023_08_28
    return config.stamp_tax_from_2023_08_28


def _transfer_window_age_trading_days(
    date: pd.Timestamp,
    trading_day_position: Mapping[pd.Timestamp, int],
    config: AllAStyleBoxConfig,
) -> int:
    """按全A交易日历计算摘牌日起的转板等待日序，摘牌日记为第1日。"""
    processing_date = pd.Timestamp(date).normalize()
    delisting_date = pd.Timestamp(config.security_transfer_delisting_date)
    if processing_date < delisting_date:
        return 0
    if delisting_date not in trading_day_position or processing_date not in trading_day_position:
        raise RuntimeError("600466转板窗口缺交易日日序，不能推测45日边界")
    return (
        int(trading_day_position[processing_date])
        - int(trading_day_position[delisting_date])
        + 1
    )


def _is_pending_security_transfer(
    code: str,
    date: pd.Timestamp,
    trading_day_position: Mapping[pd.Timestamp, int],
    config: AllAStyleBoxConfig,
) -> tuple[bool, int]:
    """只在映射公开前承认600466的官方有限等待状态。"""
    if str(code).zfill(6) != config.security_transfer_old_code:
        return False, 0
    age = _transfer_window_age_trading_days(date, trading_day_position, config)
    processing_date = pd.Timestamp(date).normalize()
    pending = bool(
        age > 0
        and age <= config.security_transfer_max_wait_trading_days
        and processing_date < pd.Timestamp(config.security_transfer_mapping_public_date)
    )
    return pending, age


def build_portfolio_targets(
    m1: M1Dataset,
    m2: M2Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """F19/B11：构造四箱、同池全 A 与四箱 1/N 的月度目标权重。

    m2 只贡献风格箱成员与箱内权重；全 A 权重及所有执行字段均显式来自 m1。
    ``STYLE_1N`` 为每个风格箱固定分配 ``1 / len(STYLE_BOXES)`` 的资金；若某
    月某箱为空，该箱额度保持现金，不对其他箱重新归一化。
    """
    panel = _normalise_dates(
        m1.monthly_panel,
        ("signal_date", "execution_date", "return_date"),
    )
    members = _normalise_dates(m2.box_memberships, ("signal_date", "execution_date"))
    _require_columns(
        panel,
        {
            "signal_date",
            "execution_date",
            "holding_month",
            "sample_phase",
            "stock_code",
            "is_eligible",
            "market_value",
            "negotiable_market_value",
        },
        "m1.monthly_panel",
    )
    _require_columns(
        members,
        {"signal_date", "stock_code", "style_box", "target_weight"},
        "m2.box_memberships",
    )
    panel["stock_code"] = panel["stock_code"].astype(str).str.zfill(6)
    members["stock_code"] = members["stock_code"].astype(str).str.zfill(6)

    metadata = panel[
        ["signal_date", "execution_date", "holding_month", "sample_phase"]
    ].drop_duplicates("signal_date")
    if metadata.duplicated("execution_date").any():
        raise AssertionError("每个 T+1 执行日必须只对应一个信号日")

    box_targets = members[
        ["signal_date", "stock_code", "style_box", "target_weight"]
    ].copy()
    if not box_targets["style_box"].isin(STYLE_BOXES).all():
        unexpected = sorted(set(box_targets["style_box"]).difference(STYLE_BOXES))
        raise ValueError(f"m2 存在非冻结四箱标签: {unexpected}")
    box_targets["portfolio"] = box_targets["style_box"]
    box_targets["target_source"] = "m2_box_market_cap_weight"

    eligible = panel.loc[
        panel["is_eligible"].fillna(False),
        [
            "signal_date",
            "stock_code",
            "market_value",
            "negotiable_market_value",
        ],
    ].copy()
    eligible["weight_market_value"] = _finite_numeric(
        eligible["negotiable_market_value"]
    ).where(
        _finite_numeric(eligible["negotiable_market_value"]).gt(0),
        _finite_numeric(eligible["market_value"]),
    )
    totals = eligible.groupby("signal_date", sort=False)[
        "weight_market_value"
    ].transform("sum")
    eligible["target_weight"] = eligible["weight_market_value"] / totals
    all_a_targets = eligible[
        ["signal_date", "stock_code", "target_weight"]
    ].assign(
        style_box=pd.NA,
        portfolio="ALL_A",
        target_source="m1_same_pool_market_cap_weight",
    )

    one_over_n = box_targets.copy()
    one_over_n["target_weight"] = one_over_n["target_weight"] / len(STYLE_BOXES)
    one_over_n["portfolio"] = "STYLE_1N"
    one_over_n["target_source"] = "fixed_equal_allocation_across_four_boxes"

    targets = pd.concat(
        [box_targets, all_a_targets, one_over_n],
        ignore_index=True,
        sort=False,
    ).merge(metadata, on="signal_date", how="left", validate="many_to_one")
    targets["target_weight"] = _finite_numeric(targets["target_weight"])
    targets = targets[
        [
            "signal_date",
            "execution_date",
            "holding_month",
            "sample_phase",
            "portfolio",
            "stock_code",
            "style_box",
            "target_weight",
            "target_source",
        ]
    ].sort_values(
        ["signal_date", "portfolio", "target_weight", "stock_code"],
        ascending=[True, True, False, True],
        kind="mergesort",
    )
    if targets.duplicated(["signal_date", "portfolio", "stock_code"]).any():
        raise AssertionError("同一信号日、组合、股票的目标权重必须唯一")
    sums = targets.groupby(["signal_date", "portfolio"])["target_weight"].sum()
    if sums.gt(1.0 + config.weight_tolerance).any():
        raise AssertionError("目标权重合计不得超过 100%")
    regular = sums.loc[sums.index.get_level_values("portfolio") != "STYLE_1N"]
    if not np.allclose(
        regular.to_numpy(dtype=float),
        np.ones(len(regular)),
        rtol=config.numeric_tolerance,
        atol=config.weight_tolerance,
    ):
        raise AssertionError("非 1/N 长组合的目标权重必须归一化为 100%")
    return targets.reset_index(drop=True)


def load_daily_mark_prices(
    target_weights: pd.DataFrame,
    schedule: pd.DataFrame,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """只读加载目标证券的日频前复权收盘价与交易日历。

    价格源固定为 ``config.path("price_forward")``。函数不做 ``bfill``；回测
    状态仅在价格实际出现后更新 last-price，因此停牌期间只能沿用历史价格。
    """
    _require_columns(target_weights, {"stock_code"}, "target_weights")
    schedule = _normalise_dates(schedule, ("execution_date", "return_date"))
    _require_columns(schedule, {"execution_date", "return_date"}, "m1.schedule")
    start = schedule["execution_date"].min()
    end = schedule["return_date"].max()
    if pd.isna(start) or pd.isna(end):
        raise ValueError("m1.schedule 没有完整的执行与收益端点")
    target_codes = set(target_weights["stock_code"].astype(str).str.zfill(6).unique())
    settlement_codes = {
        str(settlement_code).zfill(6)
        for _, _, _, settlement_code, _, _
        in config.security_share_settlement_events
    }
    codes = sorted(target_codes | settlement_codes)
    filters = [
        ("stock_code", "in", codes),
        ("date", ">=", start),
        ("date", "<=", end),
    ]
    forward = pd.read_parquet(
        config.path("price_forward"),
        columns=["stock_code", "stock_name", "date", "adj_factor", "close"],
        filters=filters,
    )
    raw = pd.read_parquet(
        config.path("price_raw"),
        columns=["stock_code", "date", "vwap", "close", "low", "high"],
        filters=filters,
    )
    trade = pd.read_parquet(
        config.path("trade"),
        columns=["stock_code", "stock_name", "date", "volume", "turn_value"],
        filters=filters,
    )
    suspend = pd.read_parquet(
        config.path("suspend"),
        columns=["stock_code", "date", "if_suspend"],
        filters=filters,
    )
    limits = pd.read_parquet(
        config.path("limit"),
        columns=["stock_code", "date", "decline_limit"],
        filters=filters,
    )
    for frame in (forward, raw, trade, suspend, limits):
        frame["stock_code"] = frame["stock_code"].astype(str).str.zfill(6)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    adjusted = _adjusted_vwap_panel(forward, raw).rename(
        columns={"forward_close": "close", "forward_vwap": "daily_vwap"}
    )
    prices = adjusted.merge(
        forward[["stock_code", "date", "stock_name"]].rename(
            columns={"stock_name": "price_stock_name"}
        ),
        on=["stock_code", "date"],
        how="outer",
    ).merge(
        trade.rename(columns={"stock_name": "trade_stock_name"}),
        on=["stock_code", "date"],
        how="outer",
    ).merge(suspend, on=["stock_code", "date"], how="outer").merge(
        limits, on=["stock_code", "date"], how="outer"
    )
    prices["stock_name"] = prices["price_stock_name"].combine_first(
        prices["trade_stock_name"]
    )
    prices["active_suspension"] = prices["if_suspend"].fillna(0).eq(1)
    prices["daily_no_volume"] = (
        pd.to_numeric(prices["volume"], errors="coerce").fillna(0).le(0)
        | pd.to_numeric(prices["turn_value"], errors="coerce").fillna(0).le(0)
    )
    prices["daily_limit_down"] = prices["decline_limit"].fillna(0).eq(1)
    prices["daily_vwap_valid"] = prices["forward_vwap_valid"].fillna(False)
    prices["daily_can_sell"] = (
        prices["daily_vwap_valid"]
        & ~prices["active_suspension"]
        & ~prices["daily_no_volume"]
        & ~prices["daily_limit_down"]
    )
    # stock_name 是静态回填字段，不作历史事件信号。
    prices["delisting_board_flag"] = False
    prices["close"] = _finite_numeric(prices["close"])
    prices["daily_vwap"] = _finite_numeric(prices["daily_vwap"])
    if config.security_transfer_old_code in target_codes:
        if prices["stock_code"].eq(config.security_transfer_new_code).any():
            raise RuntimeError(
                "本地全A主行情意外含400165；冻结第三方源不得覆盖或伪装本地主行情"
            )
        transfer_market = load_frozen_transfer_market_data(config)
        transfer_market = transfer_market.loc[
            transfer_market["date"].between(start, end)
        ].copy()
        transfer_market["stock_name"] = config.security_transfer_new_name
        transfer_market["volume"] = transfer_market["volume_shares"]
        transfer_market["turn_value"] = transfer_market["amount"]
        prices = pd.concat([prices, transfer_market], ignore_index=True, sort=False)
    prices = prices.sort_values(["date", "stock_code"], kind="mergesort").drop_duplicates(
        ["date", "stock_code"], keep="last"
    ).reset_index(drop=True)
    calendar = load_trade_calendar(
        config.data_root,
        start_date=str(start.date()),
        end_date=str(end.date()),
    )
    dates = pd.DatetimeIndex(calendar["date"].drop_duplicates().sort_values())
    return prices, dates


def _initial_state(config: AllAStyleBoxConfig) -> _PortfolioState:
    return _PortfolioState(
        shares=pd.Series(dtype=float),
        net_cash=config.initial_nav,
        gross_cash=config.initial_nav,
        last_prices=pd.Series(dtype=float),
        last_price_dates=pd.Series(dtype="datetime64[ns]"),
        current_target_weights=pd.Series(dtype=float),
        zero_target_rebalances=pd.Series(dtype="int64"),
        previous_daily_net_nav=config.initial_nav,
        previous_daily_gross_nav=config.initial_nav,
    )


def _position_value(shares: pd.Series, prices: pd.Series) -> float:
    held = shares.loc[shares.gt(0)]
    if held.empty:
        return 0.0
    marks = prices.reindex(held.index)
    if marks.isna().any():
        missing = marks.index[marks.isna()].tolist()
        raise AssertionError(f"持仓缺少历史可得估值价格: {missing[:10]}")
    return float(held.mul(marks).sum())


def _blocked_reason(
    row: pd.Series,
    side: str,
) -> str:
    if not bool(row.get("has_execution_record", False)):
        return "missing_execution_record"
    if bool(row.get("execution_is_suspended", False)):
        return "execution_suspended"
    if bool(row.get("execution_no_volume", False)):
        return "execution_no_volume"
    if not bool(row.get("execution_vwap_valid", False)):
        return "invalid_execution_vwap"
    if side == "BUY" and bool(row.get("execution_is_limit_up", False)):
        return "limit_up_cannot_buy"
    if side == "SELL" and bool(row.get("execution_is_limit_down", False)):
        return "limit_down_cannot_sell"
    return "direction_not_tradable"


def _empty_frame(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _execute_rebalance(
    *,
    state: _PortfolioState,
    portfolio: str,
    event: Mapping[str, object],
    targets: pd.DataFrame,
    status: pd.DataFrame,
    config: AllAStyleBoxConfig,
) -> _ExecutionResult:
    date = pd.Timestamp(event["execution_date"])
    signal_date = pd.Timestamp(event["signal_date"])
    holding_month = str(event["holding_month"])
    sample_phase = str(event["sample_phase"])
    status = status.copy()
    status["stock_code"] = status["stock_code"].astype(str).str.zfill(6)
    status = status.drop_duplicates("stock_code", keep="last").set_index("stock_code")
    target = targets.set_index("stock_code")["target_weight"].astype(float)

    codes = state.shares.index.union(target.index).union(status.index)
    status = status.reindex(codes)
    status["has_execution_record"] = status["execution_vwap"].notna() | status[
        "execution_vwap_valid"
    ].notna()
    for column in (
        "execution_vwap_valid",
        "execution_is_suspended",
        "execution_no_volume",
        "execution_is_limit_up",
        "execution_is_limit_down",
        "can_buy_t1",
        "can_sell_t1",
        "delisting_board_flag",
    ):
        status[column] = status[column].fillna(False).astype(bool)
    # 当日已知退市整理标记只能触发风险退出，不得新建/增加仓位。
    delisting_codes = status.index[status["delisting_board_flag"]]
    target.loc[target.index.intersection(delisting_codes)] = 0.0
    execution_price = _finite_numeric(status["execution_vwap"]).where(
        status["execution_vwap_valid"]
    )

    # T+1 VWAP 仅用于当次事件估值；历史 last-price 不从未来日期获取。
    event_marks = state.last_prices.reindex(codes)
    event_marks = execution_price.combine_first(event_marks)
    signal_price = _finite_numeric(status["signal_close"])
    order_reference_price = execution_price.combine_first(signal_price).combine_first(
        event_marks
    )
    held_codes = state.shares.index[state.shares.gt(config.numeric_tolerance)]
    pretrade_stock_count = int(len(held_codes))
    missing_marks = event_marks.reindex(held_codes).isna()
    if missing_marks.any():
        missing = missing_marks.index[missing_marks].tolist()
        raise AssertionError(f"T+1 前持仓没有历史可得价格: {missing[:10]}")
    current_shares = state.shares.reindex(codes, fill_value=0.0).astype(float)
    stock_value = current_shares.mul(event_marks.fillna(0.0))
    pretrade_stock_value = float(stock_value.sum())
    pretrade_net_cash = float(state.net_cash)
    pretrade_net_nav = state.net_cash + pretrade_stock_value
    pretrade_gross_nav = state.gross_cash + pretrade_stock_value
    if pretrade_net_nav <= config.cash_tolerance:
        raise AssertionError("组合净资产非正，无法继续调仓")

    target_weight = target.reindex(codes, fill_value=0.0)
    target_value = target_weight * pretrade_net_nav
    desired_delta_value = target_value - stock_value
    stamp_rate = _stamp_tax_rate(date, config)
    trade_records: list[dict[str, object]] = []
    unfilled_records: list[dict[str, object]] = []

    sell_request_value = (-desired_delta_value).clip(lower=0.0)
    sell_request_shares = sell_request_value.div(order_reference_price).replace(
        [np.inf, -np.inf], np.nan
    )
    sell_request_shares = sell_request_shares.clip(upper=current_shares)
    sell_mask = sell_request_value.gt(config.cash_tolerance)
    sell_fill_shares = sell_request_shares.where(
        sell_mask & status["can_sell_t1"] & execution_price.notna(),
        0.0,
    ).fillna(0.0)
    for code, shares in sell_fill_shares.loc[
        sell_fill_shares.gt(config.numeric_tolerance)
    ].items():
        price = float(execution_price.loc[code])
        notional = float(shares * price)
        commission = notional * config.commission_rate
        slippage = notional * config.slippage_rate
        stamp_tax = notional * stamp_rate
        total_cost = commission + slippage + stamp_tax
        state.net_cash += notional - total_cost
        state.gross_cash += notional
        current_shares.loc[code] -= shares
        trade_records.append(
            {
                "date": date,
                "signal_date": signal_date,
                "holding_month": holding_month,
                "sample_phase": sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "SELL",
                "shares": shares,
                "vwap": price,
                "gross_notional": notional,
                "commission_cost": commission,
                "slippage_cost": slippage,
                "stamp_tax": stamp_tax,
                "total_cost": total_cost,
                "net_cash_flow": notional - total_cost,
                "target_weight": float(target_weight.loc[code]),
            }
        )

    requested_sell_shares = sell_request_shares.fillna(0.0)
    unfilled_sell = (requested_sell_shares - sell_fill_shares).clip(lower=0.0)
    for code, shares in unfilled_sell.loc[
        unfilled_sell.gt(config.numeric_tolerance)
    ].items():
        row = status.loc[code]
        price = order_reference_price.loc[code]
        unfilled_records.append(
            {
                "date": date,
                "signal_date": signal_date,
                "holding_month": holding_month,
                "sample_phase": sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "SELL",
                "requested_shares": float(requested_sell_shares.loc[code]),
                "filled_shares": float(sell_fill_shares.loc[code]),
                "unfilled_shares": float(shares),
                "reference_price": float(price) if pd.notna(price) else np.nan,
                "unfilled_notional": float(shares * price) if pd.notna(price) else float(
                    sell_request_value.loc[code]
                ),
                "reason": _blocked_reason(row, "SELL"),
            }
        )

    post_sell_value = current_shares.mul(event_marks.fillna(0.0))
    buy_request_value = (target_value - post_sell_value).clip(lower=0.0)
    buy_request_shares = buy_request_value.div(order_reference_price).replace(
        [np.inf, -np.inf], np.nan
    )
    buy_mask = buy_request_value.gt(config.cash_tolerance)
    executable_buy_shares = buy_request_shares.where(
        buy_mask & status["can_buy_t1"] & execution_price.notna(),
        0.0,
    ).fillna(0.0)
    executable_buy_notional = executable_buy_shares.mul(execution_price).fillna(0.0)
    buy_cash_multiplier = 1.0 + config.commission_rate + config.slippage_rate
    requested_buy_cash = float(executable_buy_notional.sum() * buy_cash_multiplier)
    if requested_buy_cash > config.cash_tolerance:
        buy_scale = min(1.0, max(0.0, state.net_cash) / requested_buy_cash)
    else:
        buy_scale = 0.0
    buy_fill_shares = executable_buy_shares * buy_scale

    for code, shares in buy_fill_shares.loc[
        buy_fill_shares.gt(config.numeric_tolerance)
    ].items():
        price = float(execution_price.loc[code])
        notional = float(shares * price)
        commission = notional * config.commission_rate
        slippage = notional * config.slippage_rate
        total_cost = commission + slippage
        state.net_cash -= notional + total_cost
        state.gross_cash -= notional
        current_shares.loc[code] += shares
        trade_records.append(
            {
                "date": date,
                "signal_date": signal_date,
                "holding_month": holding_month,
                "sample_phase": sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "BUY",
                "shares": shares,
                "vwap": price,
                "gross_notional": notional,
                "commission_cost": commission,
                "slippage_cost": slippage,
                "stamp_tax": 0.0,
                "total_cost": total_cost,
                "net_cash_flow": -(notional + total_cost),
                "target_weight": float(target_weight.loc[code]),
            }
        )

    requested_buy_shares = buy_request_shares.fillna(0.0)
    unfilled_buy = (requested_buy_shares - buy_fill_shares).clip(lower=0.0)
    for code, shares in unfilled_buy.loc[
        unfilled_buy.gt(config.numeric_tolerance)
    ].items():
        row = status.loc[code]
        price = order_reference_price.loc[code]
        executable = bool(status.loc[code, "can_buy_t1"]) and pd.notna(price)
        reason = "insufficient_cash_after_costs" if executable else _blocked_reason(row, "BUY")
        unfilled_records.append(
            {
                "date": date,
                "signal_date": signal_date,
                "holding_month": holding_month,
                "sample_phase": sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "BUY",
                "requested_shares": float(requested_buy_shares.loc[code]),
                "filled_shares": float(buy_fill_shares.loc[code]),
                "unfilled_shares": float(shares),
                "reference_price": float(price) if pd.notna(price) else np.nan,
                "unfilled_notional": float(shares * price) if pd.notna(price) else float(
                    buy_request_value.loc[code]
                ),
                "reason": reason,
            }
        )

    state.shares = current_shares.loc[current_shares.gt(config.numeric_tolerance)].copy()
    state.current_target_weights = target_weight.reindex(
        state.shares.index, fill_value=0.0
    ).astype(float)
    old_zero_counts = state.zero_target_rebalances.reindex(
        state.shares.index, fill_value=0
    ).astype(int)
    state.zero_target_rebalances = (
        old_zero_counts + state.current_target_weights.le(config.weight_tolerance).astype(int)
    ).where(
        state.current_target_weights.le(config.weight_tolerance), 0
    ).astype(int)
    traded_codes = execution_price.index[execution_price.notna()]
    state.last_prices = state.last_prices.combine_first(pd.Series(index=codes, dtype=float))
    state.last_prices.loc[traded_codes] = execution_price.loc[traded_codes]
    state.last_price_dates = state.last_price_dates.combine_first(
        pd.Series(index=codes, dtype="datetime64[ns]")
    )
    state.last_price_dates.loc[traded_codes] = date
    state.active_holding_month = holding_month
    state.active_sample_phase = sample_phase
    state.active_signal_date = signal_date
    if state.net_cash < -config.cash_tolerance:
        raise AssertionError("买入成交后净现金为负")
    if abs(state.net_cash) <= config.cash_tolerance:
        state.net_cash = 0.0

    trade_columns = [
        "date", "signal_date", "holding_month", "sample_phase", "portfolio",
        "stock_code", "side", "shares", "vwap", "gross_notional",
        "commission_cost", "slippage_cost", "stamp_tax", "total_cost",
        "net_cash_flow", "target_weight",
    ]
    unfilled_columns = [
        "date", "signal_date", "holding_month", "sample_phase", "portfolio",
        "stock_code", "side", "requested_shares", "filled_shares",
        "unfilled_shares", "reference_price", "unfilled_notional", "reason",
    ]
    trades = pd.DataFrame(trade_records, columns=trade_columns)
    unfilled = pd.DataFrame(unfilled_records, columns=unfilled_columns)
    total_notional = float(trades["gross_notional"].sum()) if not trades.empty else 0.0
    buy_notional = float(
        trades.loc[trades["side"].eq("BUY"), "gross_notional"].sum()
    ) if not trades.empty else 0.0
    sell_notional = float(
        trades.loc[trades["side"].eq("SELL"), "gross_notional"].sum()
    ) if not trades.empty else 0.0
    commission_cost = float(trades["commission_cost"].sum()) if not trades.empty else 0.0
    slippage_cost = float(trades["slippage_cost"].sum()) if not trades.empty else 0.0
    stamp_tax = float(trades["stamp_tax"].sum()) if not trades.empty else 0.0
    total_cost = commission_cost + slippage_cost + stamp_tax

    posttrade_stock_value = _position_value(state.shares, state.last_prices)
    posttrade_net_nav = state.net_cash + posttrade_stock_value
    actual_records: list[dict[str, object]] = []
    holding_records: list[dict[str, object]] = []
    union_codes = state.shares.index.union(target.index)
    for code in union_codes:
        shares = float(state.shares.get(code, 0.0))
        mark = state.last_prices.get(code, np.nan)
        market_value = shares * mark if pd.notna(mark) else 0.0
        actual_weight = market_value / posttrade_net_nav
        target_value_weight = float(target.get(code, 0.0))
        actual_records.append(
            {
                "date": date,
                "signal_date": signal_date,
                "holding_month": holding_month,
                "sample_phase": sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "target_weight": target_value_weight,
                "actual_weight": actual_weight,
                "weight_gap": actual_weight - target_value_weight,
            }
        )
        if shares > config.numeric_tolerance:
            holding_records.append(
                {
                    "effective_date": date,
                    "signal_date": signal_date,
                    "holding_month": holding_month,
                    "sample_phase": sample_phase,
                    "portfolio": portfolio,
                    "stock_code": code,
                    "shares": shares,
                    "mark_price": mark,
                    "price_source_date": state.last_price_dates.get(code, pd.NaT),
                    "market_value": market_value,
                    "actual_weight": actual_weight,
                }
            )
    cash_weight = state.net_cash / posttrade_net_nav
    actual_records.append(
        {
            "date": date,
            "signal_date": signal_date,
            "holding_month": holding_month,
            "sample_phase": sample_phase,
            "portfolio": portfolio,
            "stock_code": CASH_CODE,
            "target_weight": max(0.0, 1.0 - float(target.sum())),
            "actual_weight": cash_weight,
            "weight_gap": cash_weight - max(0.0, 1.0 - float(target.sum())),
        }
    )
    holding_records.append(
        {
            "effective_date": date,
            "signal_date": signal_date,
            "holding_month": holding_month,
            "sample_phase": sample_phase,
            "portfolio": portfolio,
            "stock_code": CASH_CODE,
            "shares": np.nan,
            "mark_price": 1.0,
            "price_source_date": date,
            "market_value": state.net_cash,
            "actual_weight": cash_weight,
        }
    )

    meta = {
        "date": date,
        "signal_date": signal_date,
        "holding_month": holding_month,
        "sample_phase": sample_phase,
        "portfolio": portfolio,
    }
    turnover = {
        **meta,
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "gross_traded_notional": total_notional,
        "two_sided_turnover": total_notional / pretrade_net_nav,
        "one_way_turnover": total_notional / (2.0 * pretrade_net_nav),
    }
    costs = {
        **meta,
        "commission_cost": commission_cost,
        "slippage_cost": slippage_cost,
        "stamp_tax": stamp_tax,
        "total_cost": total_cost,
        "cost_rate_on_pretrade_nav": total_cost / pretrade_net_nav,
        "stamp_tax_rate": stamp_rate,
    }
    target_member_count = int(target_weight.gt(0).sum())
    target_execution_prices = execution_price.reindex(target_weight.index[target_weight.gt(0)])
    target_buy_flags = status["can_buy_t1"].reindex(
        target_weight.index[target_weight.gt(0)], fill_value=False
    )
    coverage = {
        **meta,
        "target_member_count": target_member_count,
        "execution_price_available_count": int(target_execution_prices.notna().sum()),
        "buy_tradable_count": int((target_execution_prices.notna() & target_buy_flags).sum()),
        "execution_price_coverage": (
            float(target_execution_prices.notna().mean()) if target_member_count else np.nan
        ),
        "buy_tradable_coverage": (
            float((target_execution_prices.notna() & target_buy_flags).mean())
            if target_member_count
            else np.nan
        ),
        "target_weight_sum": float(target.sum()),
        "actual_stock_weight_sum": 1.0 - cash_weight,
        "cash_weight": cash_weight,
        "unfilled_order_count": len(unfilled),
        "unfilled_notional": float(unfilled["unfilled_notional"].sum())
        if not unfilled.empty
        else 0.0,
        "pretrade_stock_count": pretrade_stock_count,
        "pretrade_cash_weight": pretrade_net_cash / pretrade_net_nav,
        "pre_oos_positions_carried": pretrade_stock_count
        if sample_phase == "formal_oos" and pretrade_stock_count > 0
        else 0,
    }
    return _ExecutionResult(
        state=state,
        trades=trades,
        unfilled=unfilled,
        actual_weights=pd.DataFrame(actual_records),
        holdings=pd.DataFrame(holding_records),
        turnover=turnover,
        costs=costs,
        coverage=coverage,
        pretrade_net_nav=pretrade_net_nav,
        pretrade_gross_nav=pretrade_gross_nav,
    )


def _update_close_marks(
    state: _PortfolioState,
    date: pd.Timestamp,
    observed: pd.Series,
) -> None:
    observed = _finite_numeric(observed).dropna()
    observed = observed.loc[observed.gt(0)]
    if observed.empty:
        return
    state.last_prices = state.last_prices.combine_first(
        pd.Series(index=observed.index, dtype=float)
    )
    state.last_prices.loc[observed.index] = observed
    state.last_price_dates = state.last_price_dates.combine_first(
        pd.Series(index=observed.index, dtype="datetime64[ns]")
    )
    state.last_price_dates.loc[observed.index] = date


def _normalise_security_events(events: pd.DataFrame | None) -> pd.DataFrame:
    """标准化显式公司行动；空表不代表可猜测结算。"""
    columns = [
        "stock_code",
        "event_type",
        "announcement_date",
        "event_effective_date",
        "action",
        "settlement_code",
        "settlement_ratio",
        "settlement_cash",
        "event_source",
    ]
    if events is None or events.empty:
        return pd.DataFrame(columns=columns)
    result = events.copy()
    aliases = {
        "effective_date": "event_effective_date",
        "cash_per_share": "settlement_cash",
        "settlement_cash_per_share": "settlement_cash",
        "source": "event_source",
    }
    result = result.rename(columns={k: v for k, v in aliases.items() if k in result})
    _require_columns(
        result,
        {"stock_code", "event_type", "event_effective_date", "event_source"},
        "security_events",
    )
    for column in columns:
        if column not in result:
            result[column] = np.nan
    result["stock_code"] = result["stock_code"].astype(str).str.zfill(6)
    result["settlement_code"] = result["settlement_code"].astype("string").str.zfill(6)
    for column in ("announcement_date", "event_effective_date"):
        result[column] = pd.to_datetime(result[column], errors="coerce").dt.normalize()
    result["settlement_ratio"] = _finite_numeric(result["settlement_ratio"]).fillna(0.0)
    result["settlement_cash"] = _finite_numeric(result["settlement_cash"]).fillna(0.0)
    if result[["announcement_date", "event_effective_date", "event_source"]].isna().any(axis=None):
        raise ValueError("显式证券事件缺生效日或证据来源")
    valid_settlement = (
        result["action"].isin(
            (
                "risk_exit_on_next_trade",
                "target_zero_exit_on_next_trade",
                "holding_restriction",
            )
        )
        | result["settlement_cash"].gt(0)
        | (
        result["settlement_code"].notna() & result["settlement_ratio"].gt(0)
        )
    )
    if not valid_settlement.all():
        invalid = result.loc[~valid_settlement, ["stock_code", "event_type"]]
        raise ValueError(f"证券事件缺可重算的现金或换股结算: {invalid.to_dict('records')}")
    if result.duplicated(["stock_code", "event_effective_date", "event_type"]).any():
        raise ValueError("证券事件映射键重复")
    return result[columns].sort_values(
        ["event_effective_date", "stock_code", "event_type"], kind="mergesort"
    ).reset_index(drop=True)


def _apply_effective_security_events(
    state: _PortfolioState,
    *,
    portfolio: str,
    date: pd.Timestamp,
    events: pd.DataFrame,
    observed: pd.Series,
    config: AllAStyleBoxConfig,
) -> list[dict[str, object]]:
    """只处理 processing_date 当日已生效且有明示来源的换股/现金事件。"""
    if events.empty or state.shares.empty:
        return []
    today = events.loc[
        events["event_effective_date"].eq(date)
        & ~events["action"].isin(
            (
                "risk_exit_on_next_trade",
                "target_zero_exit_on_next_trade",
                "holding_restriction",
            )
        )
    ]
    records: list[dict[str, object]] = []
    for event in today.itertuples(index=False):
        code = str(event.stock_code).zfill(6)
        shares = float(state.shares.get(code, 0.0))
        if shares <= config.numeric_tolerance:
            continue
        cash_before_net = float(state.net_cash)
        cash_before_gross = float(state.gross_cash)
        settlement_cash = shares * float(event.settlement_cash)
        new_code = str(event.settlement_code).zfill(6) if pd.notna(event.settlement_code) else None
        new_shares = shares * float(event.settlement_ratio) if new_code else 0.0
        state.shares = state.shares.drop(code)
        state.current_target_weights = state.current_target_weights.drop(code, errors="ignore")
        state.zero_target_rebalances = state.zero_target_rebalances.drop(code, errors="ignore")
        new_mark = np.nan
        if new_code is not None and new_shares > config.numeric_tolerance:
            new_mark = float(observed.get(new_code, np.nan))
            if not np.isfinite(new_mark) or new_mark <= 0:
                raise RuntimeError(
                    f"换股事件生效日缺当日可观察新证券价格: {code}->{new_code} {date.date()}"
                )
            state.shares.loc[new_code] = state.shares.get(new_code, 0.0) + new_shares
            state.last_prices.loc[new_code] = new_mark
            state.last_price_dates.loc[new_code] = date
            state.current_target_weights.loc[new_code] = 0.0
            state.zero_target_rebalances.loc[new_code] = 0
        state.net_cash += settlement_cash
        state.gross_cash += settlement_cash
        records.append(
            {
                "date": date,
                "processing_date": date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "shares": shares,
                "target_weight": float(state.current_target_weights.get(code, 0.0)),
                "price_source_date": state.last_price_dates.get(code, pd.NaT),
                "price_age_trading_days": 0,
                "consecutive_missing_price_days": 0,
                "active_suspension": False,
                "delisting_board_flag": False,
                "event_type": str(event.event_type),
                "announcement_date": pd.Timestamp(event.announcement_date),
                "event_effective_date": pd.Timestamp(event.event_effective_date),
                "settlement_code": new_code,
                "settlement_ratio": float(event.settlement_ratio),
                "settlement_cash": float(event.settlement_cash),
                "event_source": str(event.event_source),
                "mark_used_in_nav": (
                    float(event.settlement_cash)
                    + float(event.settlement_ratio) * new_mark
                    if np.isfinite(new_mark)
                    else float(event.settlement_cash)
                ),
                "executed_vwap": np.nan,
                "executed_market_volume": np.nan,
                "rule_label": "explicit_cash_or_share_settlement",
                "unexplained_stale_residual": False,
                "blocking": False,
                "settlement_holding_error": 0.0,
                "settlement_cash_error": max(
                    abs((state.net_cash - cash_before_net) - settlement_cash),
                    abs((state.gross_cash - cash_before_gross) - settlement_cash),
                ),
                "settlement_return_error": 0.0,
            }
        )
    return records


def _execute_delisting_risk_exit(
    state: _PortfolioState,
    *,
    portfolio: str,
    date: pd.Timestamp,
    daily_status: pd.DataFrame,
    events: pd.DataFrame,
    config: AllAStyleBoxConfig,
) -> tuple[pd.DataFrame, list[dict[str, object]], float]:
    """公告已知且生效后，在下一真实可卖 VWAP 风险退出。"""
    if state.shares.empty or daily_status.empty or events.empty:
        return pd.DataFrame(), [], 0.0
    status = daily_status.drop_duplicates("stock_code", keep="last").set_index("stock_code")
    available_events = events.loc[
        events["action"].isin(
            ("risk_exit_on_next_trade", "target_zero_exit_on_next_trade")
        )
        & events["announcement_date"].le(date)
        & events["event_effective_date"].le(date)
    ].drop_duplicates("stock_code", keep="last").set_index("stock_code")
    # 公告只决定“应退出”，不能覆盖交易所方向限制。只有 m1 已同时证明
    # VWAP有效、非停牌、有成交且非跌停的 daily_can_sell=True 才能成交。
    can_sell = status["daily_can_sell"].fillna(False).astype(bool)
    active_codes = state.shares.index.intersection(available_events.index)
    candidates = active_codes.intersection(status.index[can_sell])
    trade_records: list[dict[str, object]] = []
    audit_records: list[dict[str, object]] = []
    total_cost = 0.0
    blocked_codes = active_codes.difference(candidates)
    for code in blocked_codes:
        event = available_events.loc[code]
        row = status.loc[code] if code in status.index else pd.Series(dtype=object)
        observed_close_value = pd.to_numeric(row.get("close", np.nan), errors="coerce")
        observed_close = (
            float(observed_close_value) if pd.notna(observed_close_value) else np.nan
        )
        historical_mark = float(state.last_prices.get(code, np.nan))
        mark_used = (
            observed_close
            if np.isfinite(observed_close) and observed_close > 0.0
            else historical_mark
        )
        mark_source_date = (
            date
            if np.isfinite(observed_close) and observed_close > 0.0
            else state.last_price_dates.get(code, pd.NaT)
        )
        audit_records.append(
            {
                "date": date,
                "processing_date": date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "shares": float(state.shares.loc[code]),
                "target_weight": 0.0,
                "price_source_date": mark_source_date,
                "price_age_trading_days": 0,
                "consecutive_missing_price_days": 0,
                "active_suspension": bool(row.get("active_suspension", False)),
                "delisting_board_flag": str(event["action"]) == "risk_exit_on_next_trade",
                "event_type": str(event["event_type"]),
                "announcement_date": pd.Timestamp(event["announcement_date"]),
                "event_effective_date": pd.Timestamp(event["event_effective_date"]),
                "settlement_code": pd.NA,
                "settlement_ratio": 0.0,
                "settlement_cash": 0.0,
                "event_source": str(event["event_source"]) + ";waiting_for_daily_can_sell",
                "mark_used_in_nav": mark_used,
                "executed_vwap": np.nan,
                "executed_market_volume": np.nan,
                "rule_label": "risk_exit_waiting_daily_can_sell",
                "unexplained_stale_residual": False,
                "blocking": False,
                "settlement_holding_error": 0.0,
                "settlement_cash_error": 0.0,
                "settlement_return_error": 0.0,
            }
        )
    for code in candidates:
        event = available_events.loc[code]
        shares = float(state.shares.loc[code])
        price = float(status.loc[code, "daily_vwap"])
        notional = shares * price
        commission = notional * config.commission_rate
        slippage = notional * config.slippage_rate
        stamp_tax = notional * _stamp_tax_rate(date, config)
        cost = commission + slippage + stamp_tax
        state.net_cash += notional - cost
        state.gross_cash += notional
        state.shares = state.shares.drop(code)
        state.current_target_weights = state.current_target_weights.drop(code, errors="ignore")
        state.zero_target_rebalances = state.zero_target_rebalances.drop(code, errors="ignore")
        total_cost += cost
        trade_records.append(
            {
                "date": date,
                "signal_date": state.active_signal_date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "SELL",
                "shares": shares,
                "vwap": price,
                "gross_notional": notional,
                "commission_cost": commission,
                "slippage_cost": slippage,
                "stamp_tax": stamp_tax,
                "total_cost": cost,
                "net_cash_flow": notional - cost,
                "target_weight": 0.0,
            }
        )
        audit_records.append(
            {
                "date": date,
                "processing_date": date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "shares": shares,
                "target_weight": 0.0,
                "price_source_date": date,
                "price_age_trading_days": 0,
                "consecutive_missing_price_days": 0,
                "active_suspension": False,
                "delisting_board_flag": str(event["action"]) == "risk_exit_on_next_trade",
                "event_type": str(event["event_type"]),
                "announcement_date": pd.Timestamp(event["announcement_date"]),
                "event_effective_date": pd.Timestamp(event["event_effective_date"]),
                "settlement_code": pd.NA,
                "settlement_ratio": 0.0,
                "settlement_cash": price,
                "event_source": str(event["event_source"]) + ";same_day_validated_daily_vwap",
                "mark_used_in_nav": price,
                "executed_vwap": price,
                "executed_market_volume": float(status.loc[code, "volume"]),
                "rule_label": str(event["event_type"]),
                "unexplained_stale_residual": False,
                "blocking": False,
                "settlement_holding_error": 0.0,
                "settlement_cash_error": 0.0,
                "settlement_return_error": 0.0,
            }
        )
    return pd.DataFrame(trade_records), audit_records, total_cost


def _execute_security_transfer_exit(
    state: _PortfolioState,
    *,
    portfolio: str,
    date: pd.Timestamp,
    daily_status: pd.DataFrame,
    trading_day_position: Mapping[pd.Timestamp, int],
    config: AllAStyleBoxConfig,
) -> tuple[pd.DataFrame, list[dict[str, object]], float]:
    """在映射当日按冻结后继证券真实成交证据卖出1:1映射份额。"""
    old_code = config.security_transfer_old_code
    new_code = config.security_transfer_new_code
    old_shares = float(state.shares.get(old_code, 0.0))
    if old_shares <= config.numeric_tolerance:
        return pd.DataFrame(), [], 0.0
    processing_date = pd.Timestamp(date).normalize()
    delisting_date = pd.Timestamp(config.security_transfer_delisting_date)
    if processing_date < delisting_date:
        return pd.DataFrame(), [], 0.0
    window_age = _transfer_window_age_trading_days(
        processing_date, trading_day_position, config
    )
    if window_age > config.security_transfer_max_wait_trading_days:
        raise RuntimeError(
            "600466转板等待超过官方45交易日，禁止永久携带0.40旧mark"
        )
    mapping_public_date = pd.Timestamp(config.security_transfer_mapping_public_date)
    effective_date = pd.Timestamp(config.security_transfer_effective_date)
    if processing_date < mapping_public_date or processing_date < effective_date:
        return pd.DataFrame(), [], 0.0
    if processing_date > effective_date:
        raise RuntimeError("600466已过400165首个真实成交日仍未退出，禁止未来回看补成交")
    if mapping_public_date > processing_date:
        raise RuntimeError("400165映射尚未公开，禁止提前使用后继证券")
    if daily_status.empty:
        raise RuntimeError("400165映射生效日缺冻结行情，600466生命周期硬阻断")
    status = daily_status.drop_duplicates("stock_code", keep="last").set_index("stock_code")
    if new_code not in status.index:
        raise RuntimeError("400165映射生效日缺冻结行情，600466生命周期硬阻断")
    row = status.loc[new_code]
    source_hash = str(row.get("external_source_sha256", ""))
    expected_market_hash = dict(config.security_transfer_frozen_sha256)[
        config.security_transfer_market_raw_filename
    ]
    if source_hash != expected_market_hash:
        raise RuntimeError("400165冻结行情source hash不符，600466生命周期硬阻断")
    if not bool(row.get("external_transfer_exit_only", False)):
        raise RuntimeError("400165第三方源未限制为600466生命周期退出专用")
    row_date = pd.Timestamp(row.get("date", processing_date)).normalize()
    if row_date != processing_date:
        raise RuntimeError("400165冻结行情日期与处理日不一致")

    old_mark = float(state.last_prices.get(old_code, np.nan))
    old_mark_date = pd.Timestamp(state.last_price_dates.get(old_code, pd.NaT))
    if (
        not np.isfinite(old_mark)
        or not np.isclose(
            old_mark,
            config.security_transfer_old_mark,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        )
        or old_mark_date != pd.Timestamp(config.security_transfer_old_mark_date)
    ):
        raise RuntimeError("600466等待转板前的0.40旧mark或来源日不符合冻结合同")

    source_volume = float(pd.to_numeric(row.get("volumn", np.nan), errors="coerce"))
    volume_unit = str(row.get("volume_unit", ""))
    volume_shares = float(pd.to_numeric(row.get("volume_shares", np.nan), errors="coerce"))
    if (
        not np.isfinite(source_volume)
        or source_volume <= 0
        or not np.isfinite(volume_shares)
        or volume_shares <= 0
        or volume_unit != config.security_transfer_market_volume_unit
        or not np.isclose(
            volume_shares,
            source_volume,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        )
    ):
        raise RuntimeError("400165冻结行情volumn无效、非股单位或股数不一致")

    amount = float(pd.to_numeric(row.get("amount", np.nan), errors="coerce"))
    amount_available = bool(row.get("amount_available", np.isfinite(amount) and amount > 0))
    if amount_available:
        if not np.isfinite(amount) or amount <= 0:
            raise RuntimeError("400165冻结行情声明成交额可用但金额无效")
        recomputed_vwap = amount / volume_shares
        vwap_proof_method = "reported_amount_divided_by_volume_lots_times_100"
    else:
        ohlc = np.array(
            [
                pd.to_numeric(row.get(column, np.nan), errors="coerce")
                for column in ("open", "high", "low", "close")
            ],
            dtype=float,
        )
        if (
            not np.isfinite(ohlc).all()
            or not np.allclose(
                ohlc,
                np.full(len(ohlc), ohlc[0]),
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
        ):
            raise RuntimeError("400165冻结源缺成交额且OHLC并非单一成交价，禁止推断VWAP")
        recomputed_vwap = float(ohlc[0])
        vwap_proof_method = "positive_volume_and_identical_ohlc_single_price"
    quoted_vwap = float(pd.to_numeric(row.get("daily_vwap", np.nan), errors="coerce"))
    if (
        not bool(row.get("daily_can_sell", False))
        or not bool(row.get("daily_vwap_valid", False))
        or not np.isfinite(quoted_vwap)
        or quoted_vwap <= 0
        or not np.isclose(
            quoted_vwap,
            recomputed_vwap,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        )
        or not np.isclose(
            recomputed_vwap,
            config.security_transfer_expected_exit_vwap,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        )
    ):
        raise RuntimeError("400165首日缺可卖证据或真实VWAP不等于0.38元")

    preexisting_new_shares = float(state.shares.get(new_code, 0.0))
    if preexisting_new_shares > config.numeric_tolerance:
        raise RuntimeError("400165第三方源只能服务600466映射份额，不得处理普通持仓")
    mapped_shares = old_shares * config.security_transfer_ratio
    mapping_error = abs(mapped_shares - old_shares)
    if mapped_shares > volume_shares + config.numeric_tolerance:
        raise RuntimeError("600466映射退出份额超过400165首日真实成交量")
    cash_before_net = float(state.net_cash)
    cash_before_gross = float(state.gross_cash)
    target_weight = float(state.current_target_weights.get(old_code, 0.0))
    gross_notional = mapped_shares * recomputed_vwap
    commission = gross_notional * config.commission_rate
    slippage = gross_notional * config.slippage_rate
    stamp_tax_rate = _stamp_tax_rate(processing_date, config)
    stamp_tax = gross_notional * stamp_tax_rate
    total_cost = commission + slippage + stamp_tax
    net_cash_flow = gross_notional - total_cost

    state.shares = state.shares.drop(old_code)
    state.current_target_weights = state.current_target_weights.drop(old_code, errors="ignore")
    state.zero_target_rebalances = state.zero_target_rebalances.drop(old_code, errors="ignore")
    state.shares.loc[new_code] = mapped_shares
    state.last_prices.loc[new_code] = recomputed_vwap
    state.last_price_dates.loc[new_code] = processing_date
    state.current_target_weights.loc[new_code] = 0.0
    state.zero_target_rebalances.loc[new_code] = 0
    state.net_cash += net_cash_flow
    state.gross_cash += gross_notional
    state.shares = state.shares.drop(new_code)
    state.current_target_weights = state.current_target_weights.drop(new_code, errors="ignore")
    state.zero_target_rebalances = state.zero_target_rebalances.drop(new_code, errors="ignore")
    cash_error = max(
        abs((state.net_cash - cash_before_net) - net_cash_flow),
        abs((state.gross_cash - cash_before_gross) - gross_notional),
    )
    trade = pd.DataFrame(
        [
            {
                "date": processing_date,
                "signal_date": state.active_signal_date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": new_code,
                "side": "SELL",
                "shares": mapped_shares,
                "vwap": recomputed_vwap,
                "gross_notional": gross_notional,
                "commission_cost": commission,
                "slippage_cost": slippage,
                "stamp_tax": stamp_tax,
                "total_cost": total_cost,
                "net_cash_flow": net_cash_flow,
                "target_weight": 0.0,
                "lifecycle_old_code": old_code,
                "lifecycle_transfer_ratio": config.security_transfer_ratio,
                "external_source_sha256": source_hash,
            }
        ]
    )
    official_hashes = dict(config.security_transfer_frozen_sha256)
    audit = [
        {
            "date": processing_date,
            "processing_date": processing_date,
            "asof": processing_date,
            "holding_month": state.active_holding_month,
            "sample_phase": state.active_sample_phase,
            "portfolio": portfolio,
            "stock_code": old_code,
            "old_stock_code": old_code,
            "new_stock_code": new_code,
            "shares": old_shares,
            "old_shares_before": old_shares,
            "mapped_shares": mapped_shares,
            "exit_shares": mapped_shares,
            "old_shares_after": float(state.shares.get(old_code, 0.0)),
            "new_shares_after": float(state.shares.get(new_code, 0.0)),
            "target_weight": target_weight,
            "price_source_date": processing_date,
            "price_age_trading_days": 0,
            "consecutive_missing_price_days": 0,
            "transfer_window_age_trading_days": window_age,
            "active_suspension": False,
            "delisting_board_flag": True,
            "event_type": "delisted_security_transfer_market_exit",
            "announcement_date": mapping_public_date,
            "event_effective_date": effective_date,
            "mapping_public_date": mapping_public_date,
            "mapping_effective_date": effective_date,
            "settlement_code": new_code,
            "settlement_ratio": config.security_transfer_ratio,
            "settlement_cash": 0.0,
            "old_mark": old_mark,
            "new_quote": recomputed_vwap,
            "open": float(row.get("open", np.nan)),
            "high": float(row.get("high", np.nan)),
            "low": float(row.get("low", np.nan)),
            "close": float(row.get("close", np.nan)),
            "volumn": source_volume,
            "volume_unit": volume_unit,
            "volume_shares": volume_shares,
            "amount": amount if amount_available else np.nan,
            "amount_available": amount_available,
            "amount_status": config.security_transfer_market_amount_status,
            "recomputed_vwap": recomputed_vwap,
            "vwap_proof_method": vwap_proof_method,
            "gross_notional": gross_notional,
            "commission_cost": commission,
            "slippage_cost": slippage,
            "stamp_tax_rate": stamp_tax_rate,
            "stamp_tax": stamp_tax,
            "total_cost": total_cost,
            "net_cash_flow": net_cash_flow,
            "net_cash_before": cash_before_net,
            "net_cash_after": float(state.net_cash),
            "gross_cash_before": cash_before_gross,
            "gross_cash_after": float(state.gross_cash),
            "source_sha256": source_hash,
            "manifest_sha256": config.security_transfer_manifest_sha256,
            "sse_source_sha256": official_hashes[config.security_transfer_sse_raw_filename],
            "neeq_source_sha256": official_hashes[config.security_transfer_neeq_raw_filename],
            "event_source": (
                f"{config.security_transfer_manifest_filename};"
                f"sse_sha256={official_hashes[config.security_transfer_sse_raw_filename]};"
                f"neeq_sha256={official_hashes[config.security_transfer_neeq_raw_filename]};"
                f"market_sha256={source_hash}"
            ),
            "mark_used_in_nav": recomputed_vwap,
            "executed_vwap": recomputed_vwap,
            "executed_market_volume": volume_shares,
            "rule_label": "pending_transfer_successor_real_vwap_exit",
            "unexplained_stale_residual": False,
            "blocking": False,
            "settlement_holding_error": mapping_error,
            "settlement_cash_error": cash_error,
            "settlement_return_error": 0.0,
        }
    ]
    return trade, audit, total_cost


def _find_unexplained_zero_target_codes(
    state: _PortfolioState,
    status_index: pd.DataFrame,
    *,
    lifecycle_exempt_codes: set[str],
    config: AllAStyleBoxConfig,
) -> list[str]:
    """向量化扫描全部持仓，识别连续两次零目标且恢复可卖的残仓。"""
    if state.shares.empty:
        return []
    held_codes = state.shares.index
    target_weights = pd.to_numeric(
        state.current_target_weights.reindex(held_codes), errors="coerce"
    ).fillna(0.0)
    zero_rebalances = pd.to_numeric(
        state.zero_target_rebalances.reindex(held_codes), errors="coerce"
    ).fillna(0)
    candidates = held_codes[
        target_weights.le(config.weight_tolerance)
        & zero_rebalances.ge(config.maximum_zero_target_rebalances)
    ].difference(pd.Index(lifecycle_exempt_codes))
    if candidates.empty or status_index.empty:
        return []
    status = status_index.reindex(candidates)
    can_sell = status.get(
        "daily_can_sell", pd.Series(False, index=status.index, dtype=bool)
    ).fillna(False).astype(bool)
    active_suspension = status.get(
        "active_suspension", pd.Series(False, index=status.index, dtype=bool)
    ).fillna(False).astype(bool)
    return status.index[can_sell & ~active_suspension].astype(str).tolist()


def _execute_zero_target_residual_exit(
    state: _PortfolioState,
    *,
    portfolio: str,
    date: pd.Timestamp,
    status_index: pd.DataFrame,
    codes: Sequence[str],
    config: AllAStyleBoxConfig,
) -> tuple[pd.DataFrame, list[dict[str, object]], float]:
    """连续两次零目标残仓恢复可卖时，以当日真实VWAP立即退出。"""
    trade_records: list[dict[str, object]] = []
    audit_records: list[dict[str, object]] = []
    total_cost = 0.0
    for code in codes:
        if code not in state.shares.index or code not in status_index.index:
            continue
        row = status_index.loc[code]
        price = float(pd.to_numeric(row.get("daily_vwap", np.nan), errors="coerce"))
        volume = float(pd.to_numeric(row.get("volume", np.nan), errors="coerce"))
        if (
            not bool(row.get("daily_can_sell", False))
            or not bool(row.get("daily_vwap_valid", False))
            or bool(row.get("active_suspension", False))
            or bool(row.get("daily_no_volume", True))
            or not np.isfinite(price)
            or price <= 0
            or not np.isfinite(volume)
            or volume <= 0
        ):
            raise RuntimeError(
                f"连续两次零目标残仓标记可卖但缺可重算VWAP/成交量: {code} {date.date()}"
            )
        shares = float(state.shares.loc[code])
        notional = shares * price
        commission = notional * config.commission_rate
        slippage = notional * config.slippage_rate
        stamp_tax = notional * _stamp_tax_rate(date, config)
        cost = commission + slippage + stamp_tax
        state.net_cash += notional - cost
        state.gross_cash += notional
        state.shares = state.shares.drop(code)
        state.current_target_weights = state.current_target_weights.drop(code, errors="ignore")
        state.zero_target_rebalances = state.zero_target_rebalances.drop(code, errors="ignore")
        total_cost += cost
        trade_records.append(
            {
                "date": date,
                "signal_date": state.active_signal_date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "side": "SELL",
                "shares": shares,
                "vwap": price,
                "gross_notional": notional,
                "commission_cost": commission,
                "slippage_cost": slippage,
                "stamp_tax": stamp_tax,
                "total_cost": cost,
                "net_cash_flow": notional - cost,
                "target_weight": 0.0,
            }
        )
        audit_records.append(
            {
                "date": date,
                "processing_date": date,
                "holding_month": state.active_holding_month,
                "sample_phase": state.active_sample_phase,
                "portfolio": portfolio,
                "stock_code": code,
                "shares": shares,
                "target_weight": 0.0,
                "price_source_date": date,
                "price_age_trading_days": 0,
                "consecutive_missing_price_days": 0,
                "active_suspension": False,
                "delisting_board_flag": False,
                "event_type": "zero_target_residual_forced_exit",
                "announcement_date": pd.NaT,
                "event_effective_date": date,
                "settlement_code": pd.NA,
                "settlement_ratio": 0.0,
                "settlement_cash": price,
                "event_source": "portfolio_zero_target_counter+same_day_daily_status",
                "mark_used_in_nav": price,
                "executed_vwap": price,
                "executed_market_volume": volume,
                "rule_label": "zero_target_two_rebalances_exit_first_sellable_day",
                "unexplained_stale_residual": False,
                "blocking": False,
                "settlement_holding_error": 0.0,
                "settlement_cash_error": 0.0,
                "settlement_return_error": 0.0,
            }
        )
    return pd.DataFrame(trade_records), audit_records, total_cost


def _is_unexplained_missing_price_residual(
    *,
    active_suspension: bool,
    has_auditable_valuation_path: bool,
    price_age_trading_days: int,
    config: AllAStyleBoxConfig,
) -> bool:
    """判定历史点价是否已超过寿命且没有可审计估值路径。

    ``risk_exit`` 只表达退出意图，不会传入
    ``has_auditable_valuation_path=True``。目标权重是否为零也不影响估值
    真实性：仍被策略选中的证券同样不能用超期历史点价生成完整 NAV。
    """
    return bool(
        not has_auditable_valuation_path
        and price_age_trading_days > config.maximum_unexplained_price_age_trading_days
    )


def _has_auditable_valuation_path(
    *,
    active_suspension: bool,
    restriction: pd.Series | None,
    pending_action: pd.Series | None,
    pending_transfer: bool,
    transfer_window_age_trading_days: int,
    price_age_trading_days: int,
    config: AllAStyleBoxConfig,
) -> bool:
    """只承认可限期携带或参数完整的公司行动估值链。

    当日已生效的现金/换股结算由 ``_apply_effective_security_events`` 直接
    处理；尚未到生效条件的 ``pending_action`` 只作候选证据，不能提前作为
    mark。单独风险退出公告没有传入接口，因而不能形成永久豁免。
    """
    bounded_carry = bool(
        (active_suspension or restriction is not None)
        and price_age_trading_days
        <= config.maximum_unexplained_price_age_trading_days
    )
    _ = pending_action
    official_transfer_carry = bool(
        pending_transfer
        and 0 < transfer_window_age_trading_days
        <= config.security_transfer_max_wait_trading_days
    )
    return bounded_carry or official_transfer_carry


def _normalise_valuation_audit(
    records: Sequence[Mapping[str, object]],
    *,
    config: AllAStyleBoxConfig,
) -> pd.DataFrame:
    """把行为与估值候选归一为每个证券日唯一有效估值状态。

    原始候选不丢失：候选来源、规则和退出行为均聚合到选中行。选择只使用
    当日及此前字段，不查找任何未来报价或结算。
    """
    audit = pd.DataFrame(records)
    if audit.empty:
        return audit
    key = ["date", "portfolio", "stock_code"]
    _require_columns(
        audit,
        {
            *key,
            "price_source_date",
            "price_age_trading_days",
            "event_type",
            "event_source",
            "rule_label",
            "blocking",
        },
        "security_event_audit_candidates",
    )
    audit = audit.reset_index(drop=True)
    audit["_candidate_order"] = np.arange(len(audit), dtype=int)
    audit["date"] = pd.to_datetime(audit["date"], errors="coerce").dt.normalize()
    audit["price_source_date"] = pd.to_datetime(
        audit["price_source_date"], errors="coerce"
    ).dt.normalize()
    audit["stock_code"] = audit["stock_code"].astype(str)
    audit["_price_age"] = pd.to_numeric(
        audit["price_age_trading_days"], errors="coerce"
    ).fillna(0).astype(int)
    executed = pd.to_numeric(
        audit.get("executed_vwap", pd.Series(np.nan, index=audit.index)),
        errors="coerce",
    )
    mark_used = pd.to_numeric(
        audit.get("mark_used_in_nav", pd.Series(np.nan, index=audit.index)),
        errors="coerce",
    )
    settlement_cash = pd.to_numeric(
        audit.get("settlement_cash", pd.Series(0.0, index=audit.index)),
        errors="coerce",
    ).fillna(0.0)
    rule = audit["rule_label"].astype(str)
    event_type = audit["event_type"].astype(str)
    explicit_settlement = rule.eq("explicit_cash_or_share_settlement")
    cash_initialisation = rule.eq("formal_oos_cash_initialization")
    transfer_window_age = pd.to_numeric(
        audit.get(
            "transfer_window_age_trading_days",
            pd.Series(0, index=audit.index),
        ),
        errors="coerce",
    ).fillna(0)
    pending_transfer = (
        rule.eq("pending_transfer_bounded_45_trading_days")
        & mark_used.gt(0)
        & audit["price_source_date"].le(audit["date"])
        & transfer_window_age.between(
            1, config.security_transfer_max_wait_trading_days
        )
    )
    same_day_market = executed.gt(0) | (
        mark_used.gt(0) & audit["price_source_date"].eq(audit["date"])
    )
    unpriced = audit["blocking"].fillna(False).astype(bool) | audit.get(
        "unexplained_stale_residual", pd.Series(False, index=audit.index)
    ).fillna(False).astype(bool)
    behavior_only = rule.eq("risk_exit_waiting_daily_can_sell") & ~same_day_market
    bounded_carry = (
        mark_used.gt(0)
        & audit["price_source_date"].le(audit["date"])
        & audit["_price_age"].le(config.maximum_unexplained_price_age_trading_days)
        & ~unpriced
    )

    audit["valuation_source_priority"] = np.select(
        [
            same_day_market | cash_initialisation,
            explicit_settlement,
            pending_transfer,
            bounded_carry,
            unpriced,
            behavior_only,
        ],
        [
            config.valuation_priority_observable_market,
            config.valuation_priority_explicit_settlement,
            config.valuation_priority_transfer_pending,
            config.valuation_priority_bounded_carry,
            config.valuation_priority_unpriced_asset,
            config.valuation_priority_behavior_evidence,
        ],
        default=config.valuation_priority_unpriced_asset,
    ).astype(int)
    audit["valuation_status"] = np.select(
        [
            cash_initialisation,
            same_day_market,
            explicit_settlement,
            pending_transfer,
            bounded_carry,
            unpriced | behavior_only,
        ],
        [
            "cash_initialization",
            "observable_market_mark",
            "explicit_settlement",
            "pending_transfer",
            "bounded_historical_carry",
            "unpriced_asset",
        ],
        default="unpriced_asset",
    )
    audit["valuation_mark"] = mark_used.combine_first(executed)
    cash_mark = settlement_cash.where(settlement_cash.gt(0))
    audit.loc[explicit_settlement, "valuation_mark"] = audit.loc[
        explicit_settlement, "valuation_mark"
    ].combine_first(cash_mark.loc[explicit_settlement])
    audit.loc[cash_initialisation, "valuation_mark"] = audit.loc[
        cash_initialisation, "valuation_mark"
    ].combine_first(cash_mark.loc[cash_initialisation])
    audit["mark_used_in_nav"] = mark_used.combine_first(audit["valuation_mark"])
    audit["valuation_selection_reason"] = np.select(
        [
            cash_initialisation,
            same_day_market,
            explicit_settlement,
            pending_transfer,
            bounded_carry,
        ],
        [
            "formal_oos_boundary_cash",
            "same_day_observable_market_preferred",
            "parameter_complete_effective_settlement",
            "official_transfer_window_before_mapping_public_date",
            "historical_mark_within_configured_lifetime",
        ],
        default="no_auditable_valuation_path_unpriced",
    )
    audit["has_auditable_valuation_path"] = ~audit["valuation_status"].eq(
        "unpriced_asset"
    )
    behavior_mask = rule.str.contains("risk_exit|zero_target", case=False, regex=True)
    audit["_behavior_action"] = np.where(
        behavior_mask, rule + ":" + event_type, ""
    )
    audit["_candidate_source"] = (
        audit["valuation_status"].astype(str)
        + "|"
        + rule
        + "|"
        + audit["event_source"].astype(str)
    )

    candidate_count = audit.groupby(key, sort=False)["_candidate_order"].transform("size")
    candidate_sources = audit.groupby(key, sort=False)["_candidate_source"].transform(
        lambda values: ";".join(dict.fromkeys(values.astype(str)))
    )
    behavior_actions = audit.groupby(key, sort=False)["_behavior_action"].transform(
        lambda values: ";".join(value for value in dict.fromkeys(values.astype(str)) if value)
    )
    any_blocking = audit.groupby(key, sort=False)["blocking"].transform(
        lambda values: bool(pd.Series(values).fillna(False).any())
    )
    any_stale = audit.groupby(key, sort=False)["unexplained_stale_residual"].transform(
        lambda values: bool(pd.Series(values).fillna(False).any())
    )
    audit["valuation_candidate_count"] = candidate_count.astype(int)
    audit["valuation_candidate_sources"] = candidate_sources
    audit["behavior_actions"] = behavior_actions
    audit["valuation_conflict_resolved"] = candidate_count.gt(1)
    audit["blocking"] = any_blocking
    audit["unexplained_stale_residual"] = any_stale
    selected = audit.sort_values(
        [*key, "valuation_source_priority", "_candidate_order"], kind="mergesort"
    ).drop_duplicates(key, keep="first")
    selected["selected_for_valuation"] = True
    comparable_mark = selected["valuation_mark"].notna() & selected[
        "mark_used_in_nav"
    ].notna()
    selected["mark_reconciliation_error"] = 0.0
    selected.loc[comparable_mark, "mark_reconciliation_error"] = (
        selected.loc[comparable_mark, "valuation_mark"]
        - selected.loc[comparable_mark, "mark_used_in_nav"]
    ).abs()
    selected = selected.drop(
        columns=[
            "_candidate_order",
            "_price_age",
            "_behavior_action",
            "_candidate_source",
        ]
    ).sort_values(key, kind="mergesort")
    if selected.duplicated(key).any() or not selected["selected_for_valuation"].all():
        raise AssertionError("生命周期估值状态未归一为每键唯一选择")
    return selected.reset_index(drop=True)


def _mark_terminal_event(
    state: _PortfolioState,
    terminal_status: pd.DataFrame,
    terminal_date: pd.Timestamp,
) -> tuple[float, float]:
    status = terminal_status.copy()
    status["stock_code"] = status["stock_code"].astype(str).str.zfill(6)
    status = status.drop_duplicates("stock_code", keep="last").set_index("stock_code")
    prices = _finite_numeric(status["return_vwap"]).where(
        status["return_vwap_valid"].fillna(False)
    )
    marks = prices.combine_first(state.last_prices)
    position_value = _position_value(state.shares, marks)
    valid = prices.dropna()
    if not valid.empty:
        state.last_prices.loc[valid.index] = valid
        state.last_price_dates.loc[valid.index] = terminal_date
    return state.net_cash + position_value, state.gross_cash + position_value


def _monthly_record(
    *,
    portfolio: str,
    start_event: dict[str, object],
    end_date: pd.Timestamp,
    end_net_nav: float,
    end_gross_nav: float,
) -> dict[str, object]:
    start_net = float(start_event["start_net_nav"])
    start_gross = float(start_event["start_gross_nav"])
    post_close_net = float(start_event["ledger_posttrade_close_net_nav"])
    post_close_gross = float(start_event["ledger_posttrade_close_gross_nav"])
    last_close_net = float(start_event["ledger_month_last_close_net_nav"])
    last_close_gross = float(start_event["ledger_month_last_close_gross_nav"])
    net_first_bridge = post_close_net / start_net - 1.0
    gross_first_bridge = post_close_gross / start_gross - 1.0
    net_intramonth_chain = last_close_net / post_close_net - 1.0
    gross_intramonth_chain = last_close_gross / post_close_gross - 1.0
    net_tail_bridge = end_net_nav / last_close_net - 1.0
    gross_tail_bridge = end_gross_nav / last_close_gross - 1.0
    net_reconciled = (
        (1.0 + net_first_bridge)
        * (1.0 + net_intramonth_chain)
        * (1.0 + net_tail_bridge)
        - 1.0
    )
    gross_reconciled = (
        (1.0 + gross_first_bridge)
        * (1.0 + gross_intramonth_chain)
        * (1.0 + gross_tail_bridge)
        - 1.0
    )
    direct_net = end_net_nav / start_net - 1.0
    direct_gross = end_gross_nav / start_gross - 1.0
    return {
        "holding_month": start_event["holding_month"],
        "sample_phase": start_event["sample_phase"],
        "portfolio": portfolio,
        "start_date": start_event["start_date"],
        "end_date": end_date,
        "start_net_nav": start_net,
        "end_net_nav": end_net_nav,
        "net_nav": end_net_nav,
        "net_return": net_reconciled,
        "start_gross_nav": start_gross,
        "end_gross_nav": end_gross_nav,
        "gross_nav": end_gross_nav,
        "gross_return": gross_reconciled,
        "ledger_start_pretrade_vwap_net_nav": start_net,
        "ledger_posttrade_close_net_nav": post_close_net,
        "ledger_month_last_close_net_nav": last_close_net,
        "ledger_next_pretrade_vwap_net_nav": end_net_nav,
        "ledger_start_pretrade_vwap_gross_nav": start_gross,
        "ledger_posttrade_close_gross_nav": post_close_gross,
        "ledger_month_last_close_gross_nav": last_close_gross,
        "ledger_next_pretrade_vwap_gross_nav": end_gross_nav,
        "ledger_net_first_bridge_return": net_first_bridge,
        "ledger_net_intramonth_chain_return": net_intramonth_chain,
        "ledger_net_tail_bridge_return": net_tail_bridge,
        "ledger_gross_first_bridge_return": gross_first_bridge,
        "ledger_gross_intramonth_chain_return": gross_intramonth_chain,
        "ledger_gross_tail_bridge_return": gross_tail_bridge,
        "ledger_net_reconciliation_error": net_reconciled - direct_net,
        "ledger_gross_reconciliation_error": gross_reconciled - direct_gross,
        "ledger_rebalance_cost": start_event["ledger_rebalance_cost"],
        "ledger_event_cost": start_event["ledger_event_cost"],
        "ledger_cost_attribution": (
            "rebalance_cost_in_first_bridge;event_cost_on_observation_date_in_intramonth_or_tail"
        ),
        "ledger_bridge_definition": (
            "posttrade_close/start_pretrade_vwap * month_last_close/posttrade_close "
            "* next_pretrade_vwap/month_last_close"
        ),
        "buy_notional": start_event["buy_notional"],
        "sell_notional": start_event["sell_notional"],
        "gross_traded_notional": start_event["gross_traded_notional"],
        "two_sided_turnover": start_event["two_sided_turnover"],
        "one_way_turnover": start_event["one_way_turnover"],
        "commission_cost": start_event["commission_cost"],
        "slippage_cost": start_event["slippage_cost"],
        "stamp_tax": start_event["stamp_tax"],
        "total_cost": start_event["total_cost"],
    }


def _build_monthly_target_reference(
    targets: pd.DataFrame,
    panel: pd.DataFrame,
    schedule: pd.DataFrame,
    daily_prices: pd.DataFrame,
    events: pd.DataFrame,
    config: AllAStyleBoxConfig,
) -> pd.DataFrame:
    """由冻结目标权重构造独立月度参考收益，不读取实际持仓或实际毛收益。"""
    security = targets[
        [
            "signal_date",
            "execution_date",
            "holding_month",
            "sample_phase",
            "stock_code",
        ]
    ].drop_duplicates(["signal_date", "stock_code"]).copy()
    security = security.merge(
        schedule[["signal_date", "return_date"]].drop_duplicates("signal_date"),
        on="signal_date",
        how="left",
        validate="many_to_one",
    ).merge(
        panel[
            [
                "signal_date",
                "stock_code",
                "execution_vwap",
                "execution_vwap_valid",
                "return_vwap",
                "return_vwap_valid",
            ]
        ],
        on=["signal_date", "stock_code"],
        how="left",
        validate="one_to_one",
    )
    security["_reference_row"] = np.arange(len(security), dtype=np.int64)
    execution_price = _finite_numeric(security["execution_vwap"]).where(
        security["execution_vwap_valid"].fillna(False)
    )
    return_price = _finite_numeric(security["return_vwap"]).where(
        security["return_vwap_valid"].fillna(False)
    )

    valid_close = daily_prices.loc[
        _finite_numeric(daily_prices["close"]).gt(0),
        ["stock_code", "date", "close"],
    ].copy()
    valid_close["close"] = _finite_numeric(valid_close["close"])
    valid_close = valid_close.sort_values(
        ["date", "stock_code"], kind="mergesort"
    ).drop_duplicates(["date", "stock_code"], keep="last")
    close_query = security[
        ["_reference_row", "stock_code", "execution_date", "return_date"]
    ].sort_values(["return_date", "stock_code"], kind="mergesort")
    if valid_close.empty:
        last_close = close_query.assign(last_close_date=pd.NaT, last_close=np.nan)
    else:
        last_close = pd.merge_asof(
            close_query,
            valid_close.rename(columns={"date": "last_close_date", "close": "last_close"})
            .sort_values(["last_close_date", "stock_code"], kind="mergesort"),
            left_on="return_date",
            right_on="last_close_date",
            by="stock_code",
            direction="backward",
            allow_exact_matches=True,
        )
    last_close = last_close.set_index("_reference_row").reindex(security["_reference_row"])
    historical_close = _finite_numeric(last_close["last_close"]).where(
        pd.to_datetime(last_close["last_close_date"], errors="coerce")
        .ge(pd.to_datetime(last_close["execution_date"], errors="coerce"))
    )
    endpoint_price = return_price.combine_first(historical_close).combine_first(execution_price)
    endpoint_source = pd.Series("execution_vwap_carry", index=security.index, dtype="string")
    endpoint_source = endpoint_source.mask(historical_close.notna(), "historical_close_at_or_before_end")
    endpoint_source = endpoint_source.mask(return_price.notna(), "return_vwap")

    # 现金/换股只在公告已知且生效日落入持有区间时覆盖估值；公告本身绝不当作成交价。
    settlement_events = events.loc[
        events["settlement_cash"].gt(0)
        | (events["settlement_code"].notna() & events["settlement_ratio"].gt(0))
    ].copy()
    if not settlement_events.empty:
        eligible_events = security[
            [
                "_reference_row",
                "stock_code",
                "execution_date",
                "return_date",
            ]
        ].merge(settlement_events, on="stock_code", how="inner")
        eligible_events = eligible_events.loc[
            eligible_events["announcement_date"].le(eligible_events["event_effective_date"])
            & eligible_events["event_effective_date"].ge(eligible_events["execution_date"])
            & eligible_events["event_effective_date"].le(eligible_events["return_date"])
        ].sort_values(
            ["_reference_row", "event_effective_date", "event_type"], kind="mergesort"
        ).drop_duplicates("_reference_row", keep="last")
        cash_events = eligible_events.loc[eligible_events["settlement_cash"].gt(0)]
        if not cash_events.empty:
            rows = cash_events["_reference_row"].astype(int).to_numpy()
            valid_start = execution_price.iloc[rows].notna().to_numpy()
            valid_rows = rows[valid_start]
            endpoint_price.iloc[valid_rows] = _finite_numeric(
                cash_events.loc[valid_start, "settlement_cash"]
            ).to_numpy()
            endpoint_source.iloc[valid_rows] = "explicit_cash_settlement"

        share_events = eligible_events.loc[
            eligible_events["settlement_code"].notna()
            & eligible_events["settlement_ratio"].gt(0)
        ].copy()
        if not share_events.empty and not valid_close.empty:
            successor_query = share_events[
                [
                    "_reference_row",
                    "settlement_code",
                    "event_effective_date",
                    "return_date",
                    "settlement_ratio",
                ]
            ].rename(columns={"settlement_code": "stock_code"}).sort_values(
                ["return_date", "stock_code"], kind="mergesort"
            )
            successor_marks = pd.merge_asof(
                successor_query,
                valid_close.rename(
                    columns={"date": "successor_mark_date", "close": "successor_mark"}
                ).sort_values(["successor_mark_date", "stock_code"], kind="mergesort"),
                left_on="return_date",
                right_on="successor_mark_date",
                by="stock_code",
                direction="backward",
                allow_exact_matches=True,
            )
            successor_marks["equivalent_price"] = (
                _finite_numeric(successor_marks["successor_mark"])
                * _finite_numeric(successor_marks["settlement_ratio"])
            ).where(
                pd.to_datetime(successor_marks["successor_mark_date"], errors="coerce")
                .ge(pd.to_datetime(successor_marks["event_effective_date"], errors="coerce"))
            )
            successor_marks = successor_marks.loc[successor_marks["equivalent_price"].gt(0)]
            if not successor_marks.empty:
                rows = successor_marks["_reference_row"].astype(int).to_numpy()
                valid_start = execution_price.iloc[rows].notna().to_numpy()
                valid_rows = rows[valid_start]
                endpoint_price.iloc[valid_rows] = successor_marks.loc[
                    valid_start, "equivalent_price"
                ].to_numpy()
                endpoint_source.iloc[valid_rows] = "explicit_share_settlement_successor_mark"

    security["target_reference_security_return"] = (
        endpoint_price / execution_price - 1.0
    ).where(execution_price.notna(), 0.0)
    security["target_reference_mark_source"] = endpoint_source.where(
        execution_price.notna(), "cash_unexecuted_at_t_plus_1"
    )
    if not np.isfinite(security["target_reference_security_return"]).all():
        failed = security.loc[
            ~np.isfinite(security["target_reference_security_return"]),
            ["signal_date", "stock_code", "execution_date", "return_date"],
        ]
        raise AssertionError(
            "独立月度目标参考仍含不可估值证券: "
            f"{failed.head(10).to_dict('records')}"
        )
    if (
        pd.to_datetime(last_close["last_close_date"], errors="coerce")
        .gt(pd.to_datetime(last_close["return_date"], errors="coerce"))
        .any()
    ):
        raise AssertionError("目标参考估值引用了收益端点之后的价格")

    reference_input = targets.merge(
        security[
            [
                "signal_date",
                "stock_code",
                "target_reference_security_return",
                "target_reference_mark_source",
            ]
        ],
        on=["signal_date", "stock_code"],
        how="left",
        validate="many_to_one",
    )
    reference_input["weighted_reference_return"] = (
        reference_input["target_weight"]
        * reference_input["target_reference_security_return"]
    )
    reference_input["target_reference_unresolved"] = ~np.isfinite(
        reference_input["target_reference_security_return"]
    )
    reference = reference_input.groupby(
        ["holding_month", "sample_phase", "portfolio"],
        as_index=False,
        sort=False,
    ).agg(
        target_reference_return=("weighted_reference_return", "sum"),
        target_reference_missing_count=("target_reference_unresolved", "sum"),
        target_reference_cash_start_count=(
            "target_reference_mark_source",
            lambda values: int(values.eq("cash_unexecuted_at_t_plus_1").sum()),
        ),
        target_reference_stale_mark_count=(
            "target_reference_mark_source",
            lambda values: int(
                values.isin(
                    ("historical_close_at_or_before_end", "execution_vwap_carry")
                ).sum()
            ),
        ),
        target_reference_company_action_count=(
            "target_reference_mark_source",
            lambda values: int(values.str.startswith("explicit_").sum()),
        ),
    )
    if reference["target_reference_missing_count"].ne(0).any() or not np.isfinite(
        reference["target_reference_return"]
    ).all():
        raise AssertionError("月度目标参考权重链未完整闭环")
    return reference


def run_china_market_backtest(
    m1: M1Dataset,
    m2: M2Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    daily_prices: pd.DataFrame | None = None,
    trading_dates: pd.DatetimeIndex | None = None,
    security_events: pd.DataFrame | None = None,
) -> M3Dataset:
    """B7/SA3：运行冻结式前推的中国市场有状态组合回测。

    本函数不训练、不调参、不写 ``output/``。传入 ``daily_prices`` 与
    ``trading_dates`` 可运行合成 fixture；正式调用默认只读本地前复权日行情。
    月收益按相邻执行 VWAP 估值事件结算，日收益按每日收盘记账；两者均保留毛
    收益、净收益和净值。由于执行日 VWAP 与当日收盘是两个时点，月度 VWAP
    序列是正式持有期口径，不能用收盘日收益简单替代。
    """
    targets = build_portfolio_targets(m1, m2, config)
    schedule = _normalise_dates(
        m1.schedule,
        ("signal_date", "execution_date", "return_date"),
    ).sort_values("execution_date", kind="mergesort")
    panel = _normalise_dates(
        m1.monthly_panel,
        ("signal_date", "execution_date", "return_date"),
    )
    _require_columns(
        schedule,
        {
            "signal_date", "execution_date", "return_date", "holding_month",
            "sample_phase",
        },
        "m1.schedule",
    )
    execution_columns = {
        "signal_date", "stock_code", "execution_vwap", "execution_vwap_valid",
        "signal_close",
        "execution_is_suspended", "execution_no_volume", "execution_is_limit_up",
        "execution_is_limit_down", "can_buy_t1", "can_sell_t1", "return_vwap",
        "return_vwap_valid", "delisting_board_flag",
    }
    _require_columns(panel, execution_columns, "m1.monthly_panel")
    panel["stock_code"] = panel["stock_code"].astype(str).str.zfill(6)
    if daily_prices is None or trading_dates is None:
        loaded_prices, loaded_dates = load_daily_mark_prices(targets, schedule, config)
        if daily_prices is None:
            daily_prices = loaded_prices
        if trading_dates is None:
            trading_dates = loaded_dates
    daily_prices = _normalise_dates(daily_prices, ("date",))
    _require_columns(daily_prices, {"date", "stock_code", "close"}, "daily_prices")
    daily_prices["stock_code"] = daily_prices["stock_code"].astype(str).str.zfill(6)
    daily_prices["close"] = _finite_numeric(daily_prices["close"])
    optional_status_defaults: dict[str, object] = {
        "active_suspension": False,
        "delisting_board_flag": False,
        "daily_can_sell": False,
        "daily_vwap": np.nan,
        "daily_vwap_valid": False,
        "daily_no_volume": True,
    }
    for column, default in optional_status_defaults.items():
        if column not in daily_prices:
            daily_prices[column] = default
    daily_prices["daily_vwap"] = _finite_numeric(daily_prices["daily_vwap"])
    daily_status_by_date = {
        pd.Timestamp(date): group.drop_duplicates("stock_code", keep="last")
        for date, group in daily_prices.groupby("date", sort=False)
    }
    mark_prices = daily_prices.loc[daily_prices["close"].gt(0)].drop_duplicates(
        ["date", "stock_code"], keep="last"
    )
    price_by_date = {
        pd.Timestamp(date): group.set_index("stock_code")["close"]
        for date, group in mark_prices.groupby("date", sort=False)
    }
    configured_events = pd.DataFrame(
        [
            {
                "stock_code": stock_code,
                "event_type": "announced_security_lifecycle_risk_exit",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": action,
                "event_source": source,
            }
            for stock_code, announcement_date, effective_date, action, source
            in config.security_risk_exit_events
        ]
    )
    configured_warning_exits = pd.DataFrame(
        [
            {
                "stock_code": stock_code,
                "event_type": "delisting_risk_warning_exit",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": action,
                "event_source": source,
            }
            for stock_code, announcement_date, effective_date, action, source
            in config.security_delisting_risk_warning_exit_events
        ]
    )
    configured_restrictions = pd.DataFrame(
        [
            {
                "stock_code": stock_code,
                "event_type": "announced_holding_restriction",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": "holding_restriction",
                "event_source": source,
            }
            for stock_code, announcement_date, effective_date, source
            in config.security_holding_restriction_events
        ]
    )
    configured_cash_settlements = pd.DataFrame(
        [
            {
                "stock_code": stock_code,
                "event_type": "cash_choice_exercised_by_portfolio_policy",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": "cash_settlement",
                "settlement_cash": settlement_cash,
                "event_source": source,
            }
            for stock_code, announcement_date, effective_date, settlement_cash, source
            in config.security_cash_settlement_events
        ]
    )
    configured_share_settlements = pd.DataFrame(
        [
            {
                "stock_code": stock_code,
                "event_type": "stock_for_stock_merger_settlement",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": "share_settlement",
                "settlement_code": settlement_code,
                "settlement_ratio": settlement_ratio,
                "event_source": source,
            }
            for (
                stock_code,
                announcement_date,
                effective_date,
                settlement_code,
                settlement_ratio,
                source,
            ) in config.security_share_settlement_events
        ]
    )
    configured_successor_exits = pd.DataFrame(
        [
            {
                "stock_code": settlement_code,
                "event_type": "merger_successor_target_zero_exit",
                "announcement_date": announcement_date,
                "event_effective_date": effective_date,
                "action": "target_zero_exit_on_next_trade",
                "event_source": source,
            }
            for (
                _,
                announcement_date,
                effective_date,
                settlement_code,
                _,
                source,
            ) in config.security_share_settlement_events
        ]
    )
    supplied_events = security_events if security_events is not None else pd.DataFrame()
    events = _normalise_security_events(
        pd.concat(
            [
                configured_events,
                configured_warning_exits,
                configured_restrictions,
                configured_cash_settlements,
                configured_share_settlements,
                configured_successor_exits,
                supplied_events,
            ],
            ignore_index=True,
            sort=False,
        )
    )
    trading_dates = pd.DatetimeIndex(pd.to_datetime(trading_dates)).normalize().sort_values().unique()

    event_rows = schedule.to_dict("records")
    if not event_rows:
        raise ValueError("m1.schedule 为空，无法回测")
    event_by_date = {pd.Timestamp(row["execution_date"]): row for row in event_rows}
    terminal_date = pd.Timestamp(schedule.iloc[-1]["return_date"])
    if pd.isna(terminal_date):
        raise ValueError("最后持有月缺少 return_date，不能形成完整月收益")
    start_date = pd.Timestamp(schedule.iloc[0]["execution_date"])
    dates = trading_dates[(trading_dates >= start_date) & (trading_dates <= terminal_date)]
    if start_date not in dates or terminal_date not in dates:
        raise AssertionError("日频交易日历未覆盖首个执行日或最终收益端点")

    states = {portfolio: _initial_state(config) for portfolio in LONG_PORTFOLIOS}
    open_month: dict[str, dict[str, object]] = {}
    daily_records: list[dict[str, object]] = []
    monthly_records: list[dict[str, object]] = []
    trade_frames: list[pd.DataFrame] = []
    unfilled_frames: list[pd.DataFrame] = []
    actual_frames: list[pd.DataFrame] = []
    holding_frames: list[pd.DataFrame] = []
    turnover_records: list[dict[str, object]] = []
    cost_records: list[dict[str, object]] = []
    coverage_records: list[dict[str, object]] = []
    security_event_records: list[dict[str, object]] = []
    trading_day_position = {pd.Timestamp(day): idx for idx, day in enumerate(dates)}
    formal_initialised = False

    for date in dates:
        processing_date = pd.Timestamp(date)
        observed = price_by_date.get(processing_date, pd.Series(dtype=float))
        daily_status = daily_status_by_date.get(processing_date, pd.DataFrame())
        event = event_by_date.get(processing_date)

        # 在当日调仓之前先处理已生效的明示公司行动与退市整理风险退出，
        # 使上一持有月的终值包含该当日可知事件。
        for portfolio in LONG_PORTFOLIOS:
            state = states[portfolio]
            if state.active_holding_month is None:
                continue
            security_event_records.extend(
                _apply_effective_security_events(
                    state,
                    portfolio=portfolio,
                    date=processing_date,
                    events=events,
                    observed=observed,
                    config=config,
                )
            )
            transfer_trades, transfer_audit, transfer_cost = (
                _execute_security_transfer_exit(
                    state,
                    portfolio=portfolio,
                    date=processing_date,
                    daily_status=daily_status,
                    trading_day_position=trading_day_position,
                    config=config,
                )
            )
            security_event_records.extend(transfer_audit)
            if not transfer_trades.empty:
                trade_frames.append(transfer_trades)
                notional = float(transfer_trades["gross_notional"].sum())
                commission = float(transfer_trades["commission_cost"].sum())
                slippage = float(transfer_trades["slippage_cost"].sum())
                stamp_tax = float(transfer_trades["stamp_tax"].sum())
                turnover_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "buy_notional": 0.0,
                        "sell_notional": notional,
                        "gross_traded_notional": notional,
                        "two_sided_turnover": np.nan,
                        "one_way_turnover": np.nan,
                        "event_driven": True,
                    }
                )
                cost_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "commission_cost": commission,
                        "slippage_cost": slippage,
                        "stamp_tax": stamp_tax,
                        "total_cost": transfer_cost,
                        "cost_rate_on_pretrade_nav": np.nan,
                        "stamp_tax_rate": _stamp_tax_rate(processing_date, config),
                        "event_driven": True,
                    }
                )
                if portfolio in open_month:
                    open_month[portfolio]["sell_notional"] += notional
                    open_month[portfolio]["gross_traded_notional"] += notional
                    open_month[portfolio]["commission_cost"] += commission
                    open_month[portfolio]["slippage_cost"] += slippage
                    open_month[portfolio]["stamp_tax"] += stamp_tax
                    open_month[portfolio]["total_cost"] += transfer_cost
                    open_month[portfolio]["ledger_event_cost"] += transfer_cost
            risk_trades, risk_audit, risk_cost = _execute_delisting_risk_exit(
                state,
                portfolio=portfolio,
                date=processing_date,
                daily_status=daily_status,
                events=events,
                config=config,
            )
            security_event_records.extend(risk_audit)
            if not risk_trades.empty:
                trade_frames.append(risk_trades)
                notional = float(risk_trades["gross_notional"].sum())
                commission = float(risk_trades["commission_cost"].sum())
                slippage = float(risk_trades["slippage_cost"].sum())
                stamp_tax = float(risk_trades["stamp_tax"].sum())
                turnover_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "buy_notional": 0.0,
                        "sell_notional": notional,
                        "gross_traded_notional": notional,
                        "two_sided_turnover": np.nan,
                        "one_way_turnover": np.nan,
                        "event_driven": True,
                    }
                )
                cost_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "commission_cost": commission,
                        "slippage_cost": slippage,
                        "stamp_tax": stamp_tax,
                        "total_cost": risk_cost,
                        "cost_rate_on_pretrade_nav": np.nan,
                        "stamp_tax_rate": _stamp_tax_rate(processing_date, config),
                        "event_driven": True,
                    }
                )
                if portfolio in open_month:
                    open_month[portfolio]["sell_notional"] += notional
                    open_month[portfolio]["gross_traded_notional"] += notional
                    open_month[portfolio]["commission_cost"] += commission
                    open_month[portfolio]["slippage_cost"] += slippage
                    open_month[portfolio]["stamp_tax"] += stamp_tax
                    open_month[portfolio]["total_cost"] += risk_cost
                    open_month[portfolio]["ledger_event_cost"] += risk_cost
        if event is not None:
            signal_date = pd.Timestamp(event["signal_date"])
            event_status = panel.loc[
                panel["signal_date"].eq(signal_date), list(execution_columns)
            ].copy()
            active_risk_codes = set(
                events.loc[
                    events["action"].isin(
                        ("risk_exit_on_next_trade", "holding_restriction")
                    )
                    & events["announcement_date"].le(processing_date)
                    & events["event_effective_date"].le(processing_date),
                    "stock_code",
                ]
            )
            if active_risk_codes:
                event_status.loc[
                    event_status["stock_code"].isin(active_risk_codes),
                    "delisting_board_flag",
                ] = True
            for portfolio in LONG_PORTFOLIOS:
                state = states[portfolio]
                # 先按本次执行 VWAP 结算上一持有月，再改变仓位。
                status_index = event_status.set_index("stock_code")
                event_vwap = _finite_numeric(status_index["execution_vwap"]).where(
                    status_index["execution_vwap_valid"].fillna(False)
                )
                pretrade_marks = event_vwap.combine_first(state.last_prices)
                pretrade_position = _position_value(state.shares, pretrade_marks)
                pretrade_net = state.net_cash + pretrade_position
                pretrade_gross = state.gross_cash + pretrade_position
                if portfolio in open_month:
                    previous_month = open_month[portfolio]
                    monthly_records.append(
                        _monthly_record(
                            portfolio=portfolio,
                            start_event=previous_month,
                            end_date=pd.Timestamp(date),
                            end_net_nav=pretrade_net,
                            end_gross_nav=pretrade_gross,
                        )
                    )
                    daily_records.append(
                        {
                            "date": processing_date,
                            "holding_month": previous_month["holding_month"],
                            "sample_phase": previous_month["sample_phase"],
                            "portfolio": portfolio,
                            "valuation_phase": "next_execution_pretrade_vwap_tail_bridge",
                            "ledger_component": "tail_bridge",
                            "gross_nav": pretrade_gross,
                            "net_nav": pretrade_net,
                            "gross_return": (
                                pretrade_gross / state.previous_daily_gross_nav - 1.0
                            ),
                            "net_return": (
                                pretrade_net / state.previous_daily_net_nav - 1.0
                            ),
                            "gross_cash": state.gross_cash,
                            "net_cash": state.net_cash,
                            "stock_market_value": pretrade_net - state.net_cash,
                            "cash_weight": state.net_cash / pretrade_net,
                        }
                    )
                    state.previous_daily_net_nav = pretrade_net
                    state.previous_daily_gross_nav = pretrade_gross
                if str(event["sample_phase"]) == "formal_oos" and (
                    state.active_sample_phase != "formal_oos"
                ):
                    # 历史段只用于方法冻结/诊断；正式OOS不携带股票、现金、
                    # 净值或累计成本，各组合在首个正式执行日从NAV=1现金开始。
                    states[portfolio] = _initial_state(config)
                    state = states[portfolio]
                    open_month.pop(portfolio, None)
                    security_event_records.append(
                        {
                            "date": processing_date,
                            "processing_date": processing_date,
                            "holding_month": event["holding_month"],
                            "sample_phase": "formal_oos",
                            "portfolio": portfolio,
                            "stock_code": CASH_CODE,
                            "shares": 0.0,
                            "target_weight": 0.0,
                            "price_source_date": processing_date,
                            "price_age_trading_days": 0,
                            "consecutive_missing_price_days": 0,
                            "active_suspension": False,
                            "delisting_board_flag": False,
                            "event_type": "formal_oos_cash_initialization",
                            "announcement_date": pd.NaT,
                            "event_effective_date": processing_date,
                            "settlement_code": pd.NA,
                            "settlement_ratio": 0.0,
                            "settlement_cash": config.initial_nav,
                            "event_source": "frozen_oos_boundary",
                            "executed_vwap": np.nan,
                            "executed_market_volume": np.nan,
                            "rule_label": "formal_oos_cash_initialization",
                            "unexplained_stale_residual": False,
                            "blocking": False,
                            "settlement_holding_error": 0.0,
                            "settlement_cash_error": 0.0,
                            "settlement_return_error": 0.0,
                        }
                    )
                    formal_initialised = True
                portfolio_targets = targets.loc[
                    targets["signal_date"].eq(signal_date)
                    & targets["portfolio"].eq(portfolio)
                ]
                result = _execute_rebalance(
                    state=state,
                    portfolio=portfolio,
                    event=event,
                    targets=portfolio_targets,
                    status=event_status,
                    config=config,
                )
                states[portfolio] = result.state
                if not result.trades.empty:
                    trade_frames.append(result.trades)
                if not result.unfilled.empty:
                    unfilled_frames.append(result.unfilled)
                actual_frames.append(result.actual_weights)
                holding_frames.append(result.holdings)
                turnover_records.append(result.turnover)
                cost_records.append(result.costs)
                coverage_records.append(result.coverage)
                open_month[portfolio] = {
                    "holding_month": event["holding_month"],
                    "sample_phase": event["sample_phase"],
                    "start_date": pd.Timestamp(date),
                    "start_net_nav": result.pretrade_net_nav,
                    "start_gross_nav": result.pretrade_gross_nav,
                    "ledger_rebalance_cost": result.costs["total_cost"],
                    "ledger_event_cost": 0.0,
                    **{
                        key: result.turnover[key]
                        for key in (
                            "buy_notional", "sell_notional", "gross_traded_notional",
                            "two_sided_turnover", "one_way_turnover",
                        )
                    },
                    **{
                        key: result.costs[key]
                        for key in (
                            "commission_cost", "slippage_cost", "stamp_tax", "total_cost",
                        )
                    },
                }

        blocking_rows: list[dict[str, object]] = []
        known_restrictions = events.loc[
            events["action"].eq("holding_restriction")
            & events["announcement_date"].le(processing_date)
            & events["event_effective_date"].le(processing_date)
        ].drop_duplicates("stock_code", keep="last").set_index("stock_code")
        pending_company_actions = events.loc[
            events["announcement_date"].le(processing_date)
            & events["event_effective_date"].gt(processing_date)
            & (
                events["settlement_cash"].gt(0)
                | (
                    events["settlement_code"].notna()
                    & events["settlement_ratio"].gt(0)
                )
            )
        ].drop_duplicates("stock_code", keep="last").set_index("stock_code")
        pending_market_exits = events.loc[
            events["action"].isin(
                ("risk_exit_on_next_trade", "target_zero_exit_on_next_trade")
            )
            & events["announcement_date"].le(processing_date)
            & events["event_effective_date"].le(processing_date)
        ].drop_duplicates("stock_code", keep="last").set_index("stock_code")
        # 风险退出公告只触发行为，不是估值来源；不得进入生命周期豁免集合。
        lifecycle_exempt_codes: set[str] = set()
        for portfolio in LONG_PORTFOLIOS:
            state = states[portfolio]
            if state.active_holding_month is None or state.shares.empty:
                continue
            _update_close_marks(state, processing_date, observed)
            status_index = (
                daily_status.drop_duplicates("stock_code", keep="last").set_index("stock_code")
                if not daily_status.empty
                else pd.DataFrame()
            )
            missing_today = state.shares.index.difference(observed.index)
            for code in missing_today:
                source_date = pd.Timestamp(state.last_price_dates.get(code, pd.NaT))
                if pd.isna(source_date):
                    age = config.maximum_unexplained_price_age_trading_days + 1
                else:
                    source_position = trading_day_position.get(
                        source_date,
                        int(dates.searchsorted(source_date, side="left")),
                    )
                    age = trading_day_position[processing_date] - source_position
                if code in status_index.index:
                    row = status_index.loc[code]
                    active_suspension = bool(row.get("active_suspension", False))
                    delisting_flag = bool(row.get("delisting_board_flag", False))
                else:
                    active_suspension = False
                    delisting_flag = False
                restriction = (
                    known_restrictions.loc[code]
                    if code in known_restrictions.index
                    else None
                )
                pending_action = (
                    pending_company_actions.loc[code]
                    if code in pending_company_actions.index
                    else None
                )
                pending_market_exit = (
                    pending_market_exits.loc[code]
                    if code in pending_market_exits.index
                    else None
                )
                pending_transfer, transfer_window_age = _is_pending_security_transfer(
                    code,
                    processing_date,
                    trading_day_position,
                    config,
                )
                transfer_reason = (
                    pd.Series(
                        {
                            "event_type": "security_transfer_pending",
                            "announcement_date": pd.Timestamp(
                                config.security_transfer_source_public_date
                            ),
                            "event_effective_date": pd.Timestamp(
                                config.security_transfer_delisting_date
                            ),
                            "event_source": (
                                f"{config.security_transfer_sse_raw_filename};"
                                "official_45_trading_day_transfer_window;"
                                f"sha256={dict(config.security_transfer_frozen_sha256)[config.security_transfer_sse_raw_filename]}"
                            ),
                        }
                    )
                    if pending_transfer
                    else None
                )
                lifecycle_reason = (
                    transfer_reason
                    if transfer_reason is not None
                    else restriction
                    if restriction is not None
                    else pending_action
                    if pending_action is not None
                    else pending_market_exit
                )
                if restriction is not None:
                    active_suspension = True
                    delisting_flag = True
                if pending_transfer:
                    active_suspension = True
                    delisting_flag = True
                target_weight = float(state.current_target_weights.get(code, 0.0))
                has_auditable_valuation_path = _has_auditable_valuation_path(
                    active_suspension=active_suspension,
                    price_age_trading_days=int(age),
                    restriction=restriction,
                    pending_action=pending_action,
                    pending_transfer=pending_transfer,
                    transfer_window_age_trading_days=transfer_window_age,
                    config=config,
                )
                unexplained = _is_unexplained_missing_price_residual(
                    active_suspension=active_suspension,
                    has_auditable_valuation_path=has_auditable_valuation_path,
                    price_age_trading_days=int(age),
                    config=config,
                )
                record = {
                    "date": processing_date,
                    "processing_date": processing_date,
                    "asof": processing_date,
                    "holding_month": state.active_holding_month,
                    "sample_phase": state.active_sample_phase,
                    "portfolio": portfolio,
                    "stock_code": code,
                    "old_stock_code": (
                        config.security_transfer_old_code if pending_transfer else pd.NA
                    ),
                    # 映射在2023-07-26才进入信息集；此前审计行不得出现400165。
                    "new_stock_code": pd.NA,
                    "shares": float(state.shares.loc[code]),
                    "target_weight": target_weight,
                    "price_source_date": source_date,
                    "price_age_trading_days": int(age),
                    "consecutive_missing_price_days": int(age),
                    "transfer_window_age_trading_days": transfer_window_age,
                    "active_suspension": active_suspension,
                    "delisting_board_flag": delisting_flag,
                    "event_type": (
                        str(lifecycle_reason["event_type"])
                        if lifecycle_reason is not None
                        else "missing_price_observation"
                    ),
                    "announcement_date": (
                        pd.Timestamp(lifecycle_reason["announcement_date"])
                        if lifecycle_reason is not None
                        else pd.NaT
                    ),
                    "event_effective_date": (
                        pd.Timestamp(lifecycle_reason["event_effective_date"])
                        if lifecycle_reason is not None
                        else pd.NaT
                    ),
                    "settlement_code": pd.NA,
                    "settlement_ratio": 0.0,
                    "settlement_cash": 0.0,
                    "mapping_public_date": pd.NaT,
                    "mapping_effective_date": pd.NaT,
                    "old_mark": float(state.last_prices.get(code, np.nan)),
                    "new_quote": np.nan,
                    "volumn": np.nan,
                    "volume_unit": (
                        config.security_transfer_market_volume_unit
                        if pending_transfer
                        else pd.NA
                    ),
                    "amount": np.nan,
                    "amount_available": False,
                    "amount_status": (
                        "not_yet_available_before_mapping_public_date"
                        if pending_transfer
                        else pd.NA
                    ),
                    "event_source": (
                        str(lifecycle_reason["event_source"])
                        if lifecycle_reason is not None
                        else "daily_price+suspension_observation"
                    ),
                    "mark_used_in_nav": float(state.last_prices.get(code, np.nan)),
                    "executed_vwap": np.nan,
                    "executed_market_volume": np.nan,
                    "rule_label": (
                        "pending_transfer_bounded_45_trading_days"
                        if pending_transfer
                        else "announced_holding_restriction"
                        if restriction is not None
                        else "pending_company_action_settlement"
                        if pending_action is not None
                        else "risk_exit_behavior_not_valuation_source"
                        if pending_market_exit is not None
                        else "unexplained_missing_price_observation"
                    ),
                    "unexplained_stale_residual": unexplained,
                    "blocking": unexplained and state.active_sample_phase == "formal_oos",
                    "settlement_holding_error": 0.0,
                    "settlement_cash_error": 0.0,
                    "settlement_return_error": 0.0,
                }
                security_event_records.append(record)
                if record["blocking"]:
                    blocking_rows.append(record)
            zero_target_codes = _find_unexplained_zero_target_codes(
                state,
                status_index,
                lifecycle_exempt_codes=lifecycle_exempt_codes,
                config=config,
            )
            residual_trades, residual_audit, residual_cost = (
                _execute_zero_target_residual_exit(
                    state,
                    portfolio=portfolio,
                    date=processing_date,
                    status_index=status_index,
                    codes=zero_target_codes,
                    config=config,
                )
            )
            security_event_records.extend(residual_audit)
            if not residual_trades.empty:
                trade_frames.append(residual_trades)
                notional = float(residual_trades["gross_notional"].sum())
                commission = float(residual_trades["commission_cost"].sum())
                slippage = float(residual_trades["slippage_cost"].sum())
                stamp_tax = float(residual_trades["stamp_tax"].sum())
                turnover_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "buy_notional": 0.0,
                        "sell_notional": notional,
                        "gross_traded_notional": notional,
                        "two_sided_turnover": np.nan,
                        "one_way_turnover": np.nan,
                        "event_driven": True,
                    }
                )
                cost_records.append(
                    {
                        "date": processing_date,
                        "signal_date": state.active_signal_date,
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "commission_cost": commission,
                        "slippage_cost": slippage,
                        "stamp_tax": stamp_tax,
                        "total_cost": residual_cost,
                        "cost_rate_on_pretrade_nav": np.nan,
                        "stamp_tax_rate": _stamp_tax_rate(processing_date, config),
                        "event_driven": True,
                    }
                )
                if portfolio in open_month:
                    open_month[portfolio]["sell_notional"] += notional
                    open_month[portfolio]["gross_traded_notional"] += notional
                    open_month[portfolio]["commission_cost"] += commission
                    open_month[portfolio]["slippage_cost"] += slippage
                    open_month[portfolio]["stamp_tax"] += stamp_tax
                    open_month[portfolio]["total_cost"] += residual_cost
                    open_month[portfolio]["ledger_event_cost"] += residual_cost
        if blocking_rows:
            blockers = sorted({str(row["stock_code"]) for row in blocking_rows})
            raise RuntimeError(
                "正式OOS存在超出历史点价寿命且无可审计估值路径的资产；"
                "资产数量继续保留，但完整NAV、单点收益及R4/R7/R10/SA4已硬阻断，"
                f"不得以risk_exit永久豁免: {blockers}"
            )

        if pd.Timestamp(date) == terminal_date:
            last_signal = pd.Timestamp(schedule.iloc[-1]["signal_date"])
            terminal_status = panel.loc[
                panel["signal_date"].eq(last_signal),
                ["stock_code", "return_vwap", "return_vwap_valid"],
            ]
            for portfolio in LONG_PORTFOLIOS:
                state = states[portfolio]
                terminal_net, terminal_gross = _mark_terminal_event(
                    state, terminal_status, terminal_date
                )
                if portfolio not in open_month:
                    raise AssertionError("最终持有月没有起始执行事件")
                monthly_records.append(
                    _monthly_record(
                        portfolio=portfolio,
                        start_event=open_month.pop(portfolio),
                        end_date=terminal_date,
                        end_net_nav=terminal_net,
                        end_gross_nav=terminal_gross,
                    )
                )
                net_return = terminal_net / state.previous_daily_net_nav - 1.0
                gross_return = terminal_gross / state.previous_daily_gross_nav - 1.0
                daily_records.append(
                    {
                        "date": pd.Timestamp(date),
                        "holding_month": state.active_holding_month,
                        "sample_phase": state.active_sample_phase,
                        "portfolio": portfolio,
                        "valuation_phase": "terminal_return_vwap",
                        "ledger_component": "tail_bridge",
                        "gross_nav": terminal_gross,
                        "net_nav": terminal_net,
                        "gross_return": gross_return,
                        "net_return": net_return,
                        "gross_cash": state.gross_cash,
                        "net_cash": state.net_cash,
                        "stock_market_value": terminal_net - state.net_cash,
                        "cash_weight": state.net_cash / terminal_net,
                    }
                )
            continue

        for portfolio in LONG_PORTFOLIOS:
            state = states[portfolio]
            if state.active_holding_month is None:
                continue
            _update_close_marks(state, pd.Timestamp(date), observed)
            stock_value = _position_value(state.shares, state.last_prices)
            net_nav = state.net_cash + stock_value
            gross_nav = state.gross_cash + stock_value
            daily_records.append(
                {
                    "date": pd.Timestamp(date),
                    "holding_month": state.active_holding_month,
                    "sample_phase": state.active_sample_phase,
                    "portfolio": portfolio,
                    "valuation_phase": "daily_forward_adjusted_close",
                    "ledger_component": (
                        "first_bridge"
                        if event is not None
                        and portfolio in open_month
                        and pd.Timestamp(open_month[portfolio]["start_date"])
                        == processing_date
                        else "intramonth_chain"
                    ),
                    "gross_nav": gross_nav,
                    "net_nav": net_nav,
                    "gross_return": gross_nav / state.previous_daily_gross_nav - 1.0,
                    "net_return": net_nav / state.previous_daily_net_nav - 1.0,
                    "gross_cash": state.gross_cash,
                    "net_cash": state.net_cash,
                    "stock_market_value": stock_value,
                    "cash_weight": state.net_cash / net_nav,
                }
            )
            if portfolio in open_month:
                month_ledger = open_month[portfolio]
                if "ledger_posttrade_close_net_nav" not in month_ledger:
                    month_ledger["ledger_posttrade_close_net_nav"] = net_nav
                    month_ledger["ledger_posttrade_close_gross_nav"] = gross_nav
                month_ledger["ledger_month_last_close_net_nav"] = net_nav
                month_ledger["ledger_month_last_close_gross_nav"] = gross_nav
            state.previous_daily_net_nav = net_nav
            state.previous_daily_gross_nav = gross_nav

    daily = pd.DataFrame(daily_records).sort_values(
        ["date", "portfolio"], kind="mergesort"
    ).reset_index(drop=True)
    monthly = pd.DataFrame(monthly_records).sort_values(
        ["start_date", "portfolio"], kind="mergesort"
    ).reset_index(drop=True)
    reference = _build_monthly_target_reference(
        targets,
        panel,
        schedule,
        daily_prices,
        events,
        config,
    )
    monthly = monthly.merge(
        reference,
        on=["holding_month", "sample_phase", "portfolio"],
        how="left",
        validate="one_to_one",
    )
    monthly["actual_gross_before_cost_return"] = monthly["gross_return"]
    monthly["actual_net_return"] = monthly["net_return"]
    daily["target_reference_return"] = np.nan
    daily["target_reference_missing_count"] = np.nan
    daily["actual_gross_before_cost_return"] = daily["gross_return"]
    daily["actual_net_return"] = daily["net_return"]
    factors = calculate_style_factor_returns(daily, monthly, config)
    holdings = pd.concat(holding_frames, ignore_index=True)
    security_event_audit = _normalise_valuation_audit(
        security_event_records,
        config=config,
    )
    dataset = M3Dataset(
        target_weights=targets,
        daily_portfolio=daily,
        monthly_portfolio=monthly,
        actual_weights=pd.concat(actual_frames, ignore_index=True),
        trades=pd.concat(trade_frames, ignore_index=True)
        if trade_frames
        else _empty_frame(
            [
                "date", "signal_date", "holding_month", "sample_phase", "portfolio",
                "stock_code", "side", "shares", "vwap", "gross_notional",
                "commission_cost", "slippage_cost", "stamp_tax", "total_cost",
                "net_cash_flow", "target_weight",
            ]
        ),
        turnover=pd.DataFrame(turnover_records),
        costs=pd.DataFrame(cost_records),
        unfilled_orders=pd.concat(unfilled_frames, ignore_index=True)
        if unfilled_frames
        else _empty_frame(
            [
                "date", "signal_date", "holding_month", "sample_phase", "portfolio",
                "stock_code", "side", "requested_shares", "filled_shares",
                "unfilled_shares", "reference_price", "unfilled_notional", "reason",
            ]
        ),
        coverage=pd.DataFrame(coverage_records),
        factor_returns=factors,
        holdings=holdings,
        security_event_audit=security_event_audit,
        source_catalog=pd.DataFrame(
            [
                {
                    "purpose": "execution_and_return_endpoint",
                    "source": "m1.monthly_panel.execution_vwap/return_vwap",
                    "price_basis": "forward_adjusted_vwap_validated_by_m1",
                    "future_fill": False,
                },
                {
                    "purpose": "daily_mark_to_market",
                    "source": str(config.path("price_forward")),
                    "price_basis": "forward_adjusted_close; historical_ffill_only_in_state",
                    "future_fill": False,
                },
                {
                    "purpose": "600466_to_400165_lifecycle_exit_only",
                    "source": str(
                        config.security_transfer_data_root
                        / config.security_transfer_manifest_filename
                    ),
                    "price_basis": (
                        "frozen_10jqka_unadjusted_single_price_ohlc;"
                        "amount_unavailable;not_merged_into_local_all_a"
                    ),
                    "source_sha256": dict(config.security_transfer_frozen_sha256)[
                        config.security_transfer_market_raw_filename
                    ],
                    "successor_whitelist": config.security_transfer_new_code,
                    "future_fill": False,
                },
            ]
        ),
    )
    assert_m3_invariants(dataset, config)
    return dataset


def calculate_style_factor_returns(
    daily_portfolio: pd.DataFrame,
    monthly_portfolio: pd.DataFrame,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """B11：由四箱毛/净收益逐期重算 SMB、HML 与 GML。"""
    records: list[pd.DataFrame] = []
    for frequency, frame, index_columns in (
        ("daily", daily_portfolio, ["date", "holding_month", "sample_phase"]),
        ("monthly", monthly_portfolio, ["end_date", "holding_month", "sample_phase"]),
    ):
        _require_columns(
            frame,
            {*index_columns, "portfolio", "gross_return", "net_return"},
            f"{frequency}_portfolio",
        )
        boxes = frame.loc[frame["portfolio"].isin(STYLE_BOXES)]
        duplicated = boxes.duplicated([*index_columns, "portfolio"])
        if duplicated.any():
            raise AssertionError(f"{frequency} 四箱收益键不唯一")
        rows: list[pd.DataFrame] = []
        return_kinds = (
            "gross_return",
            "net_return",
            "actual_gross_before_cost_return",
            "actual_net_return",
        )
        for return_kind in return_kinds:
            wide = boxes.pivot(index=index_columns, columns="portfolio", values=return_kind)
            wide = wide.reindex(columns=STYLE_BOXES)
            if wide.isna().any(axis=None):
                raise AssertionError(f"{frequency} 四箱收益不完整，不能构造风格因子")
            smb = (wide["SV"] + wide["SG"] - wide["BV"] - wide["BG"]) / 2.0
            hml = (wide["SV"] + wide["BV"] - wide["SG"] - wide["BG"]) / 2.0
            values = pd.DataFrame({"SMB": smb, "HML": hml, "GML": -hml})
            long = values.stack().rename(return_kind).reset_index()
            long = long.rename(columns={f"level_{len(index_columns)}": "factor"})
            rows.append(long)
        combined = rows[0]
        for row in rows[1:]:
            combined = combined.merge(
                row, on=[*index_columns, "factor"], validate="one_to_one"
            )
        if frequency == "monthly":
            target = boxes.pivot(
                index=index_columns, columns="portfolio", values="target_reference_return"
            ).reindex(columns=STYLE_BOXES)
            smb = (target["SV"] + target["SG"] - target["BV"] - target["BG"]) / 2.0
            hml = (target["SV"] + target["BV"] - target["SG"] - target["BG"]) / 2.0
            target_long = pd.DataFrame({"SMB": smb, "HML": hml, "GML": -hml}).reset_index().melt(
                id_vars=index_columns,
                var_name="factor",
                value_name="target_reference_return",
            )
            combined = combined.merge(
                target_long,
                on=[*index_columns, "factor"],
                how="left",
                validate="one_to_one",
            )
            combined["factor_aggregation_contract"] = (
                "four_bridged_monthly_legs_then_linear_combination"
            )
            combined["factor_ledger_status"] = (
                "synthetic_no_independent_cash_ledger"
            )
        else:
            combined["target_reference_return"] = np.nan
            combined["factor_aggregation_contract"] = (
                "daily_linear_diagnostic_not_monthly_compound_equivalent"
            )
            combined["factor_ledger_status"] = (
                "synthetic_no_independent_cash_ledger"
            )
        combined.insert(0, "frequency", frequency)
        if frequency == "monthly":
            combined = combined.rename(columns={"end_date": "date"})
        records.append(combined)
    result = pd.concat(records, ignore_index=True).sort_values(
        ["frequency", "date", "factor"], kind="mergesort"
    ).reset_index(drop=True)
    hml = result.loc[result["factor"].eq("HML")].set_index(
        ["frequency", "date", "holding_month"]
    )
    gml = result.loc[result["factor"].eq("GML")].set_index(
        ["frequency", "date", "holding_month"]
    )
    if not np.allclose(
        hml["net_return"],
        -gml["net_return"],
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ):
        raise AssertionError("HML 与 GML 净收益必须逐期互为相反数")
    return result


def build_m3_dataset(
    m1: M1Dataset,
    m2: M2Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    daily_prices: pd.DataFrame | None = None,
    trading_dates: pd.DatetimeIndex | None = None,
    security_events: pd.DataFrame | None = None,
) -> M3Dataset:
    """m3 统一稳定入口；参数与 :func:`run_china_market_backtest` 相同。"""
    return run_china_market_backtest(
        m1,
        m2,
        config,
        daily_prices=daily_prices,
        trading_dates=trading_dates,
        security_events=security_events,
    )


def select_formal_oos(
    dataset: M3Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> M3Dataset:
    """SA3：只按冻结 holding_month 选择 2023-04 至 2025-12 正式 OOS。

    本函数只切片，不重估参数、不重跑交易。持有月终点可能落在下一自然月首个
    T+1 VWAP，选择依据始终是 m1 已冻结的 ``sample_phase=formal_oos``。
    """
    def formal(frame: pd.DataFrame) -> pd.DataFrame:
        if "sample_phase" not in frame:
            return frame.copy()
        return frame.loc[frame["sample_phase"].eq("formal_oos")].reset_index(drop=True)

    result = M3Dataset(
        target_weights=formal(dataset.target_weights),
        daily_portfolio=formal(dataset.daily_portfolio),
        monthly_portfolio=formal(dataset.monthly_portfolio),
        actual_weights=formal(dataset.actual_weights),
        trades=formal(dataset.trades),
        turnover=formal(dataset.turnover),
        costs=formal(dataset.costs),
        unfilled_orders=formal(dataset.unfilled_orders),
        coverage=formal(dataset.coverage),
        factor_returns=formal(dataset.factor_returns),
        holdings=formal(dataset.holdings),
        security_event_audit=formal(dataset.security_event_audit),
        source_catalog=dataset.source_catalog.copy(),
    )
    months = result.monthly_portfolio["holding_month"]
    if not months.empty:
        periods = pd.PeriodIndex(months, freq="M")
        if periods.min() < pd.Period(config.oos_start, freq="M") or periods.max() > pd.Period(
            config.oos_end, freq="M"
        ):
            raise AssertionError("正式 OOS 切片超出 config.oos_start/oos_end")
    return result


def assert_m3_invariants(
    dataset: M3Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> None:
    """独立勾稽成交、成本、现金、收益合成与 OOS 冻结边界。"""
    trades = dataset.trades
    for frame_name, frame in (
        ("daily_portfolio", dataset.daily_portfolio),
        ("monthly_portfolio", dataset.monthly_portfolio),
    ):
        _require_columns(
            frame,
            {
                "target_reference_return",
                "actual_gross_before_cost_return",
                "actual_net_return",
                "gross_return",
                "net_return",
            },
            frame_name,
        )
        if not np.allclose(
            frame["actual_gross_before_cost_return"],
            frame["gross_return"],
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
            equal_nan=True,
        ):
            raise AssertionError("实际持仓成本前收益与 gross 兼容列不一致")
        if not np.allclose(
            frame["actual_net_return"],
            frame["net_return"],
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
            equal_nan=True,
        ):
            raise AssertionError("实际持仓成本后收益与 net 兼容列不一致")
    if dataset.daily_portfolio["gross_nav"].lt(
        dataset.daily_portfolio["net_nav"] - config.numeric_tolerance
    ).any():
        raise AssertionError("同一实际持仓的累计成本前NAV不得低于成本后NAV")
    if not trades.empty:
        expected_cost = (
            trades["commission_cost"] + trades["slippage_cost"] + trades["stamp_tax"]
        )
        if not np.allclose(
            trades["total_cost"], expected_cost,
            rtol=config.numeric_tolerance, atol=config.numeric_tolerance,
        ):
            raise AssertionError("交易流水成本拆分不能勾稽")
        sell_stamp = trades.loc[trades["side"].eq("SELL"), "stamp_tax"]
        if sell_stamp.lt(-config.numeric_tolerance).any():
            raise AssertionError("卖出印花税不能为负")
        if trades.loc[trades["side"].eq("BUY"), "stamp_tax"].abs().gt(
            config.numeric_tolerance
        ).any():
            raise AssertionError("买入不得收取印花税")
        if trades["date"].le(trades["signal_date"]).any():
            raise AssertionError("所有成交必须严格晚于 T 日信号")
        if trades["vwap"].isna().any() or trades["vwap"].le(0).any():
            raise AssertionError("成交不得使用缺失或非正 VWAP")
    if dataset.daily_portfolio["net_cash"].lt(-config.cash_tolerance).any():
        raise AssertionError("日频记账出现负现金")
    if not np.allclose(
        dataset.costs["total_cost"],
        dataset.costs[["commission_cost", "slippage_cost", "stamp_tax"]].sum(axis=1),
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ):
        raise AssertionError("成本表拆分不能勾稽")
    actual_sum = dataset.actual_weights.groupby(
        ["date", "portfolio"], sort=False
    )["actual_weight"].sum()
    if not np.allclose(
        actual_sum,
        np.ones(len(actual_sum)),
        rtol=config.numeric_tolerance,
        atol=config.weight_tolerance,
    ):
        raise AssertionError("实际股票权重与现金权重之和不等于 100%")
    if not dataset.unfilled_orders.empty:
        if dataset.unfilled_orders["unfilled_shares"].le(config.numeric_tolerance).any():
            raise AssertionError("未成交表只能记录正的未成交数量")
        traded_keys = set(
            map(tuple, trades[["date", "portfolio", "stock_code", "side"]].to_numpy())
        )
        for row in dataset.unfilled_orders.itertuples(index=False):
            if row.filled_shares <= config.numeric_tolerance and (
                row.date, row.portfolio, row.stock_code, row.side
            ) in traded_keys:
                raise AssertionError("完全未成交订单不能同时虚构为成交")
    factors = dataset.factor_returns
    for frequency in factors["frequency"].unique():
        part = factors.loc[factors["frequency"].eq(frequency)]
        hml = part.loc[part["factor"].eq("HML")].set_index(["date", "holding_month"])
        gml = part.loc[part["factor"].eq("GML")].set_index(["date", "holding_month"])
        if not np.allclose(
            hml["net_return"], -gml["net_return"],
            rtol=config.numeric_tolerance, atol=config.numeric_tolerance,
        ):
            raise AssertionError("HML/GML 未逐期互为相反数")
    monthly_factor = factors.loc[factors["frequency"].eq("monthly")]
    monthly_boxes = dataset.monthly_portfolio.loc[
        dataset.monthly_portfolio["portfolio"].isin(STYLE_BOXES)
    ]
    factor_index = ["end_date", "holding_month", "sample_phase"]
    for return_column in ("gross_return", "net_return"):
        box_wide = monthly_boxes.pivot(
            index=factor_index, columns="portfolio", values=return_column
        ).reindex(columns=STYLE_BOXES)
        factor_wide = monthly_factor.pivot(
            index=["date", "holding_month", "sample_phase"],
            columns="factor",
            values=return_column,
        ).reindex(columns=FACTOR_NAMES)
        factor_wide.index = factor_wide.index.set_names(factor_index)
        expected_smb = (
            box_wide["SV"] + box_wide["SG"] - box_wide["BV"] - box_wide["BG"]
        ) / 2.0
        expected_hml = (
            box_wide["SV"] + box_wide["BV"] - box_wide["SG"] - box_wide["BG"]
        ) / 2.0
        expected = pd.DataFrame(
            {"SMB": expected_smb, "HML": expected_hml, "GML": -expected_hml}
        ).reindex(factor_wide.index)
        if not np.allclose(
            factor_wide.to_numpy(dtype=float),
            expected.to_numpy(dtype=float),
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        ):
            raise AssertionError("月度SMB/HML/GML未由桥接四腿先月化再线性合成")
    ledger_columns = {
        "ledger_start_pretrade_vwap_net_nav",
        "ledger_posttrade_close_net_nav",
        "ledger_month_last_close_net_nav",
        "ledger_next_pretrade_vwap_net_nav",
        "ledger_start_pretrade_vwap_gross_nav",
        "ledger_posttrade_close_gross_nav",
        "ledger_month_last_close_gross_nav",
        "ledger_next_pretrade_vwap_gross_nav",
        "ledger_net_reconciliation_error",
        "ledger_gross_reconciliation_error",
    }
    _require_columns(dataset.monthly_portfolio, ledger_columns, "monthly_portfolio")
    if dataset.monthly_portfolio[
        ["ledger_net_reconciliation_error", "ledger_gross_reconciliation_error"]
    ].abs().gt(config.numeric_tolerance).any(axis=None):
        raise AssertionError("月度首桥/月内链/尾桥与四点NAV直接收益不勾稽")
    daily_ledger = dataset.daily_portfolio.copy()
    _require_columns(daily_ledger, {"ledger_component"}, "daily_portfolio")
    component_counts = daily_ledger.groupby(
        ["holding_month", "portfolio"], sort=False
    )["ledger_component"].value_counts().unstack(fill_value=0)
    if (
        component_counts.get("first_bridge", pd.Series(0, index=component_counts.index)).ne(1).any()
        or component_counts.get("tail_bridge", pd.Series(0, index=component_counts.index)).ne(1).any()
    ):
        raise AssertionError("每个长组合持有月必须恰有一个首桥和一个尾桥")
    daily_compound = daily_ledger.groupby(
        ["holding_month", "portfolio"], as_index=False, sort=False
    ).agg(
        daily_gross_return=("gross_return", lambda values: float((1.0 + values).prod() - 1.0)),
        daily_net_return=("net_return", lambda values: float((1.0 + values).prod() - 1.0)),
    )
    monthly_bridge = dataset.monthly_portfolio.merge(
        daily_compound,
        on=["holding_month", "portfolio"],
        how="left",
        validate="one_to_one",
    )
    if not np.allclose(
        monthly_bridge["gross_return"],
        monthly_bridge["daily_gross_return"],
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ) or not np.allclose(
        monthly_bridge["net_return"],
        monthly_bridge["daily_net_return"],
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ):
        raise AssertionError("日账本按持有月复合后未与唯一月表勾稽")
    formal = dataset.monthly_portfolio.loc[
        dataset.monthly_portfolio["sample_phase"].eq("formal_oos")
    ]
    if not formal.empty:
        periods = pd.PeriodIndex(formal["holding_month"], freq="M")
        if periods.min() < pd.Period(config.oos_start, freq="M") or periods.max() > pd.Period(
            config.oos_end, freq="M"
        ):
            raise AssertionError("正式 OOS 月份越过冻结区间")
        first_coverage = (
            dataset.coverage.loc[dataset.coverage["sample_phase"].eq("formal_oos")]
            .sort_values(["date", "portfolio"], kind="mergesort")
            .groupby("portfolio", sort=False)
            .first()
        )
        if first_coverage["pretrade_stock_count"].ne(0).any() or not np.allclose(
            first_coverage["pretrade_cash_weight"],
            1.0,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
        ):
            raise AssertionError("正式OOS首次执行前必须是NAV=1的全现金状态")
    event_audit = dataset.security_event_audit
    if not event_audit.empty:
        valuation_key = ["date", "portfolio", "stock_code"]
        _require_columns(
            event_audit,
            {
                *valuation_key,
                "selected_for_valuation",
                "valuation_source_priority",
                "valuation_status",
                "valuation_selection_reason",
                "valuation_candidate_sources",
                "mark_reconciliation_error",
                "has_auditable_valuation_path",
            },
            "security_event_audit",
        )
        if event_audit.duplicated(valuation_key).any():
            raise AssertionError("证券生命周期估值状态键不唯一")
        if not event_audit["selected_for_valuation"].fillna(False).all():
            raise AssertionError("每个证券生命周期键必须恰有一个有效估值选择")
        if pd.to_numeric(
            event_audit["mark_reconciliation_error"], errors="coerce"
        ).fillna(0.0).abs().gt(config.numeric_tolerance).any():
            raise AssertionError("生命周期selected mark与NAV使用mark不一致")
        effective = pd.to_datetime(event_audit["event_effective_date"], errors="coerce")
        announced = pd.to_datetime(event_audit["announcement_date"], errors="coerce")
        processing = pd.to_datetime(event_audit["processing_date"], errors="coerce")
        known = effective.notna() & event_audit["valuation_status"].eq(
            "explicit_settlement"
        )
        if effective.loc[known].gt(processing.loc[known]).any():
            raise AssertionError("证券事件在生效日之前被使用")
        announced_known = announced.notna()
        if announced.loc[announced_known].gt(processing.loc[announced_known]).any():
            raise AssertionError("证券事件在公告日之前被使用")
        for column in (
            "settlement_holding_error",
            "settlement_cash_error",
            "settlement_return_error",
        ):
            if pd.to_numeric(event_audit[column], errors="coerce").fillna(0).abs().gt(
                config.numeric_tolerance
            ).any():
                raise AssertionError(f"证券事件 {column} 超容差")
        if event_audit["blocking"].fillna(False).any():
            raise AssertionError("返回的M3Dataset不得保留未处理生命周期阻断项")


__all__ = [
    "STYLE_BOXES",
    "LONG_PORTFOLIOS",
    "FACTOR_NAMES",
    "M3Dataset",
    "build_portfolio_targets",
    "load_daily_mark_prices",
    "run_china_market_backtest",
    "build_m3_dataset",
    "calculate_style_factor_returns",
    "select_formal_oos",
    "assert_m3_invariants",
]
