"""通用时序择时回测引擎（timing 类型首次沉淀）。

本模块是所有 timing 类研报共用的回测内核，只提供与具体研报无关的
「目标仓位 -> 逐日持仓收益 -> 绩效指标」通用逻辑：

- :func:`signal_backtest`  信号（目标仓位）逐日回测，内建 ``lag`` 防未来函数。
- :func:`timing_metrics`   基于净值/仓位/基准净值计算年化/回撤/夏普/胜率/盈亏比/调仓/超额年化。

设计约定（见 templates/timing.md 第 4 节接口规范）：
- 信号计算（F1–F8 等研报特定逻辑）写在 ``src/{report}/strategy.py``，不进本模块。
- 绩效指标复用 ``common.utils``，本模块只做择时特有的聚合（持仓日胜率/盈亏比/调仓次数）。
- ``lag`` 语义：T 日收盘形成的目标仓位滞后 ``lag`` 个交易日生效，即 T 日信号
  赚取其后区间（[T, T+1]）的收盘价到收盘价收益，从根本上杜绝前视/未来函数。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.utils import (
    calculate_annualized_return,
    calculate_annualized_volatility,
    calculate_max_drawdown,
)

# 日频交易日年化基准（一年约 252 个交易日）。timing 类默认按交易日年化，
# 与参考实现 src/test（复现精度 < 2.5%）保持一致；如某研报按自然年年化，
# 调用方通过 periods_per_year 显式切换。
TRADING_DAYS_PER_YEAR: int = 252


def signal_backtest(
    signal: pd.Series,
    asset_returns: pd.Series,
    cost_bps: float = 0.0,
    lag: int = 1,
) -> pd.DataFrame:
    """信号（目标仓位）逐日回测。

    Args:
        signal: index=date 的目标仓位/打分序列（多空取值 -1/0/1，仅做多取 0/1，
            也可为连续权重）。取值代表 T 日收盘时确定的目标仓位。
        asset_returns: index=date 的标的日收益（收盘价到收盘价，decimal，如 0.01=1%）。
        cost_bps: 单边交易成本（bp）；默认 0.0 对应研报基准「不计交易费用」(B2)。
        lag: 信号滞后交易日数，默认 1 —— T 日信号 T+1 生效并赚取 [T, T+1] 收益，
            防未来函数。若为 0 表示信号当日即赚取当日收益（一般不用）。

    Returns:
        与 ``asset_returns`` 同索引的 DataFrame，列：
        ``position``（实际生效仓位=signal.shift(lag)）、
        ``strategy_ret``（扣费后策略日收益）、
        ``nav``（策略累计净值，起点 1.0 之上）、
        ``benchmark_nav``（标的买入持有累计净值）。
    """
    sig = pd.Series(signal).sort_index()
    ret = pd.Series(asset_returns).astype(float).sort_index()
    idx = ret.index

    # 防未来函数：目标仓位滞后 lag 日生效，前 lag 日无持仓。
    position = sig.reindex(idx).shift(lag).fillna(0.0).astype(float)

    # 单边换手（首日建仓计入）与交易成本。
    turnover = position.diff().abs()
    turnover.iloc[:1] = position.iloc[:1].abs()
    cost = turnover * (cost_bps / 1e4)

    strategy_ret = (position * ret - cost).fillna(0.0)
    nav = (1.0 + strategy_ret).cumprod()
    benchmark_nav = (1.0 + ret.fillna(0.0)).cumprod()

    return pd.DataFrame(
        {
            "position": position,
            "strategy_ret": strategy_ret,
            "nav": nav,
            "benchmark_nav": benchmark_nav,
        },
        index=idx,
    )


def _reconstruct_returns(nav: pd.Series) -> pd.Series:
    """由净值序列还原逐期收益（首期以净值起点隐含 1.0 还原）。"""
    ret = nav.pct_change()
    if len(ret):
        ret.iloc[0] = float(nav.iloc[0]) - 1.0
    return ret


def timing_metrics(
    nav: pd.Series,
    position: pd.Series,
    benchmark_nav: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> dict:
    """基于净值/仓位/基准净值计算择时绩效指标。

    胜率与盈亏比按「持仓日（position != 0）」口径统计——择时策略在空仓日不产生
    盈亏，故只在实际持仓日评估方向正确率，符合研报择时胜率语义。盈亏比取 **sum
    总额比** Σ(持仓日收益>0) / |Σ(持仓日收益<0)|（非均值比），与
    ``src/test_v2/strategy.py`` 的 ``_odds``（R3 表3 赔率）统一为总额比口径——依据
    iter_01 diagnosis M1：R3 的 sum 总额比经 spec 表格逐格反推、逐格对齐研报，坐实为
    研报盈亏比口径，本共享引擎据此对齐（原均值比 mean/|mean| 系统性偏低约
    n_gain/n_loss 倍）。

    Args:
        nav: 策略累计净值序列（signal_backtest 输出的 ``nav``）。
        position: 实际生效仓位序列（signal_backtest 输出的 ``position``）。
        benchmark_nav: 基准（标的买入持有）累计净值序列。
        periods_per_year: 年化周期数，默认 252（交易日）。

    Returns:
        dict，含 annual_return / annual_volatility / max_drawdown / sharpe /
        calmar / win_rate / profit_loss_ratio / trade_count /
        annual_trade_count / excess_annual_return / benchmark_annual_return /
        cumulative_return / n_periods。
    """
    nav = pd.Series(nav).dropna().astype(float)
    if nav.empty:
        return {
            "cumulative_return": 0.0,
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_loss_ratio": 0.0,
            "trade_count": 0,
            "annual_trade_count": 0.0,
            "excess_annual_return": 0.0,
            "benchmark_annual_return": 0.0,
            "n_periods": 0,
        }

    pos = pd.Series(position).reindex(nav.index).fillna(0.0)
    strat_ret = _reconstruct_returns(nav)
    bench_nav = pd.Series(benchmark_nav).reindex(nav.index).astype(float)
    bench_ret = _reconstruct_returns(bench_nav)

    ann_return = calculate_annualized_return(strat_ret, periods_per_year)
    ann_vol = calculate_annualized_volatility(strat_ret, periods_per_year)
    max_dd = calculate_max_drawdown(nav)
    sharpe = float(ann_return / ann_vol) if ann_vol > 0 else 0.0
    calmar = float(ann_return / max_dd) if max_dd > 0 else 0.0

    # 持仓日口径的胜率与盈亏比。
    active_ret = strat_ret[pos.ne(0)]
    if active_ret.empty:
        win_rate = 0.0
        profit_loss_ratio = 0.0
    else:
        win_rate = float((active_ret > 0).mean())
        # 盈亏比 = 持仓日总盈利额 / 持仓日总亏损额绝对值 = Σ(收益>0) / |Σ(收益<0)|
        # （sum 总额比）。语义变更（依据 iter_01 diagnosis M1）：原为「持仓日均盈/均亏
        # 比」mean/|mean|，较总额比系统性偏低约 n_gain/n_loss 倍；现改「总额比」，与
        # src/test_v2/strategy.py:_odds（R3 表3 赔率，经 spec 表格逐格反推坐实为 sum
        # 总额比、逐格对齐研报）统一口径。注意 legacy 影响面：本模块为共享 timing 引擎，
        # 此变更令所有走 timing_metrics 的业绩表（R1/R7/R8/R9/R11/R13）盈亏比语义一并
        # 对齐研报总额比口径。（active_ret 非空由外层 if 保证；全盈/全亏日一侧 sum=0.0，
        # 由下方 sum_loss<0 and sum_gain>0 条件安全返回 0.0。）
        sum_gain = active_ret[active_ret > 0].sum()
        sum_loss = active_ret[active_ret < 0].sum()  # 负值
        profit_loss_ratio = (
            float(sum_gain / abs(sum_loss))
            if sum_loss < 0 and sum_gain > 0
            else 0.0
        )

    # 调仓次数：仓位发生变化的交易日数（首日建仓计入）。
    pos_change = pos.diff()
    pos_change.iloc[:1] = pos.iloc[:1]
    trade_count = int(pos_change.ne(0).sum())
    n_years = len(nav) / periods_per_year
    annual_trade_count = float(trade_count / n_years) if n_years > 0 else 0.0

    bench_ann = calculate_annualized_return(bench_ret, periods_per_year)

    return {
        "cumulative_return": float(nav.iloc[-1] - 1.0),
        "annual_return": float(ann_return),
        "annual_volatility": float(ann_vol),
        "max_drawdown": float(max_dd),
        "sharpe": float(sharpe),
        "calmar": float(calmar),
        "win_rate": float(win_rate),
        "profit_loss_ratio": float(profit_loss_ratio),
        "trade_count": trade_count,
        "annual_trade_count": annual_trade_count,
        "excess_annual_return": float(ann_return - bench_ann),
        "benchmark_annual_return": float(bench_ann),
        "n_periods": int(len(nav)),
    }
