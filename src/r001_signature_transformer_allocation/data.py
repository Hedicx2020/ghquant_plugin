"""r001 · SIT 数据层（milestone m1）。

职责：为 SIT 的 A股迁移复现构建"点时无未来函数"的数据底座——
1. 固定资产集 universe（CSI300 点时在册 → 市值 top-N → 剔 ST/停牌），供资产维注意力
   与可学习资产嵌入 e_asset 使用（SIT 架构要求资产数 d 与资产身份跨 train/val/test 固定）；
2. 前复权对数收益面板（close 对数差分，AS11）；
3. 月末调仓日历（B3）；
4. 日历特征 v_t（sin/cos 周期编码，F=8，AS4）；
5. 固定 train/val/test 划分（D3/AS13）。

数据红线（code_audit/codex 逐点核查）：
- universe 以 anchor 日**点时快照**选样，绝不用未来在册成分（get_index_members_on_date 半开区间）；
- 前复权 close 对数差分为连续可比日收益，无前视；
- 划分固定不重叠、按时间顺序，无泄漏；
- 停牌/退市资产在其不可交易期收益置 0（AS11 细化，见 assumptions），并在 universe_meta
  标注有效交易区间供 m4 回测屏蔽。

通用数据/工具逻辑一律复用 common/，本模块只做 SIT 特有的数据装配。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from common.data_loader import (
    filter_st_stocks,
    get_index_members_on_date,
    get_month_end_trading_days,
    load_index_components,
    load_st_data,
    load_stock_price_forward,
    load_stock_trade,
    load_suspend_status,
    load_trade_calendar,
)

from .config import DEFAULT_CONFIG, SITConfig


# ---------------------------------------------------------------------------
# 交易日历 / 调仓日
# ---------------------------------------------------------------------------

def get_all_trading_days(config: SITConfig) -> pd.DatetimeIndex:
    """全量交易日 index：[price_load_start, test_end]（含签名回看 buffer）。"""
    cal = load_trade_calendar(start_date=config.price_load_start, end_date=config.test_end)
    return pd.DatetimeIndex(cal["date"].values)


def build_rebalance_calendar(config: SITConfig = DEFAULT_CONFIG) -> pd.DatetimeIndex:
    """月末调仓日（B3）：train 起点 ~ test 终点的月末交易日。"""
    return get_month_end_trading_days(config.train_start, config.test_end)


def resolve_anchor_date(config: SITConfig = DEFAULT_CONFIG) -> pd.Timestamp:
    """固定资产集选样锚点（防未来函数）。

    - "train_start"（默认）：train 段首个月末交易日 → 选样只用训练期起点及之前信息；
    - "test_start"：test 段首个月末交易日 → 面板更完整但含回溯幸存偏差（与原文一致，备选）。
    """
    if config.universe_anchor == "train_start":
        return get_month_end_trading_days(config.train_start, config.train_end)[0]
    if config.universe_anchor == "test_start":
        return get_month_end_trading_days(config.test_start, config.test_end)[0]
    raise ValueError(f"未知 universe_anchor={config.universe_anchor!r}（应为 train_start/test_start）")


# ---------------------------------------------------------------------------
# 点时 universe 选样（CSI300 在册 → 市值 top-N → 剔 ST/停牌）
# ---------------------------------------------------------------------------

def _market_cap_at(
    anchor: pd.Timestamp,
    candidates: pd.Index,
    config: SITConfig,
    trade: Optional[pd.DataFrame] = None,
    lookback_days: int = 15,
) -> pd.Series:
    """候选股在 anchor 日（或前 lookback_days 内最近交易日）的市值（点时，无未来）。"""
    if trade is None:
        trade = load_stock_trade(columns=["stock_code", "date", config.market_cap_col])
    lo = anchor - pd.Timedelta(days=lookback_days)
    win = trade[
        (trade["date"] <= anchor)
        & (trade["date"] >= lo)
        & (trade["stock_code"].isin(candidates))
    ]
    if win.empty:
        return pd.Series(dtype=float)
    last = win.sort_values("date").groupby("stock_code").tail(1)
    return last.set_index("stock_code")[config.market_cap_col]


def select_universe_at(
    anchor: pd.Timestamp,
    top_n: int,
    config: SITConfig = DEFAULT_CONFIG,
    components: Optional[pd.DataFrame] = None,
    st_data: Optional[pd.DataFrame] = None,
    trade: Optional[pd.DataFrame] = None,
) -> list[str]:
    """在 anchor 日点时选出 top_n 资产：CSI300 在册 ∩ 非ST ∩ 非停牌，按市值降序取前 N。

    全部条件只用 anchor 日及之前信息，防未来函数。返回市值降序的股票代码列表。
    """
    if components is None:
        components = load_index_components(config.index_code)
    if st_data is None:
        st_data = load_st_data()

    members = get_index_members_on_date(components, anchor)          # 点时在册成分
    non_st = filter_st_stocks(pd.Series(members), anchor, st_data)   # 剔 ST
    susp = load_suspend_status(
        stock_codes=list(members),
        start_date=(anchor - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
    )
    suspended = susp[(susp["date"] == anchor) & (susp["if_suspend"] == 1)]["stock_code"].unique()
    tradable = non_st.difference(pd.Index(suspended))               # 剔当日停牌

    caps = _market_cap_at(anchor, tradable, config, trade=trade)    # 点时市值
    ranked = caps.dropna().sort_values(ascending=False)
    return ranked.head(top_n).index.tolist()


def build_pit_universe(
    rebalance_dates: pd.DatetimeIndex,
    top_n: int,
    config: SITConfig = DEFAULT_CONFIG,
) -> dict[pd.Timestamp, list[str]]:
    """逐调仓日点时 universe（浮动资产集）。

    供数据探查与 m4 浮动 universe 备选；SIT 主链用固定资产集（build_fixed_universe），
    因资产维注意力/e_asset 需固定 d。此处一次性预载 components/st/trade 复用。
    """
    components = load_index_components(config.index_code)
    st_data = load_st_data()
    trade = load_stock_trade(columns=["stock_code", "date", config.market_cap_col])
    return {
        pd.Timestamp(d): select_universe_at(
            pd.Timestamp(d), top_n, config, components=components, st_data=st_data, trade=trade
        )
        for d in rebalance_dates
    }


# ---------------------------------------------------------------------------
# 前复权对数收益面板（AS11：close 对数差分）
# ---------------------------------------------------------------------------

def load_forward_close_panel(
    codes: Sequence[str],
    config: SITConfig = DEFAULT_CONFIG,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """加载固定资产集的前复权 close，pivot 成 wide 面板（index=date, columns=codes 固定序）。"""
    start = start or config.price_load_start
    end = end or config.test_end
    raw = load_stock_price_forward(
        columns=["stock_code", "date", "close"],
        stock_codes=list(codes),
        start_date=start,
        end_date=end,
    )
    wide = raw.pivot_table(index="date", columns="stock_code", values="close")
    return wide.reindex(columns=list(codes)).sort_index()


def compute_log_returns(prices_wide: pd.DataFrame) -> pd.DataFrame:
    """前复权 close 对数差分：r_t = ln(close_t) − ln(close_{t-1})（AS11）。"""
    return np.log(prices_wide).diff()


# ---------------------------------------------------------------------------
# 日历特征 v_t（AS4：sin/cos 周期编码，F=8）
# ---------------------------------------------------------------------------

def build_calendar_features(
    dates: pd.DatetimeIndex,
    config: SITConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """确定性日历特征 v_t ∈ R^F：对 4 个日历周期各取 sin/cos，共 F=8 维（AS4）。"""
    idx = pd.DatetimeIndex(dates)
    feats: dict[str, np.ndarray] = {}
    for name, period, attr in config.calendar_cycles:
        vals = getattr(idx, attr).to_numpy(dtype=float)
        feats[f"{name}_sin"] = np.sin(2.0 * np.pi * vals / period)
        feats[f"{name}_cos"] = np.cos(2.0 * np.pi * vals / period)
    return pd.DataFrame(feats, index=idx)


# ---------------------------------------------------------------------------
# train/val/test 划分（D3 / AS13：固定、不重叠、按时间顺序）
# ---------------------------------------------------------------------------

def split_ranges(config: SITConfig = DEFAULT_CONFIG) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """三段时间区间（闭区间端点）。"""
    return {
        "train": (pd.Timestamp(config.train_start), pd.Timestamp(config.train_end)),
        "val": (pd.Timestamp(config.val_start), pd.Timestamp(config.val_end)),
        "test": (pd.Timestamp(config.test_start), pd.Timestamp(config.test_end)),
    }


def split_dates(
    dates: pd.DatetimeIndex,
    config: SITConfig = DEFAULT_CONFIG,
) -> dict[str, pd.DatetimeIndex]:
    """把给定日期序列（如调仓日）划入 train/val/test（不重叠）。"""
    ranges = split_ranges(config)
    idx = pd.DatetimeIndex(dates)
    return {
        name: idx[(idx >= lo) & (idx <= hi)]
        for name, (lo, hi) in ranges.items()
    }


# ---------------------------------------------------------------------------
# universe 元数据（有效交易区间 / test 覆盖率，供 m4 屏蔽不可交易资产）
# ---------------------------------------------------------------------------

def build_universe_meta(
    codes: Sequence[str],
    prices_wide: pd.DataFrame,
    config: SITConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """每资产的有效行情区间与 test 覆盖率（退市/停牌洞的可见性）。"""
    lo, hi = pd.Timestamp(config.test_start), pd.Timestamp(config.test_end)
    test_days = prices_wide.index[(prices_wide.index >= lo) & (prices_wide.index <= hi)]
    n_test = max(len(test_days), 1)
    rows = []
    for c in codes:
        s = prices_wide[c].dropna()
        in_test = s.index[(s.index >= lo) & (s.index <= hi)]
        rows.append({
            "stock_code": c,
            "first_date": s.index.min() if len(s) else pd.NaT,
            "last_date": s.index.max() if len(s) else pd.NaT,
            "n_obs": int(len(s)),
            "test_coverage": round(len(in_test) / n_test, 4),
            "full_test": len(in_test) >= 0.9 * n_test,
        })
    return pd.DataFrame(rows).set_index("stock_code").reindex(list(codes))


# ---------------------------------------------------------------------------
# 顶层装配
# ---------------------------------------------------------------------------

@dataclass
class DataBundle:
    """m1 数据底座打包（供 m2 特征工程 / m4 训练回测消费）。"""

    config: SITConfig
    top_n: int
    anchor_date: pd.Timestamp
    universe_codes: list[str]
    universe_meta: pd.DataFrame
    daily_prices: pd.DataFrame          # 前复权 close，wide，全交易日 × N（停牌/退市日 NaN）
    daily_log_returns: pd.DataFrame     # 对数收益，全交易日 × N，不可交易期填 0（AS11）
    daily_simple_returns: pd.DataFrame  # 简单收益，供 m4 回测 nav 结算（对数收益仅特征母源）
    rebalance_dates: pd.DatetimeIndex   # 月末调仓日（B3）
    calendar_features: pd.DataFrame     # 日历特征 v_t，全交易日 × F（AS4）
    splits: dict[str, pd.DatetimeIndex] # 调仓日的 train/val/test 划分（D3）

    def summary(self) -> dict:
        """关键形状/口径摘要（冒烟与审计用）。"""
        return {
            "top_n": self.top_n,
            "anchor_date": str(self.anchor_date.date()),
            "n_universe": len(self.universe_codes),
            "daily_prices_shape": tuple(self.daily_prices.shape),
            "daily_log_returns_shape": tuple(self.daily_log_returns.shape),
            "calendar_features_shape": tuple(self.calendar_features.shape),
            "n_rebalance": int(len(self.rebalance_dates)),
            "rebalance_split_counts": {k: int(len(v)) for k, v in self.splits.items()},
            "full_test_assets": int(self.universe_meta["full_test"].sum()),
        }


def load_data_bundle(
    config: SITConfig = DEFAULT_CONFIG,
    top_n: Optional[int] = None,
    anchor_date: Optional[pd.Timestamp] = None,
) -> DataBundle:
    """一站式装配 SIT m1 数据底座（固定资产集链路）。

    Args:
        config: 全局配置。
        top_n: 资产数（默认主档 universe_primary_n=50）。
        anchor_date: 选样锚点（默认按 config.universe_anchor 解析，防未来函数）。

    Returns:
        DataBundle：universe / 收益面板 / 调仓日 / 日历特征 / 划分。
    """
    top_n = top_n or config.universe_primary_n
    anchor_date = pd.Timestamp(anchor_date) if anchor_date is not None else resolve_anchor_date(config)

    # 1) 固定资产集（点时选样，防未来函数）
    codes = select_universe_at(anchor_date, top_n, config)
    if not codes:
        raise RuntimeError(f"anchor={anchor_date.date()} top_n={top_n} 选样为空，请检查数据/日期")

    # 2) 全交易日 index（含签名回看 buffer）
    all_days = get_all_trading_days(config)

    # 3) 前复权 close → 对数/简单收益（不可交易期填 0）
    prices_raw = load_forward_close_panel(codes, config)
    daily_prices = prices_raw.reindex(all_days)
    daily_log_returns = compute_log_returns(daily_prices).reindex(all_days).fillna(0.0)
    daily_simple_returns = daily_prices.pct_change().reindex(all_days).fillna(0.0)

    # 4) universe 元数据（有效区间 / test 覆盖率）
    universe_meta = build_universe_meta(codes, prices_raw, config)

    # 5) 调仓日历 + 划分
    rebalance_dates = build_rebalance_calendar(config)
    splits = split_dates(rebalance_dates, config)

    # 6) 日历特征 v_t
    calendar_features = build_calendar_features(all_days, config)

    return DataBundle(
        config=config,
        top_n=top_n,
        anchor_date=anchor_date,
        universe_codes=codes,
        universe_meta=universe_meta,
        daily_prices=daily_prices,
        daily_log_returns=daily_log_returns,
        daily_simple_returns=daily_simple_returns,
        rebalance_dates=rebalance_dates,
        calendar_features=calendar_features,
        splits=splits,
    )
