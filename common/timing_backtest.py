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


def rotation_backtest(
    weight: pd.Series,
    returns_a: pd.Series,
    returns_b: pd.Series,
    cost_bps: float = 0.0,
    lag: int = 1,
    drift_within_period: bool = False,
) -> pd.DataFrame:
    """双标的轮动回测（两资产间 0~1 目标权重切换，恒满仓）。

    与 :func:`signal_backtest`（单标的仓位）并列的通用择时引擎形态：目标权重
    表示资产 A 的配置比例（``1-weight`` 为资产 B），策略日收益 =
    ``w*r_a + (1-w)*r_b - cost``。适用于大小盘/股债等两资产轮动类研报。

    目标权重允许稀疏索引（如仅月末观察日）：函数内 reindex 至收益日频索引后
    前向填充，语义为「目标权重持有至下次更新」；首个非缺失权重之前的日子视为
    未建仓（当日策略收益 0，净值持平 1.0）。

    执行语义（T+lag 收盘成交，close-to-close 日收益口径）：
    T 日收盘形成的目标权重于 T+lag 个交易日后的**收盘价成交**；索引日 t 的
    日收益 ret[t] 为「t-1 收盘 → t 收盘」段收益，成交当日（T+lag）的收益段
    仍由**旧仓位**承担，新仓位自 T+lag → T+lag+1 收益段起生效。函数内分离
    两条仓位序列（CDX-C-R1-01 修复）：

    - ``executed_weight = 目标权重 ffill 后 shift(lag)``：成交后权重，
      T+lag 收盘成交即生效，用于换手与成本的**成交日**记账；
    - ``position = executed_weight.shift(1)``：收益承担仓位（= 目标权重
      ffill 后 ``shift(lag + 1)``，lag=1 时 shift 两段：T 日信号、T+1 收盘
      成交、T+1→T+2 收益段起新仓位生效），用于逐日收益计算，与修复前
      语义完全一致。

    注意与 :func:`signal_backtest` 的 lag 语义不同（后者
    position=signal.shift(lag) 等价于 T+lag-1 收盘成交、T+lag 当日收益段
    即生效），调用方按研报的成交时点口径选择引擎。

    月内漂移模式（``drift_within_period=True``，iter_04 SO-02 方法论族，
    r008 月度策略「月末调仓、月内 drift」口径）：
    默认 False 时语义如上（每日目标权重等价每日再平衡），**逐位不变**；
    True 时仓位在成交日（观察日+lag）收盘重置为目标权重（每个成交日无论
    目标权重是否变化均重置，与月度再平衡基准「每月末收盘恢复目标权重」
    口径对齐），其余日期按两腿收益递推漂移——
    ``w_A,t+1 = w_A,t·(1+r_A,t+1) / (w_A,t·(1+r_A,t+1) + w_B,t·(1+r_B,t+1))``
    （B 腿对称，w_B=1-w_A）。换手仍在成交日按重置幅度记账（|w_目标-w_成交前
    漂移|，漂移量计入下次调仓，换手较默认分支上升）；成本与 T+lag 成交时点
    不变，收益承担语义（position = executed_weight.shift(1) 的 T+1 纪律）
    不变。目标权重 ∈ {0,1} 时漂移恒等（段内漂移系数比值恒为 1），分支自动
    退化为默认语义（逐位一致）。

    Args:
        weight: index=date 的资产 A 目标权重（取值 [0,1]，如小盘权重）。
        returns_a: index=date 的资产 A 日收益（收盘价到收盘价，decimal）。
        returns_b: index=date 的资产 B 日收益（与 returns_a 同索引口径，
            缺日按 0 收益处理）。
        cost_bps: 单边交易成本（bp）。轮动调仓的双边换手 = |Δw_A| + |Δw_B|
            = 2|Δw_A|，双边各按单边费率计一次：成本 = 双边换手 × cost_bps/1e4，
            于**成交日**从当日（旧仓位承担的）毛收益中扣除。
        lag: 信号至成交的交易日数（默认 1）：T 日收盘形成的目标权重于 T+lag
            收盘成交（成交后权重 executed_weight = weight.ffill().shift(lag)，
            收益承担仓位 position = executed_weight.shift(1)），成交前的
            收益段均由旧仓位承担，防未来函数。
        drift_within_period: 是否月内权重漂移（默认 False）：False 为现有
            「目标权重持有至下次更新」语义（逐位不变）；True 为「成交日重置
            为目标权重、其余日期按两腿收益漂移」语义（见上「月内漂移模式」）。

    Returns:
        与收益同索引的 DataFrame，列：
        ``position``（收益承担仓位=实际承担当日收益段的资产 A 权重，未建仓期 NaN）、
        ``strategy_ret``（扣费后策略日收益，未建仓期 0；成本于成交日扣除，
        建仓日旧仓位为空仓、毛收益 0，成本照常扣除）、
        ``nav``（策略累计净值，期初财富 1.0）、
        ``turnover_double``（双边换手 |Δw_A|+|Δw_B|，按成交后权重
        executed_weight 的 diff 在**成交日**记账——信号日 T 的权重变化于
        T+lag 收盘成交，换手即记在 T+lag；建仓日（首个成交日）记 1.0——
        空仓满仓建立时买入 w 的 A 与 (1-w) 的 B，名义合计恰为 100%；
        终点规则：样本最后一个索引收盘成交的调仓同样计入换手与成本，
        即使其后已无收益行。``drift_within_period=True`` 时换手口径为
        成交日重置幅度 |w_目标 - w_成交前漂移| 的双边值，建仓日仍记 1.0）。
    """
    ra = pd.Series(returns_a).astype(float).sort_index()
    rb = pd.Series(returns_b).astype(float).reindex(ra.index).fillna(0.0)
    idx = ra.index

    if drift_within_period:
        # 月内漂移分支（iter_04 SO-02）：仓位在成交日（观察日+lag）收盘重置
        # 为目标权重，其余日期按两腿收益递推漂移；换手在成交日按重置幅度
        # 记账（漂移量计入下次调仓）；成本与 T+lag 成交时点、收益承担语义
        # （position = executed_weight.shift(1)）与默认分支一致。
        w_obs = pd.Series(weight).astype(float).sort_index().reindex(idx)
        exec_target = w_obs.shift(lag)  # 仅成交日有值（该日重置的目标权重）
        trade_days = exec_target.notna()  # 成交日集合（每个观察日+lag，无论目标权重是否变化）
        # 段 = [成交日, 下一成交日)：段首日收盘重置为目标权重（段内漂移系数
        # g_a=g_b=1，段首日天然取 w0），段内其余日按两腿段内累计净值漂移
        # （与 m1 基准「段内漂移、段末日重置」同一构造技巧的向量化实现）。
        seg = trade_days.cumsum()
        cum_a = (1.0 + ra.fillna(0.0)).groupby(seg).cumprod()
        cum_b = (1.0 + rb).groupby(seg).cumprod()
        g_a = cum_a / cum_a.groupby(seg).transform("first")
        g_b = cum_b / cum_b.groupby(seg).transform("first")
        w0 = exec_target.ffill()  # 段内目标权重（首个成交日前 NaN=未建仓）
        executed_weight = (w0 * g_a) / (w0 * g_a + (1.0 - w0) * g_b)
        position = executed_weight.shift(1)
        # 换手在成交日按重置幅度记账：2|w0 - w_pre|，w_pre 为「若不重置」
        # 自上一日收盘持仓经当日收益段漂移的成交前权重（漂移量由此计入
        # 本次调仓）；非成交日 0；建仓日（首个成交日，w_pre 无前值）记 1.0。
        prev_w = executed_weight.shift(1)
        w_pre = (prev_w * (1.0 + ra.fillna(0.0))) / (
            prev_w * (1.0 + ra.fillna(0.0)) + (1.0 - prev_w) * (1.0 + rb)
        )
        turnover_double = pd.Series(0.0, index=idx)
        turnover_double.loc[trade_days] = (
            2.0 * (exec_target[trade_days] - w_pre[trade_days]).abs()
        ).fillna(0.0)
        first_executed = executed_weight.first_valid_index()
        if first_executed is not None:
            turnover_double.loc[first_executed] = 1.0
    else:
        # 目标权重对齐日频并前向填充（持有至下次更新）。
        w_daily = pd.Series(weight).astype(float).sort_index().reindex(idx).ffill()
        # T+lag 收盘成交（CDX-C-01 修复，AS2 口径）：分离「成交后权重」与
        # 「收益承担仓位」（CDX-C-R1-01 修复）——
        # executed_weight = w_daily.shift(lag)：T 日信号在 T+lag 收盘成交后即
        #   成为持仓权重（成交当日的收益段仍由旧仓位承担），用于换手/成本的
        #   成交日记账；前 lag 日及首个信号日前为 NaN（未建仓）。
        # position = executed_weight.shift(1)：收益承担仓位，新仓位自
        #   T+lag→T+lag+1 收益段起生效，与旧实现 w_daily.shift(lag + 1) 逐位
        #   等价，收益语义不变。旧实现 shift(lag) 直接承担收益实为「T+lag-1
        #   收盘成交」，T 日信号的新仓位提前赚取了 T→T+lag 段收益，与 AS2
        #   「T+1 收盘成交」矛盾。
        executed_weight = w_daily.shift(lag)
        position = executed_weight.shift(1)
        # 双边换手在成交日按 executed_weight.diff() 记账（CDX-C-R1-01）：调仓日
        # 2|Δw_exec|（|Δw_A|+|Δw_B| 且 Δw_B = -Δw_A）；建仓日（首个成交日）记
        # 1.0；样本最后一个索引收盘成交的调仓同样计入（旧实现按 position.diff()
        # 记账，换手延后一行且漏记末期成交）。
        turnover_double = (2.0 * executed_weight.diff().abs()).fillna(0.0)
        first_executed = executed_weight.first_valid_index()
        if first_executed is not None:
            turnover_double.loc[first_executed] = 1.0

    active = position.notna()
    pos = position.fillna(0.0)
    gross_ret = pos * ra.fillna(0.0) + (1.0 - pos) * rb

    # 成本于成交日从当日（旧仓位承担的）毛收益中扣除；cost_bps=0 时无数值
    # 影响。建仓日旧仓位为空仓（毛收益 0），成本照常扣除。
    cost = turnover_double * (cost_bps / 1e4)
    strategy_ret = gross_ret.where(active, 0.0) - cost
    nav = (1.0 + strategy_ret).cumprod()

    return pd.DataFrame(
        {
            "position": position,
            "strategy_ret": strategy_ret,
            "nav": nav,
            "turnover_double": turnover_double,
        },
        index=idx,
    )
